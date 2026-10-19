"""
Tests for best_engine_ai_helper.throughput.

Covers the metering wrapper (transparency, accumulation across calls, which
clock is used), the refusals that keep a made-up number out of the store (no
token counts, too few tokens, failed calls), and the per-machine store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from best_engine_ai_helper import llm, throughput


@pytest.fixture(autouse=True)
def _no_leftover_observers():
    """Metering registers an observer; make sure a test never leaves one behind."""
    llm.clear_observers()
    yield
    llm.clear_observers()


def _chat_emitting(events: list[dict[str, Any]], reply: str = "ok"):
    """Build a fake chat callable that emits `events` through the observer seam."""

    def _chat(_prompt: str, **_kwargs: Any) -> str:
        for event in events:
            llm._emit(event)
        return reply

    return _chat


def _ok(out_tokens: int, gen_ms: float | None) -> dict[str, Any]:
    return {"ok": True, "out_tokens": out_tokens, "gen_ms": gen_ms}


# ---------------------------------------------------------------------------
# Transparency: metering must not change what the gates see
# ---------------------------------------------------------------------------


def test_the_wrapper_forwards_arguments_and_return_value() -> None:
    seen: dict[str, Any] = {}

    def _chat(prompt: str, **kwargs: Any) -> str:
        seen["prompt"] = prompt
        seen["kwargs"] = kwargs
        return "the answer"

    wrapped = throughput.Meter().wrap(_chat)
    assert wrapped("hello", system="be terse") == "the answer"
    assert seen["prompt"] == "hello"
    assert seen["kwargs"] == {"system": "be terse"}


def test_an_exception_still_propagates() -> None:
    """A gate that would have failed must still fail the same way when metered."""

    def _chat(_prompt: str, **_kwargs: Any) -> str:
        raise RuntimeError("model is gone")

    meter = throughput.Meter()
    with pytest.raises(RuntimeError, match="model is gone"):
        meter.wrap(_chat)("hi")
    assert meter.measurement() is None


def test_metering_leaves_other_observers_registered() -> None:
    """clear_observers would drop the user's ledger; removal must be surgical."""
    theirs: list[dict[str, Any]] = []
    llm.add_observer(theirs.append)

    throughput.Meter().wrap(_chat_emitting([_ok(100, 500.0)]))("hi")

    assert len(theirs) == 1  # their subscription saw the call...
    assert len(llm._OBSERVERS) == 1  # ...and survived the meter


# ---------------------------------------------------------------------------
# Which clock, and what it is worth
# ---------------------------------------------------------------------------


def test_the_daemon_decode_clock_is_preferred_and_labelled() -> None:
    """100 tokens in 500 ms of decode time is 200 tok/s, and it is trustworthy."""
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([_ok(100, 500.0)]))("hi")

    m = meter.measurement()
    assert m is not None
    assert m["tokens_per_second"] == 200.0
    assert m["basis"] == "eval_duration"
    assert m["tokens"] == 100
    assert m["calls"] == 1


def test_a_backend_without_a_decode_clock_falls_back_and_says_so() -> None:
    """No gen_ms means the wall clock, which is a hint rather than a verdict."""
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([_ok(100, None)]))("hi")

    m = meter.measurement()
    assert m is not None
    assert m["basis"] == "wall_clock"
    assert m["tokens_per_second"] > 0


def test_samples_accumulate_across_the_whole_gate_run() -> None:
    """Six gate calls give one measurement over all six, not six noisy ones."""
    meter = throughput.Meter()
    wrapped = meter.wrap(_chat_emitting([_ok(60, 300.0)]))
    for _ in range(3):
        wrapped("hi")

    m = meter.measurement()
    assert m is not None
    assert m["tokens"] == 180
    assert m["calls"] == 3
    assert m["tokens_per_second"] == 200.0  # 180 tokens / 0.9 s


# ---------------------------------------------------------------------------
# Refusals: better no number than an invented one
# ---------------------------------------------------------------------------


def test_a_backend_that_reports_no_tokens_yields_no_measurement() -> None:
    """Counting characters instead would invent a tokeniser."""
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([{"ok": True, "out_tokens": None, "gen_ms": 500.0}]))("hi")
    assert meter.measurement() is None


def test_a_failed_call_is_not_a_sample() -> None:
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([{"ok": False, "out_tokens": None, "gen_ms": None}]))("hi")
    assert meter.calls == 0
    assert meter.measurement() is None


def test_too_few_tokens_is_noise_not_a_measurement() -> None:
    """A handful of tokens is dominated by first-token latency."""
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([_ok(throughput.MIN_TOKENS_FOR_CONFIDENCE - 1, 10.0)]))("hi")
    assert meter.measurement() is None


