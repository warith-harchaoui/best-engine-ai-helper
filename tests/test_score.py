"""
Tests for best_engine_ai_helper.score.

Synthetic catalogs only, so the tests never depend on disk files or network.
Each functional test below walks through several related decisions the
ranker makes — budget arithmetic, memory-fit selection, structured-output
priority, throughput — with the numbers worked out in the comments so a
regression is easy to read.
"""

from __future__ import annotations

import logging

import pytest

from best_engine_ai_helper import score


def _vlm(id_: str, ram_gb: float, vision: float, general: float) -> dict:
    return {
        "id": id_,
        "kind": "vlm",
        "ram_gb": ram_gb,
        "benchmarks": {"general": general, "vision": vision},
    }


def _llm(id_: str, ram_gb: float, general: float) -> dict:
    return {
        "id": id_,
        "kind": "llm",
        "ram_gb": ram_gb,
        "benchmarks": {"general": general, "vision": None},
    }


SMALL_VLM = _vlm("small-vlm", 3.5, vision=70.0, general=65.0)
MID_VLM = _vlm("mid-vlm", 9.0, vision=80.0, general=75.0)
LARGE_VLM = _vlm("large-vlm", 52.0, vision=91.0, general=88.0)
SMALL_LLM = _llm("small-llm", 2.2, general=62.0)
MID_LLM = _llm("mid-llm", 10.5, general=78.0)
LARGE_LLM = _llm("large-llm", 48.0, general=87.0)
ALL_MODELS = [SMALL_LLM, SMALL_VLM, MID_LLM, MID_VLM, LARGE_LLM, LARGE_VLM]


def test_effective_budget() -> None:
    # Unified pool wins over VRAM; >36 GB triggers the 0.75 Metal cap, then the
    # default 0.5 headroom: 96 * 0.75 * 0.5.
    assert score.effective_budget(
        {"unified_gb": 96.0, "vram_gb": 24.0, "ram_gb": 96.0}
    ) == pytest.approx(36.0)
    # No unified -> VRAM budget (0.92 usable * 0.5).
    assert score.effective_budget(
        {"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0}
    ) == pytest.approx(11.04)
    # No accelerator -> half of system RAM * 0.5 headroom.
    assert score.effective_budget(
        {"unified_gb": None, "vram_gb": None, "ram_gb": 32.0}
    ) == pytest.approx(8.0)
    # Headroom is CLAMPED to MAX_HEADROOM (0.5): a caller asking for 0.90 still
    # gets 64 * 0.75 * 0.5, never * 0.90 — the anti-greed ceiling.
    assert score.MAX_HEADROOM == 0.5
    assert score.effective_budget(
        {"unified_gb": 64.0, "vram_gb": None, "ram_gb": 64.0}, headroom=0.90
    ) == pytest.approx(24.0)

    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}  # load-blind budget: 36.0 GB
    # `load=None` (the default) reproduces the load-blind figure exactly.
    assert score.effective_budget(hw) == pytest.approx(36.0)
    # Live free RAM below the theoretical budget caps it; above it, no change.
    assert score.effective_budget(hw, load={"available_ram_gb": 10.0}) == pytest.approx(10.0)
    assert score.effective_budget(hw, load={"available_ram_gb": 80.0}) == pytest.approx(36.0)
    # A saturated CPU derates further, on top of (not instead of) the memory cap.
    busy = score.effective_budget(hw, load={"cpu_percent": 90.0})
    assert busy == pytest.approx(36.0 * score._CPU_BUSY_DERATE)
    # A nearly-full disk derates further too; both penalties compound.
    busy_and_low_disk = score.effective_budget(hw, load={"cpu_percent": 90.0, "disk_free_gb": 2.0})
    assert busy_and_low_disk == pytest.approx(
        36.0 * score._CPU_BUSY_DERATE * score._DISK_LOW_DERATE
    )
    # Below the busy/low-disk thresholds, no extra derating applies.
    idle = score.effective_budget(hw, load={"cpu_percent": 10.0, "disk_free_gb": 500.0})
    assert idle == pytest.approx(36.0)


