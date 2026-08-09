"""
Tests for best_engine_ai_helper.catalog.

Covers the bundled seed load and its invariants, the cache-overlay merge (cache
entries overwrite seed entries by id; a missing seed raises), the RAM estimator,
and the `catalog update` normalization path (ApXML spec -> catalog entry).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from best_engine_ai_helper import catalog


def test_load_catalog_seed_invariants() -> None:
    entries = catalog.load_catalog()
    assert len(entries) > 0
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))  # ids are unique
    for e in entries:
        assert {"id", "kind", "ram_gb", "benchmarks"} <= e.keys()
        # embed entries (text embedders for the ann-router index) join llm/vlm as
        # a third kind; the generative picker ignores them, the F3 usage selects
        # among them by memory fit.
        assert e["kind"] in ("llm", "vlm", "embed")
        assert float(e["ram_gb"]) > 0


def test_load_catalog_cache_overlays_seed(tmp_path: Path, monkeypatch) -> None:
    def _entry(general: int, note: str, fetched: str | None) -> str:
        return textwrap.dedent(f"""\
            - id: test-model:1b
              kind: llm
              ram_gb: 1.1
              benchmarks: {{general: {general}, vision: null}}
              notes: "{note}"
              fetched_at: {fetched or "null"}
        """)

    seed = tmp_path / "models.yaml"
    seed.write_text(_entry(50, "seed", None))
    cache = tmp_path / "catalog_cache.yaml"
    cache.write_text(_entry(99, "cache override", "2026-07-28"))
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)

    entries = catalog.load_catalog(catalog_path=seed)
    assert len(entries) == 1  # same id -> overwritten, not duplicated
    assert entries[0]["benchmarks"]["general"] == 99
    assert entries[0]["notes"] == "cache override"


def test_load_catalog_missing_seed_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        catalog.load_catalog(catalog_path=tmp_path / "does_not_exist.yaml")


def test_estimate_ram_applies_quant_overhead() -> None:
    # Known quants use their overhead factor; unknown quants fall back to 1.15.
    for disk, quant, expected in [
        (6.1, "Q4_K_M", 6.832),
        (6.1, "Q8_0", 6.71),
        (10.0, "FP16", 10.5),
        (5.0, "Q2_K", 6.0),
        (10.0, "UNKNOWN", 11.5),
    ]:
        assert catalog.estimate_ram(disk, quant) == pytest.approx(expected, rel=1e-3)


def _apxml_spec() -> dict:
    return {
        "slug": "qwen3-8b",
        "name": "Qwen3 8B",
        "kind": "llm",
        "size_b": 8.0,
        "ram_gb": 6.0,
        "vllm_id": "Qwen/Qwen3-8B",
        "context_length": 32768,
        "license": "apache-2.0",
        "url": "https://apxml.com/models/qwen3-8b",
    }


def test_normalize_apxml_spec_maps_and_filters() -> None:
    entry = catalog.normalize_apxml_spec(_apxml_spec(), "2026-08-01")
    assert entry["id"] == "qwen3-8b" and entry["kind"] == "llm"
    assert entry["quant"] == "Q4_K_M" and entry["source"] == "apxml"
    assert entry["fetched_at"] == "2026-08-01"
    # disk_gb is the Q4 VRAM figure with the quant overhead divided back out.
    assert entry["disk_gb"] == pytest.approx(6.0 / 1.12, rel=1e-3)
    # ApXML carries no numeric benchmarks, so every axis stays null.
    assert all(v is None for v in entry["benchmarks"].values())
    # A spec with no slug can't be keyed, so it is dropped from a batch.
    assert catalog.normalize_apxml_spec({"name": "no slug"}, "2026-08-01") is None
    assert [
        e["id"]
        for e in catalog.normalize_apxml_specs(
            [_apxml_spec(), {"name": "no slug"}], fetched_at="2026-08-01"
        )
    ] == ["qwen3-8b"]


def test_write_cache_creates_and_merges_by_id(tmp_path: Path) -> None:
    cache = tmp_path / "catalog_cache.yaml"
    catalog.write_cache(
        catalog.normalize_apxml_specs([_apxml_spec()], fetched_at="2026-08-01"), cache_path=cache
    )
    # A second refresh: same id overwrites (new ram), a new id appends.
    spec_b = dict(_apxml_spec(), slug="gemma3-4b")
    updated = dict(_apxml_spec(), ram_gb=7.0)
    catalog.write_cache(
        catalog.normalize_apxml_specs([updated, spec_b], fetched_at="2026-08-02"), cache_path=cache
    )
    by_id = {e["id"]: e for e in yaml.safe_load(cache.read_text())}
    assert set(by_id) == {"qwen3-8b", "gemma3-4b"}
    assert by_id["qwen3-8b"]["ram_gb"] == 7.0
