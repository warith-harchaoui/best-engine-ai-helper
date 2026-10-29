#!/usr/bin/env python3
"""Draw the memory-budget bridge that `README.md` shows, from `score.py` itself.

The figure answers one question a reader asks the moment they see "96 GB" on a
spec sheet: *how much of that can a model actually occupy?* The answer is a
bridge — the pool, minus what the GPU driver will not hand out, minus the
safety headroom — and the honest way to draw it is to take every number from
the code that enforces it rather than to type them in by hand. Change
``_APPLE_GPU_FRACTION_LARGE`` or ``MAX_HEADROOM`` in
:mod:`best_engine_ai_helper.score` and re-run this; the bars move with them.

The drawing itself comes from `sprezzature-figures`' ``waterfall`` kind, which
is not a dependency of this package — it is a tool on the author's machine, and
the committed SVG/PNG under ``assets/diagrams/`` are what the documentation
loads. Run this only to regenerate them.

Two things are corrected on the way out, because the generator's defaults do
not match what was asked of it:

1. ``--theme academic`` changes the typography to Latin Modern but leaves the
   bars in Apple's system colours. The three semantic hexes are remapped to
   Okabe-Ito (<https://deraison.ai/colors/academic>), which is the palette the
   rest of this project's figures use and the one that survives colour-vision
   deficiency.
2. The legend is built for a profit-and-loss bridge, so it reads
   "Gain / Loss / Total" — and "Gain" labels a colour no bar here uses, since a
   memory budget only ever subtracts. It is rewritten in the units of the
   actual question.

Usage
-----
    python scripts/make_memory_budget_figure.py [--pool 96]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# One stem per language. The figure is embedded in BOTH root READMEs, and for a
# long time only the English one existed: LISEZMOI.md carried a carefully
# translated caption above a picture whose every label was in English. The
# EN/FR parity checker could not see it — both documents link the same URL,
# which is precisely what that check calls agreement — so the gap had to be
# found by reading the figure rather than the markup.
STEMS = {"en": "memory-budget", "fr": "budget-memoire"}

# The waterfall generator sets the subtitle on one line and does not wrap it, so
# a string wider than the canvas is simply cut off at the right edge. Nothing
# errors; you only find out by looking at the picture. French runs roughly 15%
# longer than English, which is exactly enough for a sentence that fits in one
# language to be truncated in the other -- observed, on the first draw of the
# French twin. The cap is the longest subtitle that was measured to fit, with no
# margin added: a guess about margin would be the kind of unverified number this
# repository spends its time deleting.
SUBTITLE_MAX_CHARS = 125

# Okabe-Ito, the colour-vision-safe scientific standard, keyed by the role the
# generator gives each hex. Source: https://deraison.ai/colors/academic
OKABE_ITO = {
    "#28CD41": "#009E73",  # gain   -> green    (unused here, remapped anyway)
    "#FF3B30": "#D55E00",  # loss   -> vermilion
    "#007AFF": "#0072B2",  # total  -> blue
}

# What the two colours that DO appear mean, in the units of this figure.
LEGEND = {
    "en": [("#D55E00", "Reserved, not yours"), ("#0072B2", "Available to a model")],
    "fr": [("#D55E00", "Réservé, pas à vous"), ("#0072B2", "Disponible pour un modèle")],
}

# Every string the drawing shows, per language. Kept here rather than inside
# `bridge` so that adding a third language is a dictionary entry and not a
# second code path that can disagree with the first.
WORDS = {
    "en": {
        "pool": "Unified memory\nthe chip reports",
        "driver": "Metal hands out\nonly {pct}% of it\nto the GPU",
        "headroom": "The OS, your app,\nand a KV cache that\ngrows with context",
        "budget": "What a model\nmay weigh here\nram_gb ≤ this",
        "title": "What {pool:g} GB of unified memory is actually worth to a model",
        "subtitle": (
            "{chip} — gigabytes a model may occupy (higher is better). "
            "A candidate fits when its ram_gb lands under the last bar."
        ),
        "desc": (
            "A bridge chart. A {pool:g} GB unified-memory pool is reduced twice before a "
            "model may use it: Metal hands only {pct}% of the pool to the GPU, which "
            "removes {driver:.1f} GB, and a safety headroom for the operating system, "
            "your own application and a KV cache that grows with context removes "
            "{headroom:.1f} GB more. What is left, {budget:.1f} GB, is the figure a "
            "candidate model's ram_gb has to land under. Every number is read out of "
            "score.py rather than typed in, so the bars move when the arithmetic does."
        ),
    },
    "fr": {
        "pool": "Mémoire unifiée\nannoncée par la puce",
        "driver": "Metal n'en confère\nque {pct} % au GPU",
        "headroom": "Le système, votre appli,\npuis un cache KV qui\ngrandit avec le contexte",
        "budget": "Ce qu'un modèle\npeut peser ici\nram_gb ≤ ceci",
        "title": "Ce que {pool:g} Go de mémoire unifiée valent vraiment pour un modèle",
        "subtitle": (
            "{chip} — gigaoctets qu'un modèle peut occuper. "
            "Un candidat tient si son ram_gb passe sous la dernière barre."
        ),
        "desc": (
            "Un graphique en cascade. Un pool de mémoire unifiée de {pool:g} Go est "
            "réduit deux fois avant qu'un modèle puisse s'en servir : Metal n'en "
            "confère que {pct} % au GPU, ce qui retire {driver:.1f} Go, puis une marge "
            "de sécurité pour le système d'exploitation, votre propre application puis "
            "un cache KV qui grandit avec le contexte en retire {headroom:.1f} de plus. "
            "Ce qui reste, {budget:.1f} Go, est le chiffre sous lequel le ram_gb d'un "
            "modèle candidat doit passer. Chaque nombre est lu dans score.py plutôt que "
            "saisi à la main : les barres bougent quand l'arithmétique bouge."
        ),
    },
}


def bridge(pool_gb: float, lang: str = "en") -> tuple[list[dict[str, object]], dict[str, str]]:
    """Return the waterfall rows and every string the figure shows, in *lang*.

    Every quantity is read back out of :mod:`best_engine_ai_helper.score`, so
    the figure cannot drift from the arithmetic the selector actually runs.

    Parameters
    ----------
    pool_gb : float
        Unified-memory pool to draw the bridge for, in GB.
    lang : str
        Key into :data:`WORDS` and :data:`LEGEND`.

    Returns
    -------
    tuple[list[dict[str, object]], dict[str, str]]
        The rows the waterfall generator wants, and a dict carrying ``title``,
        ``subtitle`` and ``desc`` already formatted with the measured numbers.
    """
    from best_engine_ai_helper import detect, score

    hw = {"unified_gb": pool_gb, "vram_gb": None, "ram_gb": pool_gb}
    usable = score.usable_pool_gb(hw)
    budget = score.effective_budget(hw)
    driver_cut = pool_gb - usable
    headroom_cut = usable - budget

    gpu_pct = round(100 * usable / pool_gb)
    chip = detect.chip_name() or "this machine"
    words = WORDS[lang]

    rows: list[dict[str, object]] = [
        {"label": words["pool"], "value": pool_gb, "kind": "total"},
        {"label": words["driver"].format(pct=gpu_pct), "value": -driver_cut, "kind": "negative"},
        {"label": words["headroom"], "value": -headroom_cut, "kind": "negative"},
        {"label": words["budget"], "value": budget, "kind": "total"},
    ]
    numbers = {
        "pool": pool_gb,
        "pct": gpu_pct,
        "driver": driver_cut,
        "headroom": headroom_cut,
        "budget": budget,
        "chip": chip,
    }
    text = {key: words[key].format(**numbers) for key in ("title", "subtitle", "desc")}
    if len(text["subtitle"]) > SUBTITLE_MAX_CHARS:
        raise SystemExit(
            f"{lang}: the subtitle is {len(text['subtitle'])} characters, over the "
            f"{SUBTITLE_MAX_CHARS} that fit on one line. The generator would draw it "
            "anyway and let the right edge cut it off, which is how the French twin "
            "shipped clipped the first time. Shorten it in WORDS."
        )
    return rows, text


def recolour(svg: str, lang: str = "en") -> str:
    """Remap the generator's palette to Okabe-Ito and rewrite its legend."""
    legend = "".join(
        f'<rect x="{88 + 190 * i}" y="102" width="12" height="12" rx="2" '
        f'fill="{colour}"/>\n'
        f'<text x="{105 + 190 * i}" y="112" font-size="13" fill="#6E6E73">'
        f"{label}</text>"
        for i, (colour, label) in enumerate(LEGEND[lang])
    )
    # The generator emits exactly three legend rows, in a run of its own.
    pattern = re.compile(
        r'<rect x="88" y="102".*?<text x="265" y="112"[^>]*>Total</text>',
        re.DOTALL,
    )
    svg, n = pattern.subn(legend, svg)
    if n != 1:
        raise SystemExit(
            "the waterfall generator's legend markup changed: "
            f"matched {n} times, expected 1 -- re-read make_waterfall.py"
        )
    for old, new in OKABE_ITO.items():
        svg = svg.replace(old, new)
    return svg


