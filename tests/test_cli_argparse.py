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
    "doctor",
    "storage",
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
    # The best-cloud-pick section is on by default (no API key/network needed).
    assert main(["report", "--task", "write copy"]) == 0
    assert "Best cloud engine" in capsys.readouterr().out
    assert main(["report", "--task", "write copy", "--no-cloud"]) == 0
    assert "Best cloud engine" not in capsys.readouterr().out
    assert main(["report", "--format", "json"]) == 0
    report_json = json.loads(capsys.readouterr().out)  # must parse as JSON
    assert "cloud" in report_json
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


# ---------------------------------------------------------------------------
# Flag parity between the two CLI twins
# ---------------------------------------------------------------------------

# CODING.md 20.1: the argparse twin mirrors every click command 1:1, "same
# flags, same defaults, same output". The smoke test above pins the command
# NAMES; this pins the flags, which is where drift actually happens — adding an
# option to one surface and forgetting the other is a one-line mistake that
# nothing else catches.
#
# Two differences are deliberate and allowed:
#   detect --json   hidden in click, always True, kept only for compatibility.
#   report --cloud  click declares the pair `--cloud/--no-cloud`, so it also
#                   accepts the redundant positive spelling. Both surfaces
#                   default to cloud ON and both turn it off with --no-cloud,
#                   so the behaviour is identical.
_ALLOWED_CLICK_ONLY = {"detect": {"--json"}, "report": {"--cloud"}}


def _click_options() -> dict[str, set[str]]:
    import click

    from best_engine_ai_helper.cli import main as click_main

    def walk(cmd, prefix=""):
        found: dict[str, set[str]] = {}
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                found.update(walk(sub, f"{prefix}{name} "))
        else:
            # `secondary_opts` holds the negative half of a boolean pair
            # (`--cloud/--no-cloud`); reading only `opts` would report the
            # other surface's `--no-cloud` as an addition it never made.
            opts = {
                o
                for p in cmd.params
                if isinstance(p, click.Option)
                for o in (*p.opts, *p.secondary_opts)
                if o.startswith("--")
            }
            found[prefix.strip()] = opts - {"--help"}
        return found

    return walk(click_main)


def _argparse_options() -> dict[str, set[str]]:
    def walk(parser, prefix=""):
        found: dict[str, set[str]] = {}
        subs = [a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"]
        if subs:
            for name, sub in subs[0].choices.items():
                found.update(walk(sub, f"{prefix}{name} "))
        else:
            opts = {o for a in parser._actions for o in a.option_strings if o.startswith("--")}
            found[prefix.strip()] = opts - {"--help"}
        return found

    return walk(build_parser())


def test_both_surfaces_expose_the_same_commands() -> None:
    assert set(_click_options()) == set(_argparse_options())


def test_both_surfaces_expose_the_same_flags() -> None:
    """An option added to one twin and not the other is the drift this catches."""
    click_opts, argparse_opts = _click_options(), _argparse_options()

    divergent: dict[str, dict[str, list[str]]] = {}
    for command in sorted(set(click_opts) & set(argparse_opts)):
        allowed = _ALLOWED_CLICK_ONLY.get(command, set())
        click_only = click_opts[command] - argparse_opts[command] - allowed
        argparse_only = argparse_opts[command] - click_opts[command]
        if click_only or argparse_only:
            divergent[command] = {
                "click_only": sorted(click_only),
                "argparse_only": sorted(argparse_only),
            }

    assert not divergent, f"the two CLI surfaces have drifted apart: {divergent}"


def test_the_allowlist_still_describes_real_differences() -> None:
    """An allowlist nobody prunes quietly stops being a list of exceptions."""
    click_opts, argparse_opts = _click_options(), _argparse_options()

    for command, allowed in _ALLOWED_CLICK_ONLY.items():
        assert command in click_opts, f"{command} no longer exists"
        stale = allowed - (click_opts[command] - argparse_opts[command])
        assert not stale, f"{command}: no longer click-only, drop from the allowlist: {stale}"
