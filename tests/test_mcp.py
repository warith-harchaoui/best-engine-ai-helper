"""Tests for the MCP surface (`best_engine_ai_helper.mcp`).

FastAPI + fastapi-mcp are core dependencies. Importing
`best_engine_ai_helper.mcp` mounts an MCP endpoint onto the FastAPI app; this
checks the endpoint is wired, that the HTTP API keeps serving alongside it,
and that `main()` boots uvicorn on the configured host/port.
"""

from __future__ import annotations

import pytest
from starlette import testclient as starlette_testclient

from best_engine_ai_helper import mcp as mcp_module


def test_mcp_mounted_api_served_and_main_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    # Importing the module publishes an /mcp endpoint named 'best-engine-ai-helper'.
    paths = {r.path for r in mcp_module.app.routes}
    assert any("/mcp" in p for p in paths), paths
    assert mcp_module.mcp.name == "best-engine-ai-helper"

    # The FastAPI routes still work once the MCP endpoint is mounted.
    client = starlette_testclient.TestClient(mcp_module.app)
    res = client.get("/api/system")
    assert res.status_code == 200
    assert res.json()["hardware"]["ram_gb"] > 0

    # main() boots uvicorn on the configured host/port. conftest's autouse
    # fixture sets BEST_ENGINE_NO_LEDGER=1, so this never touches the real
    # ~/.best-engine-ai-helper/usage.db.
    calls: dict[str, object] = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(app=app, **kw))
    monkeypatch.setenv("BEST_ENGINE_HOST", "0.0.0.0")
    monkeypatch.setenv("BEST_ENGINE_PORT", "9100")
    mcp_module.main()
    assert calls["app"] is mcp_module.app
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 9100)