def test_select_and_rank() -> None:
    hw96 = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    catalog = [SMALL_LLM, MID_LLM, LARGE_LLM]

    # A tight live-RAM cap should disqualify the otherwise-comfortable mid model.
    tight = {"available_ram_gb": 3.0}
    ranked = score.rank(hw96, catalog, kind="llm", load=tight)
    assert {r["id"]: r["_fits"] for r in ranked} == {
        "small-llm": True,
        "mid-llm": False,
        "large-llm": False,
    }
    assert score.select(hw96, catalog, kind="llm", load=tight)["id"] == "small-llm"

    small = {"unified_gb": 24.0, "vram_gb": None, "ram_gb": 24.0}  # budget 7.92 GB
    tiny = {"unified_gb": None, "vram_gb": 2.0, "ram_gb": 8.0}  # budget 0.92 GB

    # VLM: under the 0.5-clamped budget only small-vlm fits the 7.92 GB machine
    # (mid-vlm is 9 GB); mid-vlm fits the 36 GB machine and beats small-vlm on
    # vision; when nothing fits, the smallest is the last resort. large-vlm (52)
    # no longer fits any of these once headroom is capped at 0.5.
    assert score.select(small, ALL_MODELS, kind="vlm")["id"] == "small-vlm"
    assert score.select(hw96, ALL_MODELS, kind="vlm")["id"] == "mid-vlm"
    assert score.select(tiny, ALL_MODELS, kind="vlm")["id"] == "small-vlm"

    # LLM: a VLM is a valid LLM candidate. On the tight 7.92 GB budget small-vlm
    # (general 65) edges small-llm (62); on the 36 GB machine mid-llm (78) is the
    # top fitting general score (the large models no longer fit).
    assert score.select(small, ALL_MODELS, kind="llm")["id"] == "small-vlm"
    assert score.select(hw96, ALL_MODELS, kind="llm")["id"] == "mid-llm"

    with pytest.raises(ValueError, match="empty"):
        score.select(hw96, [], kind="llm")

    all_ranked = score.rank(hw96, ALL_MODELS, kind="vlm")
    # Descending by the vision axis, and the first entry is what select() returns.
    scores = [r["benchmarks"]["vision"] for r in all_ranked]
    assert scores == sorted(scores, reverse=True)
    # rank() sorts by score regardless of fit, so its top is the highest scorer
    # (large-vlm) even though it no longer fits the 36 GB budget. select() returns
    # the best-scoring model that DOES fit — the first fitting entry in the rank.
    assert all_ranked[0]["id"] == "large-vlm"
    first_fitting = next(r for r in all_ranked if r["_fits"])
    assert first_fitting["id"] == score.select(hw96, ALL_MODELS, kind="vlm")["id"]
    # Two of three VLMs fit in 96 GB (budget 36 GB under the 0.5 cap; large-vlm
    # is 52 GB and no longer fits).
    assert [r["_fits"] for r in all_ranked].count(True) == 2

    # select() must apply the same structured-output priority as rank(), so the
    # library's select() and the CLI's rank()[0] recommend the same model: a
    # capable model is chosen over a higher-scoring incapable one. A
    # structured-incapable VLM with a HIGHER vision score must still rank
    # below a capable one, since the helper runs everything through a JSON
    # schema — raw score can't rescue a model that returns empty on it. Both
    # still appear in the ranking.
    capable = dict(_vlm("capable-vlm", 9.0, vision=78.0, general=77.0), structured_output=True)
    incapable = dict(_vlm("incapable-vlm", 9.0, vision=91.0, general=88.0), structured_output=False)
    chosen = score.select(hw96, [incapable, capable], kind="vlm", application="vision")
    assert chosen["id"] == "capable-vlm"
    priority_ranked = score.rank(hw96, [incapable, capable], kind="vlm", application="vision")
    assert chosen["id"] == priority_ranked[0]["id"]
    assert [r["id"] for r in priority_ranked] == ["capable-vlm", "incapable-vlm"]

    # tok/s = bandwidth / ram * 0.65 efficiency; smaller model -> faster.
    fast = score.estimated_tokens_per_second({"ram_gb": 8.0}, 400.0)
    slow = score.estimated_tokens_per_second({"ram_gb": 52.0}, 400.0)
    assert fast is not None and slow is not None and fast > slow
    assert score.estimated_tokens_per_second({"ram_gb": 10.0}, 400.0) == pytest.approx(26.0)
    # No bandwidth or zero size -> not estimable.
    assert score.estimated_tokens_per_second({"ram_gb": 8.0}, None) is None
    assert score.estimated_tokens_per_second({"ram_gb": 0}, 400.0) is None


