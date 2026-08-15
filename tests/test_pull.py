"""
Tests for best_engine_ai_helper.pull.

The ollama subprocess calls are mocked (Popen / subprocess.run), so nothing is
downloaded or removed. write_env is exercised against a tmp dir.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from best_engine_ai_helper import pull as _pull


class _FakeProc:
    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class _HangingProc:
    """A process whose stdout never yields a line until killed.

    Simulates a stalled `ollama pull` (network stall, hung server): nothing
    to read, nothing to signal completion, until the watchdog kills it.
    """

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.killed = False

    def __iter__(self) -> _HangingProc:
        return self

    def __next__(self) -> str:
        while not self.killed:
            time.sleep(0.01)
        raise StopIteration

    @property
    def stdout(self) -> _HangingProc:
        return self

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


def test_write_env_and_ollama_pull_rm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "a" / "b"  # also proves the directory is created
    env_path = _pull.write_env(
        "qwen3:8b", "gemma3:12b", "ollama", "http://localhost:11434", user_dir=nested
    )
    assert env_path.name == "env.sh" and env_path.exists()
    sh = env_path.read_text()
    assert "BEST_LLM_TEXT=qwen3:8b" in sh and "BEST_LLM_BACKEND=ollama" in sh
    written_config = json.loads((nested / "config.json").read_text())
    assert written_config["BEST_LLM_TEXT"] == "qwen3:8b"
    assert written_config["BEST_LLM_VISION"] == "gemma3:12b"

    # Success: progress is streamed to the sink and True is returned.
    monkeypatch.setattr(
        _pull.subprocess, "Popen", lambda *a, **k: _FakeProc(["10%\n", "done\n"], 0)
    )
    sink = io.StringIO()
    assert _pull.ollama_pull("qwen3:8b", out=sink) is True
    assert "done" in sink.getvalue()

    # Non-zero exit -> False.
    monkeypatch.setattr(_pull.subprocess, "Popen", lambda *a, **k: _FakeProc([], 1))
    assert _pull.ollama_pull("x", out=io.StringIO()) is False

    # Missing ollama binary -> a clear FileNotFoundError.
    def _missing(*a: object, **k: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(_pull.subprocess, "Popen", _missing)
    with pytest.raises(FileNotFoundError):
        _pull.ollama_pull("x", out=io.StringIO())

    monkeypatch.setattr(_pull.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    assert _pull.ollama_rm("x") is True
    monkeypatch.setattr(_pull.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1})())
    assert _pull.ollama_rm("x") is False


def test_ollama_pull_enforces_timeout_on_a_stalled_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `for line in proc.stdout` blocks until a line arrives or the pipe
    # closes -- it has no timeout of its own, so a stalled pull (network
    # stall, hung server) used to hang forever regardless of `timeout`. The
    # watchdog thread must kill the process and raise TimeoutExpired instead.
    proc = _HangingProc()
    monkeypatch.setattr(_pull.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(_pull.subprocess.TimeoutExpired):
        _pull.ollama_pull("x", timeout=0.05, out=io.StringIO())
    assert proc.killed is True
