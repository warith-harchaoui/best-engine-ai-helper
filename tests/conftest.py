"""
Shared fixtures for the test suite.

Kept deliberately small: only objects reused across more than one module live
here. Module-specific fixtures and synthetic catalogs stay in their own file so
each test reads top-to-bottom without chasing indirection.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture()
def runner() -> CliRunner:
    """A Click CliRunner; the CLI never spawns subprocesses under test."""
    return CliRunner()