# --- An entry with no size is unknown, not weightless -----------------------
#
# `model_footprint_gb` had no test of any kind, including for the vLLM sizing
# the README advertises as what keeps a vLLM pick realistic. It also returned
# 0.0 for an entry carrying neither `ram_gb` nor `size_b`, which made such an
# entry fit every machine and win every leanness tiebreak. The line was on
# `scripts/measure_absent_vs_zero.py`'s survivor list and the hand review
# cleared it; these tests are what the review should have been.

_SIZELESS = {"id": "ghost", "kind": "llm", "benchmarks": {"general": 70}}
_REAL = {
    "id": "real-8b",
    "kind": "llm",
    "ram_gb": 5.6,
    "size_b": 8.0,
    "benchmarks": {"general": 74},
}


def test_vllm_is_sized_against_fp16_not_the_q4_figure() -> None:
    """The guard the README names: a vLLM pick must be sized heavier."""
    q4 = score.model_footprint_gb(_REAL, "ollama")
    vllm = score.model_footprint_gb(_REAL, "vllm")
    assert q4 == 5.6
    # 8B x 2 bytes/param x 1.15 overhead = 18.4 GB, ~3x the Q4 estimate.
    assert vllm == pytest.approx(18.4)
    assert vllm > q4

    # No parameter count: fall back to the Q4 figure rather than invent one.
    assert score.model_footprint_gb({"ram_gb": 5.0}, "vllm") == 5.0
    # FP16 is always heavier, so the Q4 number is a hard floor.
    assert score.model_footprint_gb({"ram_gb": 40.0, "size_b": 1.0}, "vllm") == 40.0
    # An unknown backend gets the conservative catalog figure.
    assert score.model_footprint_gb(_REAL, "something-else") == 5.6


def test_an_unsizeable_entry_reports_infinity_rather_than_zero() -> None:
    import math

    assert math.isinf(score.model_footprint_gb(_SIZELESS, "ollama"))
    assert math.isinf(score.model_footprint_gb(_SIZELESS, "vllm"))
    assert score.is_sizeable(_SIZELESS) is False
    assert score.is_sizeable(_REAL) is True


