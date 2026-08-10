"""
api — FastAPI HTTP surface for best-engine-ai-helper.

Exposes the two calls the GUI needs:

- ``GET /api/system``    — detected hardware + compute profile + memory budget.
- ``POST /api/recommend`` — a free-text task -> the same report ``recommend()``
  produces for the CLI's ``report`` command, as JSON.

A minimal single-page GUI is served at ``GET /gui`` (``GET /`` redirects
there): it shows the machine's characteristics and lets you type a task
description to get the best local engine(s) for it. It is bilingual —
French by default, English at ``GET /gui?lang=en`` — with a header link to
switch between the two.

Install the extra to get the runtime dependencies::

    pip install 'best-engine-ai-helper[api]'

Then run the app with any ASGI server::

    uvicorn best_engine_ai_helper.api:app --port 8000
    # or: best-engine-ai-helper gui

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The FastAPI HTTP surface requires the [api] extra. "
        "Install with: pip install 'best-engine-ai-helper[api]'"
    ) from exc

import os_helper as osh

from . import catalog as _catalog
from . import detect as _detect
from . import observe as _observe
from .gui import render_gui
from .recommend import recommend as _recommend_engines
from .score import effective_budget as _effective_budget

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Best Engine AI Helper",
    description="Detect this machine's hardware and recommend the best local LLM/VLM engine(s).",
)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class RecommendRequest(BaseModel):
    """Body for ``POST /api/recommend``."""

    task: str | None = None
    headroom: float = 0.85
    # Off by default: weighing live server load (free RAM, CPU/GPU/disk usage,
    # already-running engines) adds a probe (~0.1-0.5s) and makes the result
    # depend on this exact moment rather than the hardware alone — see
    # cli.py's --live for the same trade-off spelled out.
    live: bool = False


def _system_info() -> dict[str, Any]:
    """Assemble the hardware snapshot shown at the top of the GUI."""
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    return {
        "platform": _detect.platform_name(),
        "chip_vendor": _detect.chip_vendor(),
        "memory": hw,
        "compute": compute,
        "memory_budget_gb": _effective_budget(hw),
        # Raw CPU/GPU facts straight from os_helper (cores, model names,
        # per-GPU VRAM) — distinct from "compute" above (the AI-throughput
        # bandwidth estimate derived from these facts).
        "hardware": osh.hardware_info(),
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the bare root path to the browser GUI."""
    return RedirectResponse(url="/gui")


@app.get("/gui", response_class=HTMLResponse, include_in_schema=False)
def gui(lang: str = "fr") -> str:
    """Serve the single-page GUI (``?lang=en`` for English, French by default)."""
    # render_gui falls back to French for any unknown code, so a bad value
    # never errors.
    return render_gui(lang)


@app.get("/api/system")
def system() -> dict[str, Any]:
    """Detected hardware, compute profile, and usable memory budget."""
    return _system_info()


@app.post("/api/recommend")
def recommend(body: RecommendRequest) -> dict[str, Any]:
    """Best local engine(s) for ``body.task`` on this machine's hardware."""
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    load = _detect.server_load() if body.live else None
    return _recommend_engines(
        hw, entries, task=body.task, headroom=body.headroom, compute=compute, load=load
    )


@app.get("/api/activity")
def activity() -> dict[str, Any]:
    """
    Local activity/cost ledger summary (calls, cost, by user/model, errors).

    Reads the ledger even when THIS process never called ``observe.enable()``
    — e.g. a plain ``uvicorn best_engine_ai_helper.api:app`` that skips the
    CLI's/MCP's auto-enable — by opening the default-path database read-only
    in that case, same fallback :func:`cli.activity_cmd` uses. Never 404s or
    errors over "no data": an unrecorded/empty ledger is a valid, common state.
    """
    ledger = _observe.active_ledger() or _observe.Ledger()
    return ledger.summary()
