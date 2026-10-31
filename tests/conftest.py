"""
Shared fixtures for the test suite.

Kept deliberately small: only objects reused across more than one module live
here. Module-specific fixtures and synthetic catalogs stay in their own file so
each test reads top-to-bottom without chasing indirection.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

import best_engine_ai_helper as _package
from best_engine_ai_helper import observe

#: The directory every user-state file in this project lives under. Nothing in
#: it belongs to the repository, so nothing in it may be read during a run.
USER_ROOT = Path.home() / ".best-engine-ai-helper"


def _raise(name: str) -> None:
    """
    Make an unimportable module loud instead of invisible.

    Read the stdlib before claiming what this protects, because the obvious
    reading is wrong. `walk_packages` consults `onerror` **only** when
    `info.ispkg` -- it imports a package to find what is inside it, and yields
    plain modules without importing them at all. So this covers exactly one
    case: a subpackage (`sources`) that stops importing, whose submodules
    would otherwise be skipped in silence while the sweep still reported
    success.

    Plain modules are imported by the caller below, where a failure already
    propagates and is loud. The remaining gap -- a module missed for any other
    reason -- is covered by comparing the walk against what is on disk, in
    `tests/test_cache_isolation.py`. One guard is narrower than it looks;
    saying so is what keeps the other two from being skipped.
    """
    raise ImportError(f"{name} could not be imported, so the sweep would silently skip it")


def redirect_user_paths(monkeypatch: pytest.MonkeyPatch, destination: Path) -> list[str]:
    """
    Point every module-level path under :data:`USER_ROOT` at ``destination``.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The patcher whose scope decides how long the redirection lasts.
    destination : Path
        An empty directory standing in for the user's own.

    Returns
    -------
    list[str]
        ``module.attribute`` for everything redirected, so a test can assert
        the sweep actually reached the stores it was built for.

    Notes
    -----
    This used to be four `setattr` lines naming four stores, and the list was
    wrong twice. Iteration 10 found the fourth the hard way: a test asserting
    that an undeclared context window stays unpublished passed in CI, where
    nothing has been pulled, and failed for the author, whose
    `measurements.yaml` held one. Green on the robot and red for the author is
    the worst shape a test failure takes.

    It was still wrong after that. A sweep of the package found **nineteen**
    module-level paths under the user directory against four redirected, and
    four of the gaps were live rather than theoretical: `usages._CACHE_PATH`
    (an overlay on the bundled profiles, read by `load_profiles`),
    `config._PREFERENCES_YAML`, `config._USER_DIR` (which `config.json` is read
    from) and `pull._USER_DIR` (which `write_env` writes to by default). They
    were dormant only because this particular machine has never written those
    files -- which is to say, dormant until the first developer who had.

    So the list is discovered rather than remembered. `catalog.CACHE_PATH` is
    a second name bound to the same path as `catalog._CACHE_PATH`, and
    `from .pull import _USER_DIR` makes `config._USER_DIR` a third independent
    binding; patching one name never moves another, which is why the rule is
    "every attribute that resolves under the user directory" rather than "every
    store". Relative layout is preserved, so a path ending in
    `catalog_cache.yaml` still does.
    """
    redirected: list[str] = []
    modules = [_package] + [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(_package.__path__, _package.__name__ + ".", _raise)
    ]
    for module in modules:
        for name, value in list(vars(module).items()):
            if name.startswith("__") or not isinstance(value, Path):
                continue
            try:
                relative = value.relative_to(USER_ROOT)
            except ValueError:
                continue
            monkeypatch.setattr(module, name, destination / relative)
            redirected.append(f"{module.__name__}.{name}")
    return redirected


@pytest.fixture()
def runner() -> CliRunner:
    """A Click CliRunner; the CLI never spawns subprocesses under test."""
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_ledger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    Never let the test suite write to the real ``~/.best-engine-ai-helper/usage.db``.

    `cli.py` and `api.py` both call `observe.enable()` at
    startup by default, and a `CliRunner`/`TestClient` invocation in these
    tests genuinely runs that startup code. Without this, running the suite
    once would leave real rows in the developer's actual ledger. Tests that
    specifically exercise `observe.py` pass their own `db_path` (e.g.
    ``":memory:"``) and are unaffected by the env var.
    """
    monkeypatch.setenv("BEST_ENGINE_NO_LEDGER", "1")
    observe.disable()
    yield
    observe.disable()


@pytest.fixture(autouse=True)
def _isolate_user_caches(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Never let the suite read the developer's ``~/.best-engine-ai-helper`` caches.

    Four stores overlay the bundled seeds — the local catalogue, the paid one,
    the hardware table and the per-machine measurements — and every loader
    reads them by default. So a suite run described whatever the machine
    happened to have refreshed last rather than what the repository contains:
    two `report` tests went red the first time `catalog update --cloud --arena`
    populated the paid cache with models that rank differently from the seed's
    ten, and the code they test had not changed.

    `measurements.yaml` joined the list the moment `/v1/models` learned to fall
    back to a *measured* context length. The test asserting that an undeclared
    window stays unpublished then failed on this developer's machine and would
    have passed in CI — because CI has pulled nothing, and this machine had
    pulled `gemma3:12b`, which reports 131072. Green on the robot and red for
    the author is the worst shape a test failure takes, and it is the shape
    this fixture exists to prevent.

    Same stance as :func:`_isolate_ledger` above, and the same reason: a test
    must describe the repository, not the machine it runs on. A test that wants
    a cache monkeypatches the same attribute itself, which still wins — this
    only changes the default from "whatever is in $HOME" to "nothing".
    """
    empty = tmp_path_factory.mktemp("no-user-caches")
    redirect_user_paths(monkeypatch, empty)
