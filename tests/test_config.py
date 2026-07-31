"""
Tests for best_engine_ai_helper.config — the cheap model-tag resolvers.

The resolvers must be pure reads with a fixed precedence (env override ->
persisted config.json -> built-in default), never probe hardware, and never
raise. These tests pin that contract and its determinism in CI, where neither a
config file nor Ollama exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from best_engine_ai_helper import config as _config

# Env vars the resolver consults; cleared before each test so a developer's
# shell (which may export BEST_LLM_* for real use) cannot leak into assertions.
_ENV_VARS = (
    "BEST_LLM_TEXT",
    "BEST_LLM_VISION",
    "SPREZZATURE_LLM_TEXT",
    "SPREZZATURE_LLM_VISION",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a known state: no model env vars set."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _point_config_at(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect the resolver's config-file lookup into a temp dir.

    ``load_config`` builds its path from ``_USER_DIR / _CONFIG_JSON``; patching
    ``_USER_DIR`` keeps the test off the real ``~/.best-engine-ai-helper``.
    """
    monkeypatch.setattr(_config, "_USER_DIR", tmp_path)
    return tmp_path / _config._CONFIG_JSON


class TestDefaults:
    """With nothing configured, the built-in defaults are returned."""

    def test_text_and_vision_fall_back_to_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # No env vars (autouse fixture) and no config file on disk.
        _point_config_at(monkeypatch, tmp_path)
        assert _config.text_model() == _config.DEFAULT_TEXT_MODEL
        assert _config.vision_model() == _config.DEFAULT_VISION_MODEL

    def test_missing_config_file_is_empty_not_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _point_config_at(monkeypatch, tmp_path)
        assert _config.load_config() == {}

    def test_corrupt_config_file_degrades_to_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # A truncated / non-JSON file must never crash a downstream caller.
        cfg_path = _point_config_at(monkeypatch, tmp_path)
        cfg_path.write_text("{ not valid json", encoding="utf-8")
        assert _config.load_config() == {}
        assert _config.text_model() == _config.DEFAULT_TEXT_MODEL


class TestPersistedConfig:
    """A config.json written by `pull` drives the resolution when env is unset."""

    def test_persisted_values_win_over_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_path = _point_config_at(monkeypatch, tmp_path)
        cfg_path.write_text(
            json.dumps({"BEST_LLM_TEXT": "qwen3:14b", "BEST_LLM_VISION": "gemma3:12b"}),
            encoding="utf-8",
        )
        assert _config.text_model() == "qwen3:14b"
        assert _config.vision_model() == "gemma3:12b"

    def test_resolved_models_returns_both(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_path = _point_config_at(monkeypatch, tmp_path)
        cfg_path.write_text(
            json.dumps({"BEST_LLM_TEXT": "qwen3:8b", "BEST_LLM_VISION": "qwen3-vl:14b"}),
            encoding="utf-8",
        )
        assert _config.resolved_models() == {"text": "qwen3:8b", "vision": "qwen3-vl:14b"}


class TestEnvOverride:
    """An explicit env var beats both the config file and the default."""

    def test_env_beats_config_and_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg_path = _point_config_at(monkeypatch, tmp_path)
        cfg_path.write_text(json.dumps({"BEST_LLM_TEXT": "qwen3:14b"}), encoding="utf-8")
        monkeypatch.setenv("BEST_LLM_TEXT", "override:latest")
        assert _config.text_model() == "override:latest"

    def test_legacy_sprezzature_alias_is_honoured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _point_config_at(monkeypatch, tmp_path)
        monkeypatch.setenv("SPREZZATURE_LLM_VISION", "legacy:vlm")
        assert _config.vision_model() == "legacy:vlm"
