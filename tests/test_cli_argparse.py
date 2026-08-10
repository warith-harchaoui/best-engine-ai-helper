"""
Tests for best_engine_ai_helper.cli_argparse.

The argparse twin delegates every handler to the same library functions
`test_cli.py` already exercises through the click surface, so this module
does NOT re-verify business logic (which candidate is comfortable, which
gate fails, etc. — see test_cli.py). It verifies the argparse-specific
seam instead: the parser builds, every subcommand's --help works, flags map
to the right handler with the right defaults, and one representative
happy-path per command proves the plumbing (parsing -> handler -> library
call -> stdout) actually connects end to end.
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


def test_parser_builds_and_exposes_every_command() -> None:
    """Building the parser never fails and lists the same commands as cli.py."""
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    )
    assert EXPECTED_COMMANDS == set(subparsers_action.choices.keys())


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`--help` at the root exits 0 and prints usage."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "best-engine-ai-helper" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("command", sorted(EXPECTED_COMMANDS))
def test_group_help_exits_zero(command: str) -> None:
    """Every top-level command's `--help` exits 0 (argparse convention)."""
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0


def test_detect_emits_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["detect"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"platform", "chip_vendor", "memory", "hardware"} <= data.keys()
    assert data["memory"]["ram_gb"] > 0


def test_recommend_kinds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["recommend", "--kind", "llm"]) == 0
    assert "LLM" in capsys.readouterr().out
    assert main(["recommend", "--kind", "vlm", "--headroom", "0.5"]) == 0
    assert "VLM" in capsys.readouterr().out
    assert main(["recommend", "--kind", "llm", "--live"]) == 0
    assert "LLM" in capsys.readouterr().out


def test_report_live_includes_server_load_section(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", "--task", "write copy", "--live"]) == 0
    assert "Server load (live, at recommendation time)" in capsys.readouterr().out


def test_activity_empty_and_populated(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # Test-owned ledger enabled up front; see test_cli.py's equivalent test
    # for why (avoids the "no active ledger" fallback touching the real path).
    ledger = observe.enable(str(tmp_path / "usage.db"))

    assert main(["activity"]) == 0
    assert "No calls recorded yet." in capsys.readouterr().out

    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")

    assert main(["activity"]) == 0
    out = capsys.readouterr().out
    assert "Total calls: 1" in out and "qwen3:8b" in out

    assert main(["activity", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total_calls"] == 1 and data["total_cost_usd"] == 0.0
    ledger.close()


def test_report_markdown_json_and_write_files(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["report", "--task", "write python code"]) == 0
    assert "#" in capsys.readouterr().out  # markdown heading

    assert main(["report", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)  # must parse as JSON

    stem = str(tmp_path / "r")
    assert main(["report", "--out", stem]) == 0
    capsys.readouterr()
    assert Path(f"{stem}.md").exists() and Path(f"{stem}.json").exists()


def test_resolve_writes_engine_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    brief = tmp_path / "llm.brief.yaml"
    brief.write_text(
        "mode: local\nkind: llm\nheadroom: 0.5\nmin_tps: 15\n"
        "structured_output: false\ntask: generalist chat\n"
    )
    out = tmp_path / "llm.engine.yaml"
    assert main(["resolve", "--brief", str(brief), "--out", str(out)]) == 0
    assert out.is_file()
    assert "Wrote" in capsys.readouterr().out


def test_resolve_missing_brief_errors(tmp_path: Path) -> None:
    assert main(["resolve", "--brief", str(tmp_path / "nope.yaml")]) == 1


def test_usages_list_show_and_resolve(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["usages", "list"]) == 0
    assert "Profiles" in capsys.readouterr().out

    assert main(["usages", "show", "text2sql"]) == 0
    assert "text2sql" in capsys.readouterr().out

    assert main(["usages", "show", "not-a-real-profile"]) == 1
    capsys.readouterr()

    assert main(["usages", "resolve", "--family", "F1"]) == 0
    capsys.readouterr()

    assert main(["usages", "resolve"]) == 1  # neither name nor --family


def test_catalog_show(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalog", "show"]) == 0
    assert "qwen3-vl:8b" in capsys.readouterr().out


def test_hardware_show(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["hardware", "show"]) == 0
    assert capsys.readouterr().out.strip()


def test_catalog_update_writes_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from best_engine_ai_helper import catalog
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


def test_hardware_update_records_this_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import hardware

    cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", cache)
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
    assert yaml.safe_load(cache.read_text())[0]["chip"] == "Apple M2 Max"


def test_pull_writes_env_when_both_gates_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from best_engine_ai_helper import pull, validate_llm, validate_vlm

    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: True)
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    monkeypatch.setattr(pull, "write_env", lambda **kw: tmp_path / "env.sh")

    assert main(["pull"]) == 0
    assert "Both gates passed" in capsys.readouterr().out


def test_pull_vllm_prints_serve_command_without_downloading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from best_engine_ai_helper import pull

    monkeypatch.setattr(pull, "ollama_pull", lambda *a, **k: pytest.fail("--vllm must not pull"))
    assert main(["pull", "--vllm"]) == 0
    assert "vllm serve" in capsys.readouterr().out


def test_validate_and_env_require_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.delenv("SPREZZATURE_LLM_TEXT", raising=False)
    assert main(["validate"]) == 1
    assert main(["env"]) == 1


def test_gui_requires_api_extra_when_uvicorn_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import builtins

    real_import = builtins.__import__

    def _no_uvicorn(name: str, *a: object, **k: object) -> object:
        if name == "uvicorn":
            raise ImportError("no uvicorn")
        return real_import(name, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _no_uvicorn)
    assert main(["gui"]) == 1
    assert "[api] extra" in capsys.readouterr().err
