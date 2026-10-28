"""
api — FastAPI HTTP surface for best-engine-ai-helper.

Exposes the two calls the GUI needs:

- ``GET /api/system``    — detected hardware + compute profile + memory budget.
- ``GET /api/lightweight``    — whether layer streaming is available/warranted here,
  and which too-large models it would unlock (see
  :mod:`best_engine_ai_helper.offload`).

It also mounts the **OpenAI-compatible** surface from
:mod:`best_engine_ai_helper.openai_api` on the same app: ``/v1/models``,
``/v1/chat/completions`` (text and vision, streaming or not),
``/v1/completions``, ``/v1/embeddings`` and ``/v1/images/generations``. Point
any OpenAI SDK at ``http://127.0.0.1:8000/v1`` and ask for the model named
``best`` — from the outside this package then behaves like an OpenAI endpoint,
while inside it is choosing the model this machine should actually run.
- ``POST /api/recommend`` — a free-text task -> the same report ``recommend()``
  produces for the CLI's ``report`` command, as JSON, plus the best PAID model
  under ``"cloud"`` (reference only, on by default; see ``cli.py``'s
  ``report --cloud``).

A minimal single-page GUI is served at ``GET /gui`` (``GET /`` redirects
there): it shows the machine's characteristics and lets you type a task
description to get the best local engine(s) for it, alongside the best paid
model for comparison. It is bilingual —
French by default, English at ``GET /gui?lang=en`` — with a header link to
switch between the two.

Run the app with any ASGI server::

    uvicorn best_engine_ai_helper.api:app --port 8000
    # or: best-engine-ai-helper gui

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import os_helper as osh
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog as _catalog
from . import cloud_catalog as _cloud_catalog
from . import detect as _detect
from . import observe as _observe
from .engine import default_backend as _default_backend
from .gui import render_gui
from .openai_api import install_error_handlers as _install_openai_errors
from .openai_api import router as _openai_router
from .recommend import cloud_recommend as _cloud_recommend_engines
from .recommend import recommend as _recommend_engines
from .score import MAX_HEADROOM as _MAX_HEADROOM
from .score import effective_budget as _effective_budget

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Best Engine AI Helper",
    description="Detect this machine's hardware and recommend the best local LLM/VLM engine(s).",
)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# The OpenAI-compatible surface, on the same app rather than a second server:
# one process, one port, one thing to start. `/api/*` is this package's own
# idiom (hardware, recommendations, decisions); `/v1/*` is somebody else's
# protocol, implemented so an existing client needs no changes at all. Keeping
# them side by side is deliberate — the `/v1` caller never has to learn this
# package, and the `/api` caller never has to pretend to be OpenAI.
app.include_router(_openai_router)
# And its error envelope: FastAPI nests a raised detail under `detail`, which
# is one level too deep for a client reading `error.message`.
_install_openai_errors(app)


class RecommendRequest(BaseModel):
    """Body for ``POST /api/recommend``."""

    task: str | None = None
    # Matches score.MAX_HEADROOM: a larger value is silently clamped down to
    # it inside effective_budget, so a bigger default here would be dishonest.
    headroom: float = _MAX_HEADROOM
    # Off by default: weighing live server load (free RAM, CPU/GPU/disk usage,
    # already-running engines) adds a probe (~0.1-0.5s) and makes the result
    # depend on this exact moment rather than the hardware alone — see
    # cli.py's --live for the same trade-off spelled out.
    live: bool = False
    # On by default, matching `report`'s own default: the best PAID model for
    # the task, reference only (no API key read, no network call — it ranks
    # the bundled pricing.yaml catalog). See cli.py's `report --cloud`.
    cloud: bool = True
    quality_vs_cost: float = _cloud_catalog.DEFAULT_QUALITY_VS_COST
    cloud_provider: str | None = None


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


class PreferencesRequest(BaseModel):
    """Preferences to persist. Every field optional: a form saves what changed."""

    quality_vs_cost: float | None = None
    headroom: float | None = None
    min_tps: float | None = None
    local_only: bool | None = None
    live_load: bool | None = None


@app.get("/api/preferences")
def preferences_get() -> dict[str, Any]:
    """The saved preferences, with defaults filled in for anything unset."""
    from . import config as _config

    return _config.load_preferences()


@app.post("/api/preferences")
def preferences_set(body: PreferencesRequest) -> dict[str, Any]:
    """Save preferences and return the full set as now stored.

    Writes `~/.best-engine-ai-helper/preferences.yaml`, deliberately **not**
    `settings.yaml`: that file holds API keys, and a browser form should never
    be in a position to rewrite a file containing secrets. The YAML remains the
    source of truth — this endpoint writes it and reads it back like any other
    client, rather than holding state of its own.
    """
    from . import config as _config

    return _config.save_preferences(body.model_dump(exclude_none=True))


@app.get("/api/providers")
def providers() -> dict[str, Any]:
    """Which cloud providers are usable right now, and for the rest, why not.

    The package routes on the keys you actually hold, and this is that rule
    made visible: a provider with no key is not a candidate, and the row says
    which variable to set rather than leaving a silently shorter list.

    Reports only whether a key resolved and the NAME of the variable it would
    come from. No key value is ever returned.
    """
    rows = _cloud_catalog.provider_status()
    return {
        "providers": rows,
        "available": sum(1 for r in rows if r["available"]),
        "total": len(rows),
    }


@app.post("/api/recommend")
def recommend(body: RecommendRequest) -> dict[str, Any]:
    """Best local engine(s) for ``body.task`` on this machine's hardware.

    Also carries the best PAID model under ``"cloud"`` unless ``body.cloud`` is
    false — a reference ranking only (no API key, no network call), the same
    one the CLI's ``report --cloud`` shows; see
    :func:`best_engine_ai_helper.recommend.cloud_recommend`.
    """
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    load = _detect.server_load() if body.live else None
    rep = _recommend_engines(
        hw, entries, task=body.task, headroom=body.headroom, compute=compute, load=load
    )
    if body.cloud:
        rep["cloud"] = _cloud_recommend_engines(
            body.task, quality_vs_cost=body.quality_vs_cost, provider=body.cloud_provider
        )
    return rep


@app.get("/api/lightweight")
def lightweight(
    measure: bool = False,
    kind: str = "llm",
    compression: str | None = None,
    answer_tokens: int = 300,
    batch: int = 1,
) -> dict[str, Any]:
    """
    Layer streaming: can this machine do it, should it, and what would it run?

    The read-only half of the ``lightweight`` command group (``status`` plus
    ``plan``) in one call, so the GUI and any other consumer can show the
    capability without shelling out.

    Parameters
    ----------
    measure : bool
        Measure disk read bandwidth instead of reading the storage-class table.
        Off by default: it writes and reads back ~256 MB, which is not something
        a page load should do unasked.
    kind : str
        ``llm`` or ``vlm``.
    compression : str or None
        ``4bit`` / ``8bit``, lightweight's block-wise weight compression.
    answer_tokens : int
        Answer length every timing is computed for. The per-token rate alone
        does not tell a caller whether a job finishes before lunch.
    batch : int
        Sequences answered together. Nearly free in time under streaming (one
        pass is shared) and one KV cache each in memory.

    Returns
    -------
    dict[str, Any]
        ``decision`` (:func:`offload.decide`), ``disk``, ``memory_budget_gb``,
        ``chosen`` (:func:`offload.pick`), the ranked ``plans``, and
        ``comparison`` (:func:`offload.compare`) — the same model streamed
        against the best this machine runs natively, both priced in seconds for
        one answer, which is the decision a caller is actually making.
    """
    from . import offload as _offload

    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    disk = _detect.disk_profile(measure=measure)
    budget = _offload.budget_gb(hw)
    entries = _catalog.servable_only(_catalog.load_catalog(), "lightweight")
    plans = _offload.rank(
        entries,
        budget_gb=budget,
        disk=disk,
        compression=compression,
        kind="vlm" if kind == "vlm" else "llm",
        batch=batch,
        new_tokens=answer_tokens,
    )
    comparison = _offload.compare(
        _catalog.load_catalog(),
        hw=hw,
        disk=disk,
        bandwidth_gbs=compute.get("bandwidth_gbs"),
        kind="vlm" if kind == "vlm" else "llm",
        native_backend=_default_backend(),
        new_tokens=answer_tokens,
        batch=batch,
        compression=compression,
    )
    return {
        "decision": _offload.decide(compute=compute, disk=disk),
        "disk": disk,
        "memory_budget_gb": budget,
        "comfort_tps_streaming": _offload.COMFORT_TPS_STREAMING,
        "install": _offload.INSTALL_HINT,
        "chosen": _offload.pick(plans),
        "plans": plans,
        "comparison": comparison,
    }


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