def describe(svg: str, title: str, desc: str) -> str:
    """Give the drawing a name and a prose description a screen reader can read.

    The waterfall generator emits a ``<desc>`` and no ``<title>``, and nothing
    pointed ``aria-labelledby`` at either — so this was the one figure in
    ``assets/diagrams/`` with no accessible name at all. Every other figure in
    this repository is hand-authored and carries both; a generated one has no
    excuse to be the exception, and `tests/test_figures.py` now refuses it.

    Parameters
    ----------
    svg : str
        The generator's output.
    title : str
        Short accessible name, shown by a screen reader before the description.
    desc : str
        Long description: what the chart shows, in the numbers it was drawn
        from, for a reader who will never see it.

    Returns
    -------
    str
        The same SVG with ``role``, ``aria-labelledby``, ``<title>`` and
        ``<desc>`` in place.

    Examples
    --------
    >>> out = describe('<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>', "T", "D")
    >>> '<title id="mb-title">T</title>' in out
    True
    >>> 'aria-labelledby="mb-title mb-desc"' in out
    True
    """

    def escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    svg = re.sub(r"\s*<desc\b.*?</desc>", "", svg, flags=re.DOTALL)
    opening = re.match(r"<svg\b[^>]*>", svg)
    if opening is None:
        raise SystemExit("the waterfall generator stopped emitting an <svg> element")
    head = opening.group(0)
    for attribute in (' role="img"', ' aria-labelledby="mb-title mb-desc"'):
        if attribute.strip().split("=")[0] not in head:
            head = head[:-1] + attribute + ">"
    block = (
        f'\n  <title id="mb-title">{escape(title)}</title>'
        f'\n  <desc id="mb-desc">{escape(desc)}</desc>'
    )
    return head + block + svg[opening.end() :]


