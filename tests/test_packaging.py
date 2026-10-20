"""
Tests that the package ships the data it needs to run.

Written after the defect they describe. Up to 1.6.0 the five data files —
`models.yaml`, `hardware.yaml`, `usages.yaml`, `pricing.yaml` and
`locales/i18n.yaml` — sat NEXT TO the package rather than inside it, while
`pyproject.toml` listed them under `[tool.setuptools.package-data]` as if
that covered them. It did not: those patterns resolve relative to a *package
directory*, so they matched nothing, and the published wheel contained no
data at all.

The consequence was not subtle and went unnoticed for every release up to
1.5.0: on a machine with no user cache, `load_catalog()` returned an **empty
catalogue**, so the package's whole purpose — pick the best local model —
could not work for anyone installing from PyPI. Two things hid it. A repo
checkout has the files exactly where the code looked, and a developer machine
has a populated `~/.best-engine-ai-helper` cache that the loader merges over
the (missing) seed, so the count looked plausible.

The property asserted here is the one that survives packaging: every runtime
data file lives under the importable package directory, and the build is told
to ship it.

Usage Example
-------------
>>> #   pytest tests/test_packaging.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

import best_engine_ai_helper
from best_engine_ai_helper import catalog, cloud_catalog, hardware, i18n, observe, usages

_PACKAGE_DIR = Path(best_engine_ai_helper.__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent


@pytest.mark.parametrize(
    ("label", "path"),
    [
        ("models.yaml", catalog._SEED_PATH),
        ("hardware.yaml", hardware._SEED_PATH),
        ("usages.yaml", usages._SEED_PATH),
        ("pricing.yaml", observe._PRICING_PATH),
        ("pricing.yaml (cloud_catalog)", cloud_catalog._PRICING_PATH),
        ("locales/i18n.yaml", i18n._LOCALES_PATH),
    ],
)
def test_every_runtime_data_file_lives_inside_the_package(label: str, path: Path) -> None:
    """Beside the package is not inside it, and only inside it travels."""
    assert path.exists(), f"{label}: {path} does not exist"
    assert path.resolve().is_relative_to(_PACKAGE_DIR), (
        f"{label}: {path} is outside {_PACKAGE_DIR}; it will not travel in the wheel"
    )


def test_the_build_is_told_to_ship_that_data() -> None:
    """Living inside the package is necessary and not sufficient.

    setuptools ships `.py` on its own; every other extension needs declaring,
    and the declaration is keyed by package name with package-relative globs.
    """
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = config["tool"]["setuptools"]["package-data"]["best_engine_ai_helper"]
    for needed in ("data/*.yaml", "locales/*.yaml"):
        assert needed in patterns, f"package-data does not cover {needed}: {patterns}"


def test_no_runtime_data_file_was_left_at_the_repo_root() -> None:
    """The old location, which looked right and shipped nothing."""
    stragglers = [
        name
        for name in ("models.yaml", "hardware.yaml", "usages.yaml", "pricing.yaml")
        if (_REPO_ROOT / name).exists()
    ]
    assert not stragglers, f"data still at the repo root, outside the wheel: {stragglers}"


def test_the_catalogue_is_not_empty_from_its_bundled_seed_alone() -> None:
    """The symptom itself, read straight from the seed.

    `load_catalog()` merges a user cache over the seed, which is exactly what
    masked the empty seed on developer machines — so this reads the seed file
    rather than the merged result.
    """
    import yaml

    seed = yaml.safe_load(catalog._SEED_PATH.read_text(encoding="utf-8"))
    entries = seed.get("models", seed) if isinstance(seed, dict) else seed
    assert len(entries) >= 10, f"the bundled seed carries only {len(entries)} entries"