def test_unsizeable_entries_are_dropped_from_rank_and_select_and_announced(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dropped, and said out loud — a pool that shrinks silently reads as covered."""
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}

    with caplog.at_level(logging.WARNING, logger="os_helper"):
        ranked = score.rank(hw, [_REAL, _SIZELESS], kind="llm")
    assert [e["id"] for e in ranked] == ["real-8b"]
    assert any("cannot be sized" in r.message for r in caplog.records)
    caplog.clear()

    assert score.select(hw, [_REAL, _SIZELESS], kind="llm")["id"] == "real-8b"

    # Nothing sizeable at all is an error, not a silent empty answer.
    with pytest.raises(ValueError, match="usable size"):
        score.select(hw, [_SIZELESS], kind="llm")


def test_a_sizeless_entry_no_longer_beats_a_real_one_on_a_small_machine() -> None:
    """The end-to-end shape of the defect: it won precisely where it hurt.

    On a machine too small for the real model, the entry with no size at all
    was reported as fitting and was recommended.
    """
    from best_engine_ai_helper import recommend as _recommend

    tiny = {"unified_gb": 4.0, "vram_gb": None, "ram_gb": 4.0}
    block = _recommend.recommend(tiny, [_REAL, _SIZELESS], task="write code")
    rows = block["recommendations"]["llm"]["candidates"]
    assert [r["id"] for r in rows] == ["real-8b"]
    assert block["recommendations"]["llm"]["chosen"]["id"] == "real-8b"


# ---------------------------------------------------------------------------
# The default benchmark axis — one rule, not two
# ---------------------------------------------------------------------------
#
# `catalog update --arena` writes an `arena` rating onto entries whose every
# other axis is null, because the spec sources (ApXML, the Ollama library)
# publish no benchmarks at all. The default lookup could not read that axis, so
# the refresh that had just scored a model ranked it at 0.0 — below every
# hand-scored seed entry — while the same entry, asked for by name as
# `--application generalist`, scored 84. Two rules that disagreed about exactly
# the thing a refresh adds.


def _arena_only(kind: str = "llm") -> dict[str, object]:
    """An entry as a `--arena` refresh leaves it: one rating, nothing else."""
    axis = "arena_vision" if kind == "vlm" else "arena"
    return {
        "id": "refreshed",
        "kind": kind,
        "ram_gb": 8.0,
        "benchmarks": {"general": None, "vision": None, "code": None, axis: 84.0},
    }


def test_default_axis_reads_an_arena_only_entry() -> None:
    """The refresh scores a model; the default path must not rank it at zero."""
    assert score._benchmark_score(_arena_only("llm"), "llm") == 84.0
    assert score._benchmark_score(_arena_only("vlm"), "vlm") == 84.0


def test_default_and_named_application_cannot_disagree() -> None:
    """`application=None` resolves through the same table as every keyword."""
    for entry, kind, named in (
        (_arena_only("llm"), "llm", "generalist"),
        (_arena_only("vlm"), "vlm", "vision"),
    ):
        assert score._benchmark_score(entry, kind) == score._benchmark_score(entry, kind, named)


def test_a_measured_axis_always_beats_the_fallback_behind_it() -> None:
    """The Arena rung is a fallback, never an override of a curated score."""
    entry = {"benchmarks": {"general": 60, "arena": 84.0}}
    assert score._benchmark_score(entry, "llm") == 60.0


def test_an_unknown_application_falls_back_rather_than_scoring_zero() -> None:
    """A typo in a brief must not silently flatten every candidate to 0."""
    entry = {"benchmarks": {"general": 77}}
    assert score._benchmark_score(entry, "llm", "nonsense") == 77.0


def test_absent_is_distinguishable_from_measured_at_zero() -> None:
    """The distinction a min-max normalisation needs and `0.0` cannot carry."""
    assert score.benchmark_score_or_none({"benchmarks": {"general": 0.0}}, "llm") == 0.0
    assert score.benchmark_score_or_none({"benchmarks": {"general": None}}, "llm") is None
    # Scored on a different board than the one asked for is still "not this one".
    assert score.benchmark_score_or_none({"benchmarks": {"arena_code": 96.1}}, "llm") is None


def test_the_axis_a_score_came_from_is_reportable() -> None:
    """Two rows in one table can be measured with two different rulers."""
    assert score.resolve_benchmark({"benchmarks": {"general": 88}}, "llm") == ("general", 88.0)
    assert score.resolve_benchmark({"benchmarks": {"general": None, "arena": 85.2}}, "llm") == (
        "arena",
        85.2,
    )
    assert score.resolve_benchmark({"benchmarks": {}}, "llm") is None


def test_every_priority_list_ends_at_the_broadest_axis_it_can_reach() -> None:
    """A list that stops early turns a censored axis into a zero.

    The leaderboard mirror publishes a top twenty per board, so a model rated
    for code can be missing from text. Every list therefore falls through to
    `arena`, the broadest rung available, before giving up.
    """
    for application, priority in score._APP_BENCH_PRIORITY.items():
        assert priority[-1] in {"arena", "general"}, application
