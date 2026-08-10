"""
Tests for best_engine_ai_helper.score.

Synthetic catalogs only, so the tests never depend on disk files or network.
Each test pins one decision the ranker makes — budget arithmetic, memory-fit
selection, structured-output priority, throughput — with the numbers worked out
in the comments so a regression is easy to read.
"""

from __future__ import annotations

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


def test_effective_budget_priority_and_headroom() -> None:
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


def test_effective_budget_is_load_aware() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}  # load-blind budget: 36.0 GB

    # `load=None` (the default) reproduces the load-blind figure exactly.
    assert score.effective_budget(hw) == pytest.approx(36.0)

    # Live free RAM below the theoretical budget caps it.
    assert score.effective_budget(hw, load={"available_ram_gb": 10.0}) == pytest.approx(10.0)
    # Live free RAM above the theoretical budget changes nothing.
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


def test_rank_and_select_forward_load_to_effective_budget() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    catalog = [SMALL_LLM, MID_LLM, LARGE_LLM]

    # A tight live-RAM cap should disqualify the otherwise-comfortable mid model.
    tight = {"available_ram_gb": 3.0}
    ranked = score.rank(hw, catalog, kind="llm", load=tight)
    assert {r["id"]: r["_fits"] for r in ranked} == {
        "small-llm": True,
        "mid-llm": False,
        "large-llm": False,
    }
    assert score.select(hw, catalog, kind="llm", load=tight)["id"] == "small-llm"


def test_select_picks_best_that_fits_and_falls_back() -> None:
    small = {"unified_gb": 24.0, "vram_gb": None, "ram_gb": 24.0}  # budget 7.92 GB
    large = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}  # budget 36.0 GB
    tiny = {"unified_gb": None, "vram_gb": 2.0, "ram_gb": 8.0}  # budget 0.92 GB

    # VLM: under the 0.5-clamped budget only small-vlm fits the 7.92 GB machine
    # (mid-vlm is 9 GB); mid-vlm fits the 36 GB machine and beats small-vlm on
    # vision; when nothing fits, the smallest is the last resort. large-vlm (52)
    # no longer fits any of these once headroom is capped at 0.5.
    assert score.select(small, ALL_MODELS, kind="vlm")["id"] == "small-vlm"
    assert score.select(large, ALL_MODELS, kind="vlm")["id"] == "mid-vlm"
    assert score.select(tiny, ALL_MODELS, kind="vlm")["id"] == "small-vlm"

    # LLM: a VLM is a valid LLM candidate. On the tight 7.92 GB budget small-vlm
    # (general 65) edges small-llm (62); on the 36 GB machine mid-llm (78) is the
    # top fitting general score (the large models no longer fit).
    assert score.select(small, ALL_MODELS, kind="llm")["id"] == "small-vlm"
    assert score.select(large, ALL_MODELS, kind="llm")["id"] == "mid-llm"


def test_select_raises_on_empty_catalog() -> None:
    with pytest.raises(ValueError, match="empty"):
        score.select({"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}, [], kind="llm")


def test_rank_orders_by_score_and_marks_fit() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    ranked = score.rank(hw, ALL_MODELS, kind="vlm")
    # Descending by the vision axis, and the first entry is what select() returns.
    scores = [r["benchmarks"]["vision"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    # rank() sorts by score regardless of fit, so its top is the highest scorer
    # (large-vlm) even though it no longer fits the 36 GB budget. select() returns
    # the best-scoring model that DOES fit — the first fitting entry in the rank.
    assert ranked[0]["id"] == "large-vlm"
    first_fitting = next(r for r in ranked if r["_fits"])
    assert first_fitting["id"] == score.select(hw, ALL_MODELS, kind="vlm")["id"]
    # Two of three VLMs fit in 96 GB (budget 36 GB under the 0.5 cap; large-vlm
    # is 52 GB and no longer fits).
    assert [r["_fits"] for r in ranked].count(True) == 2


def test_select_agrees_with_rank_on_structured_output() -> None:
    # select() must apply the same structured-output priority as rank(), so the
    # library's select() and the CLI's rank()[0] recommend the same model: a
    # capable model is chosen over a higher-scoring incapable one.
    capable = dict(_vlm("capable-vlm", 9.0, vision=78.0, general=77.0), structured_output=True)
    incapable = dict(_vlm("incapable-vlm", 9.0, vision=91.0, general=88.0), structured_output=False)
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    chosen = score.select(hw, [incapable, capable], kind="vlm", application="vision")
    assert chosen["id"] == "capable-vlm"
    assert (
        chosen["id"]
        == score.rank(hw, [incapable, capable], kind="vlm", application="vision")[0]["id"]
    )


def test_rank_prefers_structured_capable_over_higher_score() -> None:
    # A structured-incapable VLM with a HIGHER vision score must rank below a
    # capable one: the helper runs everything through a JSON schema, so raw
    # score can't rescue a model that returns empty on it. Both still appear.
    capable = dict(_vlm("capable-vlm", 9.0, vision=78.0, general=77.0), structured_output=True)
    incapable = dict(_vlm("incapable-vlm", 9.0, vision=91.0, general=88.0), structured_output=False)
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    ranked = score.rank(hw, [incapable, capable], kind="vlm", application="vision")
    assert [r["id"] for r in ranked] == ["capable-vlm", "incapable-vlm"]


def test_estimated_tokens_per_second() -> None:
    # tok/s = bandwidth / ram * 0.65 efficiency; smaller model -> faster.
    fast = score.estimated_tokens_per_second({"ram_gb": 8.0}, 400.0)
    slow = score.estimated_tokens_per_second({"ram_gb": 52.0}, 400.0)
    assert fast is not None and slow is not None and fast > slow
    assert score.estimated_tokens_per_second({"ram_gb": 10.0}, 400.0) == pytest.approx(26.0)
    # No bandwidth or zero size -> not estimable.
    assert score.estimated_tokens_per_second({"ram_gb": 8.0}, None) is None
    assert score.estimated_tokens_per_second({"ram_gb": 0}, 400.0) is None
