"""
Tests for best_engine_ai_helper.recommend (the end-to-end algorithm).

Uses a synthetic catalog so the report is deterministic. Covers task parsing
(text vs vision, code/ocr axes, blank/undetectable-language warnings), the
report structure and JSON round-trip, the comfort floor and live-load budget
capping, and the Markdown / file emitters.
"""

from __future__ import annotations

import json
import logging

import pytest

# Import the submodule explicitly: the package also exports a `recommend`
# function, which would otherwise shadow the module name on `from pkg import`.
import best_engine_ai_helper.recommend as recommend

_CATALOG = [
    {"id": "tiny-llm", "kind": "llm", "ram_gb": 5.6, "benchmarks": {"general": 74}},
    {"id": "mid-llm", "kind": "llm", "ram_gb": 10.5, "benchmarks": {"general": 78}},
    {"id": "big-llm", "kind": "llm", "ram_gb": 48.0, "benchmarks": {"general": 87}},
    {
        "id": "tiny-vlm",
        "kind": "vlm",
        "ram_gb": 6.8,
        "benchmarks": {"general": 73, "vision": 80, "ocr": 78},
    },
    {
        "id": "big-vlm",
        "kind": "vlm",
        "ram_gb": 52.0,
        "benchmarks": {"general": 88, "vision": 91, "ocr": 85},
    },
]
_HW = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
_COMPUTE = {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0}


def test_parse_task_and_report_core_behavior(caplog: pytest.LogCaptureFixture, tmp_path) -> None:
    # Text-only stays a generalist LLM.
    text = recommend.parse_task("write blog posts")
    assert text["kinds"] == ["llm"] and text["application"] == "generalist"
    # A code word picks the code axis.
    assert recommend.parse_task("help me write python code")["application"] == "code"
    # Vision words add a VLM; OCR words set the VLM's OCR axis.
    vision = recommend.parse_task("product descriptions and image quality assessment")
    assert {"llm", "vlm"} <= set(vision["kinds"]) and "image" in vision["matched"]
    assert recommend.parse_task("read scanned invoices")["vlm_application"] == "ocr"

    for blank in (None, "", "   "):
        with caplog.at_level(logging.WARNING, logger="os_helper"):
            parsed = recommend.parse_task(blank)
        assert parsed["language"] is None
        assert any("no task description provided" in r.message for r in caplog.records)
        caplog.clear()

    with caplog.at_level(logging.WARNING, logger="os_helper"):
        undetectable = recommend.parse_task("123 456 !!!")
    assert undetectable["language"] is None
    assert any("no detectable language" in r.message for r in caplog.records)
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="os_helper"):
        clean = recommend.parse_task("rédiger des fiches produit et vérifier des photos")
    assert clean["language"] == "fr"
    assert caplog.records == []

    rep = recommend.recommend(_HW, _CATALOG, task="descriptions and image checks", compute=_COMPUTE)
    assert {"llm", "vlm"} <= rep["recommendations"].keys()
    chosen = rep["recommendations"]["llm"]["chosen"]
    assert chosen["fits"] is True and chosen["est_tokens_per_s"] is not None
    json.loads(json.dumps(rep))  # the whole report round-trips through JSON

    # A structured-incapable model that is lighter and scores within 3 points
    # of the chosen (structured-capable) model must NOT be offered as the
    # leaner alternative: following it would fail the suite's schema-driven
    # tasks.
    catalog = [
        {
            "id": "cap-vlm",
            "kind": "vlm",
            "ram_gb": 9.0,
            "benchmarks": {"general": 77, "vision": 78},
            "structured_output": True,
        },
        {
            "id": "incap-vlm",
            "kind": "vlm",
            "ram_gb": 6.8,
            "benchmarks": {"general": 79, "vision": 80},
            "structured_output": False,
        },
    ]
    capable_rep = recommend.recommend(_HW, catalog, task="image quality", compute=_COMPUTE)
    block = capable_rep["recommendations"]["vlm"]
    assert block["chosen"]["id"] == "cap-vlm"  # structured-capable wins the slot
    assert block["lighter_alternative"] is None  # incapable model not suggested

    # Without a compute profile there is no bandwidth, so tok/s is not estimated.
    no_compute_rep = recommend.recommend(_HW, _CATALOG, task="write copy")
    assert no_compute_rep["recommendations"]["llm"]["chosen"]["est_tokens_per_s"] is None

    md = recommend.to_markdown(rep)
    for section in (
        "# Best local engine",
        "Usable model budget",
        "How this was decided",
        "Sources:",
    ):
        assert section in md
    md_path, json_path = recommend.write_report(rep, tmp_path / "r")
    assert md_path.is_file() and json_path.is_file()
    assert json.loads(json_path.read_text())["memory_budget_gb"] > 0


