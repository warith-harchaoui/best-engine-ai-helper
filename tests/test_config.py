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


# ---------------------------------------------------------------------------
# The other half of what `pull` persists
# ---------------------------------------------------------------------------
#
# `pull.write_env` writes four values into `env.sh` and `config.json`, the
# README tells the user to source that file, and the transport read only two of
# them. `BEST_LLM_BACKEND` and `BEST_LLM_BASE_URL` were written, documented,
# sourced — and resolved by nobody, because `llm.py` consulted the legacy
# `SPREZZATURE_*` spelling alone. Proven before the fix: `pull` writing
# `vllm` at `http://gpu-box:8000` left the transport on `ollama` at
# `http://localhost:11434`.
#
# Half a block working is what made this hard to notice: the model tags were
# honoured, so the file looked like it was being read.

_CONNECTION_VARS = (
    "BEST_LLM_BACKEND",
    "BEST_LLM_BASE_URL",
    "SPREZZATURE_LLM_BACKEND",
    "SPREZZATURE_LLM_BASE_URL",
)


def test_backend_and_base_url_follow_the_same_precedence_as_the_model_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for var in _CONNECTION_VARS:
        monkeypatch.delenv(var, raising=False)
    cfg_path = _point_config_at(monkeypatch, tmp_path)

    # 1. Nothing anywhere: the built-in defaults.
    assert _config.backend() == _config.DEFAULT_BACKEND
    assert _config.base_url() == _config.DEFAULT_BASE_URL

    # 2. The persisted selection from the last `pull`, with no env sourced.
    cfg_path.write_text(
        json.dumps({"BEST_LLM_BACKEND": "vllm", "BEST_LLM_BASE_URL": "http://gpu-box:8000"})
    )
    assert _config.backend() == "vllm"
    assert _config.base_url() == "http://gpu-box:8000"

    # 3. The env wins over the persisted value, as it does for the model tags.
    monkeypatch.setenv("BEST_LLM_BACKEND", "openai")
    monkeypatch.setenv("BEST_LLM_BASE_URL", "https://api.example.com/")
    assert _config.backend() == "openai"
    # A trailing slash is removed, so callers can join paths without doubling it.
    assert _config.base_url() == "https://api.example.com"

    # 4. The legacy spelling still resolves, and the canonical one outranks it.
    monkeypatch.delenv("BEST_LLM_BACKEND")
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "anthropic")
    assert _config.backend() == "anthropic"
    monkeypatch.setenv("BEST_LLM_BACKEND", "vllm")
    assert _config.backend() == "vllm"

    # 5. Lower-cased: the transport dispatches on an exact string and env.sh
    #    is hand-editable.
    monkeypatch.setenv("BEST_LLM_BACKEND", "VLLM")
    assert _config.backend() == "vllm"


def test_the_transport_reads_what_pull_actually_wrote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end: `pull` writes the file, the user sources it, `llm` obeys.

    Asserted through `llm._backend` / `llm._base_url` rather than `config`,
    because the defect lived in the transport's own accessors — `config` was
    never the part that was wrong.
    """
    from best_engine_ai_helper import llm, pull

    for var in _CONNECTION_VARS:
        monkeypatch.delenv(var, raising=False)
    _point_config_at(monkeypatch, tmp_path)

    env_sh = pull.write_env(
        "qwen3:8b", "qwen3-vl:8b", "vllm", "http://gpu-box:8000", user_dir=tmp_path
    )
    written = Path(env_sh).read_text()
    assert "export BEST_LLM_BACKEND=vllm" in written
    assert "export BEST_LLM_BASE_URL=http://gpu-box:8000" in written

    # Sourcing env.sh is what the README tells the reader to do.
    for line in written.splitlines():
        if line.startswith("export "):
            name, _, value = line[len("export ") :].partition("=")
            monkeypatch.setenv(name, value)

    assert llm._backend() == "vllm"
    assert llm._base_url() == "http://gpu-box:8000"
