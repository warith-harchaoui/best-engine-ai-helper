"""
i18n — this package's view of ``locales/i18n.yaml``, the human-language source of truth.

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
    translated — see ``locales/i18n.yaml``'s header and ``references/CODING.md``
    section 21.3.3 for why prompt wording is not localized like GUI copy.

Parsing, locale resolution and validation are **not** done here: they are
:class:`os_helper.Locales`, the loader shared by the whole suite. This module
used to re-implement them, which is how two packages came to hold two answers
to the same question. What stays is the part os-helper must not know: that a
``prompts`` section exists at all, and what a prompt's fields mean. That
separation is the point — the generic mechanism lives in the foundation, the
domain vocabulary lives where the domain is.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import os_helper as osh

# Inside the package, not beside it. It used to sit next to pyproject.toml,
# one level above — which is not package data, and so never entered the wheel:
# on PyPI up to 1.5.0 a clean `pip install` produced a package whose every GUI
# string and every prompt raised FileNotFoundError. A repo checkout and an
# editable install both have the file where the code looked, which is why
# nothing caught it.
_LOCALES_PATH = Path(__file__).resolve().parent / "locales" / "i18n.yaml"

#: The namespace holding model-facing templates. Named here rather than in
#: os-helper, which has no business knowing that prompts are a thing. Since
#: the GUI moved to gettext, this is the only section this module reads: the
#: prompts are single-language templates keyed on meaning, which is exactly
#: what `Locales` is for and exactly what gettext is not.
PROMPTS_SECTION = "prompts"


@functools.lru_cache(maxsize=1)
def locales() -> osh.Locales:
    """Return the parsed locale file, loaded once.

    Returns
    -------
    os_helper.Locales
        The shared loader bound to this package's ``locales/i18n.yaml``.

    Raises
    ------
    RuntimeError
        If the file is malformed or lacks its ``meta`` section — a broken
        locale file fails loudly at first use rather than surfacing as a
        confusing ``KeyError`` deep inside a caller.

    Examples
    --------
    >>> sorted(locales().supported_locales)
    ['en', 'fr']
    """
    return osh.Locales.from_path(_LOCALES_PATH)


def meta() -> dict[str, Any]:
    """
    Return the ``meta`` block: locale defaults and the model-prompt language.

    Returns
    -------
    dict
        Keys ``default_locale``, ``supported_locales``, ``model_prompt_locale``
        and ``unlocalized_sections``.

    Examples
    --------
    >>> meta()["model_prompt_locale"]
    'en'
    """
    result: dict[str, Any] = locales().document[osh.META_SECTION]
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
    # ``raw``, not ``text``: this section is declared unlocalized, so its
    # sub-keys are roles and no locale could resolve them.
    entry = locales().raw(PROMPTS_SECTION, key)
    return str(entry[field])
