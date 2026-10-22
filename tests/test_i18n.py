"""
Tests for best_engine_ai_helper.i18n and the locale file behind it.

`locales/i18n.yaml` is the single source of truth for every GUI-visible string
and every model-facing prompt template, and the invariants that make that
claim true were held by nothing: this module had no tests at all. They were
checked by hand on 2026-10-20 and all four passed — 89 GUI keys with complete
fr/en parity, every key `gui.py` asks for present, all eight prompt templates
resolving, and no user-visible literal bypassing the file. An invariant that
holds today and is guarded by nothing is the one that breaks on the next
feature, which is the lesson the rest of this release keeps relearning.

The GUI's fallback is what makes the parity test worth having specifically: a
locale the file does not cover falls back to the default rather than erroring,
so a missing English translation would show French in the English UI and raise
nothing at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from best_engine_ai_helper import i18n

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def test_the_locale_file_satisfies_the_shared_validator() -> None:
    """The §21.3.7 check, which the shared loader makes a one-liner.

    `problems()` reports every missing translation, undeclared locale and
    mismatched placeholder at once. It is worth asserting here rather than
    trusting the hand-rolled checks below, because it also covers the faults
    nobody thought to write a test for.

    It only reads clean because `meta.unlocalized_sections` declares
    `prompts`: that section is keyed by role, not by locale, and without the
    declaration its role names read as undeclared locales — 38 findings about
    translations that were never meant to exist.
    """
    assert i18n.locales().problems() == []


def test_the_default_and_prompt_locales_are_declared_and_supported() -> None:
    meta = i18n.meta()
    assert meta["default_locale"] in meta["supported_locales"]
    # Prompts are deliberately authored in one language rather than translated
    # (see the file header and references/CODING.md 21.3.3), so this one is NOT required
    # to be in supported_locales — it only has to be stated.
    assert str(meta["model_prompt_locale"]).strip()


def test_every_prompt_template_the_package_uses_resolves() -> None:
    """Every `i18n.prompt("key", "field")` call site, resolved for real."""
    pattern = re.compile(r'i18n\.prompt\(\s*"([a-z0-9_]+)"\s*,\s*"([a-z0-9_]+)"\s*\)')
    call_sites = [
        (path.name, key, field)
        for path in (_PACKAGE_ROOT / "best_engine_ai_helper").rglob("*.py")
        for key, field in pattern.findall(path.read_text())
    ]
    assert call_sites, "no i18n.prompt call sites found; the scan is broken, not the code"
    for name, key, field in call_sites:
        assert i18n.prompt(key, field).strip(), f"{name}: empty prompt for {key}.{field}"


def test_an_unknown_prompt_key_fails_loudly() -> None:
    """A missing prompt must not degrade to an empty string sent to a model."""
    with pytest.raises(KeyError):
        i18n.prompt("no_such_prompt_key_exists", "user")


def test_the_page_formats_numbers_in_its_own_language() -> None:
    """Labels were localised; the numbers beside them were not.

    `toFixed` and a bare ``$`` prefix write English conventions whatever the
    page language is, so the French GUI read ``47.2 GB`` and ``$0.0020`` where
    French writes ``47,2`` and puts the currency after the amount. `Intl` does
    this with no dependency — the fix is to give the page the locale it
    resolved to and let the browser format.

    Asserted as "no raw formatter survives", because that is the property that
    rots: a new cell written with `toFixed` would be wrong in exactly one of
    the two languages, which is the kind of defect nobody reports.
    """
    from best_engine_ai_helper.gui import render_gui

    for lang in ("fr", "en"):
        page = render_gui(lang)
        assert f'const LOCALE = "{lang}"' in page
        assert ".toFixed(" not in page, f"{lang}: a number is formatted outside Intl"
        assert "Math.round(" not in page, f"{lang}: a number is rounded outside Intl"

    # An unknown locale formats in the language it actually fell back to.
    default = i18n.meta()["default_locale"]
    assert f'const LOCALE = "{default}"' in render_gui("tlh")


def test_the_shared_loader_is_what_resolves_the_prompts() -> None:
    """One prompt loader in the suite, not one per member.

    This module kept a three-line accessor over `Locales.raw` until 1.8.1.
    `os_helper.Prompts` serves this package's single-language shape
    (`key -> role -> text`) as readily as a multi-language one, so delegating
    cost no reshaping of the file and gave up none of the deliberate choice
    to author one model-facing language.
    """
    import os_helper as osh

    assert isinstance(i18n.prompts(), osh.Prompts)


def test_the_prompt_section_is_sound() -> None:
    """The whole-section check the shared loader makes a one-liner."""
    faults = i18n.prompts().problems()
    assert faults == [], "prompt faults:\n  " + "\n  ".join(faults)
