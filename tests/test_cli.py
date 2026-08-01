"""
Tests for best_engine_ai_helper.cli.

Uses Click's CliRunner, so no real subprocess or server is spawned. The
read-only commands run against real detection and the bundled catalog; the
side-effectful ones (refresh, pull, validate) have their network / detection /
ollama layer patched so the tests stay offline and never touch the real user
config under ~/.best-engine-ai-helper.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from best_engine_ai_helper.cli import main


def test_read_only_commands_smoke(runner: CliRunner) -> None:
    # Each read-only command exits 0 and prints its headline content.
    cases = [
        (["detect"], "platform"),
        (["recommend"], ""),
        (["recommend", "--kind", "llm"], "LLM"),
        (["recommend", "--kind", "vlm"], "VLM"),
        (["recommend", "--headroom", "0.5"], ""),
        (["catalog", "show"], "qwen3-vl:8b"),
        (["hardware", "show"], "Apple M2 Max"),
    ]
    for args, needle in cases:
        result = runner.invoke(main, args)
        assert result.exit_code == 0, f"{args} -> {result.exit_code}\n{result.output}"
        assert result.output.strip() and needle in result.output, args


def test_detect_emits_valid_json(runner: CliRunner) -> None:
    data = json.loads(runner.invoke(main, ["detect"]).output)
    assert {"platform", "chip_vendor", "memory"} <= data.keys()
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert data["memory"]["ram_gb"] > 0


def test_report_prints_markdown_json_and_writes_files(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = runner.invoke(main, ["report", "--task", "write python code"])
    assert md.exit_code == 0 and "# Best local engine" in md.output
    js = runner.invoke(main, ["report", "--format", "json"])
    assert js.exit_code == 0 and "recommendations" in json.loads(js.output)
    out = runner.invoke(main, ["report", "--out", str(tmp_path / "r")])
    assert out.exit_code == 0
    assert (tmp_path / "r.md").is_file() and (tmp_path / "r.json").is_file()


# ---------------------------------------------------------------------------
# catalog update / hardware update — offline via patched fetch / detection.
# ---------------------------------------------------------------------------

def test_catalog_update_writes_and_empty_feed_fails(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import catalog
    from best_engine_ai_helper.sources import apxml

    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)

    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [{
        "slug": "qwen3-8b", "kind": "llm", "size_b": 8.0, "ram_gb": 6.0,
        "vllm_id": "Qwen/Qwen3-8B", "url": "https://apxml.com/models/qwen3-8b",
    }])
    ok = runner.invoke(main, ["catalog", "update"])
    assert ok.exit_code == 0 and cache.exists()
    written = yaml.safe_load(cache.read_text())
    assert written[0]["id"] == "qwen3-8b" and written[0]["source"] == "apxml"

    # An empty feed leaves the cache untouched and reports failure.
    cache.unlink()
    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [])
    empty = runner.invoke(main, ["catalog", "update"])
    assert empty.exit_code != 0 and not cache.exists()


def test_hardware_update_records_or_reports_nothing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import hardware

    cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", cache)

    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: {
        "chip": "Apple M2 Max", "vendor": "apple", "memory_gb": 32.0,
        "ollama_usable_gb": 28.0, "source": "detected", "fetched_at": "2026-08-01",
    })
    ok = runner.invoke(main, ["hardware", "update"])
    assert ok.exit_code == 0 and yaml.safe_load(cache.read_text())[0]["chip"] == "Apple M2 Max"

    # Nothing detectable -> cache untouched, non-zero exit.
    cache.unlink()
    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: None)
    none = runner.invoke(main, ["hardware", "update"])
    assert none.exit_code != 0 and not cache.exists()


# ---------------------------------------------------------------------------
# pull / validate / env — ollama + gates patched, so no downloads or network.
# ---------------------------------------------------------------------------

def _patch_gates(monkeypatch: pytest.MonkeyPatch, vlm: bool, prose: bool) -> None:
    from best_engine_ai_helper import pull, validate_llm, validate_vlm
    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: True)
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: vlm)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: prose)


def test_pull_writes_env_when_both_gates_pass(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import pull

    _patch_gates(monkeypatch, vlm=True, prose=True)
    written: dict[str, object] = {}
    monkeypatch.setattr(pull, "write_env",
                        lambda **kw: (written.update(kw), tmp_path / "env.sh")[1])
    result = runner.invoke(main, ["pull"])
    assert result.exit_code == 0 and "Both gates passed" in result.output
    assert written["text_model"]  # the chosen tag was persisted


def test_pull_removes_failed_model_and_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from best_engine_ai_helper import pull

    _patch_gates(monkeypatch, vlm=False, prose=True)  # VLM gate fails
    removed: list[str] = []
    monkeypatch.setattr(pull, "ollama_rm", lambda tag: (removed.append(tag), True)[1])
    result = runner.invoke(main, ["pull"])
    assert result.exit_code == 1 and removed  # failed candidates are cleaned up


def test_pull_vllm_prints_serve_command_without_downloading(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from best_engine_ai_helper import pull

    monkeypatch.setattr(pull, "ollama_pull",
                        lambda *a, **k: pytest.fail("--vllm must not pull"))
    result = runner.invoke(main, ["pull", "--vllm"])
    assert result.exit_code == 0 and "vllm serve" in result.output


def test_validate_and_env_require_configuration(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.delenv("SPREZZATURE_LLM_TEXT", raising=False)
    # With nothing configured, both commands explain what to run and exit non-zero.
    for cmd in (["validate"], ["env"]):
        result = runner.invoke(main, cmd)
        combined = (result.output or "") + (result.stderr or "")
        assert result.exit_code != 0 and combined.strip()


def test_validate_runs_gates_when_configured(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from best_engine_ai_helper import validate_llm, validate_vlm
    monkeypatch.setenv("BEST_LLM_TEXT", "qwen3:8b")
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    result = runner.invoke(main, ["validate"])
    assert result.exit_code == 0
    assert "pass" in result.output.lower()


def test_gui_command_binds_and_needs_extra(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    uvicorn = pytest.importorskip("uvicorn")
    calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    result = runner.invoke(main, ["gui", "--host", "0.0.0.0", "--port", "9000"])
    assert result.exit_code == 0
    assert calls["app"] == "best_engine_ai_helper.api:app"
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 9000)
    # Without the [api] extra, the command names the missing dependency.
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    missing = runner.invoke(main, ["gui"])
    assert missing.exit_code == 1
    assert "[api]" in (missing.output or "") + (missing.stderr or "")
