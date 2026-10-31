"""The suite cannot reach `~/.best-engine-ai-helper`, and that is now checked.

A test must describe the repository, not the machine it runs on. Iteration 6
established that for three catalogue caches, iteration 10 added a fourth after
a failure that was **green in CI and red for the author** -- CI had pulled no
model, this machine had pulled `gemma3:12b`, and a test asserting that an
undeclared context window stays unpublished saw 131072. Both fixes were four
lines naming four stores, and a hand-written list of stores is a list somebody
has to remember.

Nobody did. Sweeping the package for module-level paths under the user
directory found **nineteen** against four redirected, and four of the gaps
were live rather than theoretical:

* `usages._CACHE_PATH` -- an overlay on the bundled profiles, read by
  `load_profiles` and `load_families` exactly the way the catalogue caches are
  read;
* `config._PREFERENCES_YAML` -- the developer's saved preferences;
* `config._USER_DIR` -- where `config.json`, the persisted engine selection,
  is read from;
* `pull._USER_DIR` -- where `write_env` writes when no directory is passed.

None of them had bitten, for one reason: this machine has never written those
four files. The failure was waiting for the first developer who had, and it
would have arrived in the same disguise as last time -- passing for the robot,
failing for the person.

Two spellings make the hand-written list specially hard to keep right.
`catalog.CACHE_PATH` is a second name bound to the same path object as
`catalog._CACHE_PATH`, and `from .pull import _USER_DIR` gives `config` a
third independent binding of a fourth. Patching one name never moves another,
so the rule has to be "every attribute that resolves under the user
directory", never "every store".

These tests hold that rule. A new store added tomorrow fails here, by name,
instead of being found by a confused author six months later.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

import best_engine_ai_helper as package
from tests.conftest import USER_ROOT, _raise


def _user_paths() -> list[tuple[str, str, Path]]:
    """Every module-level ``Path`` in the package that resolves under USER_ROOT."""
    modules = [package] + [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + ".", _raise)
    ]
    found: list[tuple[str, str, Path]] = []
    for module in modules:
        for name, value in vars(module).items():
            if name.startswith("__") or not isinstance(value, Path):
                continue
            try:
                value.relative_to(USER_ROOT)
            except ValueError:
                continue
            found.append((module.__name__, name, value))
    return found


def test_the_sweep_sees_every_module_on_disk() -> None:
    """A sweep that covers less than the package still reports success.

    `_raise` covers one narrow case -- `walk_packages` consults `onerror` only
    for *packages*, so a subpackage that stops importing takes its submodules
    out of the sweep in silence. It does nothing for a plain module, which the
    walk never imports. This test covers the rest, and does not care why: it
    compares what the walk yields against what is on disk, so a module missed
    for any reason at all shows up here, including reasons nobody has thought
    of yet.

    The lesson is borrowed, from a concurrent session that nearly shipped a
    crash-dump guard calling `py-spy` -- which needs root on macOS and would
    have written "This program requires root" instead of a stack trace on the
    one day it mattered. A guard that looks armed is worse than none.
    """
    walked = {
        info.name.rsplit(".", 1)[-1]
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + ".", _raise)
    }
    on_disk = {
        path.stem for path in Path(package.__path__[0]).rglob("*.py") if path.stem != "__init__"
    }
    missed = sorted(on_disk - walked)
    assert not missed, (
        f"{len(missed)} module(s) on disk the sweep never reached: {missed}. "
        "Their user-directory paths would not be redirected, and nothing else "
        "would say so."
    )


def test_no_module_level_path_still_points_at_the_developers_home() -> None:
    """The gate itself, with the autouse fixture already applied.

    This is the assertion the four-line version could never make: not "the
    stores I thought of are redirected" but "nothing at all reaches the user
    directory".
    """
    leaks = [f"{module}.{name} = {value}" for module, name, value in _user_paths()]
    assert not leaks, (
        "these still read the developer's own files during the suite:\n"
        + "\n".join(leaks)
        + "\n\nAdd them by making `redirect_user_paths` reach them, never by "
        "naming them one at a time."
    )


#: Stores the sweep has to have moved, named so a silent miss is loud. The
#: first four are what iterations 6 and 10 hand-listed; the last four are the
#: gaps this one found, each of them a live read or write path.
_MUST_BE_MOVED = [
    ("catalog", "_CACHE_PATH"),
    ("cloud_catalog", "_CLOUD_CACHE_PATH"),
    ("hardware", "_HW_CACHE_PATH"),
    ("throughput", "_STORE_PATH"),
    ("usages", "_CACHE_PATH"),
    ("config", "_PREFERENCES_YAML"),
    ("config", "_USER_DIR"),
    ("pull", "_USER_DIR"),
]


@pytest.mark.parametrize(("module_name", "attribute"), _MUST_BE_MOVED)
def test_each_known_store_was_actually_moved(module_name: str, attribute: str) -> None:
    """A sweep that silently matched nothing would pass forever.

    The assertion above is equally satisfied by a sweep that finds zero paths
    for the wrong reason: an attribute renamed, an import that quietly failed,
    a `Path` turned into a `str`. Naming the stores closes that -- a renamed
    attribute raises here rather than disappearing into a green run.

    It cannot be written by re-running the sweep, because the autouse fixture
    has already moved everything by the time any test executes and a second
    sweep correctly finds nothing left to move. So the check is after the fact:
    the attribute exists, and it no longer lives under the user directory.
    """
    module = importlib.import_module(f"best_engine_ai_helper.{module_name}")
    assert hasattr(module, attribute), (
        f"{module_name}.{attribute} is gone; if it was renamed, rename it here "
        "too, and if its store was retired, drop the row"
    )
    value = getattr(module, attribute)
    assert isinstance(value, Path), f"{module_name}.{attribute} is no longer a Path"
    with pytest.raises(ValueError):
        value.relative_to(USER_ROOT)


def test_a_public_alias_is_moved_with_the_private_name_it_shadows() -> None:
    """`CACHE_PATH` and `_CACHE_PATH` are two names, and only one used to move.

    Nothing in the package reads the public spelling today, so this never bit;
    it is here because "the private one is the one that matters" is exactly the
    reasoning that leaves a second door open.
    """
    from best_engine_ai_helper import catalog, cloud_catalog, hardware, usages

    pairs = [
        (catalog.CACHE_PATH, catalog._CACHE_PATH),
        (cloud_catalog.CLOUD_CACHE_PATH, cloud_catalog._CLOUD_CACHE_PATH),
        (hardware.CACHE_PATH, hardware._HW_CACHE_PATH),
        (usages.CACHE_PATH, usages._CACHE_PATH),
    ]
    for public, private in pairs:
        assert public == private, f"{public} drifted from {private}"


def test_the_bundled_seed_is_what_a_merged_load_returns_here() -> None:
    """Isolation is only worth having if it changes the answer, so prove it does.

    `load_catalog()` merges the user cache over the bundled seed. Under this
    suite there is no user cache, so it has to return exactly the seed --
    which is 31 rows in the repository and 51 on the machine this was written
    on. A count taken without isolation describes the developer, and one draft
    of the iteration-11 changelog said 51 for precisely that reason.
    """
    from best_engine_ai_helper import catalog

    merged = catalog.load_catalog()
    seed = catalog._load_yaml_file(catalog._SEED_PATH)
    assert [row["id"] for row in merged] == [row["id"] for row in seed]
