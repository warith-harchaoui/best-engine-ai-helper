"""
Tests for best_engine_ai_helper.pull.

The ollama subprocess calls are mocked (Popen / subprocess.run), so nothing is
downloaded or removed. write_env is exercised against a tmp dir.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from best_engine_ai_helper import pull as _pull


class _FakeProc:
    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


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
