"""
Tests for scripts/generate_icons.py.

The script lives outside the installed package (it's a one-off maintenance
tool, not a runtime dependency — see its own docstring), so it is loaded
directly from its file path rather than imported as a module. Each test
redirects its output directory to a pytest tmp_path so the committed
best_engine_ai_helper/static/icons/ files are never touched or regenerated
by the suite; the real assets/logo.png is used as input since it is small,
already committed, and exercising the real source is the point.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "generate_icons.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_icons", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script() -> ModuleType:
    return _load_script()


def test_source_logo_exists(script: ModuleType) -> None:
    assert script._SOURCE.is_file(), "assets/logo.png must exist for icons to build"


def test_composite_is_square_rgba_with_cream_background(script: ModuleType) -> None:
    img = script._composite(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    # A corner pixel is outside the (scaled) glove artwork, so it must be the
    # cream backing color, not left transparent.
    assert img.getpixel((0, 0)) == script._BG


def test_main_writes_every_expected_icon(script: ModuleType, tmp_path: Path) -> None:
    script._OUT_DIR = tmp_path
    script.main()

    expected = {
        "favicon-16x16.png": (16, 16),
        "favicon-32x32.png": (32, 32),
        "favicon.ico": None,  # multi-size; checked separately below
        "apple-touch-icon.png": (180, 180),
        "android-chrome-192x192.png": (192, 192),
        "android-chrome-512x512.png": (512, 512),
    }
    for name, size in expected.items():
        path = tmp_path / name
        assert path.is_file(), f"{name} was not written"
        if size is not None:
            with Image.open(path) as img:
                assert img.size == size


def test_apple_touch_icon_has_no_alpha(script: ModuleType, tmp_path: Path) -> None:
    # iOS paints transparency black on the home screen, so this icon must be
    # fully opaque (see the script's own docstring on this point).
    script._OUT_DIR = tmp_path
    script.main()
    with Image.open(tmp_path / "apple-touch-icon.png") as img:
        assert img.mode == "RGB"


def test_favicon_ico_contains_multiple_sizes(script: ModuleType, tmp_path: Path) -> None:
    script._OUT_DIR = tmp_path
    script.main()
    with Image.open(tmp_path / "favicon.ico") as img:
        sizes = {frame for frame in img.info.get("sizes", [])}
        assert {(16, 16), (32, 32), (48, 48)} <= sizes
