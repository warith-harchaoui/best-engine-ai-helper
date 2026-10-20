"""
Tests for best_engine_ai_helper.cloud_catalog — the paid-model picker.

Synthetic catalog, no network, no API key. Covers loading (real bundled
pricing.yaml + a missing/explicit path), the kind filter (vlm-only vs
llm-accepts-both), the provider filter, the quality_vs_cost trade-off at its
extremes, the structured-output gate, and pick_cloud's None-on-empty case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from best_engine_ai_helper import cloud_catalog

_CATALOG = [
    {
        "id": "cheap-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": True,
        "benchmarks": {"general": 60, "code": 55},
        "input_per_1m": 0.10,
        "output_per_1m": 0.10,
    },
    {
        "id": "strong-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": True,
        "benchmarks": {"general": 90, "code": 92},
        "input_per_1m": 5.00,
        "output_per_1m": 15.00,
    },
    {
        "id": "vision-model",
        "provider": "other",
        "kind": "vlm",
        "structured_output": True,
        "benchmarks": {"general": 80, "vision": 85},
        "input_per_1m": 2.00,
        "output_per_1m": 6.00,
    },
    {
        "id": "unstructured-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": False,
        "benchmarks": {"general": 99},
        "input_per_1m": 0.01,
        "output_per_1m": 0.01,
    },
]


def test_load_cloud_catalog_real_bundle_and_missing_path(tmp_path: Path) -> None:
    # The real bundled pricing.yaml loads and every entry has the fields
    # rank_cloud/pick_cloud need.
    entries = cloud_catalog.load_cloud_catalog()
    assert entries
    for e in entries:
        assert {"id", "provider", "kind", "benchmarks", "input_per_1m", "output_per_1m"} <= e.keys()

    # An explicit missing path is a real error, not a silent empty result.
    with pytest.raises(FileNotFoundError):
        cloud_catalog.load_cloud_catalog(tmp_path / "nope.yaml")


def test_load_cloud_catalog_default_path_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cloud_catalog, "_PRICING_PATH", tmp_path / "nope.yaml")
    assert cloud_catalog.load_cloud_catalog() == []


def test_rank_and_pick_cloud_kind_provider_and_weight() -> None:
    # kind="vlm" keeps only vlm entries.
    vlm_ranked = cloud_catalog.rank_cloud(_CATALOG, "vlm")
    assert [e["id"] for e in vlm_ranked] == ["vision-model"]

    # kind="llm" accepts both llm and vlm entries (a VLM answers text too) --
    # same rule as score.rank.
    llm_ids = {e["id"] for e in cloud_catalog.rank_cloud(_CATALOG, "llm")}
    assert "vision-model" in llm_ids and "cheap-text" in llm_ids

    # Provider filter narrows the pool.
    acme_only = cloud_catalog.rank_cloud(_CATALOG, "llm", provider="ACME")  # case-insensitive
    assert all(e["provider"] == "acme" for e in acme_only)
    assert "vision-model" not in {e["id"] for e in acme_only}

    # Structured-output capability is checked before the quality/price blend:
    # unstructured-text scores highest (99) and is cheapest, yet never wins.
    top = cloud_catalog.pick_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=1.0)
    assert top is not None and top["id"] == "strong-text"

    # quality_vs_cost=0.0 (pure price) picks the cheapest STRUCTURED candidate.
    cheapest = cloud_catalog.pick_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=0.0)
    assert cheapest is not None and cheapest["id"] == "cheap-text"

    # An out-of-range weight is clamped, not rejected.
    clamped = cloud_catalog.rank_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=5.0)
    assert (
        clamped[0]["id"]
        == cloud_catalog.rank_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=1.0)[0]["id"]
    )

    # No match -> pick_cloud returns None, never an IndexError.
    assert cloud_catalog.pick_cloud(_CATALOG, "vlm", provider="acme") is None


def test_blended_price_per_1m() -> None:
    assert cloud_catalog.blended_price_per_1m({"input_per_1m": 2.0, "output_per_1m": 10.0}) == 6.0
    # An entry with no prices used to blend to 0.0, which the cost axis then
    # inverted into the best possible score -- an unpriced model looked free.
    # It now says it does not know. See the tests below the next banner.
    assert cloud_catalog.blended_price_per_1m({}) is None


# ---------------------------------------------------------------------------
# An unpriced model is not a free model
# ---------------------------------------------------------------------------


def test_no_price_is_not_the_same_as_a_price_of_zero() -> None:
    """Collapsing both to 0.0 is what made an unpriced model look free."""
    assert cloud_catalog.blended_price_per_1m({"id": "nobody-priced-this"}) is None
    assert cloud_catalog.blended_price_per_1m({"input_per_1m": 0.0, "output_per_1m": 0.0}) == 0.0


def test_billing_on_one_side_only_is_a_real_arrangement() -> None:
    """A provider that charges for output and not input is priced, not unpriced."""
    assert cloud_catalog.blended_price_per_1m({"output_per_1m": 10.0}) == 5.0


def test_an_unpriced_model_never_wins_the_cost_axis() -> None:
    """The defect: inverted normalisation turned an absent price into the best score."""
    catalog = [
        {
            "id": "priced-cheap",
            "kind": "llm",
            "benchmarks": {"general": 70.0},
            "input_per_1m": 1.0,
            "output_per_1m": 1.0,
        },
        {
            "id": "priced-dear",
            "kind": "llm",
            "benchmarks": {"general": 70.0},
            "input_per_1m": 50.0,
            "output_per_1m": 50.0,
        },
        {"id": "unpriced", "kind": "llm", "benchmarks": {"general": 70.0}},
    ]

    # Rank on cost alone so the price axis is the only thing deciding.
    ranked = cloud_catalog.rank_cloud(catalog, "llm", quality_vs_cost=0.0)
    order = [r["id"] for r in ranked]

    assert order[0] == "priced-cheap"
    assert order[-1] == "unpriced"  # unknown cost is pessimistic, not optimistic


def test_an_unpriced_entry_carries_none_through_to_the_caller() -> None:
    catalog = [{"id": "unpriced", "kind": "llm", "benchmarks": {"general": 70.0}}]

    ranked = cloud_catalog.rank_cloud(catalog, "llm")

    assert ranked[0]["price_per_1m"] is None


def test_a_catalog_with_no_prices_at_all_still_ranks() -> None:
    """Every price unknown must not divide by an empty range."""
    catalog = [
        {"id": "a", "kind": "llm", "benchmarks": {"general": 90.0}},
        {"id": "b", "kind": "llm", "benchmarks": {"general": 50.0}},
    ]

    ranked = cloud_catalog.rank_cloud(catalog, "llm")

    assert [r["id"] for r in ranked] == ["a", "b"]  # falls back to quality order


# ---------------------------------------------------------------------------
# Which providers are usable, and why the rest are not
# ---------------------------------------------------------------------------


def test_provider_status_names_the_variable_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A silently shorter list of options is not actionable; a variable name is."""
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: "")

    rows = cloud_catalog.provider_status(_CATALOG)

    by_name = {r["provider"]: r for r in rows}
    assert set(by_name) == {"acme", "other"}
    assert by_name["acme"]["available"] is False
    assert "ACME_API_KEY" in by_name["acme"]["reason"]
    assert by_name["acme"]["key_env"] == "ACME_API_KEY"


