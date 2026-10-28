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
OUT_SVG = REPO / "assets" / "diagrams" / "memory-budget.svg"
OUT_PNG = REPO / "assets" / "diagrams" / "memory-budget.png"

# Okabe-Ito, the colour-vision-safe scientific standard, keyed by the role the
# generator gives each hex. Source: https://deraison.ai/colors/academic
OKABE_ITO = {
    "#28CD41": "#009E73",  # gain   -> green    (unused here, remapped anyway)
    "#FF3B30": "#D55E00",  # loss   -> vermilion
    "#007AFF": "#0072B2",  # total  -> blue
}

# What the two colours that DO appear mean, in the units of this figure.
LEGEND = [("#D55E00", "Reserved, not yours"), ("#0072B2", "Available to a model")]


def bridge(pool_gb: float) -> tuple[list[dict[str, object]], str, str]:
    """Return the waterfall rows, title and subtitle for a pool of *pool_gb*.

    Every quantity is read back out of :mod:`best_engine_ai_helper.score`, so
    the figure cannot drift from the arithmetic the selector actually runs.
    """
    from best_engine_ai_helper import detect, score

    hw = {"unified_gb": pool_gb, "vram_gb": None, "ram_gb": pool_gb}
    usable = score.usable_pool_gb(hw)
    budget = score.effective_budget(hw)
    driver_cut = pool_gb - usable
    headroom_cut = usable - budget

    gpu_pct = round(100 * usable / pool_gb)
    chip = detect.chip_name() or "this machine"

    rows: list[dict[str, object]] = [
        {
            "label": "Unified memory\nthe chip reports",
            "value": pool_gb,
            "kind": "total",
        },
        {
            "label": f"Metal hands out\nonly {gpu_pct}% of it\nto the GPU",
            "value": -driver_cut,
            "kind": "negative",
        },
        {
            "label": "The OS, your app,\nand a KV cache that\ngrows with context",
            "value": -headroom_cut,
            "kind": "negative",
        },
        {
            "label": "What a model\nmay weigh here\nram_gb ≤ this",
            "value": budget,
            "kind": "total",
        },
    ]
    title = f"What {pool_gb:g} GB of unified memory is actually worth to a model"
    subtitle = (
        f"{chip} — gigabytes a model may occupy (higher is better). "
        "A candidate fits when its ram_gb lands under the last bar."
    )
    return rows, title, subtitle


def recolour(svg: str) -> str:
    """Remap the generator's palette to Okabe-Ito and rewrite its legend."""
    legend = "".join(
        f'<rect x="{88 + 170 * i}" y="102" width="12" height="12" rx="2" '
        f'fill="{colour}"/>\n'
        f'<text x="{105 + 170 * i}" y="112" font-size="13" fill="#6E6E73">'
        f"{label}</text>"
        for i, (colour, label) in enumerate(LEGEND)
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
            f"matched {n} times, expected 1 — re-read make_waterfall.py"
        )
    for old, new in OKABE_ITO.items():
        svg = svg.replace(old, new)
    return svg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pool",
        type=float,
        default=96.0,
        help="unified-memory pool to draw the bridge for, in GB (default: 96)",
    )
    args = ap.parse_args()

    try:
        from sprezzature_figures_scripts.make_waterfall import (  # type: ignore[import-not-found]
            make_waterfall,
        )
    except ImportError:
        print(
            "sprezzature-figures is not importable, and it is not a dependency "
            "of this package — it is the author's drawing tool.\n"
            "  pip install 'sprezzature-figures[cli]'\n"
            "The committed assets/diagrams/memory-budget.{svg,png} are what the "
            "documentation loads; regenerating them is only needed when the "
            "arithmetic in score.py changes.",
            file=sys.stderr,
        )
        return 1

    rows, title, subtitle = bridge(args.pool)
    OUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    make_waterfall(rows, out=OUT_SVG, title=title, subtitle=subtitle, theme="academic")
    OUT_SVG.write_text(recolour(OUT_SVG.read_text()), encoding="utf-8")
    print(f"wrote {OUT_SVG.relative_to(REPO)}")

    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        print("rsvg-convert not found: PNG not refreshed", file=sys.stderr)
        return 0
    subprocess.run(
        [rsvg, "-z", "2", "-o", str(OUT_PNG), str(OUT_SVG)],
        check=True,
    )
    print(f"wrote {OUT_PNG.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
