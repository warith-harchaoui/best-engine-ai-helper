"""
Tests for scripts/generate_icons.py.

The script lives outside the installed package (a one-off maintenance tool), so
it is loaded from its file path. Output is redirected to a tmp dir so the
committed static/icons/ files are never regenerated; the real assets/logo.png is
the input since exercising the real source is the point.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "generate_icons.py"


@pytest.fixture()
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_icons", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_composite_is_square_rgba_over_cream(script: ModuleType) -> None:
    assert script._SOURCE.is_file()  # the source logo must exist to build from
    img = script._composite(64)
    assert img.size == (64, 64) and img.mode == "RGBA"
    # A corner pixel sits outside the scaled glove, so it is the cream backing.
    assert img.getpixel((0, 0)) == script._BG


def test_main_writes_every_icon_at_the_right_size(script: ModuleType, tmp_path: Path) -> None:
    script._OUT_DIR = tmp_path
    script.main()
    sized = {
        "favicon-16x16.png": (16, 16), "favicon-32x32.png": (32, 32),
        "apple-touch-icon.png": (180, 180),
        "android-chrome-192x192.png": (192, 192), "android-chrome-512x512.png": (512, 512),
    }
    for name, size in sized.items():
        with Image.open(tmp_path / name) as img:
            assert img.size == size, name


def test_icon_formats_are_platform_correct(script: ModuleType, tmp_path: Path) -> None:
    script._OUT_DIR = tmp_path
    script.main()
    # iOS paints transparency black, so the apple-touch icon must be opaque.
    with Image.open(tmp_path / "apple-touch-icon.png") as apple:
        assert apple.mode == "RGB"
    # The .ico bundles several sizes (Pillow drops sizes larger than the source).
    with Image.open(tmp_path / "favicon.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info.get("sizes", []))
