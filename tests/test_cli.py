"""
Tests for best_engine_ai_helper.cli.

Uses Click's CliRunner so no subprocess spawning is needed and the working
directory is irrelevant. The refresh commands (`catalog update`,
`hardware update`) are exercised with their network / detection layer patched
so the tests stay offline and never touch the real user cache.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from best_engine_ai_helper.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def test_detect_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["detect"])
    assert result.exit_code == 0, f"detect exited {result.exit_code}:\n{result.output}"


def test_detect_output_is_valid_json(runner: CliRunner) -> None:
    result = runner.invoke(main, ["detect"])
    data = json.loads(result.output)
    assert "platform" in data
    assert "chip_vendor" in data
    assert "memory" in data


def test_detect_memory_keys(runner: CliRunner) -> None:
    result = runner.invoke(main, ["detect"])
    data = json.loads(result.output)
    mem = data["memory"]
    assert set(mem.keys()) == {"unified_gb", "vram_gb", "ram_gb"}
    assert mem["ram_gb"] > 0


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------

def test_recommend_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["recommend"])
    assert result.exit_code == 0, f"recommend exited {result.exit_code}:\n{result.output}"


def test_recommend_output_nonempty(runner: CliRunner) -> None:
    result = runner.invoke(main, ["recommend"])
    assert result.output.strip(), "recommend should produce non-empty output"


def test_recommend_kind_llm(runner: CliRunner) -> None:
    result = runner.invoke(main, ["recommend", "--kind", "llm"])
    assert result.exit_code == 0
    assert "LLM" in result.output


def test_recommend_kind_vlm(runner: CliRunner) -> None:
    result = runner.invoke(main, ["recommend", "--kind", "vlm"])
    assert result.exit_code == 0
    assert "VLM" in result.output


def test_recommend_custom_headroom(runner: CliRunner) -> None:
    result = runner.invoke(main, ["recommend", "--headroom", "0.5"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# catalog show
# ---------------------------------------------------------------------------

def test_catalog_show_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["catalog", "show"])
    assert result.exit_code == 0, f"catalog show exited {result.exit_code}:\n{result.output}"


def test_catalog_show_output_nonempty(runner: CliRunner) -> None:
    result = runner.invoke(main, ["catalog", "show"])
    assert result.output.strip(), "catalog show should produce non-empty output"


def test_catalog_show_contains_known_model(runner: CliRunner) -> None:
    result = runner.invoke(main, ["catalog", "show"])
    # The bundled seed always has this model
    assert "qwen3-vl:8b" in result.output


# ---------------------------------------------------------------------------
# hardware show
# ---------------------------------------------------------------------------

def test_hardware_show_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(main, ["hardware", "show"])
    assert result.exit_code == 0, f"hardware show exited {result.exit_code}:\n{result.output}"


def test_hardware_show_output_nonempty(runner: CliRunner) -> None:
    result = runner.invoke(main, ["hardware", "show"])
    assert result.output.strip()


def test_hardware_show_contains_apple_m2_max(runner: CliRunner) -> None:
    result = runner.invoke(main, ["hardware", "show"])
    assert "Apple M2 Max" in result.output


# ---------------------------------------------------------------------------
# catalog update / hardware update — refresh the user caches.
# The network fetch (catalog) and live detection (hardware) are patched so the
# tests run offline and write only into a tmp cache, never the real ~/.best-*.
# ---------------------------------------------------------------------------

def test_catalog_update_writes_cache(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """catalog update fetches specs, normalizes them, and writes the cache."""
    from best_engine_ai_helper import catalog
    from best_engine_ai_helper.sources import apxml

    fake_specs = [{
        "slug": "qwen3-8b",
        "name": "Qwen3 8B",
        "kind": "llm",
        "size_b": 8.0,
        "ram_gb": 6.0,
        "vllm_id": "Qwen/Qwen3-8B",
        "context_length": 32768,
        "license": "apache-2.0",
        "url": "https://apxml.com/models/qwen3-8b",
    }]
    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: fake_specs)
    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)

    result = runner.invoke(main, ["catalog", "update"])
    assert result.exit_code == 0, result.output
    assert cache.exists()
    written = yaml.safe_load(cache.read_text(encoding="utf-8"))
    assert written[0]["id"] == "qwen3-8b"
    assert written[0]["source"] == "apxml"


def test_catalog_update_empty_feed_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty feed leaves the cache untouched and reports failure."""
    from best_engine_ai_helper import catalog
    from best_engine_ai_helper.sources import apxml

    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [])
    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)

    result = runner.invoke(main, ["catalog", "update"])
    assert result.exit_code != 0
    assert not cache.exists()


def test_hardware_update_records_machine(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """hardware update writes the detected machine into the cache."""
    from best_engine_ai_helper import hardware

    entry = {
        "chip": "Apple M2 Max",
        "vendor": "apple",
        "memory_gb": 32.0,
        "ollama_usable_gb": 28.0,
        "source": "detected",
        "fetched_at": "2026-08-01",
    }
    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: entry)
    cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", cache)

    result = runner.invoke(main, ["hardware", "update"])
    assert result.exit_code == 0, result.output
    assert cache.exists()
    written = yaml.safe_load(cache.read_text(encoding="utf-8"))
    assert written[0]["chip"] == "Apple M2 Max"


def test_hardware_update_no_memory_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When detection finds nothing usable, the cache stays untouched."""
    from best_engine_ai_helper import hardware

    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: None)
    cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", cache)

    result = runner.invoke(main, ["hardware", "update"])
    assert result.exit_code != 0
    assert not cache.exists()


def test_env_missing_reports_gracefully(runner: CliRunner) -> None:
    """env command reports that env.sh is missing when pull has not been run."""
    result = runner.invoke(main, ["env"])
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    # Either env.sh not found or BEST_LLM_TEXT not set; both are acceptable messages
    assert "env.sh" in combined.lower() or "best_llm" in combined.lower(), (
        f"env command should report missing env.sh or unconfigured model, got: {combined!r}"
    )


def test_validate_missing_env_reports_gracefully(runner: CliRunner) -> None:
    """validate command reports missing configuration when env.sh is absent."""
    result = runner.invoke(main, ["validate"])
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    assert combined.strip(), "validate should produce output even with no model configured"


# ---------------------------------------------------------------------------
# gui
#
# uvicorn.run() would otherwise block the test process serving forever, so
# every happy-path test replaces it with a recording stub before invoking the
# command. The extra-not-installed path is simulated by setting
# sys.modules["uvicorn"] = None, which makes `import uvicorn` raise
# ImportError regardless of whether the [api] extra is actually present.
# ---------------------------------------------------------------------------

def test_gui_invokes_uvicorn_with_defaults(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    uvicorn = pytest.importorskip("uvicorn")
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw)
    )

    result = runner.invoke(main, ["gui"])

    assert result.exit_code == 0, result.output
    assert calls["app"] == "best_engine_ai_helper.api:app"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8000
    assert "Serving GUI" in result.output


def test_gui_respects_host_and_port_flags(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    uvicorn = pytest.importorskip("uvicorn")
    calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw))

    result = runner.invoke(main, ["gui", "--host", "0.0.0.0", "--port", "9000"])

    assert result.exit_code == 0, result.output
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000


def test_gui_without_api_extra_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "uvicorn", None)

    result = runner.invoke(main, ["gui"])

    assert result.exit_code == 1
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    assert "[api]" in combined
