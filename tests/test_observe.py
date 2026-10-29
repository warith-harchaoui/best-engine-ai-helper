"""
Tests for best_engine_ai_helper.observe.

Every ledger is opened on ``:memory:`` or a tmp_path file, never the real
``~/.best-engine-ai-helper/usage.db`` (see conftest.py's autouse
``_isolate_ledger`` fixture, which also resets `observe`'s module-level
singleton between tests).
"""

from __future__ import annotations

from typing import Any

import pytest

from best_engine_ai_helper import llm, observe


def _event(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "backend": "ollama",
        "model": "qwen3:8b",
        "kind": "llm",
        "in_chars": 400,
        "images": 0,
        "out_chars": 400,
        "latency_ms": 12.3,
        "ok": True,
        "error": None,
    }
    base.update(overrides)
    return base


def test_current_user_and_cost_estimation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEST_ENGINE_USER", raising=False)
    os_name = observe.current_user()
    assert os_name  # the OS login name, whatever it is on this machine

    monkeypatch.setenv("BEST_ENGINE_USER", "carol")
    assert observe.current_user() == "carol"
    with observe.as_user("dave"):
        assert observe.current_user() == "dave"  # scope wins over the env var
    assert observe.current_user() == "carol"  # scope released after the block

    # Local backends are always free, regardless of the pricing table.
    assert observe.estimate_cost_usd(_event(backend="ollama")) == 0.0
    assert observe.estimate_cost_usd(_event(backend="vllm")) == 0.0

    # A paid backend with no pricing entry is unknown, never fabricated.
    monkeypatch.setattr(observe, "_load_pricing", lambda: {})
    assert observe.estimate_cost_usd(_event(backend="openai", model="gpt-4o")) is None

    # A priced model computes from the chars-per-token heuristic.
    monkeypatch.setattr(
        observe,
        "_load_pricing",
        lambda: {"gpt-4o": {"input_per_1m": 2.5, "output_per_1m": 10.0}},
    )
    heuristic_cost = observe.estimate_cost_usd(
        _event(backend="openai", model="gpt-4o", in_chars=4_000_000, out_chars=4_000_000)
    )
    # 4_000_000 chars / 4 chars-per-token = 1_000_000 tokens each side.
    assert heuristic_cost == pytest.approx(2.5 + 10.0)

    # in_chars/out_chars would heuristically suggest far more tokens than the
    # provider actually reports; the real in_tokens/out_tokens must win.
    monkeypatch.setattr(
        observe,
        "_load_pricing",
        lambda: {"mistral-small-latest": {"input_per_1m": 0.10, "output_per_1m": 0.30}},
    )
    real_token_event = _event(
        backend="mistral",
        model="mistral-small-latest",
        in_chars=10_000,
        out_chars=10_000,
        in_tokens=33,
        out_tokens=5,
    )
    real_cost = observe.estimate_cost_usd(real_token_event)
    # estimate_cost_usd rounds to 6 decimals; compare with the same rounding
    # rather than pytest.approx's tight default tolerance at this magnitude.
    assert real_cost == round(33 / 1_000_000 * 0.10 + 5 / 1_000_000 * 0.30, 6)


