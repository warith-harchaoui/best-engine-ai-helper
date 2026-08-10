"""
Tests for best_engine_ai_helper.cli_argparse.

The argparse twin delegates every handler to the same library functions
`test_cli.py` already exercises through the click surface, so this module
does NOT re-verify business logic (which candidate is comfortable, which
gate fails, etc. — see test_cli.py). It verifies the argparse-specific seam
instead, as a handful of parity/smoke checks: the parser builds, every
subcommand's --help works, and one representative happy path plus one error
path per command family proves the plumbing (parsing -> handler -> library
call -> stdout) connects end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from best_engine_ai_helper.cli_argparse import build_parser, main

EXPECTED_COMMANDS = {
    "detect",
    "recommend",
    "resolve",
    "report",
    "usages",
    "catalog",
    "hardware",
    "pull",
    "validate",
    "gui",
    "env",
    "activity",
}


def test_parser_and_help_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    )
    assert EXPECTED_COMMANDS == set(subparsers_action.choices.keys())

    with pytest.raises(SystemExit) as root_help:
        main(["--help"])
    assert root_help.value.code == 0
    assert "best-engine-ai-helper" in capsys.readouterr().out.lower()

    # Every top-level command's --help exits 0 (argparse convention).
    for command in sorted(EXPECTED_COMMANDS):
        with pytest.raises(SystemExit) as command_help:
            main([command, "--help"])
        assert command_help.value.code == 0
        capsys.readouterr()


def test_read_only_commands_happy_path(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["detect"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"platform", "chip_vendor", "memory", "hardware"} <= data.keys()
    assert data["memory"]["ram_gb"] > 0

    assert main(["recommend", "--kind", "llm", "--live"]) == 0
    assert "LLM" in capsys.readouterr().out

    assert main(["report", "--task", "write copy", "--live"]) == 0
    assert "Server load (live, at recommendation time)" in capsys.readouterr().out
    assert main(["report", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)  # must parse as JSON
    stem = str(tmp_path / "r")
    assert main(["report", "--out", stem]) == 0
    capsys.readouterr()
    assert Path(f"{stem}.md").exists() and Path(f"{stem}.json").exists()

    brief = tmp_path / "llm.brief.yaml"
    brief.write_text(
        "mode: local\nkind: llm\nheadroom: 0.5\nmin_tps: 15\n"
        "structured_output: false\ntask: generalist chat\n"
    )
    engine_out = tmp_path / "llm.engine.yaml"
    assert main(["resolve", "--brief", str(brief), "--out", str(engine_out)]) == 0
    assert engine_out.is_file()
    assert "Wrote" in capsys.readouterr().out

    assert main(["usages", "list"]) == 0
    assert "Profiles" in capsys.readouterr().out
    assert main(["usages", "show", "text2sql"]) == 0
    assert "text2sql" in capsys.readouterr().out
    assert main(["usages", "resolve", "--family", "F1"]) == 0
    capsys.readouterr()

    assert main(["catalog", "show"]) == 0
    assert "qwen3-vl:8b" in capsys.readouterr().out
    assert main(["hardware", "show"]) == 0
    assert capsys.readouterr().out.strip()

    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # Test-owned ledger, so the "no active ledger" fallback never touches the
    # real ~/.best-engine-ai-helper/usage.db.
    ledger = observe.enable(str(tmp_path / "usage.db"))
    assert main(["activity"]) == 0
    assert "No calls recorded yet." in capsys.readouterr().out
    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")
    assert main(["activity", "--format", "json"]) == 0
    activity_data = json.loads(capsys.readouterr().out)
    assert activity_data["total_calls"] == 1 and activity_data["total_cost_usd"] == 0.0
    ledger.close()


def test_side_effectful_commands_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from best_engine_ai_helper import catalog, hardware, pull, validate_llm, validate_vlm
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
    assert main(["catalog", "update"]) == 0
    assert yaml.safe_load(cache.read_text())[0]["id"] == "qwen3-8b"
    capsys.readouterr()

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
    assert main(["hardware", "update"]) == 0
    assert yaml.safe_load(hw_cache.read_text())[0]["chip"] == "Apple M2 Max"
    capsys.readouterr()

    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: True)
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    monkeypatch.setattr(pull, "write_env", lambda **kw: tmp_path / "env.sh")
    assert main(["pull"]) == 0
    assert "Both gates passed" in capsys.readouterr().out

    monkeypatch.setattr(pull, "ollama_pull", lambda *a, **k: pytest.fail("--vllm must not pull"))
    assert main(["pull", "--vllm"]) == 0
    assert "vllm serve" in capsys.readouterr().out

    monkeypatch.setenv("BEST_LLM_TEXT", "qwen3:8b")
    assert main(["validate"]) == 0
    capsys.readouterr()

    import uvicorn

    gui_calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: gui_calls.update(app=app, **kw))
    assert main(["gui", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert gui_calls["app"] == "best_engine_ai_helper.api:app"
    assert (gui_calls["host"], gui_calls["port"]) == ("0.0.0.0", 9000)


def test_error_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert main(["resolve", "--brief", str(tmp_path / "nope.yaml")]) == 1
    assert main(["usages", "show", "not-a-real-profile"]) == 1
    assert main(["usages", "resolve"]) == 1  # neither name nor --family

    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.delenv("SPREZZATURE_LLM_TEXT", raising=False)
    assert main(["validate"]) == 1
    assert main(["env"]) == 1
