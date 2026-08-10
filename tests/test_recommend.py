"""
Tests for best_engine_ai_helper.recommend (the end-to-end algorithm).

Uses a synthetic catalog so the report is deterministic. Covers task parsing
(text vs vision, code/ocr axes), the report structure and JSON round-trip, the
throughput estimate's dependence on compute info, and the Markdown / file
emitters.
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


def test_parse_task_maps_words_to_kinds_and_axes() -> None:
    # Text-only stays a generalist LLM.
    text = recommend.parse_task("write blog posts")
    assert text["kinds"] == ["llm"] and text["application"] == "generalist"
    # A code word picks the code axis.
    assert recommend.parse_task("help me write python code")["application"] == "code"
    # Vision words add a VLM; OCR words set the VLM's OCR axis.
    vision = recommend.parse_task("product descriptions and image quality assessment")
    assert {"llm", "vlm"} <= set(vision["kinds"]) and "image" in vision["matched"]
    assert recommend.parse_task("read scanned invoices")["vlm_application"] == "ocr"


@pytest.mark.parametrize("task", [None, "", "   "])
def test_parse_task_warns_loudly_when_no_description(
    task: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="os_helper"):
        parsed = recommend.parse_task(task)
    assert parsed["language"] is None
    assert any("no task description provided" in r.message for r in caplog.records)


def test_parse_task_warns_when_description_has_no_detectable_language(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="os_helper"):
        parsed = recommend.parse_task("123 456 !!!")
    assert parsed["language"] is None
    assert any("no detectable language" in r.message for r in caplog.records)


def test_parse_task_records_language_for_a_clean_description(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="os_helper"):
        parsed = recommend.parse_task("rédiger des fiches produit et vérifier des photos")
    assert parsed["language"] == "fr"
    assert caplog.records == []


def test_recommend_report_is_coherent_and_json_serializable() -> None:
    rep = recommend.recommend(_HW, _CATALOG, task="descriptions and image checks", compute=_COMPUTE)
    assert {"llm", "vlm"} <= rep["recommendations"].keys()
    chosen = rep["recommendations"]["llm"]["chosen"]
    assert chosen["fits"] is True and chosen["est_tokens_per_s"] is not None
    json.loads(json.dumps(rep))  # the whole report round-trips through JSON


def test_lighter_alternative_is_not_less_structured_capable() -> None:
    # A structured-incapable model that is lighter and scores within 3 points of
    # the chosen (structured-capable) model must NOT be offered as the leaner
    # alternative: following it would fail the suite's schema-driven tasks.
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
    rep = recommend.recommend(_HW, catalog, task="image quality", compute=_COMPUTE)
    block = rep["recommendations"]["vlm"]
    assert block["chosen"]["id"] == "cap-vlm"  # structured-capable wins the slot
    # The lighter, higher-scoring but structured-incapable model is not suggested.
    assert block["lighter_alternative"] is None


def test_recommend_throughput_needs_compute() -> None:
    # Without a compute profile there is no bandwidth, so tok/s is not estimated.
    rep = recommend.recommend(_HW, _CATALOG, task="write copy")
    assert rep["recommendations"]["llm"]["chosen"]["est_tokens_per_s"] is None


def test_markdown_and_file_emitters(tmp_path) -> None:
    rep = recommend.recommend(_HW, _CATALOG, task="image quality", compute=_COMPUTE)
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


def test_recommend_with_load_caps_budget_and_appears_in_report() -> None:
    load = {
        "available_ram_gb": 8.0,
        "cpu_percent": 12.0,
        "gpu_percent": 5.0,
        "disk_free_gb": 100.0,
        "disk_percent_used": 40.0,
        "running_engines": 1,
    }
    rep = recommend.recommend(_HW, _CATALOG, task="write copy", compute=_COMPUTE, load=load)
    # Live free RAM (8 GB) is tighter than the load-blind budget, so it wins.
    assert rep["memory_budget_gb"] == pytest.approx(8.0)
    assert rep["server_load"] == load

    md = recommend.to_markdown(rep)
    assert "Server load (live, at recommendation time)" in md
    assert "Already-running engines: 1" in md

    # Without `load`, no server-load section is emitted at all.
    rep_no_load = recommend.recommend(_HW, _CATALOG, task="write copy", compute=_COMPUTE)
    assert "server_load" not in rep_no_load
    assert "Server load" not in recommend.to_markdown(rep_no_load)


def test_comfort_floor_demotes_fits_but_slow_models() -> None:
    # slow-big (30 GB) fits the 36 GB budget (0.5 headroom on a 96 GB M2 Max) but
    # decodes at ~8.7 tok/s; fast-mid (10.5 GB) clears the comfort floor at
    # ~25 tok/s. The comfort gate must pick the comfortable model, not the
    # higher-scoring slow one, and mark the slow-but-fitting model not comfortable.
    catalog = [
        {"id": "slow-big", "kind": "llm", "ram_gb": 30.0, "benchmarks": {"general": 87}},
        {"id": "fast-mid", "kind": "llm", "ram_gb": 10.5, "benchmarks": {"general": 78}},
    ]
    rep = recommend.recommend(_HW, catalog, task="write copy", compute=_COMPUTE)
    block = rep["recommendations"]["llm"]
    assert block["chosen"]["id"] == "fast-mid"
    rows = {r["id"]: r for r in block["candidates"]}
    assert rows["slow-big"]["fits"] is True
    assert rows["slow-big"]["comfortable"] is False
    assert rows["fast-mid"]["comfortable"] is True
    assert rep["comfort_tps"] == recommend.COMFORT_TPS


def test_comfort_floor_ignored_when_bandwidth_unknown() -> None:
    # Without a compute profile there is no throughput estimate, so the comfort
    # gate cannot fire: memory fit alone decides. Under the 0.5 headroom the big
    # models (48/52 GB) no longer fit the 36 GB budget, so the leanest-sufficient
    # pick among fitting models (mid-llm, general 78) wins and is comfortable by
    # default when speed is unknown.
    rep = recommend.recommend(_HW, _CATALOG, task="write copy")
    chosen = rep["recommendations"]["llm"]["chosen"]
    assert chosen["id"] == "mid-llm"
    assert chosen["est_tokens_per_s"] is None and chosen["comfortable"] is True
