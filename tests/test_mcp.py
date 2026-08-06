"""Smoke test for the MCP surface (`best_engine_ai_helper.mcp`).

Gated on the ``mcp`` extra (FastAPI + fastapi-mcp). Importing
`best_engine_ai_helper.mcp` mounts an MCP endpoint onto the FastAPI app; we
check the endpoint is wired and that the HTTP API keeps serving alongside it.
Skips cleanly when the extra isn't installed, so the default suite is
unaffected.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("fastapi_mcp")
starlette_testclient = pytest.importorskip("starlette.testclient")

from best_engine_ai_helper import mcp as mcp_module  # noqa: E402


def test_mcp_endpoint_is_mounted() -> None:
    """Importing the module publishes an `/mcp` endpoint named 'best-engine-ai-helper'."""
    paths = {r.path for r in mcp_module.app.routes}
    assert any("/mcp" in p for p in paths), paths
    assert mcp_module.mcp.name == "best-engine-ai-helper"


def test_api_still_served_next_to_mcp() -> None:
    """The FastAPI routes still work once the MCP endpoint is mounted."""
    client = starlette_testclient.TestClient(mcp_module.app)
    res = client.get("/api/system")
    assert res.status_code == 200
    assert res.json()["hardware"]["ram_gb"] > 0
