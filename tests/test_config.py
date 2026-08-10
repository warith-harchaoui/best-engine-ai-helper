"""
Tests for best_engine_ai_helper.config — the cheap model-tag resolvers.

The resolvers must be pure reads with a fixed precedence (env override ->
persisted config.json -> built-in default), never probe hardware, and never
raise. This test walks the whole precedence chain in one pass, pinning that
contract and its determinism in CI, where neither a config file nor Ollama
exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from best_engine_ai_helper import config as _config

# Env vars the resolver consults; cleared before the test so a developer's
# shell (which may export BEST_LLM_* for real use) cannot leak into assertions.
_ENV_VARS = (
    "BEST_LLM_TEXT",
    "BEST_LLM_VISION",
    "SPREZZATURE_LLM_TEXT",
    "SPREZZATURE_LLM_VISION",
)


def _point_config_at(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect the resolver's config-file lookup into a temp dir.

    ``load_config`` builds its path from ``_USER_DIR / _CONFIG_JSON``; patching
    ``_USER_DIR`` keeps the test off the real ``~/.best-engine-ai-helper``.
    """
    monkeypatch.setattr(_config, "_USER_DIR", tmp_path)
    return tmp_path / _config._CONFIG_JSON


def test_text_and_vision_model_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    # With nothing configured, the built-in defaults are returned.
    cfg_path = _point_config_at(monkeypatch, tmp_path)
    assert _config.text_model() == _config.DEFAULT_TEXT_MODEL
    assert _config.vision_model() == _config.DEFAULT_VISION_MODEL
    assert _config.load_config() == {}

    # A truncated / non-JSON file must never crash a downstream caller.
    cfg_path.write_text("{ not valid json", encoding="utf-8")
    assert _config.load_config() == {}
    assert _config.text_model() == _config.DEFAULT_TEXT_MODEL

    # A config.json written by `pull` drives resolution when env is unset.
    cfg_path.write_text(
        json.dumps({"BEST_LLM_TEXT": "qwen3:14b", "BEST_LLM_VISION": "gemma3:12b"}),
        encoding="utf-8",
    )
    assert _config.text_model() == "qwen3:14b"
    assert _config.vision_model() == "gemma3:12b"

    cfg_path.write_text(
        json.dumps({"BEST_LLM_TEXT": "qwen3:8b", "BEST_LLM_VISION": "qwen3-vl:14b"}),
        encoding="utf-8",
    )
    assert _config.resolved_models() == {"text": "qwen3:8b", "vision": "qwen3-vl:14b"}

    # An explicit env var beats both the config file and the default.
    cfg_path.write_text(json.dumps({"BEST_LLM_TEXT": "qwen3:14b"}), encoding="utf-8")
    monkeypatch.setenv("BEST_LLM_TEXT", "override:latest")
    assert _config.text_model() == "override:latest"

    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.setenv("SPREZZATURE_LLM_VISION", "legacy:vlm")
    assert _config.vision_model() == "legacy:vlm"
