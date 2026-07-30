"""Tests for best_engine_ai_helper.recommend (the end-to-end algorithm)."""
from __future__ import annotations

import json

# Import the submodule explicitly: the package also exports a `recommend`
# function, which would otherwise shadow the module name on `from pkg import`.
import best_engine_ai_helper.recommend as recommend

_CATALOG = [
    {"id": "tiny-llm", "kind": "llm", "ram_gb": 5.6, "benchmarks": {"general": 74}},
    {"id": "mid-llm", "kind": "llm", "ram_gb": 10.5, "benchmarks": {"general": 78}},
    {"id": "big-llm", "kind": "llm", "ram_gb": 48.0, "benchmarks": {"general": 87}},
    {"id": "tiny-vlm", "kind": "vlm", "ram_gb": 6.8,
     "benchmarks": {"general": 73, "vision": 80, "ocr": 78}},
    {"id": "big-vlm", "kind": "vlm", "ram_gb": 52.0,
     "benchmarks": {"general": 88, "vision": 91, "ocr": 85}},
]
_HW = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
_COMPUTE = {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0}


def test_parse_task_text_only_is_llm_generalist() -> None:
    p = recommend.parse_task("write blog posts")
    assert p["kinds"] == ["llm"]
    assert p["application"] == "generalist"


def test_parse_task_vision_adds_vlm() -> None:
    p = recommend.parse_task("product descriptions and image quality assessment")
    assert "vlm" in p["kinds"] and "llm" in p["kinds"]
    assert "image" in p["matched"]


def test_parse_task_code_axis() -> None:
    p = recommend.parse_task("help me write python code")
    assert p["application"] == "code"
    assert p["kinds"] == ["llm"]


def test_parse_task_ocr_sets_vlm_ocr_axis() -> None:
    p = recommend.parse_task("read scanned invoices")
    assert "vlm" in p["kinds"]
    assert p["vlm_application"] == "ocr"


def test_recommend_returns_both_and_is_json_serializable() -> None:
    rep = recommend.recommend(
        _HW, _CATALOG, task="descriptions and image checks", compute=_COMPUTE
    )
    assert "llm" in rep["recommendations"] and "vlm" in rep["recommendations"]
    # chosen models fit the budget and carry a throughput estimate
    llm = rep["recommendations"]["llm"]["chosen"]
    assert llm["fits"] is True
    assert llm["est_tokens_per_s"] is not None
    # the whole report round-trips through JSON
    json.loads(json.dumps(rep))


def test_recommend_throughput_none_without_compute() -> None:
    rep = recommend.recommend(_HW, _CATALOG, task="write copy")
    assert rep["recommendations"]["llm"]["chosen"]["est_tokens_per_s"] is None


def test_to_markdown_contains_key_sections() -> None:
    rep = recommend.recommend(_HW, _CATALOG, task="image quality", compute=_COMPUTE)
    md = recommend.to_markdown(rep)
    assert "# Best local engine" in md
    assert "Usable model budget" in md
    assert "How this was decided" in md
    assert "Sources:" in md


def test_write_report_emits_md_and_json(tmp_path) -> None:
    rep = recommend.recommend(_HW, _CATALOG, task="descriptions", compute=_COMPUTE)
    md_path, json_path = recommend.write_report(rep, tmp_path / "r")
    assert md_path.is_file() and json_path.is_file()
    assert json.loads(json_path.read_text())["memory_budget_gb"] > 0
