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

from best_engine_ai_helper import observe


@pytest.fixture()
def runner() -> CliRunner:
    """A Click CliRunner; the CLI never spawns subprocesses under test."""
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_ledger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    Never let the test suite write to the real ``~/.best-engine-ai-helper/usage.db``.

    `cli.py` / `cli_argparse.py` / `api.py` all call `observe.enable()` at
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
