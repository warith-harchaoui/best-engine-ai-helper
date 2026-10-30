"""Tests for the figures under ``assets/diagrams/``.

Every one of these is a picture the documentation embeds, so two readers have
to be able to use it: the one who sees it, and the one who does not. The second
reader was being forgotten in two different ways, and neither was visible from
the Markdown:

* ``memory-budget.svg`` is the only *generated* figure here, and the generator
  emitted a ``<desc>`` with no ``<title>`` and nothing pointing
  ``aria-labelledby`` at either — so it had no accessible name at all, while
  every hand-authored figure beside it did.
* Three figures were English-only and embedded in the **French** documents.
  ``LISEZMOI.md`` carried a carefully translated caption above a picture whose
  every label read ``1 · PREDICT`` / ``Reserved, not yours`` / ``EVERY ARENA
  SOURCE``. The EN/FR parity checker passes that by construction: both
  documents link the same URL, which is exactly what it calls agreement. The
  check verifies that both languages point at the same thing; it cannot verify
  that the thing is in both languages. These tests close that gap.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parent.parent
_DIAGRAMS = _REPO / "assets" / "diagrams"


def _load_parity() -> ModuleType:
    """Import the parity checker, for its declared EN→FR name map."""
    spec = importlib.util.spec_from_file_location(
        "check_doc_parity", _REPO / "scripts" / "check_doc_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parity = _load_parity()


def _svgs() -> list[Path]:
    return sorted(_DIAGRAMS.glob("*.svg"))


@pytest.mark.parametrize("svg", _svgs(), ids=lambda p: p.stem)
def test_every_figure_has_an_accessible_name_and_description(svg: Path) -> None:
    """A picture nobody can name is a picture one reader simply does not get."""
    text = svg.read_text(encoding="utf-8")
    assert 'role="img"' in text, f"{svg.name}: no role=img"
    assert "aria-labelledby=" in text, f"{svg.name}: nothing points at its title/desc"
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.DOTALL)
    desc = re.search(r"<desc[^>]*>(.*?)</desc>", text, re.DOTALL)
    assert title and title.group(1).strip(), f"{svg.name}: no <title>"
    assert desc and desc.group(1).strip(), f"{svg.name}: no <desc>"
    # A description that merely repeats the title tells a screen-reader user
    # nothing they did not already have.
    assert len(desc.group(1).strip()) > 2 * len(title.group(1).strip()), (
        f"{svg.name}: the <desc> is barely longer than the <title>; it should "
        "say what the picture shows, not repeat its name"
    )


@pytest.mark.parametrize("svg", _svgs(), ids=lambda p: p.stem)
def test_every_figure_ships_a_png(svg: Path) -> None:
    """The Markdown embeds the PNG; an SVG with no twin is a broken image."""
    png = svg.with_suffix(".png")
    assert png.is_file(), f"{svg.name}: no {png.name} beside it"
    assert png.stat().st_size > 1000, f"{png.name} is suspiciously small"


def test_no_root_document_still_draws_with_mermaid() -> None:
    """Every diagram in this repository is hand-authored, and that is a rule.

    A Mermaid fence has no mechanism for a text alternative at all: the ten
    diagrams that used to live in the two READMEs were, between them, invisible
    to any reader who could not see them. Hand-authored SVG carries a
    ``<title>`` and a ``<desc>``, lays out where the geometry actually allows
    rather than where a solver puts it, and is reviewable as text in a diff.

    This is the preference made mechanical, which is the only form a preference
    survives in.
    """
    offenders = [
        name
        for name in sorted(p.name for p in _REPO.glob("*.md"))
        if "```mermaid" in (_REPO / name).read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "Mermaid fences found in " + ", ".join(offenders) + ". Draw it by hand "
        "under assets/diagrams/ instead: a Mermaid block cannot carry a <desc>, "
        "so it is a picture one reader simply does not get."
    )


def test_every_declared_twin_name_points_at_a_real_pair() -> None:
    """`MIRROR` is a promise about assets, and a promise can outlive its asset.

    The map is what lets a French document point at `paysage.png` and still
    count as agreeing with an English one pointing at `landscape.png`, so every
    entry reads as a statement that both halves exist. One did not:
    `parity-skeleton` / `parite-squelette` named a figure that was planned and
    never drawn, and sat in the map for two iterations describing nothing.

    Nothing consumes a stale entry, which is exactly why nothing noticed it.
    An entry here is documentation for the next person reading the map, and
    documentation that names a file nobody ships is the cheapest kind of lie.
    """
    missing = []
    for english, french in parity.MIRROR.items():
        if english.endswith(".md"):
            for name in (english, french):
                if not (_REPO / name).is_file():
                    missing.append(f"MIRROR names {name}, which is not a root document")
            continue
        for stem in (english, french):
            if not list((_REPO / "assets").rglob(f"{stem}.svg")):
                missing.append(f"MIRROR names {stem}, and no {stem}.svg exists under assets/")
    assert not missing, "declared twins with nothing behind them:\n" + "\n".join(missing)


def test_every_figure_a_french_document_embeds_is_french() -> None:
    """The gap the parity checker cannot see, stated as a rule.

    Both documents linking the same URL is what `check_doc_parity` calls
    agreement, so an English-only picture under a translated caption passes it
    silently. Here the rule is the other one: a figure referenced from a French
    document must be a figure whose own name is French — which, given
    `MIRROR`, means it must be a declared twin.
    """
    offenders = []
    for doc in ("LISEZMOI.md", "EXEMPLES.md", "PAYSAGE.md"):
        text = (_REPO / doc).read_text(encoding="utf-8")
        for stem in re.findall(r"assets/diagrams/([\w-]+)\.png", text):
            if stem in parity.MIRROR:  # an English stem, named in a French file
                offenders.append(f"{doc} embeds the English figure {stem}.png")
    assert not offenders, "English figures in French documents:\n" + "\n".join(offenders)


# Two further invariants were proposed for twinned figures and are deliberately
# NOT here, because measuring them against the figures that already ship showed
# both to be false:
#
#   "twins share a viewBox" -- `comment-ca-marche.svg` is 1474 units wide
#   against `how-it-works.svg`'s 1357, and that is correct rather than drift:
#   French labels run longer, and widening the canvas is the right remedy for a
#   label that would otherwise overflow its box.
#
#   "no French label exceeds its English twin by more than N" -- a ratio cannot
#   see how much slack a box has. `AUCUNE API PUBLIQUE` is 1.46x `NO PUBLIC
#   API` and sits comfortably inside its pill; the two labels that genuinely
#   overflowed on 2026-10-29 were at 1.24x and 1.11x. The largest ratio that
#   survived the eyeball loop was 1.18, which is below both of them: any
#   threshold that catches the second passes almost nothing and fails most of
#   the first. The constant and its label extractor lived here unused for two
#   iterations, reading like an enforced rule to anyone opening the file.
#
# Catching an overflow needs real text metrics, which means asking a renderer
# rather than counting characters. Until that is worth building, the eyeball
# loop is the check -- and saying so is better than shipping a threshold tuned
# until it went green.
