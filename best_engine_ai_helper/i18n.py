"""
i18n — shared loader for ``locales/i18n.yaml``, the human-language source of truth.

Every GUI-visible string and every model-facing prompt template used by this
package is authored once, in ``locales/i18n.yaml`` (package root), under two
top-level namespaces:

``gui``
    UI strings keyed by a stable semantic name, each with a value per
    supported locale (``fr`` / ``en``). Consumed by :mod:`best_engine_ai_helper.gui`.
``prompts``
    Model-facing prompt templates (system / user text sent to the local LLM or
    VLM by :mod:`best_engine_ai_helper.ralph`, :mod:`best_engine_ai_helper.validate_llm`,
    and :mod:`best_engine_ai_helper.validate_vlm`), authored in a single language
    declared at ``meta.model_prompt_locale`` (English here) rather than
    translated — see ``locales/i18n.yaml``'s header and CODING.md section 21.3.3
    for why prompt wording is not localized like GUI copy.

This module owns parsing and caching the file; it does not know what any
individual key means to its caller.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

# Root of the installed package; locales/i18n.yaml sits next to pyproject.toml,
# same convention as models.yaml / hardware.yaml / usages.yaml (see catalog.py).
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_LOCALES_PATH = _PACKAGE_ROOT / "locales" / "i18n.yaml"

_REQUIRED_SECTIONS = ("meta", "gui", "prompts")


@functools.lru_cache(maxsize=1)
def _document() -> dict[str, Any]:
    """Parse and cache ``locales/i18n.yaml`` in full.

    Returns
    -------
    dict
        The parsed document (``meta``, ``gui``, ``prompts`` top-level keys).

    Raises
    ------
    RuntimeError
        If a required top-level section is missing, so a malformed locale
        file fails loudly at first use rather than surfacing as a confusing
        ``KeyError`` deep inside a caller.
    """
    raw: dict[str, Any] = yaml.safe_load(_LOCALES_PATH.read_text(encoding="utf-8")) or {}
    missing = [section for section in _REQUIRED_SECTIONS if section not in raw]
    if missing:
        raise RuntimeError(f"{_LOCALES_PATH} is missing required section(s): {missing}")
    return raw


def meta() -> dict[str, Any]:
    """
    Return the ``meta`` block: locale defaults and the model-prompt language.

    Returns
    -------
    dict
        Keys ``default_locale``, ``supported_locales``, ``model_prompt_locale``.

    Examples
    --------
    >>> sorted(meta().keys())
    ['default_locale', 'model_prompt_locale', 'supported_locales']
    """
    result: dict[str, Any] = _document()["meta"]
    return result


def gui_strings() -> dict[str, dict[str, str]]:
    """
    Return the ``gui`` namespace: semantic key -> ``{locale: text}``.

    Returns
    -------
    dict
        One entry per GUI string; each value maps a locale code to its text.

    Examples
    --------
    >>> "hero_title" in gui_strings()
    True
    """
    result: dict[str, dict[str, str]] = _document()["gui"]
    return result


def prompt(key: str, field: str = "user") -> str:
    """
    Return one field of a model-facing prompt template.

    Parameters
    ----------
    key : str
        Top-level key under ``prompts:`` in ``locales/i18n.yaml``
        (e.g. ``"eyeball_critique"``).
    field : str
        Which sub-field to return: ``"system"``, ``"user"``, or ``"text"``
        for a fragment with no role split. Defaults to ``"user"``.

    Returns
    -------
    str
        The raw template text, with any ``{placeholder}`` markers intact for
        the caller to fill via ``str.format``.

    Raises
    ------
    KeyError
        If ``key`` or ``field`` is not present — a missing prompt must fail
        loudly rather than silently send an empty string to a model.

    Examples
    --------
    >>> prompt("writing_charter_excerpt", "text").startswith("Rule 5")
    True
    """
    entry = _document()["prompts"][key]
    return str(entry[field])
