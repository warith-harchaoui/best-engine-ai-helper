"""
config — cheap, deterministic resolution of the chosen model tags.

This module answers a single question for downstream consumers (md2star and the
rest of the AI Helpers suite): *"which local model tag should I use right now?"*
It never probes hardware and never pulls anything — that expensive, machine-
dependent work belongs to the ``recommend`` / ``pull`` flow. Here we only read,
in a fixed precedence, what has already been decided:

    1. an explicit environment override (``BEST_LLM_TEXT`` / ``BEST_LLM_VISION``,
       with the legacy ``SPREZZATURE_LLM_*`` spellings accepted as aliases),
    2. the persisted selection written by ``best-engine-ai-helper pull`` to
       ``~/.best-engine-ai-helper/config.json`` (see :func:`pull.write_env`),
    3. a conservative built-in default (:data:`DEFAULT_TEXT_MODEL` /
       :data:`DEFAULT_VISION_MODEL`) so the call *always* returns a usable tag,
       even on a machine that has never run detection.

Because the resolvers are pure reads with a guaranteed fallback, they are safe
to call at import time, in CI (where no config file and no Ollama exist), and
inside unit tests — the result is deterministic and never raises.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import json
import os
from typing import Any

# Reuse the single source of truth for the runtime directory and the config
# file name, so this resolver and the writer (``pull.write_env``) can never
# disagree about where the selection lives.
from .pull import _CONFIG_JSON, _USER_DIR

# Conservative defaults used when nothing has been selected yet. ``qwen3-vl:8b``
# is multimodal (vision + text), so the same tag safely backs both the text and
# vision fallbacks: one model to pull, and it answers either kind of prompt.
DEFAULT_TEXT_MODEL = "qwen3-vl:8b"
DEFAULT_VISION_MODEL = "qwen3-vl:8b"

# Config keys, canonical spelling first. The canonical names match what
# ``pull.write_env`` persists; the ``SPREZZATURE_*`` names are the legacy
# spelling the transport layer (``llm.py``) shipped with — accepted so a value
# set either way is honoured everywhere.
_TEXT_KEYS = ("BEST_LLM_TEXT", "SPREZZATURE_LLM_TEXT")
_VISION_KEYS = ("BEST_LLM_VISION", "SPREZZATURE_LLM_VISION")


def load_config() -> dict[str, Any]:
    """Return the persisted selection dict, or an empty dict if absent/unreadable.

    Reads ``~/.best-engine-ai-helper/config.json`` (written by
    :func:`pull.write_env`). A missing file is the normal "never ran detection"
    case, so it maps to ``{}`` rather than an error; a corrupt file is treated
    the same way so a bad write can never break a downstream caller.

    Returns
    -------
    dict
        The parsed config, or ``{}`` when the file does not exist or cannot be
        parsed as a JSON object.
    """
    path = _USER_DIR / _CONFIG_JSON
    # Missing file == "no selection yet": the overwhelmingly common path in CI
    # and on a fresh machine. Return empty rather than raising.
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Unreadable or malformed: degrade to "no selection" so the caller
        # falls through to its default instead of crashing on a bad file.
        return {}
    # Guard the shape: only a JSON object carries the string values we expect.
    return data if isinstance(data, dict) else {}


def _resolve(keys: tuple[str, ...], default: str, config: dict[str, Any] | None) -> str:
    """Resolve one model tag by the fixed env -> config -> default precedence.

    Parameters
    ----------
    keys : tuple of str
        Candidate keys, most-canonical first, tried in order against both the
        process environment and the persisted config.
    default : str
        The built-in fallback returned when no source supplies a value.
    config : dict or None
        A pre-loaded config to consult (avoids re-reading the file when several
        tags are resolved together). ``None`` triggers a lazy :func:`load_config`.

    Returns
    -------
    str
        The resolved, non-empty model tag.
    """
    # 1. Environment override wins — it is the most explicit, per-process signal.
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    # 2. Otherwise consult the persisted selection from the last `pull`.
    cfg = load_config() if config is None else config
    for key in keys:
        value = cfg.get(key)
        if isinstance(value, str) and value:
            return value
    # 3. Nothing decided anywhere: hand back the safe built-in default.
    return default


def text_model() -> str:
    """Return the model tag to use for text-only prompts (lint, summaries, …).

    Precedence: ``BEST_LLM_TEXT`` env (or legacy ``SPREZZATURE_LLM_TEXT``) ->
    persisted ``config.json`` -> :data:`DEFAULT_TEXT_MODEL`. Never probes
    hardware, never raises.
    """
    return _resolve(_TEXT_KEYS, DEFAULT_TEXT_MODEL, None)


def vision_model() -> str:
    """Return the model tag to use for prompts that include images (alt-text, OCR).

    Precedence: ``BEST_LLM_VISION`` env (or legacy ``SPREZZATURE_LLM_VISION``) ->
    persisted ``config.json`` -> :data:`DEFAULT_VISION_MODEL`. Never probes
    hardware, never raises.
    """
    return _resolve(_VISION_KEYS, DEFAULT_VISION_MODEL, None)


def resolved_models() -> dict[str, str]:
    """Return both resolved tags in one call, reading the config file at most once.

    Returns
    -------
    dict
        ``{"text": <tag>, "vision": <tag>}`` — the same values
        :func:`text_model` and :func:`vision_model` would return.
    """
    # Load once and share, so resolving both tags does not stat/parse twice.
    cfg = load_config()
    return {
        "text": _resolve(_TEXT_KEYS, DEFAULT_TEXT_MODEL, cfg),
        "vision": _resolve(_VISION_KEYS, DEFAULT_VISION_MODEL, cfg),
    }
