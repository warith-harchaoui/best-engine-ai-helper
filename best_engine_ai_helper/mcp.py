"""best-engine-ai-helper: Model Context Protocol (MCP) surface.

A thin adapter that exposes the FastAPI app from :mod:`best_engine_ai_helper.api`
as MCP tools, so any MCP-aware host (an agent runtime, an IDE integration, a
custom shell) can call ``/api/system`` (this machine's hardware snapshot) and
``/api/recommend`` (the best local LLM/VLM engine for a free-text task) as
first-class tools — the same detect-then-recommend workflow the CLI's
``detect``/``recommend``/``report`` commands expose. Uses `fastapi-mcp`
(https://github.com/tadata-org/fastapi_mcp): one wrapper publishes the whole
existing HTTP surface, so the routes are never duplicated.

**The `/v1` routes are excluded.** The same app serves an OpenAI-compatible
surface, and publishing ``/v1/chat/completions`` as an MCP tool would make the
description below untrue: an MCP host would gain a tool that runs a model, when
the point of this surface is that it decides and never calls. A host that wants
inference has the OpenAI protocol for it, on the same port.

Run the server (HTTP API + MCP endpoint at ``/mcp``)::

    best-engine-ai-helper-mcp                 # console entry point
    python -m best_engine_ai_helper.mcp       # equivalent

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from fastapi_mcp import FastApiMCP

# Reuse the exact same FastAPI app: MCP is a thin wrapper on top, no new routes.
from best_engine_ai_helper.api import app

# Publish the HTTP endpoints (/api/system, /api/recommend) as MCP tools.
#
# The `/v1/*` routes are deliberately NOT published. The app now also serves an
# OpenAI-compatible surface, and exposing `/v1/chat/completions` here would
# make the sentence below false: an MCP host would gain a tool that runs
# inference, when the whole claim of this surface is that it decides and never
# calls. A host that wants inference already has the OpenAI protocol for it,
# over the same port.
# Measured rather than hardcoded: a new `/v1` route must be excluded by having
# been written, not by somebody remembering to add it to a list here.
# Read out of the OpenAPI schema rather than off `app.routes`: an included
# router appears there as one opaque entry, so walking the routes finds no
# `/v1` path at all and the exclusion silently covers nothing (observed — the
# first spelling of this list came back empty while the tools kept appearing).
# The schema is also exactly what fastapi-mcp reads to build its tool list, so
# the two agree by construction, and a `/v1` route added later is excluded by
# having been written rather than by somebody remembering this list.
_INFERENCE_OPERATIONS = sorted(
    str(operation["operationId"])
    for path, methods in app.openapi().get("paths", {}).items()
    if path.startswith("/v1")
    for operation in methods.values()
    if isinstance(operation, dict) and operation.get("operationId")
)

mcp = FastApiMCP(
    app,
    name="best-engine-ai-helper",
    description=(
        "best-engine-ai-helper MCP tools: detect this machine's hardware "
        "(CPU, RAM, GPU, accelerator, memory bandwidth) and recommend the "
        "best local LLM/VLM engine(s) for a free-text task, entirely on the "
        "local machine — no model call happens inside these tools, only "
        "hardware detection and catalog ranking. Inference itself is reachable "
        "on the same port through the OpenAI-compatible `/v1` routes, which are "
        "deliberately not MCP tools."
    ),
    exclude_operations=_INFERENCE_OPERATIONS,
)
# Newer fastapi-mcp splits mount() into transport-specific mount_http(); fall back to
# the legacy mount() so a range of fastapi-mcp versions keeps working.
if hasattr(mcp, "mount_http"):
    mcp.mount_http()
else:  # pragma: no cover - legacy fastapi-mcp
    mcp.mount()


def main() -> None:
    """Console entry point (``best-engine-ai-helper-mcp``): serve the API + MCP endpoint.

    Boots the FastAPI app (now serving both the ``/api/...`` routes, the
    ``/gui`` page, and the ``/mcp`` MCP endpoint) with uvicorn in a single
    worker. Local-first: binds to loopback by default (override with
    ``BEST_ENGINE_HOST`` / ``BEST_ENGINE_PORT``).
    """
    import os

    import uvicorn

    from . import observe

    host = os.environ.get("BEST_ENGINE_HOST", "127.0.0.1")
    port = int(os.environ.get("BEST_ENGINE_PORT", "8000"))
    # Local-only activity/cost ledger (see observe.py, GET /api/usage); opt out
    # with BEST_ENGINE_NO_LEDGER=1.
    if not os.environ.get("BEST_ENGINE_NO_LEDGER"):
        observe.enable()
    print(f"best-engine-ai-helper API + MCP -> http://{host}:{port}  (MCP at /mcp)")
    uvicorn.run(app, host=host, port=port, workers=1)


if __name__ == "__main__":  # pragma: no cover
    main()