def test_exactly_the_confidence_floor_is_enough() -> None:
    meter = throughput.Meter()
    meter.wrap(_chat_emitting([_ok(throughput.MIN_TOKENS_FOR_CONFIDENCE, 100.0)]))("hi")
    assert meter.measurement() is not None


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


def test_record_and_read_back_round_trip(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    m = {
        "tokens_per_second": 42.5,
        "basis": "eval_duration",
        "tokens": 200,
        "calls": 2,
        "measured_at": "2026-10-19T12:00:00+00:00",
        "measured_on": "Apple M2 Max",
    }
    throughput.record("qwen3:8b", m, store_path=store)

    assert throughput.measured_tps("qwen3:8b", machine="Apple M2 Max", store_path=store) == 42.5


def test_the_same_pair_is_one_row_and_a_faster_sample_wins(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "tokens": 200, "calls": 1, "measured_on": "Apple M2 Max"}
    throughput.record("qwen3:8b", {**base, "tokens_per_second": 10.0}, store_path=store)
    throughput.record("qwen3:8b", {**base, "tokens_per_second": 20.0}, store_path=store)

    rows = throughput.load_measurements(store)
    assert len(rows) == 1
    assert throughput.measured_tps("qwen3:8b", machine="Apple M2 Max", store_path=store) == 20.0
    assert rows["qwen3:8b@Apple M2 Max"]["samples"] == 2


def test_a_slower_later_sample_does_not_win(tmp_path: Path) -> None:
    """Measured for real: 15.2 tok/s idle vs 8.7 with three test suites running.

    Contention can only push an observation below the hardware's capability, so
    the slow one is the wrong input for calibrating a bandwidth ceiling.
    """
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "measured_on": "Apple M2 Max"}
    throughput.record("gemma3:12b", {**base, "tokens_per_second": 15.2}, store_path=store)
    throughput.record("gemma3:12b", {**base, "tokens_per_second": 8.7}, store_path=store)

    row = throughput.load_measurements(store)["gemma3:12b@Apple M2 Max"]
    assert row["tokens_per_second"] == 15.2  # the busy-machine sample is not trusted
    assert row["samples"] == 2  # but the evidence count still grows


def test_replace_overrules_the_best_of_rule(tmp_path: Path) -> None:
    """For when the hardware really did get slower, not just busier."""
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "measured_on": "Apple M2 Max"}
    throughput.record("gemma3:12b", {**base, "tokens_per_second": 15.2}, store_path=store)
    throughput.record(
        "gemma3:12b", {**base, "tokens_per_second": 8.7}, store_path=store, replace=True
    )

    row = throughput.load_measurements(store)["gemma3:12b@Apple M2 Max"]
    assert row["tokens_per_second"] == 8.7


def test_a_busy_sample_cannot_poison_the_calibration(tmp_path: Path) -> None:
    """The bug this rule fixes: 0.307 instead of 0.537, from one contended run."""
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "measured_on": "Apple M2 Max"}
    throughput.record(
        "gemma3:12b", {**base, "tokens_per_second": 15.2}, store_path=store, estimated_tps=28.3
    )
    throughput.record(
        "gemma3:12b", {**base, "tokens_per_second": 8.7}, store_path=store, estimated_tps=28.3
    )

    result = throughput.calibration_factor(machine="Apple M2 Max", store_path=store)
    assert result is not None
    assert result[0] == 0.537  # the idle figure, not the contended 0.307


def test_a_different_machine_is_a_different_row(tmp_path: Path) -> None:
    """Tokens per second belongs to a model AND the hardware under it."""
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "tokens": 200, "calls": 1}
    throughput.record(
        "qwen3:8b", {**base, "tokens_per_second": 90.0, "measured_on": "Apple M2 Max"}, store
    )
    throughput.record(
        "qwen3:8b", {**base, "tokens_per_second": 12.0, "measured_on": "Intel i5-8250U"}, store
    )

    assert len(throughput.load_measurements(store)) == 2
    assert throughput.measured_tps("qwen3:8b", machine="Apple M2 Max", store_path=store) == 90.0
    assert throughput.measured_tps("qwen3:8b", machine="Intel i5-8250U", store_path=store) == 12.0


