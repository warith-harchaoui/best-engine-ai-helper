"""
End-to-end scenario tests.

These walk realistic workflows across module seams — detect -> catalog ->
score -> recommend -> emit; refresh -> load; pull -> env -> config resolve — so
they catch integration bugs the per-module unit tests can't, and double as
executable documentation of how the pieces fit together. Only true I/O
boundaries (the ApXML network fetch) are stubbed.
"""

from __future__ import annotations

import json
from pathlib import Path

import best_engine_ai_helper.recommend as recommend
from best_engine_ai_helper import catalog, config, detect, pull, score


def test_recommendation_report_pipeline_on_real_catalog(tmp_path: Path) -> None:
    # The full report path the CLI's `report` command runs: real detection, real
    # bundled catalog, ranked recommendation, Markdown + JSON emitted to disk.
    hw = detect.available_memory()
    compute = detect.compute_profile()
    entries = catalog.load_catalog()
    known_ids = {e["id"] for e in entries}

    rep = recommend.recommend(
        hw, entries, task="check photo quality and write product copy", compute=compute
    )
    assert {"llm", "vlm"} <= rep["recommendations"].keys()
    for kind in ("llm", "vlm"):
        chosen = rep["recommendations"][kind]["chosen"]
        assert chosen is not None and chosen["id"] in known_ids  # picked from the real catalog

    md_path, json_path = recommend.write_report(rep, tmp_path / "report")
    assert md_path.is_file() and "# Best local engine" in md_path.read_text()
    assert json.loads(json_path.read_text())["memory_budget_gb"] > 0


def test_catalog_refresh_then_appears_in_recommendation(tmp_path: Path, monkeypatch) -> None:
    # A `catalog update` refresh writes the cache; the merged catalog then
    # carries the new model, and the recommender can rank it.
    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)
    spec = {
        "slug": "scenario-vlm",
        "kind": "vlm",
        "size_b": 7.0,
        "ram_gb": 5.0,
        "url": "https://apxml.com/models/scenario-vlm",
    }
    catalog.write_cache(
        catalog.normalize_apxml_specs([spec], fetched_at="2026-08-01"), cache_path=cache
    )

    merged = catalog.load_catalog()
    assert any(e["id"] == "scenario-vlm" for e in merged)
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    assert "scenario-vlm" in {r["id"] for r in score.rank(hw, merged, kind="vlm")}


def test_pull_writes_env_then_config_resolves_it(tmp_path: Path, monkeypatch) -> None:
    # The tail of the pull workflow: write_env persists the chosen tags, and the
    # config resolver reads them back with no env vars set.
    pull.write_env("qwen3:8b", "gemma3:12b", "ollama", "http://localhost:11434", user_dir=tmp_path)
    monkeypatch.setattr(config, "_USER_DIR", tmp_path)
    for var in (
        "BEST_LLM_TEXT",
        "BEST_LLM_VISION",
        "SPREZZATURE_LLM_TEXT",
        "SPREZZATURE_LLM_VISION",
    ):
        monkeypatch.delenv(var, raising=False)
    assert config.resolved_models() == {"text": "qwen3:8b", "vision": "gemma3:12b"}
