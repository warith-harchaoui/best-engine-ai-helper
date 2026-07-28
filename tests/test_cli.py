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
# Phase 0b stubs — must exit non-zero and print a message
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["pull"],
    ["validate"],
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
    ["pull"],
    ["validate"],
    ["env"],
    ["catalog", "update"],
    ["hardware", "update"],
])
def test_stub_commands_print_not_yet_implemented(
    runner: CliRunner, args: list[str]
) -> None:
    result = runner.invoke(main, args)
    # The message goes to stderr; CliRunner mixes streams by default
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    assert "not yet implemented" in combined.lower() or "phase 0b" in combined.lower(), (
        f"Stub {args} should say 'not yet implemented', got: {combined!r}"
    )
