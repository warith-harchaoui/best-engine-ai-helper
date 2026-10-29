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
    # `getattr`, because an included router appears in `app.routes` as one
    # opaque entry with no `.path` of its own — which is what the
    # OpenAI-compatible router is.
    paths = {getattr(r, "path", "") for r in mcp_module.app.routes}
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


def test_the_description_names_every_half_of_what_the_tools_answer() -> None:
    """The one string a host reads before loading these tools must not omit a half.

    It said the work happens "entirely on the local machine" and stopped, which
    had become false by omission: `/api/recommend` has carried a paid-model
    ranking for several iterations and `/api/providers` reports which providers
    hold a usable key. A host told only "local" would never ask for the half of
    the answer that prices a paid model.

    What must stay in the sentence is the *other* claim, the one that is still
    exactly true and is the reason `/v1` is excluded: these tools decide, and
    never call.
    """
    description = mcp_module.mcp.description or ""
    lowered = description.lower()

    for promised in ("hardware", "local", "paid", "key", "catalogue"):
        assert promised in lowered, f"the MCP description no longer mentions {promised!r}"

    assert "no model call" in lowered, (
        "the description must keep saying these tools never run a model -- it is "
        "what justifies excluding the /v1 routes from the tool list"
    )


def test_the_inference_routes_are_excluded_by_having_been_written() -> None:
    """Every `/v1` operation is excluded, discovered from the schema, not a list."""
    v1_operations = {
        str(operation["operationId"])
        for path, methods in mcp_module.app.openapi().get("paths", {}).items()
        if path.startswith("/v1")
        for operation in methods.values()
        if isinstance(operation, dict) and operation.get("operationId")
    }
    assert v1_operations, "the OpenAI-compatible router publishes no operations at all"
    assert v1_operations <= set(mcp_module._INFERENCE_OPERATIONS)
