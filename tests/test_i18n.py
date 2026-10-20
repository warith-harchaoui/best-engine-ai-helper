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


def test_every_gui_string_exists_in_every_supported_locale() -> None:
    locales = i18n.meta()["supported_locales"]
    assert set(locales) >= {"fr", "en"}

    missing: dict[str, list[str]] = {}
    for key, values in i18n.gui_strings().items():
        absent = [loc for loc in locales if not str(values.get(loc, "")).strip()]
        if absent:
            missing[key] = absent
    assert not missing, f"GUI strings missing a translation: {missing}"


def test_the_default_and_prompt_locales_are_declared_and_supported() -> None:
    meta = i18n.meta()
    assert meta["default_locale"] in meta["supported_locales"]
    # Prompts are deliberately authored in one language rather than translated
    # (see the file header and CODING.md 21.3.3), so this one is NOT required
    # to be in supported_locales — it only has to be stated.
    assert str(meta["model_prompt_locale"]).strip()


def test_every_key_the_gui_asks_for_exists() -> None:
    """`gui.py` maps template placeholders to locale keys by name.

    A typo there yields a placeholder that renders as itself, which reads as a
    layout bug rather than as a missing translation.

    Read from the two maps by name rather than by scanning the whole file for
    anything dict-shaped: a looser scan would pick up unrelated literals and
    would have to excuse them, and an assertion with an excuse list is one
    step from an assertion that cannot fail.
    """
    from best_engine_ai_helper import gui

    asked = set(gui._HTML_TOKEN_TO_KEY.values()) | set(gui._JS_NAME_TO_KEY.values())
    known = set(i18n.gui_strings())
    assert asked, "neither key map was read; the test is broken, not the code"
    assert asked <= known, f"gui.py asks for keys the locale file lacks: {sorted(asked - known)}"


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


def test_the_gui_actually_renders_in_both_languages() -> None:
    """End to end: the locale switch changes the page, and an unknown one is safe."""
    from best_engine_ai_helper.gui import render_gui

    french, english = render_gui("fr"), render_gui("en")
    assert french != english
    # A locale the file does not cover falls back rather than raising.
    assert render_gui("tlh") == render_gui(i18n.meta()["default_locale"])


def test_no_user_visible_text_is_hard_coded_in_the_template() -> None:
    """Anything between tags must come from the locale file.

    The three exceptions are names, which are not translated: the product, the
    package, and the author.
    """
    source = (_PACKAGE_ROOT / "best_engine_ai_helper" / "gui.py").read_text()
    allowed = {"Best Engine AI Helper", "best-engine-ai-helper", "Warith Harchaoui"}
    literals = {
        text.strip()
        for text in re.findall(r">([^<>{}$]{4,60})<", source)
        if re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’ -]{3,}", text.strip())
    }
    assert literals <= allowed, f"user-visible text bypassing i18n: {literals - allowed}"


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
