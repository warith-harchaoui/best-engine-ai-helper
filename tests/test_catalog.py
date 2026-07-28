"""
Tests for best_engine_ai_helper.catalog.

Exercises both the bundled seed load and the estimate_ram calculation.
The cache-merge path is tested with a temporary YAML fixture.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from best_engine_ai_helper import catalog

# ---------------------------------------------------------------------------
# load_catalog — bundled seed
# ---------------------------------------------------------------------------

def test_load_catalog_returns_nonempty_list() -> None:
    entries = catalog.load_catalog()
    assert len(entries) > 0, "Bundled catalog should have at least one entry"


def test_load_catalog_entries_have_required_keys() -> None:
    required = {"id", "kind", "ram_gb", "benchmarks"}
    entries = catalog.load_catalog()
    for e in entries:
        missing = required - set(e.keys())
        assert not missing, f"Entry {e.get('id')} missing keys: {missing}"


def test_load_catalog_kinds_are_valid() -> None:
    entries = catalog.load_catalog()
    for e in entries:
        assert e["kind"] in ("llm", "vlm"), (
            f"Entry {e.get('id')} has invalid kind: {e['kind']!r}"
        )


def test_load_catalog_ram_gb_positive() -> None:
    entries = catalog.load_catalog()
    for e in entries:
        assert float(e["ram_gb"]) > 0, (
            f"Entry {e.get('id')} has non-positive ram_gb: {e['ram_gb']}"
        )


def test_load_catalog_ids_are_unique() -> None:
    entries = catalog.load_catalog()
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "Catalog has duplicate ids"


# ---------------------------------------------------------------------------
# load_catalog — cache merge
# ---------------------------------------------------------------------------

def test_load_catalog_cache_overwrites_seed(tmp_path: Path) -> None:
    # Write a minimal seed with one entry
    seed = tmp_path / "models.yaml"
    seed.write_text(textwrap.dedent("""\
        - id: test-model:1b
          kind: llm
          size_b: 1
          quant: Q4_K_M
          disk_gb: 1.0
          ram_gb: 1.1
          benchmarks:
            general: 50
            vision: null
            ocr: null
            code: null
            math: null
          notes: "seed"
          vllm_id: null
          fetched_at: null
    """))

    # Patch the cache path to our temp dir
    cache = tmp_path / "catalog_cache.yaml"
    cache.write_text(textwrap.dedent("""\
        - id: test-model:1b
          kind: llm
          size_b: 1
          quant: Q4_K_M
          disk_gb: 1.0
          ram_gb: 1.1
          benchmarks:
            general: 99
            vision: null
            ocr: null
            code: null
            math: null
          notes: "cache override"
          vllm_id: null
          fetched_at: "2026-07-28"
    """))

    import best_engine_ai_helper.catalog as cat_mod
    original_cache = cat_mod._CACHE_PATH
    try:
        cat_mod._CACHE_PATH = cache
        entries = catalog.load_catalog(catalog_path=seed)
        assert len(entries) == 1
        assert entries[0]["benchmarks"]["general"] == 99, (
            "Cache entry should overwrite seed entry"
        )
        assert entries[0]["notes"] == "cache override"
    finally:
        # Restore the real cache path so other tests are unaffected
        cat_mod._CACHE_PATH = original_cache


def test_load_catalog_missing_seed_raises(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError):
        catalog.load_catalog(catalog_path=nonexistent)


# ---------------------------------------------------------------------------
# estimate_ram
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quant,disk_gb,expected", [
    ("Q4_K_M", 6.1,  6.832),
    ("Q8_0",   6.1,  6.71),
    ("FP16",   10.0, 10.5),
    ("Q2_K",   5.0,  6.0),
])
def test_estimate_ram_known_quants(quant: str, disk_gb: float, expected: float) -> None:
    result = catalog.estimate_ram(disk_gb, quant)
    assert result == pytest.approx(expected, rel=1e-3)


def test_estimate_ram_unknown_quant_uses_default() -> None:
    # Unknown quant should use the 1.15 default overhead
    result = catalog.estimate_ram(10.0, "UNKNOWN_QUANT")
    assert result == pytest.approx(11.5, rel=1e-3)
