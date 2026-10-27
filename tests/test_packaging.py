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

import subprocess
import sys
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


# ---------------------------------------------------------------------------
# Layer streaming ships by default, and that is a decision rather than a drift
# ---------------------------------------------------------------------------


def test_the_streaming_runtime_is_a_core_dependency_not_an_extra() -> None:
    """airllm installs with the package, so streaming works on every install.

    Pinned because the opposite is the tempting refactor: airllm pulls torch,
    transformers and accelerate, so someone reading the install size will reach
    for an extra. The decision is that "which model can this machine run" and
    "which model can this machine run if it streams the layers" are the same
    question, and a capability behind an extra is one most callers never
    discover. If that is ever revisited it should be revisited on purpose, with
    this test as the place the reasoning is written down.
    """
    manifest = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    config = tomllib.loads(manifest)
    core = config["project"]["dependencies"]
    extras = config["project"]["optional-dependencies"]

    assert any(dep.startswith("airllm") for dep in core), core
    # The extra name survives as an empty alias: it is published in release
    # notes and sits in lockfiles, and an unknown extra is a hard resolution
    # error rather than a warning.
    assert extras["airllm"] == []
    # requirements.txt is the runtime mirror of the core list, so it has to
    # agree or a pip-based install diverges from a pyproject-based one.
    runtime = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "airllm" in runtime


def test_importing_the_package_does_not_import_torch() -> None:
    """The weight is install size, never startup time.

    airllm (and so torch) is imported lazily, inside `offload.load`, because a
    gigabyte of deep-learning stack must not be paged in to answer `detect`.
    This is the test that keeps a convenience import at the top of a module
    from quietly costing every CLI invocation a second or two.
    """
    source = (_REPO_ROOT / "best_engine_ai_helper" / "offload.py").read_text(encoding="utf-8")
    module_level = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and ("airllm" in line or "torch" in line)
    ]
    assert module_level == [], module_level

    # And the claim itself, measured rather than inferred from the source: a
    # fresh interpreter that imports the package must not have torch loaded.
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, best_engine_ai_helper; "
            "print('torch' in sys.modules or 'airllm' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "False", probe.stdout