def main(argv: list[str] | None = None) -> int:
    """Draw the bridge for one language, or for every language in :data:`STEMS`.

    Parameters
    ----------
    argv : list[str] or None
        Command-line arguments; ``None`` reads :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on success, ``1`` when the drawing tool is not installed.

    Examples
    --------
    >>> import argparse
    >>> sorted(STEMS)
    ['en', 'fr']
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pool",
        type=float,
        default=96.0,
        help="unified-memory pool to draw the bridge for, in GB (default: 96)",
    )
    ap.add_argument(
        "--lang",
        choices=[*STEMS, "all"],
        default="all",
        help="which language to draw; 'all' redraws every twin (default: all)",
    )
    args = ap.parse_args(argv)

    try:
        from sprezzature_figures_scripts.make_waterfall import (  # type: ignore[import-not-found]
            make_waterfall,
        )
    except ImportError:
        print(
            "sprezzature-figures is not importable, and it is not a dependency "
            "of this package -- it is the author's drawing tool.\n"
            "  pip install 'sprezzature-figures[cli]'\n"
            "The committed assets/diagrams/*.{svg,png} are what the "
            "documentation loads; regenerating them is only needed when the "
            "arithmetic in score.py changes.",
            file=sys.stderr,
        )
        return 1

    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        print("rsvg-convert not found: PNGs will not be refreshed", file=sys.stderr)

    for lang in STEMS if args.lang == "all" else [args.lang]:
        out_svg = REPO / "assets" / "diagrams" / f"{STEMS[lang]}.svg"
        out_png = out_svg.with_suffix(".png")
        rows, text = bridge(args.pool, lang)
        out_svg.parent.mkdir(parents=True, exist_ok=True)
        make_waterfall(
            rows, out=out_svg, title=text["title"], subtitle=text["subtitle"], theme="academic"
        )
        out_svg.write_text(
            describe(
                recolour(out_svg.read_text(encoding="utf-8"), lang), text["title"], text["desc"]
            ),
            encoding="utf-8",
        )
        print(f"wrote {out_svg.relative_to(REPO)}")
        if rsvg is not None:
            subprocess.run([rsvg, "-z", "2", "-o", str(out_png), str(out_svg)], check=True)
            print(f"wrote {out_png.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
