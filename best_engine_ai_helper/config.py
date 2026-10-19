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
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import json
import os
from typing import Any

import os_helper as osh

# Reuse the single source of truth for the runtime directory and the config
# file name, so this resolver and the writer (``pull.write_env``) can never
# disagree about where the selection lives.
from .pull import _CONFIG_JSON, _USER_DIR

# Conservative defaults used when nothing has been selected yet.
#
# Neither default is the multimodal ``qwen3-vl:8b``: that model returns an empty
# response under Ollama's JSON-schema structured output on /api/generate, which
# silently broke every structured call -- text extraction (intent, edit
# proposals) and vision critique alike.
#
# Text  -> ``qwen3:8b``   (catalog's solid text-only 8B; honours ``format=<schema>``).
# Vision-> ``gemma3:12b``  (multimodal; the only catalog VLM that reliably emits
#          grammar-constrained structured JSON for image prompts). It is heavier
#          (~12B) than qwen3-vl:8b, so a memory-constrained machine should pull a
#          smaller working VLM via the recommend/pull flow, which overrides this.
DEFAULT_TEXT_MODEL = "qwen3:8b"
DEFAULT_VISION_MODEL = "gemma3:12b"

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
    if not osh.file_exists(str(path)):
        osh.debug(f"No persisted selection yet:\n\t{path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Unreadable or malformed: degrade to "no selection" so the caller
        # falls through to its default instead of crashing on a bad file.
        osh.warning(f"Unreadable/malformed config, ignoring:\n\t{path}\n\t{exc}")
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
            osh.debug(f"Model tag from env {key}: {value}")
            return value
    # 2. Otherwise consult the persisted selection from the last `pull`.
    cfg = load_config() if config is None else config
    for key in keys:
        value = cfg.get(key)
        if isinstance(value, str) and value:
            osh.debug(f"Model tag from config {key}: {value}")
            return value
    # 3. Nothing decided anywhere: hand back the safe built-in default.
    osh.debug(f"No selection found, using default: {default}")
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


# ---------------------------------------------------------------------------
# User preferences (written by the GUI, read by anything that ranks)
# ---------------------------------------------------------------------------

#: Where preferences live. Deliberately **not** ``settings.yaml``.
#:
#: That file holds API keys, and a browser form is the last thing that should
#: be able to rewrite it: one naive dump and a user's keys are gone. Secrets
#: and preferences also have different lifetimes, different blast radii, and
#: different people editing them. Keeping them apart means the GUI can save a
#: slider position without ever holding a file that contains a secret.
#:
#: The YAML stays the source of truth either way — the GUI writes this file and
#: then reads it back like any other client, rather than keeping its own state.
_PREFERENCES_YAML = _USER_DIR / "preferences.yaml"

#: Preferences this module will persist, with the default each falls back to.
#: An unknown key sent by a client is ignored rather than stored: a settings
#: file that accumulates whatever anyone posted stops being readable.
_PREFERENCE_DEFAULTS: dict[str, Any] = {
    # 0 = rank purely on price, 1 = purely on quality.
    "quality_vs_cost": 0.7,
    # Fraction of the usable memory pool a model may occupy.
    "headroom": 0.5,
    # Throughput floor in tokens/s, below which a model is not comfortable.
    "min_tps": 15.0,
    # Never suggest a paid model, whatever keys are present.
    "local_only": False,
    # Also weigh what the machine is doing right now, not just its capacity.
    "live_load": False,
}


def load_preferences() -> dict[str, Any]:
    """
    Read the saved preferences, falling back to the defaults for anything unset.

    A missing or unreadable file is not an error: no preferences yet is the
    normal state, and every value has a usable default. Returns a fresh dict,
    so a caller mutating the result cannot corrupt the next read.

    Returns
    -------
    dict
        Every key in :data:`_PREFERENCE_DEFAULTS`, saved value or default.
    """
    import yaml

    prefs = dict(_PREFERENCE_DEFAULTS)
    if not _PREFERENCES_YAML.exists():
        return prefs
    try:
        saved = yaml.safe_load(_PREFERENCES_YAML.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a corrupt file must not break ranking
        osh.warning(f"Could not read preferences, using defaults:\n\t{_PREFERENCES_YAML}\n\t{exc}")
        return prefs
    if isinstance(saved, dict):
        for key in prefs:
            if saved.get(key) is not None:
                prefs[key] = saved[key]
    return prefs


def save_preferences(values: dict[str, Any]) -> dict[str, Any]:
    """
    Merge `values` into the saved preferences and write them back.

    Only known keys are kept, and each is coerced to the type its default
    implies — a form posts strings, and a ``headroom`` of ``"0.4"`` that stayed
    a string would compare wrongly against a float for the rest of its life.
    A value that cannot be coerced is skipped with a warning rather than stored
    broken.

    Parameters
    ----------
    values : dict
        Preferences to set. Unknown keys are ignored.

    Returns
    -------
    dict
        The full set of preferences as now saved.
    """
    import yaml

    prefs = load_preferences()
    for key, raw in (values or {}).items():
        if key not in _PREFERENCE_DEFAULTS:
            osh.debug(f"Ignoring unknown preference {key!r}")
            continue
        default = _PREFERENCE_DEFAULTS[key]
        try:
            prefs[key] = bool(raw) if isinstance(default, bool) else type(default)(raw)
        except (TypeError, ValueError):
            osh.warning(
                f"Preference {key!r} could not be read as {type(default).__name__}: {raw!r}"
            )

    _PREFERENCES_YAML.parent.mkdir(parents=True, exist_ok=True)
    _PREFERENCES_YAML.write_text(
        yaml.safe_dump(prefs, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )
    osh.info(f"Preferences saved:\n\t{_PREFERENCES_YAML}")
    return prefs