def test_recommend_load_and_comfort_gate() -> None:
    load = {
        "available_ram_gb": 8.0,
        "cpu_percent": 12.0,
        "gpu_percent": 5.0,
        "disk_free_gb": 100.0,
        "disk_percent_used": 40.0,
        "running_engines": 1,
    }
    loaded_rep = recommend.recommend(_HW, _CATALOG, task="write copy", compute=_COMPUTE, load=load)
    # Live free RAM (8 GB) is tighter than the load-blind budget, so it wins.
    assert loaded_rep["memory_budget_gb"] == pytest.approx(8.0)
    assert loaded_rep["server_load"] == load
    loaded_md = recommend.to_markdown(loaded_rep)
    assert "Server load (live, at recommendation time)" in loaded_md
    assert "Already-running engines: 1" in loaded_md

    # Without `load`, no server-load section is emitted at all.
    no_load_rep = recommend.recommend(_HW, _CATALOG, task="write copy", compute=_COMPUTE)
    assert "server_load" not in no_load_rep
    assert "Server load" not in recommend.to_markdown(no_load_rep)

    # slow-big (30 GB) fits the 36 GB budget (0.5 headroom on a 96 GB M2 Max)
    # but decodes at ~8.7 tok/s; fast-mid (10.5 GB) clears the comfort floor at
    # ~25 tok/s. The comfort gate must pick the comfortable model, not the
    # higher-scoring slow one, and mark the slow-but-fitting model not
    # comfortable.
    comfort_catalog = [
        {"id": "slow-big", "kind": "llm", "ram_gb": 30.0, "benchmarks": {"general": 87}},
        {"id": "fast-mid", "kind": "llm", "ram_gb": 10.5, "benchmarks": {"general": 78}},
    ]
    comfort_rep = recommend.recommend(_HW, comfort_catalog, task="write copy", compute=_COMPUTE)
    comfort_block = comfort_rep["recommendations"]["llm"]
    assert comfort_block["chosen"]["id"] == "fast-mid"
    rows = {r["id"]: r for r in comfort_block["candidates"]}
    assert rows["slow-big"]["fits"] is True
    assert rows["slow-big"]["comfortable"] is False
    assert rows["fast-mid"]["comfortable"] is True
    assert comfort_rep["comfort_tps"] == recommend.COMFORT_TPS

    # Without a compute profile there is no throughput estimate, so the
    # comfort gate cannot fire: memory fit alone decides. Under the 0.5
    # headroom the big models (48/52 GB) no longer fit the 36 GB budget, so
    # the leanest-sufficient pick among fitting models (mid-llm, general 78)
    # wins and is comfortable by default when speed is unknown.
    no_bandwidth_rep = recommend.recommend(_HW, _CATALOG, task="write copy")
    no_bandwidth_chosen = no_bandwidth_rep["recommendations"]["llm"]["chosen"]
    assert no_bandwidth_chosen["id"] == "mid-llm"
    assert no_bandwidth_chosen["est_tokens_per_s"] is None
    assert no_bandwidth_chosen["comfortable"] is True