def test_ledger_record_summary_and_enable(tmp_path: Any) -> None:
    ledger = observe.Ledger(":memory:")

    empty_summary = ledger.summary()
    assert empty_summary == {
        "total_calls": 0,
        "total_cost_usd": 0.0,
        "error_rate": 0.0,
        "by_user": [],
        "by_model": [],
        "recent_errors": [],
    }

    with observe.as_user("alice"):
        ledger.record(_event(model="qwen3:8b", ok=True))
        ledger.record(_event(model="qwen3:8b", ok=False, error="boom"))
    with observe.as_user("bob"):
        ledger.record(_event(model="gemma3:12b", ok=True))

    summary = ledger.summary()
    assert summary["total_calls"] == 3
    assert summary["total_cost_usd"] == 0.0  # all local -> free
    assert summary["error_rate"] == pytest.approx(1 / 3, abs=1e-4)
    by_user = {row["user"]: row["calls"] for row in summary["by_user"]}
    assert by_user == {"alice": 2, "bob": 1}
    by_model = {row["model"]: row["calls"] for row in summary["by_model"]}
    assert by_model == {"qwen3:8b": 2, "gemma3:12b": 1}
    assert len(summary["recent_errors"]) == 1
    assert summary["recent_errors"][0]["user"] == "alice"
    assert summary["recent_errors"][0]["error"] == "boom"
    ledger.close()

    ledger1 = observe.enable(str(tmp_path / "usage.db"))
    ledger2 = observe.enable(str(tmp_path / "somewhere-else.db"))
    assert ledger1 is ledger2  # second call is a no-op, returns the same ledger

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "requests.post",
            lambda *a, **k: type(
                "R",
                (),
                {"json": lambda self: {"response": "hi"}, "raise_for_status": lambda self: None},
            )(),
        )
        mp.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
        llm.chat("hello", model="qwen3:8b")

    assert ledger1.summary()["total_calls"] == 1
    assert observe.is_enabled() is True

    observe.disable()
    assert observe.is_enabled() is False
    assert observe.active_ledger() is None


def test_a_refreshed_price_reaches_the_bill(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A model the refresh cache adopted must be priceable, not "cost unknown".

    `catalog update --cloud` writes adopted entries to the pricing cache, and
    the ledger used to read the seed file directly — so it answered "nobody
    priced this" about a price sitting one module away, while `report --cloud`
    ranked the same model on it.
    """
    from best_engine_ai_helper import cloud_catalog

    cache = tmp_path / "pricing_cache.yaml"
    cache.write_text(
        "models:\n"
        "  only-in-the-cache:\n"
        "    provider: openai\n"
        "    kind: llm\n"
        "    benchmarks: {arena: 80.0}\n"
        "    input_per_1m: 1.0\n"
        "    output_per_1m: 2.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cloud_catalog, "_CLOUD_CACHE_PATH", cache)

    cost = observe.estimate_cost_usd(
        _event(backend="openai", model="only-in-the-cache", in_chars=4000, out_chars=4000)
    )
    assert cost is not None, "a cached price must reach the ledger"
    # 1000 in-tokens at $1/M + 1000 out-tokens at $2/M.
    assert cost == pytest.approx(0.003)


def test_counterfactual_prices_the_free_calls_only(tmp_path: Any) -> None:
    """The what-if answers for the local calls; a paid call already has a bill."""
    ledger = observe.Ledger(str(tmp_path / "usage.db"))
    ledger.record(_event(in_chars=4000, out_chars=4000))  # local, free
    ledger.record(_event(backend="openai", model="gpt-4o", in_chars=8000, out_chars=8000))

    what_if = ledger.counterfactual()
    assert what_if["free_calls"] == 1
    assert (what_if["in_tokens"], what_if["out_tokens"]) == (1000, 1000)

    priced = {row["model"]: row["cost_usd"] for row in what_if["models"]}
    # gpt-4o's seed price: $2.50 in / $10.00 out per 1M tokens.
    assert priced["gpt-4o"] == pytest.approx(0.0125)
    costs = [row["cost_usd"] for row in what_if["models"]]
    assert costs == sorted(costs), "cheapest first, so the top row is the answer"
    ledger.close()


def test_counterfactual_says_nothing_rather_than_zero_when_the_ledger_is_empty(
    tmp_path: Any,
) -> None:
    """No free call is not the same as a free workload."""
    ledger = observe.Ledger(str(tmp_path / "usage.db"))
    what_if = ledger.counterfactual()
    assert what_if["free_calls"] == 0
    assert what_if["models"] == [], "pricing an empty workload would print a wall of 0.0"
    ledger.close()


def test_a_failed_free_call_is_not_part_of_the_counterfactual(tmp_path: Any) -> None:
    """A call that errored produced no answer, so a provider would not have been asked for one."""
    ledger = observe.Ledger(str(tmp_path / "usage.db"))
    ledger.record(_event(in_chars=4000, out_chars=0, ok=False, error="boom"))
    assert ledger.counterfactual()["free_calls"] == 0
    ledger.close()
