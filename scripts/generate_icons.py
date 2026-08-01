"""
generate_icons — build the GUI's favicon / touch-icon set from assets/logo.png.

One-off maintenance script, not a runtime dependency: run it by hand whenever
assets/logo.png changes, and commit the regenerated files under
best_engine_ai_helper/static/icons/. Keeping this as a script (rather than
generating icons on every request) means the FastAPI GUI serves static files
with zero per-request image work.

The source logo is a dark engraved glove on a transparent background. Browser
chrome and phone home screens are not reliably light, so every generated icon
gets a solid cream backing (the brand's paper tone) rather than staying
transparent — the glove needs to read on both light and dark surfaces.

Usage
-----
    python scripts/generate_icons.py

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = _ROOT / "assets" / "logo.png"
_OUT_DIR = _ROOT / "best_engine_ai_helper" / "static" / "icons"

# Brand palette: cream paper backing behind the ink-on-transparent glove.
_BG = (247, 243, 234, 255)  # #f7f3ea

# Fraction of the canvas the glove artwork occupies; the rest is margin so the
# glyph doesn't touch the edges at small sizes (favicons look cramped
# edge-to-edge).
_GLYPH_SCALE = 0.82


def _composite(size: int) -> Image.Image:
    """Return the logo centered on a cream square canvas of ``size`` px."""
    src = Image.open(_SOURCE).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), _BG)

    glyph_side = int(size * _GLYPH_SCALE)
    glyph = src.resize((glyph_side, glyph_side), Image.LANCZOS)

    offset = ((size - glyph_side) // 2, (size - glyph_side) // 2)
    canvas.alpha_composite(glyph, offset)
    return canvas


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Browser tab favicons (kept as PNG + a multi-size .ico).
    sizes_png = {"favicon-16x16.png": 16, "favicon-32x32.png": 32}
    for name, size in sizes_png.items():
        _composite(size).save(_OUT_DIR / name)

    ico_frames = [_composite(s) for s in (16, 32, 48)]
    # Pillow's ICO encoder downsamples FROM the saved image for each requested
    # size and silently drops any size larger than it — so this must save the
    # largest frame, not the smallest, or only the 16x16 entry survives.
    ico_frames[-1].save(
        _OUT_DIR / "favicon.ico",
        format="ICO",
        sizes=[(f.width, f.height) for f in ico_frames],
    )

    # iOS home-screen icon: iOS paints transparency black, so this must (and
    # does, via _composite's cream backing) be fully opaque.
    _composite(180).convert("RGB").save(_OUT_DIR / "apple-touch-icon.png")

    # Android / PWA manifest icons.
    _composite(192).save(_OUT_DIR / "android-chrome-192x192.png")
    _composite(512).save(_OUT_DIR / "android-chrome-512x512.png")

    print(f"Wrote icons to {_OUT_DIR}")


if __name__ == "__main__":
    main()