def test_a_provider_with_a_key_is_available_and_gives_no_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: "sk-whatever")

    rows = cloud_catalog.provider_status(_CATALOG)

    assert all(r["available"] for r in rows)
    assert all(r["reason"] == "" for r in rows)


def test_provider_status_never_returns_a_key_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of storing the variable NAME is that the secret stays out."""
    secret = "sk-this-must-never-appear"
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: secret)

    rows = cloud_catalog.provider_status(_CATALOG)

    assert secret not in repr(rows)


def test_a_lookup_that_raises_is_a_finding_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_entry):
        raise RuntimeError("keyring is locked")

    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", _boom)

    rows = cloud_catalog.provider_status(_CATALOG)

    assert all(r["available"] is False for r in rows)
    assert "keyring is locked" in rows[0]["reason"]


def test_providers_carry_the_models_they_serve() -> None:
    rows = cloud_catalog.provider_status(_CATALOG)

    by_name = {r["provider"]: r for r in rows}
    assert by_name["other"]["models"] == ["vision-model"]
    assert "cheap-text" in by_name["acme"]["models"]


# ---------------------------------------------------------------------------
# What ships must be documented where the reader is told to look
# ---------------------------------------------------------------------------
#
# The bundled catalog carries four providers; `settings.yaml.example` — the
# file README tells you to copy — listed one. The mechanism was never broken
# (any `api_key_env` name resolves, and `provider_status` names it at runtime),
# but someone holding an OpenAI key had to read an internal map in `engine.py`
# to learn what to call it. These two tests make the example file's
# completeness an invariant rather than something to remember when a provider
# is added to `pricing.yaml`.


def _documented_keys() -> set[str]:
    example = Path(__file__).resolve().parent.parent / "settings.yaml.example"
    return {
        line.split(":", 1)[0].strip()
        for line in example.read_text().splitlines()
        if ":" in line and not line.strip().startswith("#")
    }


def test_every_shipped_provider_resolves_a_key_variable_name() -> None:
    """A provider with no name to look up could never be authenticated."""
    from best_engine_ai_helper import engine

    providers = {entry["provider"] for entry in cloud_catalog.load_cloud_catalog()}
    assert providers, "the bundled catalog is empty; the test is broken, not the code"
    unnamed = sorted(p for p in providers if not engine._DEFAULT_API_KEY_ENV.get(p))
    assert not unnamed, f"shipped providers with no api_key_env default: {unnamed}"


def test_every_shipped_provider_is_documented_in_the_settings_example() -> None:
    from best_engine_ai_helper import engine

    providers = {entry["provider"] for entry in cloud_catalog.load_cloud_catalog()}
    needed = {engine._DEFAULT_API_KEY_ENV[p] for p in providers}
    documented = _documented_keys()
    assert needed <= documented, (
        "settings.yaml.example is the file the README tells the reader to copy; "
        f"these shipped providers have no entry there: {sorted(needed - documented)}"
    )
