"""
Tests for best_engine_ai_helper.cli.

Uses Click's CliRunner, so no real subprocess or server is spawned. The
read-only commands run against real detection and the bundled catalog; the
side-effectful ones (refresh, pull, validate) have their network / detection /
ollama layer patched so the tests stay offline and never touch the real user
config under ~/.best-engine-ai-helper. Each test groups several related
commands/scenarios into one functional check rather than one test per
command, so the suite stays small while covering the same ground.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from best_engine_ai_helper.cli import main


def test_read_only_and_report_commands(runner: CliRunner, tmp_path: Path) -> None:
    cases = [
        (["detect"], "platform"),
        (["recommend"], ""),
        (["recommend", "--kind", "llm"], "LLM"),
        (["recommend", "--kind", "vlm"], "VLM"),
        (["recommend", "--headroom", "0.5"], ""),
        (["recommend", "--live"], ""),
        (["catalog", "show"], "qwen3-vl:8b"),
        (["hardware", "show"], "Apple M2 Max"),
    ]
    for args, needle in cases:
        result = runner.invoke(main, args)
        assert result.exit_code == 0, f"{args} -> {result.exit_code}\n{result.output}"
        assert result.output.strip() and needle in result.output, args

    live = runner.invoke(main, ["report", "--task", "write copy", "--live"])
    assert live.exit_code == 0
    assert "Server load (live, at recommendation time)" in live.stdout

    data = json.loads(runner.invoke(main, ["detect"]).output)
    assert {"platform", "chip_vendor", "memory"} <= data.keys()
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert data["memory"]["ram_gb"] > 0

    md = runner.invoke(main, ["report", "--task", "write python code"])
    assert md.exit_code == 0 and "# Best local engine" in md.output
    # No --task here: parse_task logs a WARNING (see recommend.py), and
    # CliRunner's `.output` merges stdout+stderr, so parse strictly from
    # `.stdout` — the CLI's real machine-readable-JSON contract is stdout only.
    js = runner.invoke(main, ["report", "--format", "json"])
    assert js.exit_code == 0 and "recommendations" in json.loads(js.stdout)
    out = runner.invoke(main, ["report", "--out", str(tmp_path / "r")])
    assert out.exit_code == 0
    assert (tmp_path / "r.md").is_file() and (tmp_path / "r.json").is_file()

    brief = tmp_path / "llm.brief.yaml"
    brief.write_text(yaml.safe_dump({"kind": "llm", "task": "write python code"}))
    engine_out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(main, ["resolve", "--brief", str(brief), "--out", str(engine_out)])
    assert resolved.exit_code == 0
    assert f"Wrote {engine_out}" in resolved.output
    assert engine_out.is_file() and "backend" in yaml.safe_load(engine_out.read_text())

    missing = runner.invoke(main, ["resolve", "--brief", str(tmp_path / "nope.yaml")])
    assert missing.exit_code == 1
    assert "not found" in missing.output


def test_activity_empty_and_populated(runner: CliRunner, tmp_path: Path) -> None:
    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # A test-owned ledger, enabled up front, so `activity_cmd`'s "no active
    # ledger -> open the default path" fallback never touches the real
    # ~/.best-engine-ai-helper/usage.db (conftest's autouse fixture sets
    # BEST_ENGINE_NO_LEDGER=1, so `main()`'s own auto-enable stays a no-op).
    ledger = observe.enable(str(tmp_path / "usage.db"))

    empty = runner.invoke(main, ["activity"])
    assert empty.exit_code == 0 and "No calls recorded yet." in empty.stdout

    empty_json = runner.invoke(main, ["activity", "--format", "json"])
    assert json.loads(empty_json.stdout)["total_calls"] == 0

    # Record one call, then check both output formats reflect it.
    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")

    table = runner.invoke(main, ["activity"])
    assert table.exit_code == 0
    assert "Total calls: 1" in table.stdout and "qwen3:8b" in table.stdout

    as_json = runner.invoke(main, ["activity", "--format", "json"])
    data = json.loads(as_json.stdout)
    assert data["total_calls"] == 1 and data["total_cost_usd"] == 0.0
    ledger.close()


def test_usages_subcommands(runner: CliRunner, tmp_path: Path) -> None:
    listing = runner.invoke(main, ["usages", "list"])
    assert listing.exit_code == 0
    assert "Families" in listing.output and "Profiles" in listing.output
    assert "text2sql" in listing.output and "F1" in listing.output

    shown = runner.invoke(main, ["usages", "show", "text2sql"])
    assert shown.exit_code == 0
    assert "Needs (selection criteria):" in shown.output
    assert "structured_output" in shown.output

    unknown_show = runner.invoke(main, ["usages", "show", "not-a-real-profile"])
    assert unknown_show.exit_code == 1

    out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(main, ["usages", "resolve", "text2sql", "--out", str(out)])
    assert resolved.exit_code == 0
    assert "text2sql: backend" in resolved.output
    assert out.is_file()

    family = runner.invoke(main, ["usages", "resolve", "--family", "F1"])
    assert family.exit_code == 0
    assert "F1: backend" in family.output

    no_target = runner.invoke(main, ["usages", "resolve"])
    assert no_target.exit_code == 1
    assert "NAME or --family" in no_target.output

    unknown_resolve = runner.invoke(main, ["usages", "resolve", "not-a-real-profile"])
    assert unknown_resolve.exit_code == 1
    assert "resolve failed" in unknown_resolve.output


def test_catalog_and_hardware_update(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import catalog, hardware
    from best_engine_ai_helper.sources import apxml

    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)
    monkeypatch.setattr(
        apxml,
        "fetch_open_weight_models",
        lambda **kw: [
            {
                "slug": "qwen3-8b",
                "kind": "llm",
                "size_b": 8.0,
                "ram_gb": 6.0,
                "vllm_id": "Qwen/Qwen3-8B",
                "url": "https://apxml.com/models/qwen3-8b",
            }
        ],
    )
    ok = runner.invoke(main, ["catalog", "update"])
    assert ok.exit_code == 0 and cache.exists()
    written = yaml.safe_load(cache.read_text())
    assert written[0]["id"] == "qwen3-8b" and written[0]["source"] == "apxml"

    # An empty feed leaves the cache untouched and reports failure.
    cache.unlink()
    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [])
    empty = runner.invoke(main, ["catalog", "update"])
    assert empty.exit_code != 0 and not cache.exists()

    hw_cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", hw_cache)
    monkeypatch.setattr(
        hardware,
        "detect_local_entry",
        lambda *a, **k: {
            "chip": "Apple M2 Max",
            "vendor": "apple",
            "memory_gb": 32.0,
            "ollama_usable_gb": 28.0,
            "source": "detected",
            "fetched_at": "2026-08-01",
        },
    )
    hw_ok = runner.invoke(main, ["hardware", "update"])
    assert hw_ok.exit_code == 0
    assert yaml.safe_load(hw_cache.read_text())[0]["chip"] == "Apple M2 Max"

    # Nothing detectable -> cache untouched, non-zero exit.
    hw_cache.unlink()
    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: None)
    hw_none = runner.invoke(main, ["hardware", "update"])
    assert hw_none.exit_code != 0 and not hw_cache.exists()


def _patch_gates(monkeypatch: pytest.MonkeyPatch, vlm: bool, prose: bool) -> None:
    from best_engine_ai_helper import pull, validate_llm, validate_vlm

    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: True)
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: vlm)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: prose)


def test_pull_validate_env(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import catalog, detect, pull, validate_llm, validate_vlm

    _patch_gates(monkeypatch, vlm=True, prose=True)
    written: dict[str, object] = {}
    monkeypatch.setattr(
        pull, "write_env", lambda **kw: (written.update(kw), tmp_path / "env.sh")[1]
    )
    passed = runner.invoke(main, ["pull"])
    assert passed.exit_code == 0 and "Both gates passed" in passed.output
    assert written["text_model"]  # the chosen tag was persisted

    # On an M2-Max-like machine a 48 GB model fits memory but crawls (~5 tok/s);
    # a 10 GB model clears the comfort floor (~26 tok/s). pull must try the
    # comfortable model first even though the slow one scores higher.
    monkeypatch.setattr(
        detect, "available_memory", lambda: {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    )
    monkeypatch.setattr(
        detect,
        "compute_profile",
        lambda: {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
    )
    monkeypatch.setattr(
        catalog,
        "load_catalog",
        lambda: [
            {
                "id": "big-slow",
                "kind": "vlm",
                "ram_gb": 48.0,
                "benchmarks": {"vision": 90, "general": 90},
                "structured_output": True,
            },
            {
                "id": "small-fast",
                "kind": "vlm",
                "ram_gb": 10.0,
                "benchmarks": {"vision": 80, "general": 80},
                "structured_output": True,
            },
        ],
    )
    pulled: list[str] = []
    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: (pulled.append(tag), True)[1])
    monkeypatch.setattr(pull, "write_env", lambda **kw: tmp_path / "env.sh")
    comfortable = runner.invoke(main, ["pull"])
    assert comfortable.exit_code == 0
    assert pulled[0] == "small-fast"  # comfortable model tried first, not big-slow

    # A failed VLM gate removes the candidate and exits non-zero.
    _patch_gates(monkeypatch, vlm=False, prose=True)
    removed: list[str] = []
    monkeypatch.setattr(pull, "ollama_rm", lambda tag: (removed.append(tag), True)[1])
    failed = runner.invoke(main, ["pull"])
    assert failed.exit_code == 1 and removed  # failed candidates are cleaned up

    # --vllm prints the serve command without ever calling ollama_pull.
    monkeypatch.setattr(pull, "ollama_pull", lambda *a, **k: pytest.fail("--vllm must not pull"))
    vllm = runner.invoke(main, ["pull", "--vllm"])
    assert vllm.exit_code == 0 and "vllm serve" in vllm.output

    # validate/env with nothing configured: both explain what to run.
    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.delenv("SPREZZATURE_LLM_TEXT", raising=False)
    for cmd in (["validate"], ["env"]):
        unconfigured = runner.invoke(main, cmd)
        combined = (unconfigured.output or "") + (unconfigured.stderr or "")
        assert unconfigured.exit_code != 0 and combined.strip()

    # validate with a model configured and both gates passing.
    monkeypatch.setenv("BEST_LLM_TEXT", "qwen3:8b")
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    configured = runner.invoke(main, ["validate"])
    assert configured.exit_code == 0
    assert "pass" in configured.output.lower()

    import uvicorn

    gui_calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: gui_calls.update(app=app, **kw))
    gui_result = runner.invoke(main, ["gui", "--host", "0.0.0.0", "--port", "9000"])
    assert gui_result.exit_code == 0
    assert gui_calls["app"] == "best_engine_ai_helper.api:app"
    assert (gui_calls["host"], gui_calls["port"]) == ("0.0.0.0", 9000)
