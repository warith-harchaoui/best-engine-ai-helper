"""
Tests for engine.diagnose — the gap between "resolved" and "runnable".

An engine file is written once; the daemon it names is mutable, and `ollama rm`
leaves no trace in the descriptor. These cover the cases where the two disagree,
and the ones where the honest answer is "cannot tell from here".
"""

from __future__ import annotations

from pathlib import Path

from best_engine_ai_helper import engine


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "llm.engine.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_missing_engine_file_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    report = engine.diagnose(tmp_path)

    assert report["ok"] is False
    assert "No engine file" in report["findings"][0]["message"]


def test_a_model_the_daemon_no_longer_serves_is_named(tmp_path: Path, monkeypatch) -> None:
    """The case this command exists for: `ollama rm` left the file untouched."""
    monkeypatch.setattr("best_engine_ai_helper.pull.installed_tags", lambda *_a, **_k: {"qwen3:8b"})
    directory = _write(
        tmp_path,
        "backend: ollama\nbase_url: http://localhost:11434\n"
        "llm:\n  model: qwen3:8b\nvlm:\n  model: gone:70b\n",
    )

    report = engine.diagnose(directory)

    assert report["ok"] is False
    assert [f["kind"] for f in report["findings"]] == ["vlm"]
    assert "gone:70b" in report["findings"][0]["message"]
    assert "ollama pull gone:70b" in report["findings"][0]["message"]


def test_everything_served_is_a_clean_bill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "best_engine_ai_helper.pull.installed_tags",
        lambda *_a, **_k: {"qwen3:8b", "qwen3-vl:8b"},
    )
    directory = _write(
        tmp_path,
        "backend: ollama\nllm:\n  model: qwen3:8b\nvlm:\n  model: qwen3-vl:8b\n",
    )

    report = engine.diagnose(directory)

    assert report["ok"] is True
    assert report["findings"] == []


def test_a_bare_tag_counts_as_served(tmp_path: Path, monkeypatch) -> None:
    """`gemma3` and `gemma3:latest` are the same model to Ollama."""
    monkeypatch.setattr("best_engine_ai_helper.pull.installed_tags", lambda *_a, **_k: {"gemma3"})
    directory = _write(tmp_path, "backend: ollama\nllm:\n  model: gemma3:latest\n")

    assert engine.diagnose(directory)["ok"] is True


def test_an_unreachable_daemon_is_reported_rather_than_passed(tmp_path: Path, monkeypatch) -> None:
    """An empty tag set means "cannot tell", which must not read as "all fine"."""
    monkeypatch.setattr("best_engine_ai_helper.pull.installed_tags", lambda *_a, **_k: set())
    directory = _write(
        tmp_path, "backend: ollama\nbase_url: http://localhost:11434\nllm:\n  model: qwen3:8b\n"
    )

    report = engine.diagnose(directory)

    assert report["ok"] is False
    assert report["daemon_reachable"] is False
    assert "No Ollama daemon answered" in report["findings"][0]["message"]


def test_a_backend_it_cannot_interrogate_says_so(tmp_path: Path) -> None:
    """vLLM exposes no tag list; claiming a pass would be a guess."""
    directory = _write(tmp_path, "backend: vllm\nllm:\n  model: Qwen/Qwen3-8B\n")

    report = engine.diagnose(directory)

    assert report["ok"] is False
    assert "cannot interrogate" in report["findings"][0]["message"]


def test_an_engine_file_naming_no_model_is_a_finding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("best_engine_ai_helper.pull.installed_tags", lambda *_a, **_k: {"qwen3:8b"})
    directory = _write(tmp_path, "backend: ollama\nllm: null\nvlm: null\n")

    report = engine.diagnose(directory)

    assert report["ok"] is False
    assert "names no model" in report["findings"][0]["message"]
