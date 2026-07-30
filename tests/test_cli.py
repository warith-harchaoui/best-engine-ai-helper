"""
Tests for best_engine_ai_helper.cli.

Uses Click's CliRunner so no subprocess spawning is needed and the working
directory is irrelevant. Phase 0b stubs are verified to exit with a non-zero
code and print a useful message to stderr.
"""

from __future__ import annotations

import json

import pytest
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
# Remaining stubs — must exit non-zero and print a message.
# `pull` and `validate` are implemented (Phase 0b) and drive a live model
# loop; they are covered by their own graceful-degradation tests below, not
# here, so this list must never invoke them.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["env"],
    ["catalog", "update"],
    ["hardware", "update"],
])
def test_stub_commands_exit_nonzero(runner: CliRunner, args: list[str]) -> None:
    result = runner.invoke(main, args)
    assert result.exit_code != 0, (
        f"Stub command {args} should exit non-zero; got {result.exit_code}"
    )


@pytest.mark.parametrize("args", [
    ["catalog", "update"],
    ["hardware", "update"],
])
def test_stub_commands_print_not_yet_implemented(
    runner: CliRunner, args: list[str]
) -> None:
    """catalog update and hardware update remain Phase 0b stubs."""
    result = runner.invoke(main, args)
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    assert "not yet implemented" in combined.lower() or "phase 0b" in combined.lower(), (
        f"Stub {args} should say 'not yet implemented', got: {combined!r}"
    )


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