def test_trusted_only_rejects_a_wall_clock_figure(tmp_path: Path) -> None:
    """Wall time understates decode speed, so it must never disqualify a model."""
    store = tmp_path / "measurements.yaml"
    throughput.record(
        "qwen3:8b",
        {"tokens_per_second": 5.0, "basis": "wall_clock", "measured_on": "Apple M2 Max"},
        store_path=store,
    )

    assert throughput.measured_tps("qwen3:8b", machine="Apple M2 Max", store_path=store) == 5.0
    assert (
        throughput.measured_tps(
            "qwen3:8b", machine="Apple M2 Max", store_path=store, trusted_only=True
        )
        is None
    )


def test_a_missing_store_is_empty_not_an_error(tmp_path: Path) -> None:
    """No measurement yet is the normal state on a fresh machine."""
    assert throughput.load_measurements(tmp_path / "nope.yaml") == {}
    assert throughput.measured_tps("qwen3:8b", store_path=tmp_path / "nope.yaml") is None


def test_a_corrupt_store_warns_rather_than_raising(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    store.write_text("this: [is not: valid: yaml", encoding="utf-8")
    assert throughput.load_measurements(store) == {}


# ---------------------------------------------------------------------------
# The floor as a disqualifier (score.rank), and the line it must not cross
# ---------------------------------------------------------------------------


def _two_candidates() -> list[dict[str, Any]]:
    """A strong-but-slow model and a weaker-but-fast one, both fitting memory."""
    return [
        {"id": "slow:32b", "kind": "llm", "ram_gb": 20.0, "benchmarks": {"general": 90.0}},
        {"id": "fast:8b", "kind": "llm", "ram_gb": 6.0, "benchmarks": {"general": 70.0}},
    ]


_ROOMY = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}


def test_an_estimate_below_the_floor_never_demotes(tmp_path: Path, monkeypatch) -> None:
    """The estimator was measured here to run ~86% optimistic; it may flag, not reject."""
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")

    ranked = score.rank(_ROOMY, _two_candidates(), kind="llm", bandwidth_gbs=100.0, min_tps=1000.0)

    # Every candidate is "estimated" below an absurd floor, yet the order is
    # still by benchmark score -- i.e. unchanged from before measurements existed.
    assert [e["id"] for e in ranked] == ["slow:32b", "fast:8b"]
    assert all(e["_tps_basis"] == "estimated" for e in ranked)
    assert all(e["_comfy"] is False for e in ranked)


def test_a_measurement_below_the_floor_does_demote(tmp_path: Path, monkeypatch) -> None:
    """Too slow to use here is as disqualifying as not fitting in memory."""
    from best_engine_ai_helper import score

    store = tmp_path / "measurements.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    monkeypatch.setattr(throughput, "machine_id", lambda: "Test Box")
    throughput.record(
        "slow:32b",
        {"tokens_per_second": 4.0, "basis": "eval_duration", "measured_on": "Test Box"},
        store_path=store,
    )

    ranked = score.rank(_ROOMY, _two_candidates(), kind="llm", bandwidth_gbs=400.0, min_tps=15.0)

    # The higher-scoring model is measured at 4 tok/s, so it drops below the
    # weaker one it would otherwise outrank.
    assert [e["id"] for e in ranked] == ["fast:8b", "slow:32b"]
    by_id = {e["id"]: e for e in ranked}
    assert by_id["slow:32b"]["_tps"] == 4.0
    assert by_id["slow:32b"]["_tps_basis"] == "measured"
    assert by_id["slow:32b"]["_comfy"] is False


def test_a_measurement_above_the_floor_keeps_its_rank(tmp_path: Path, monkeypatch) -> None:
    from best_engine_ai_helper import score

    store = tmp_path / "measurements.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    monkeypatch.setattr(throughput, "machine_id", lambda: "Test Box")
    throughput.record(
        "slow:32b",
        {"tokens_per_second": 40.0, "basis": "eval_duration", "measured_on": "Test Box"},
        store_path=store,
    )

    ranked = score.rank(_ROOMY, _two_candidates(), kind="llm", bandwidth_gbs=400.0, min_tps=15.0)

    assert [e["id"] for e in ranked] == ["slow:32b", "fast:8b"]
    assert ranked[0]["_comfy"] is True


def test_a_wall_clock_measurement_cannot_demote(tmp_path: Path, monkeypatch) -> None:
    """Wall time understates decode speed, so acting on it would reject unfairly."""
    from best_engine_ai_helper import score

    store = tmp_path / "measurements.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    monkeypatch.setattr(throughput, "machine_id", lambda: "Test Box")
    throughput.record(
        "slow:32b",
        {"tokens_per_second": 2.0, "basis": "wall_clock", "measured_on": "Test Box"},
        store_path=store,
    )

    ranked = score.rank(_ROOMY, _two_candidates(), kind="llm", bandwidth_gbs=400.0, min_tps=15.0)

    assert [e["id"] for e in ranked] == ["slow:32b", "fast:8b"]
    assert ranked[0]["_tps_basis"] == "estimated"  # the untrusted figure is ignored


