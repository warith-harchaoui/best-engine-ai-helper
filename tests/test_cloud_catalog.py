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
    assert cloud_catalog.blended_price_per_1m({}) == 0.0
