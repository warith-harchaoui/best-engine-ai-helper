"""
Shared fixtures for the test suite.

Kept deliberately small: only objects reused across more than one module live
here. Module-specific fixtures and synthetic catalogs stay in their own file so
each test reads top-to-bottom without chasing indirection.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from click.testing import CliRunner

from best_engine_ai_helper import catalog, cloud_catalog, hardware, observe, throughput


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
    monkeypatch.setattr(catalog, "_CACHE_PATH", empty / "catalog_cache.yaml")
    monkeypatch.setattr(cloud_catalog, "_CLOUD_CACHE_PATH", empty / "pricing_cache.yaml")
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", empty / "hardware_cache.yaml")
    monkeypatch.setattr(throughput, "_STORE_PATH", empty / "measurements.yaml")