def test_no_floor_given_disables_the_check_entirely(tmp_path: Path, monkeypatch) -> None:
    from best_engine_ai_helper import score

    store = tmp_path / "measurements.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    monkeypatch.setattr(throughput, "machine_id", lambda: "Test Box")
    throughput.record(
        "slow:32b",
        {"tokens_per_second": 1.0, "basis": "eval_duration", "measured_on": "Test Box"},
        store_path=store,
    )

    ranked = score.rank(_ROOMY, _two_candidates(), kind="llm", bandwidth_gbs=400.0, min_tps=None)

    assert [e["id"] for e in ranked] == ["slow:32b", "fast:8b"]
    assert "_comfy" not in ranked[0]


# ---------------------------------------------------------------------------
# Calibration: what measuring one model teaches about the nineteen others
# ---------------------------------------------------------------------------


def _measured(tps: float, basis: str = "eval_duration", machine: str = "Test Box") -> dict:
    return {"tokens_per_second": tps, "basis": basis, "measured_on": machine}


def test_the_ratio_is_stored_next_to_the_measurement(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    throughput.record("m:8b", _measured(15.2), store_path=store, estimated_tps=28.3)

    row = throughput.load_measurements(store)["m:8b@Test Box"]
    assert row["estimated_tps"] == 28.3
    assert row["calibration_ratio"] == 0.537  # the real M2 Max figure


def test_the_factor_is_the_measured_over_estimated_ratio(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    throughput.record("m:8b", _measured(15.2), store_path=store, estimated_tps=28.3)

    result = throughput.calibration_factor(machine="Test Box", store_path=store)
    assert result is not None
    factor, samples = result
    assert factor == 0.537
    assert samples == 1


def test_the_median_is_used_so_one_odd_model_cannot_drag_the_machine(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    for i, (measured, estimated) in enumerate([(5.0, 10.0), (6.0, 10.0), (50.0, 10.0)]):
        throughput.record(f"m{i}", _measured(measured), store_path=store, estimated_tps=estimated)

    result = throughput.calibration_factor(machine="Test Box", store_path=store)
    assert result is not None
    # Ratios are 0.5, 0.6 and 5.0; the median is 0.6, while the mean would be 2.03.
    assert result[0] == 0.6
    assert result[1] == 3


def test_an_absurd_ratio_is_ignored_rather_than_trusted(tmp_path: Path) -> None:
    """Outside the band, the inputs are likelier wrong than the hardware."""
    store = tmp_path / "measurements.yaml"
    throughput.record("m:8b", _measured(500.0), store_path=store, estimated_tps=10.0)

    assert throughput.calibration_factor(machine="Test Box", store_path=store) is None


def test_a_wall_clock_ratio_does_not_calibrate(tmp_path: Path) -> None:
    """It would bake prompt-processing time into a decode correction."""
    store = tmp_path / "measurements.yaml"
    throughput.record(
        "m:8b", _measured(5.0, basis="wall_clock"), store_path=store, estimated_tps=10.0
    )

    assert throughput.calibration_factor(machine="Test Box", store_path=store) is None


def test_another_machine_does_not_calibrate_this_one(tmp_path: Path) -> None:
    store = tmp_path / "measurements.yaml"
    throughput.record(
        "m:8b", _measured(5.0, machine="Other Box"), store_path=store, estimated_tps=10.0
    )

    assert throughput.calibration_factor(machine="Test Box", store_path=store) is None
    assert throughput.calibration_factor(machine="Other Box", store_path=store) == (0.5, 1)


def test_measuring_one_model_corrects_the_estimate_for_an_unmeasured_one(
    tmp_path: Path, monkeypatch
) -> None:
    """The payoff: the correction transfers to models that were never pulled."""
    from best_engine_ai_helper import score

    store = tmp_path / "measurements.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    monkeypatch.setattr(throughput, "machine_id", lambda: "Test Box")

    never_pulled = {"id": "never:8b", "kind": "llm", "ram_gb": 10.0}
    raw = score.estimated_tokens_per_second(never_pulled, 400.0, calibrated=False)
    assert raw == 26.0  # 400 / 10 * 0.65

    # No measurement yet: calibration is a no-op, so nothing changes.
    assert score.estimated_tokens_per_second(never_pulled, 400.0) == raw

    # Measure a DIFFERENT model and the untouched one's estimate improves.
    throughput.record("other:12b", _measured(15.2), store_path=store, estimated_tps=28.3)
    corrected = score.estimated_tokens_per_second(never_pulled, 400.0)

    assert corrected is not None
    assert corrected == round(raw * 0.537, 1)
    assert corrected < raw  # the estimator was optimistic, so this pulls it down


def test_a_kept_faster_sample_still_picks_up_a_later_estimate(tmp_path: Path) -> None:
    """The faster row wins, but it should not refuse the estimate offered with the loser.

    The ratio has to be derived against the figure actually kept: pairing the
    new measurement with the estimate, when the new measurement was discarded,
    would calibrate against a comparison that never happened.
    """
    store = tmp_path / "measurements.yaml"
    base = {"basis": "eval_duration", "measured_on": "Apple M2 Max"}

    # First record carries no estimate at all.
    throughput.record("gemma3:12b", {**base, "tokens_per_second": 15.2}, store_path=store)
    assert throughput.calibration_factor(machine="Apple M2 Max", store_path=store) is None

    # A slower sample arrives, this time with the estimate attached.
    throughput.record(
        "gemma3:12b", {**base, "tokens_per_second": 8.7}, store_path=store, estimated_tps=28.3
    )

    row = throughput.load_measurements(store)["gemma3:12b@Apple M2 Max"]
    assert row["tokens_per_second"] == 15.2  # the faster figure is still the one kept
    assert row["calibration_ratio"] == 0.537  # 15.2 / 28.3, not 8.7 / 28.3


# ---------------------------------------------------------------------------
# "Already on disk" as a tiebreak, and the line it must not cross
# ---------------------------------------------------------------------------


def _pair(score_a: float, score_b: float) -> list[dict[str, Any]]:
    return [
        {"id": "remote:8b", "kind": "llm", "ram_gb": 6.0, "benchmarks": {"general": score_a}},
        {"id": "ondisk:8b", "kind": "llm", "ram_gb": 6.0, "benchmarks": {"general": score_b}},
    ]


def test_at_comparable_quality_the_pulled_model_wins(tmp_path, monkeypatch) -> None:
    """80.5 vs 80.0 is the same model as far as a leaderboard knows."""
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")

    ranked = score.rank(_ROOMY, _pair(80.5, 80.0), kind="llm", installed={"ondisk:8b"})
    assert [e["id"] for e in ranked] == ["ondisk:8b", "remote:8b"]
    assert ranked[0]["_installed"] is True


def test_a_clearly_better_model_still_beats_one_already_on_disk(tmp_path, monkeypatch) -> None:
    """The tiebreak must never promote a worse model to save a download."""
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")

    ranked = score.rank(_ROOMY, _pair(90.0, 70.0), kind="llm", installed={"ondisk:8b"})
    assert [e["id"] for e in ranked] == ["remote:8b", "ondisk:8b"]


def test_without_an_installed_set_the_order_is_unchanged(tmp_path, monkeypatch) -> None:
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")

    ranked = score.rank(_ROOMY, _pair(80.5, 80.0), kind="llm")
    assert [e["id"] for e in ranked] == ["remote:8b", "ondisk:8b"]
    assert ranked[0]["_installed"] is False


def test_a_different_size_of_the_same_family_is_not_installed(tmp_path, monkeypatch) -> None:
    """`ondisk:8b` is not present just because the daemon holds `ondisk:latest`.

    `pull.installed_tags` already adds the bare form for a `:latest` tag and
    only for that, so matching on the family name would promote a model that
    still needs a full download.
    """
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")

    ranked = score.rank(
        _ROOMY, _pair(80.5, 80.0), kind="llm", installed={"ondisk:latest", "ondisk"}
    )
    assert [e["id"] for e in ranked] == ["remote:8b", "ondisk:8b"]
    assert all(e["_installed"] is False for e in ranked)


def test_a_bare_tag_is_matched_when_the_daemon_reports_it(tmp_path, monkeypatch) -> None:
    """The normalisation that IS sound: a bare id against a `:latest` pull."""
    from best_engine_ai_helper import score

    monkeypatch.setattr(throughput, "_STORE_PATH", tmp_path / "none.yaml")
    catalog = [
        {"id": "remote:8b", "kind": "llm", "ram_gb": 6.0, "benchmarks": {"general": 80.5}},
        {"id": "ondisk", "kind": "llm", "ram_gb": 6.0, "benchmarks": {"general": 80.0}},
    ]

    ranked = score.rank(_ROOMY, catalog, kind="llm", installed={"ondisk:latest", "ondisk"})
    assert [e["id"] for e in ranked] == ["ondisk", "remote:8b"]
