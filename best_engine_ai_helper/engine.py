"""
engine — resolve a repo's LLM/VLM usage brief into a concrete serving engine.

The suite's model-selection contract has two YAML files per consumer repo:

1. an **input brief** (committed, hardware-independent) describing what the repo
   needs from an LLM/VLM — the kinds, memory headroom, comfort floor, and a
   free-text ``task``; and
2. an **output engine** file (gitignored, machine-specific) this module writes:
   the backend chosen for the current machine plus the concrete model per kind,
   sized realistically for that backend.

Backend rule (``resolve(..., backend="auto")``): **vLLM only on Linux with a
real discrete GPU (NVIDIA/AMD); Ollama everywhere else** — macOS (vLLM has no
native macOS runtime), Windows (no native vLLM wheel, WSL-only), CPU-only
machines (vLLM's CPU-only path is its own weak spot, notably on Linux), and
Intel iGPUs all use Ollama; only a Linux CUDA/ROCm box gets vLLM, chiefly for
the request-batching/concurrency handling it offers under real production
load, which Ollama does not match. This keeps picks realistic. When vLLM
gains a first-class runtime elsewhere, widening this rule is the only change
needed.

No ``DEFAULT_MODEL`` constant lives in any consumer: the model is always read
from the resolved engine file. :func:`ensure` is the missing-file policy — a
missing engine file is auto-resolved from the brief; a missing *brief* is a hard
error, because the brief is committed and its absence is a real bug.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

import os_helper as osh
import yaml

from .score import COMFORT_TPS, MAX_HEADROOM

# Canonical filenames for the two contract files. Consumers may override, but
# these are the suite default so every repo looks the same.
BRIEF_NAME = "llm.brief.yaml"
ENGINE_NAME = "llm.engine.yaml"

# Default endpoints per backend. Ollama's native API and a local vLLM
# OpenAI-compatible server, respectively. Overridable via ``endpoint=``.
_OLLAMA_URL = "http://localhost:11434"
_VLLM_URL = "http://localhost:8000/v1"

# `lightweight` is valid but never automatic: `default_backend` cannot return it,
# and `_resolve_local` only reaches it when a human asks or when nothing else
# fits (see offload.decide). Streaming is a rescue, not a preference.
_VALID_BACKENDS = ("ollama", "vllm", "lightweight")

# Default API roots for cloud providers, used when a cloud brief does not pin
# its own base_url.
_CLOUD_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}

# Default env-var NAME (never the key value) a cloud brief's api_key_env falls
# back to when unset, keyed by provider — the conventional variable name each
# provider's own SDK/docs use. Only the name is stored/read; see
# llm._cloud_api_key for the actual lookup (settings.yaml/.env/env, then
# keyring).
_DEFAULT_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "azure": "AZURE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


# Accelerator vendors that have a real (fast) vLLM runtime today, and only on
# Linux (see default_backend): a discrete CUDA (NVIDIA) or ROCm (AMD) GPU gets
# vLLM there. Apple Silicon (no native vLLM runtime), Intel iGPUs, and
# CPU-only machines fall back to Ollama, where vLLM is either unsupported or
# too slow to be realistic.
_VLLM_VENDORS = frozenset({"nvidia", "amd"})


def default_backend() -> str:
    """Return the backend for the current machine.

    A three-branch decision tree, matching what each backend actually
    supports well rather than what it merely runs on:

    - **macOS** -> Ollama. vLLM ships no native macOS runtime.
    - **CPU-only** (Linux or macOS) -> Ollama. vLLM's CPU-only path — notably
      on Linux — is its own reported weak spot; Ollama's CPU path is the
      well-trodden one.
    - **discrete GPU (NVIDIA/AMD) on Linux** — the real production case ->
      vLLM, chiefly for the request-batching/concurrency handling it offers
      under real load, which Ollama does not match.

    Windows falls back to Ollama too (vLLM has no native Windows wheel, only
    a WSL path), so in practice: **vLLM only on Linux with a real discrete
    GPU; Ollama everywhere else.** Endgame: when vLLM gains a first-class
    runtime on Mac, Windows, or CPU-only Linux, replace this whole body with
    ``return "vllm"`` and the suite is fully on vLLM.
    """
    from .detect import chip_vendor, platform_name

    return "vllm" if platform_name() == "linux" and chip_vendor() in _VLLM_VENDORS else "ollama"


def _kinds_from_brief(kind: str) -> list[Literal["llm", "vlm"]]:
    """Map a brief's ``kind`` field to the ordered list of kinds to resolve."""
    k = (kind or "both").strip().lower()
    if k == "both":
        return ["llm", "vlm"]
    if k in ("llm", "vlm"):
        return [cast(Literal["llm", "vlm"], k)]
    osh.warning(f"Unknown brief kind {kind!r}; defaulting to both llm and vlm.")
    return ["llm", "vlm"]


def _base_url(backend: str, endpoint: str | None) -> str:
    """Resolve the server base URL for a backend, honouring an explicit endpoint."""
    if endpoint:
        return endpoint.rstrip("/")
    if backend == "lightweight":
        # There is no URL to resolve: lightweight is a library that runs inside the
        # caller's own process. An empty string says so; inventing a localhost
        # port would send `llm.chat` looking for a daemon that will never exist.
        return ""
    return _OLLAMA_URL if backend == "ollama" else _VLLM_URL


def _serve_command(backend: str, model: str, base_url: str) -> str:
    """The shell command that brings ``model`` up on ``backend`` for this machine."""
    if backend == "ollama":
        return f"ollama pull {model}"
    if backend == "lightweight":
        # Nothing to bring up, but something to do: the first call pays for the
        # download, and a caller who discovers that inside a
        # job will think it hung. This command pays it deliberately instead.
        return f"best-engine-ai-helper lightweight prepare --model {model}"
    # vLLM: serve the HuggingFace model on the base URL's port (default 8000).
    port = urlparse(base_url).port or 8000
    return f"vllm serve {model} --port {port}"


def load_brief(brief: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Return the brief as a dict, whether given inline or as a YAML path."""
    if isinstance(brief, dict):
        return brief
    path = Path(brief)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Brief {path} is not a YAML mapping: {data!r}")
    return data


def resolve(
    brief: str | Path | dict[str, Any],
    *,
    backend: str = "auto",
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
    cloud_catalog: list[dict[str, Any]] | None = None,
    disk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve a usage brief into a concrete engine descriptor.

    The brief's ``mode`` selects local vs cloud (default ``local``):

    - ``local`` (default) -> a hardware-specific descriptor: the backend chosen
      for this machine (Ollama/vLLM) plus the model per kind.
    - ``cloud`` -> a provider descriptor (``provider``, ``model``, optional
      ``base_url``/``api_key_env``) plus a local ``fallback`` resolved from the
      SAME brief, so a failed paid call degrades to the always-available local
      model (paid -> local, the safe direction). ``model`` is OPTIONAL: when
      omitted, the best paid model is auto-picked from the bundled
      ``pricing.yaml`` catalog on a quality-vs-price trade-off (see
      :func:`_resolve_cloud` and :mod:`best_engine_ai_helper.cloud_catalog`).

    In ``local`` mode there is one escalation: when the conventional backend
    resolves nothing that FITS for a kind the brief needs, resolution consults
    :func:`offload.decide` and, if this machine can stream, rescues that kind
    alone with a layer-streamed model (``backend: lightweight`` inside the kind's
    own section — see :func:`model_for`). The descriptor records the decision
    and its reason under ``lightweight``, including when the answer was no. Set
    ``lightweight: never`` in the brief, or ``BEST_ENGINE_LIGHTWEIGHT=never``, to switch
    the escalation off.

    Parameters
    ----------
    brief : str | Path | dict
        The input brief (path to ``llm.brief.yaml`` or an already-loaded dict).
        Keys: ``mode`` (``local``/``cloud``, default ``local``), ``kind``
        (``llm``/``vlm``/``both``), ``headroom``, ``min_tps``,
        ``structured_output``, ``task`` (free text); cloud-only:
        ``provider``, ``model`` (both optional -> auto-pick), ``vlm_model``,
        ``base_url``, ``api_key_env``, ``quality_vs_cost`` (0..1, default
        :data:`cloud_catalog.DEFAULT_QUALITY_VS_COST`, only used when
        auto-picking); streaming-only: ``lightweight``
        (``auto``/``always``/``never``, default ``auto``) and
        ``lightweight`` (``auto``/``always``/``never``).
    backend : {'auto', 'ollama', 'vllm', 'lightweight'}
        ``auto`` picks per :func:`default_backend` — which never returns
        ``lightweight``: layer streaming is reached automatically only as a rescue
        (see below), and otherwise by naming it here. Local mode only.
    endpoint : str or None
        Override the server base URL (defaults to the local endpoint for the
        backend, or the provider's default API root for cloud mode).
    catalog, hw, compute : optional
        Injectable for tests; default to the live local catalog and detected
        hardware.
    cloud_catalog : optional
        Injectable for tests; defaults to the live ``pricing.yaml`` catalog.
        Cloud mode only, and only consulted when the brief omits ``model``.
    disk : optional
        Injectable storage profile (:func:`detect.disk_profile`). Read only on
        the layer-streaming path, where the drive bounds throughput.

    Returns
    -------
    dict
        The engine descriptor (see :func:`write_engine` for the on-disk shape).
    """
    spec = load_brief(brief)
    mode = str(spec.get("mode", "local")).strip().lower()
    if mode == "cloud":
        return _resolve_cloud(
            spec,
            endpoint=endpoint,
            catalog=catalog,
            hw=hw,
            compute=compute,
            cloud_catalog=cloud_catalog,
        )
    if mode != "local":
        osh.warning(f"Unknown brief mode {mode!r}; treating as 'local'.")
    return _resolve_local(
        spec,
        backend=backend,
        endpoint=endpoint,
        catalog=catalog,
        hw=hw,
        compute=compute,
        disk=disk,
    )


def _resolve_local(
    spec: dict[str, Any],
    *,
    backend: str = "auto",
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
    disk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a ``mode: local`` brief into a hardware-specific descriptor."""
    from . import catalog as _catalog
    from . import detect as _detect
    from . import offload as _offload
    from .recommend import recommend as _recommend

    if backend == "auto":
        backend = default_backend()
    if backend not in _VALID_BACKENDS:
        raise ValueError(f"backend must be one of {_VALID_BACKENDS} or 'auto', got {backend!r}")

    headroom = min(float(spec.get("headroom", MAX_HEADROOM)), MAX_HEADROOM)
    min_tps = float(spec.get("min_tps", COMFORT_TPS))
    # A brief that says nothing about streaming gets `auto`, which only fires
    # when the conventional backend comes back empty. `--backend lightweight` is the
    # manual door and does not consult this.
    stream_request = _offload.requested(spec.get("lightweight"))
    kinds = _kinds_from_brief(spec.get("kind", "both"))
    task = spec.get("task")
    # The brief's own word on whether the job needs schema-constrained output.
    # Absent means "did not say", which keeps the gate on: the helper's own
    # tasks go through a JSON schema, so widening by default would be the
    # wrong direction. Only an explicit `false` relaxes it -- and that case
    # used to be read on the cloud path and ignored here, so a consumer that
    # does not need schemas was denied the better model for nothing.
    require_structured = spec.get("structured_output") is not False

    hw = hw if hw is not None else _detect.available_memory()
    compute = compute if compute is not None else _detect.compute_profile()
    catalog = catalog if catalog is not None else _catalog.load_catalog()
    # The catalog is a catalog of models; this backend can only run some of
    # them. Auto-refreshed sources key entries by a directory slug rather than
    # by a pull tag, and recommending one of those produced a descriptor
    # naming a model the server cannot load — a failure at the first call
    # instead of at resolution, which is the worst possible place for it.
    before = len(catalog)
    catalog = _catalog.servable_only(catalog, backend)
    if before and not catalog:
        # Unresolved is a warning here, never an exception: an empty catalog
        # already leaves each kind null rather than raising deep inside the
        # picker, and a catalog emptied by this filter is the same situation.
        osh.warning(
            f"No catalog entry can be served by {backend}: every candidate comes from "
            "a source that names models by slug rather than by pull tag. Run "
            "`best-engine-ai-helper catalog update`, or resolve for another backend."
        )
    base_url = _base_url(backend, endpoint)

    if backend == "lightweight":
        # Asked for by name. `decide` is still consulted — not to veto the
        # request, but so an unusable machine is told why here instead of at
        # the first generate() call — and `never` still wins, because an
        # environment that switched streaming off meant it.
        decision = _offload.decide(
            request="never" if stream_request == "never" else "always",
            compute=compute,
            disk=disk,
        )
        return _resolve_streaming(
            spec,
            kinds=kinds,
            task=task,
            headroom=headroom,
            hw=hw,
            compute=compute,
            disk=decision["disk"],
            catalog=catalog,
            decision=decision,
            min_tps=spec.get("min_tps"),
        )

    # What the daemon has right now. Asked before ranking rather than after, so
    # the list can break a tie between two comparable candidates instead of only
    # annotating the winner after the fact.
    present: set[str] = set()
    if backend == "ollama":
        from .pull import installed_tags

        present = installed_tags(base_url)

    report = _recommend(
        hw,
        catalog,
        task,
        headroom=headroom,
        compute=compute,
        min_tps=min_tps,
        require_structured=require_structured,
        backend=backend,
        kinds=kinds,
        installed=present,
    )

    memory_gb = hw.get("unified_gb") or hw.get("vram_gb") or hw.get("ram_gb")
    engine: dict[str, Any] = {
        "generated_by": "best-engine-ai-helper — machine-specific, do not commit",
        "mode": "local",
        "resolved_for": {
            "chip": compute.get("chip") or _detect.chip_vendor(),
            "accelerator": compute.get("accelerator"),
            "memory_gb": round(float(memory_gb), 1) if memory_gb else None,
        },
        "backend": backend,
        "base_url": base_url,
        "headroom": headroom,
        "min_tps": min_tps,
    }

    serve: list[str] = []
    for kind in kinds:
        chosen = (report.get("recommendations", {}).get(kind) or {}).get("chosen")
        if not chosen:
            osh.warning(f"No {kind} model could be resolved for this machine.")
            engine[kind] = None
            continue
        # Ollama uses the pull tag; vLLM uses the HuggingFace id when known.
        if backend == "ollama":
            model = chosen["id"]
        else:
            model = chosen.get("vllm_id") or chosen["id"]
            if not chosen.get("vllm_id"):
                osh.warning(
                    f"{kind} model {chosen['id']} has no vLLM HuggingFace id; "
                    f"the serve command uses the raw tag and may need adjusting."
                )
        engine[kind] = {
            "model": model,
            "ram_gb": chosen["ram_gb"],
            "est_tokens_per_s": chosen["est_tokens_per_s"],
            # Whether that figure was measured on this machine or estimated
            # from memory bandwidth. The engine file is the artefact other
            # packages read, and every other number in it already says where
            # it came from; this one used to be the exception.
            "tps_basis": chosen.get("tps_basis"),
            "structured_output": chosen["structured_output"],
            "score": chosen["score"],
            "fits": chosen["fits"],
            "comfortable": chosen["comfortable"],
        }
        if backend == "ollama" and present:
            # "Resolved" and "runnable" are different claims, and a caller
            # that cannot tell them apart discovers the difference at its
            # first inference call — usually in the middle of a long job.
            ready = model in present
            engine[kind]["available"] = ready
            if not ready:
                engine[kind]["pull"] = f"ollama pull {model}"
                osh.warning(
                    f"{kind} model {model} is not on this Ollama daemon yet: "
                    f"run `ollama pull {model}` before the first call."
                )
        cmd = _serve_command(backend, model, base_url)
        if cmd not in serve:
            serve.append(cmd)

    engine["serve"] = serve

    # The automatic trigger. A kind is "unrescued" when the conventional
    # backend found nothing for it, or found only something that does not fit
    # this machine's budget -- in both cases the caller has no usable model,
    # which is the one situation where trading three orders of magnitude of
    # speed for capability is the better deal.
    unrescued = [k for k in kinds if not (engine.get(k) or {}).get("fits")]
    if unrescued and stream_request != "never":
        decision = _offload.decide(
            request=stream_request,
            conventional_resolved=False,
            compute=compute,
            disk=disk,
        )
        engine["lightweight"] = {
            "activate": decision["activate"],
            "trigger": decision["trigger"],
            "reason": decision["reason"],
            "runtime": decision["runtime"],
            "installed": decision["installed"],
            "blockers": decision["blockers"],
            "kinds": unrescued,
        }
        if decision["activate"]:
            streamed = _resolve_streaming(
                spec,
                kinds=unrescued,
                task=task,
                headroom=headroom,
                hw=hw,
                compute=compute,
                disk=decision["disk"],
                catalog=_catalog.load_catalog(),
                decision=decision,
                min_tps=spec.get("min_tps"),
            )
            rescued: list[str] = []
            for kind in unrescued:
                section = streamed.get(kind)
                if not section:
                    continue
                rescued.append(kind)
                # The descriptor stays on its conventional backend and the
                # rescued kind carries its own, so a mixed engine file
                # (Ollama for the LLM, streaming for the VLM) says exactly
                # that. `model_for` reads the per-kind value first.
                engine[kind] = section
                osh.warning(
                    f"No {kind} model fits this machine, so {kind} fell back to layer "
                    f"streaming: {section['model']} at ~{section.get('seconds_per_token')} "
                    "s/token. This is a batch-grade speed, not an interactive one."
                )
            # What the rescue actually achieved, which is not always what it
            # set out to do: a machine small enough that nothing fits in
            # memory can also be small enough that no single layer
            # fits. `activate: true` with an empty `rescued` is that case,
            # and it has to be visible rather than inferred from the absence
            # of a change.
            engine["lightweight"]["rescued"] = rescued
            if not rescued:
                osh.warning(
                    "Layer streaming was activated but rescued nothing: no catalog "
                    "entry fits both one resident layer and the disk its checkpoint "
                    "split needs on this machine."
                )
            for cmd in streamed.get("serve", []):
                if cmd not in engine["serve"]:
                    engine["serve"].append(cmd)

    return engine


def _resolve_streaming(
    spec: dict[str, Any],
    *,
    kinds: list[Literal["llm", "vlm"]],
    task: str | None,
    headroom: float,
    hw: dict[str, float | None],
    compute: dict[str, Any],
    disk: dict[str, Any],
    catalog: list[dict[str, Any]],
    decision: dict[str, Any],
    min_tps: float | str | None = None,
) -> dict[str, Any]:
    """
    Resolve a brief against the layer-streaming backend.

    Deliberately the SAME pipeline as every other backend —
    :func:`recommend.recommend` with ``backend='lightweight'`` — rather than a second
    picker. The backend-specific parts (one layer instead of the whole model, a
    disk-bound rate) already live in ``score``/``offload``, so routing through
    the common path keeps one ranking, one report shape, and one place where the
    four decision factors are applied.

    Parameters
    ----------
    spec : dict[str, Any]
        The brief.
    kinds : list of {'llm', 'vlm'}
        Kinds to resolve. The automatic trigger passes only the unrescued ones.
    task : str or None
        The brief's free-text task, for the benchmark axis.
    headroom : float
        Memory safety fraction, already clamped.
    hw, compute, disk : dict
        Detected hardware, compute profile and storage profile.
    catalog : list of dict
        Catalog entries, not yet filtered for this backend.
    decision : dict[str, Any]
        The :func:`offload.decide` verdict that got us here, echoed into the
        descriptor so the file records WHY it names a streamed model.
    min_tps : float or str or None
        The brief's ``min_tps`` if it set one (YAML may hand it over as a
        string). When it did not, the floor
        becomes :data:`offload.COMFORT_TPS_STREAMING` instead of the 15 tok/s
        interactive default — a floor written for a resident model would reject
        every streamed candidate and report "nothing fits" about a backend whose
        entire purpose is to fit.

    Returns
    -------
    dict[str, Any]
        An engine descriptor with ``backend: lightweight``, a per-kind section, and
        the streaming facts a caller needs: resident layer size, checkpoint
        size, disk requirement, and seconds per token.
    """
    from . import catalog as _catalog
    from . import offload as _offload
    from .recommend import recommend as _recommend

    floor = float(min_tps) if min_tps is not None else _offload.COMFORT_TPS_STREAMING
    rows = _catalog.servable_only(catalog, "lightweight")
    if catalog and not rows:
        osh.warning(
            "No catalog entry can be streamed: layer streaming loads safetensors "
            "from the HuggingFace Hub, and no entry names a repository "
            "(`hf_id`/`vllm_id`). Run `best-engine-ai-helper catalog update`."
        )

    # `recommend` supplies the candidate table: the right footprints, the right
    # disk-bound rates, the right benchmark axis per kind. What it must NOT
    # supply here is the PICK — its anti-greed selector takes the leanest model
    # within a quality band, and under streaming that lands on an 8B checkpoint
    # (see offload.pick for why that is the one senseless answer). So the table
    # comes from the common pipeline and the choice from the streaming rule.
    report = _recommend(
        hw,
        rows,
        task,
        headroom=headroom,
        compute=compute,
        min_tps=floor,
        # Streaming has no schema enforcement at all (the runtime exposes raw
        # generation), so requiring structured output would disqualify the
        # whole pool. The brief's own wish is honoured by the warning below
        # rather than by a filter that can only ever return nothing.
        require_structured=False,
        backend="lightweight",
        kinds=kinds,
        disk=disk,
    )
    # Same figure the report just used (recommend switches to the streaming
    # budget for this backend); read from the report rather than recomputed, so
    # the table's `fits` column and the pick can never disagree.
    budget_gb = report["memory_budget_gb"]

    memory_gb = hw.get("unified_gb") or hw.get("vram_gb") or hw.get("ram_gb")
    engine: dict[str, Any] = {
        "generated_by": "best-engine-ai-helper — machine-specific, do not commit",
        "mode": "local",
        "resolved_for": {
            "chip": compute.get("chip"),
            "accelerator": compute.get("accelerator"),
            "memory_gb": round(float(memory_gb), 1) if memory_gb else None,
            "storage": disk.get("storage"),
            "disk_read_gbs": disk.get("read_gbs"),
            "disk_read_basis": disk.get("basis"),
        },
        "backend": "lightweight",
        # No URL, on purpose: lightweight is a library and runs in the caller's own
        # process. `llm.chat` dispatches on the backend name, not on a port.
        "base_url": "",
        "headroom": headroom,
        "min_tps": floor,
        "lightweight": {
            "activate": decision["activate"],
            "trigger": decision["trigger"],
            "reason": decision["reason"],
            "runtime": decision["runtime"],
            "installed": decision["installed"],
            "blockers": decision["blockers"],
            "install": _offload.INSTALL_HINT,
        },
    }

    serve: list[str] = []
    for kind in kinds:
        axis_scores = {
            str(row.get("id")): row.get("score")
            for row in (report.get("recommendations", {}).get(kind) or {}).get("candidates", [])
        }
        plans = _offload.rank(
            rows,
            budget_gb=budget_gb,
            disk=disk,
            prefetching=True,
            kind=kind,
        )
        # Score on the TASK's axis, not the generic one `rank` carried, so a
        # vision brief chooses between two streamable giants on vision.
        for row in plans:
            if row["catalog_id"] in axis_scores:
                row["score"] = axis_scores[str(row["catalog_id"])]
        plan = _offload.pick(plans)
        if plan is None:
            osh.warning(
                f"No {kind} model can be streamed on this machine: nothing in the "
                "catalog fits both one resident layer and the disk its checkpoint "
                "split needs."
            )
            engine[kind] = None
            continue
        engine[kind] = {
            "model": plan["model"],
            "catalog_id": plan["catalog_id"],
            # Named `backend` per kind so a MIXED descriptor is readable: the
            # automatic trigger rescues one kind and leaves the other alone.
            "backend": "lightweight",
            "base_url": "",
            "streaming": True,
            "ram_gb": plan["resident_gb"],
            "checkpoint_gb": plan["checkpoint_gb"],
            "layers": plan["layers"],
            "layers_estimated": plan["layers_estimated"],
            "disk_peak_gb": plan["disk"]["peak_gb"],
            "disk_steady_gb": plan["disk"]["steady_gb"],
            "disk_fits": plan["disk_fits"],
            "est_tokens_per_s": plan["est_tokens_per_s"],
            "seconds_per_token": plan["seconds_per_token"],
            "tps_basis": "estimated",
            # A fact about the backend, not about the weights: lightweight has no
            # equivalent of Ollama's `format=<schema>`.
            "structured_output": False,
            "score": plan.get("score"),
            "fits": plan["fits"],
            "comfortable": plan["usable"],
            "blockers": plan["blockers"],
        }
        for blocker in plan["blockers"]:
            osh.warning(f"{kind} streaming candidate {plan['model']}: {blocker}.")
        if spec.get("structured_output") is not False:
            osh.warning(
                f"The brief wants schema-constrained output and {kind} resolved to a "
                "streamed model, which cannot honour one. Schema-driven calls must "
                "stay on an Ollama model."
            )
        cmd = _serve_command("lightweight", plan["model"], "")
        if cmd not in serve:
            serve.append(cmd)

    engine["serve"] = serve
    return engine


def _auto_pick_cloud(
    spec: dict[str, Any],
    kinds: list[Literal["llm", "vlm"]],
    provider_pin: str | None,
    cloud_catalog: list[dict[str, Any]] | None,
) -> tuple[str, dict[Literal["llm", "vlm"], dict[str, Any]]]:
    """Auto-pick a provider + one model per kind from the paid-model catalog.

    Anchors on the ``vlm`` kind first when needed (fewer providers offer
    vision, so anchoring there and then constraining the ``llm`` pick to the
    SAME provider is more likely to succeed than the reverse) — one provider
    serves the whole engine, the same rule :func:`_resolve_local` applies to
    the backend (one Ollama/vLLM backend for both kinds).

    Parameters
    ----------
    spec : dict
        The cloud brief (for ``task`` and ``quality_vs_cost``).
    kinds : list of {'llm', 'vlm'}
        Kinds the engine needs.
    provider_pin : str or None
        Restrict the pick to one provider (from ``spec['provider']``), or
        None to search every provider in the catalog.
    cloud_catalog : list[dict[str, Any]] or None
        Injectable for tests; defaults to :func:`cloud_catalog.load_cloud_catalog`.

    Returns
    -------
    tuple[str, dict]
        ``(provider, {kind: catalog_entry})`` — the chosen provider and the
        winning catalog entry for each requested kind.

    Raises
    ------
    ValueError
        If the catalog is empty, or no candidate matches the anchor kind
        (and ``provider_pin``, if given).
    """
    from . import cloud_catalog as _cc
    from .recommend import parse_task

    cc = cloud_catalog if cloud_catalog is not None else _cc.load_cloud_catalog()
    if not cc:
        raise ValueError(
            "mode: cloud with no 'model' asks for an auto-pick, but no cloud "
            "catalog is available (pricing.yaml missing or empty). Fix "
            "pricing.yaml, or pin 'provider' and 'model' explicitly instead."
        )

    parsed = parse_task(spec.get("task"))
    weight = float(spec.get("quality_vs_cost", _cc.DEFAULT_QUALITY_VS_COST))

    anchor_kind: Literal["llm", "vlm"] = "vlm" if "vlm" in kinds else "llm"
    anchor_axis = parsed["vlm_application"] if anchor_kind == "vlm" else parsed["application"]
    anchor = _cc.pick_cloud(cc, anchor_kind, anchor_axis, weight, provider=provider_pin)
    if not anchor:
        raise ValueError(
            f"mode: cloud auto-pick found no {anchor_kind} model in the catalog"
            + (f" from provider {provider_pin!r}" if provider_pin else "")
            + ". Pin 'provider' and 'model' explicitly instead."
        )

    provider = str(anchor["provider"]).strip().lower()
    picks: dict[Literal["llm", "vlm"], dict[str, Any]] = {anchor_kind: anchor}
    for kind in kinds:
        if kind == anchor_kind:
            continue
        axis = parsed["vlm_application"] if kind == "vlm" else parsed["application"]
        chosen = _cc.pick_cloud(cc, kind, axis, weight, provider=provider)
        if not chosen:
            osh.warning(
                f"No cloud {kind} model from provider {provider!r}; reusing "
                f"the {anchor_kind} pick {anchor['id']!r} for {kind} too."
            )
            chosen = anchor
        picks[kind] = chosen

    osh.info(
        f"Auto-picked cloud provider={provider} (quality_vs_cost={weight}): "
        + ", ".join(f"{k}={v['id']}" for k, v in picks.items())
    )
    return provider, picks


def _resolve_cloud(
    spec: dict[str, Any],
    *,
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
    cloud_catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a ``mode: cloud`` brief: a provider primary + a local fallback.

    The primary is declarative (provider, model, base_url, api-key env *name*);
    the ``fallback`` is a full local descriptor resolved from the same brief, so
    a failed paid call can degrade to the always-available local model — the safe
    direction (paid -> local). ``llm.chat`` reads ``api_key_env`` to look the key
    up (env var, then optionally the OS keychain via ``keyring``) — the key
    VALUE is never read or stored here.

    ``model`` is optional. When given, ``provider``/``model``/``vlm_model`` are
    used exactly as written (the pre-existing, manual-pin behaviour). When
    omitted, the best paid model per kind is auto-picked from the bundled
    ``pricing.yaml`` catalog on a quality-vs-price trade-off — see
    :func:`_auto_pick_cloud` and :mod:`best_engine_ai_helper.cloud_catalog`.
    ``provider``, if also given, restricts the auto-pick to that provider
    instead of searching every provider in the catalog.

    Parameters
    ----------
    spec : dict
        The loaded brief with ``mode: cloud``. ``provider`` and ``model`` are
        both optional (omit both, or ``model`` alone, to auto-pick). Optional:
        ``vlm_model``, ``base_url``, ``api_key_env``, ``structured_output``,
        ``kind``, ``task`` (drives the auto-pick's benchmark axis),
        ``quality_vs_cost`` (0..1, auto-pick only, default
        :data:`cloud_catalog.DEFAULT_QUALITY_VS_COST`).
    endpoint, catalog, hw, compute : optional
        See :func:`resolve`.
    cloud_catalog : optional
        Injectable for tests; see :func:`resolve`.

    Returns
    -------
    dict
        Engine descriptor with ``mode: cloud``, ``backend`` = provider name,
        per-kind ``model``/``structured_output``/``cloud: True``, and
        ``fallback`` = a full local engine descriptor (or None if none could
        be resolved).
    """
    provider = spec.get("provider")
    model = spec.get("model")
    kinds = _kinds_from_brief(spec.get("kind", "both"))
    structured_override = spec.get("structured_output")  # None unless explicitly set

    picks: dict[Literal["llm", "vlm"], dict[str, Any]] = {}
    model_by_kind: dict[Literal["llm", "vlm"], str] = {}
    if not model:
        provider_pin = str(provider).strip().lower() if provider else None
        provider, picks = _auto_pick_cloud(spec, kinds, provider_pin, cloud_catalog)
        model_by_kind = {k: cast(str, v["id"]) for k, v in picks.items()}
        log_model = model_by_kind.get("llm") or model_by_kind.get("vlm")
    else:
        provider = str(provider or "openai").strip().lower()
        vlm_model = spec.get("vlm_model") or model
        model_by_kind = {"llm": model, "vlm": vlm_model}
        log_model = model

    base_url = endpoint or spec.get("base_url") or _CLOUD_BASE_URLS.get(provider, "")
    api_key_env = spec.get("api_key_env") or _DEFAULT_API_KEY_ENV.get(provider)

    engine: dict[str, Any] = {
        "generated_by": "best-engine-ai-helper — machine-specific, do not commit",
        "mode": "cloud",
        "backend": provider,
        "base_url": base_url,
        # NAME of the env var holding the key — never the key value itself.
        "api_key_env": api_key_env,
    }
    for kind in kinds:
        if structured_override is not None:
            structured = bool(structured_override)
        elif kind in picks:
            structured = bool(picks[kind].get("structured_output", True))
        else:
            structured = True
        engine[kind] = {
            "model": model_by_kind[kind],
            "structured_output": structured,
            "cloud": True,
        }
    engine["serve"] = []

    # Local backup resolved from the SAME brief, so a failed paid call degrades to
    # the always-available local model (paid -> local, the safe direction).
    local_spec = {k: v for k, v in spec.items() if k != "mode"}
    try:
        engine["fallback"] = _resolve_local(
            local_spec, backend="auto", catalog=catalog, hw=hw, compute=compute
        )
    except Exception as exc:  # a missing local model must not break cloud resolution
        osh.warning(f"Could not resolve a local fallback for the cloud engine: {exc}")
        engine["fallback"] = None

    osh.info(f"Resolved cloud engine: provider={provider}, model={log_model} (+ local fallback)")
    return engine


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically: no reader ever sees a partial write.

    Writes to a sibling temp file in the same directory (so the final
    ``os.replace`` is a same-filesystem rename, not a cross-filesystem copy)
    then renames it over the destination. A crash or a concurrent
    :func:`load_engine` mid-write sees either the old engine file or the
    fully-written new one, never a truncated one -- unlike ``catalog``'s
    cache loader, ``load_engine`` has no ``try/except`` around a malformed
    YAML parse, so a truncated read here would crash the caller outright.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_engine(engine: dict[str, Any], path: str | Path) -> Path:
    """Write an engine descriptor to ``path`` as YAML with a do-not-commit header.

    The file is machine-specific (it encodes the chosen backend and models for
    *this* hardware), so it belongs in ``.gitignore``, not in version control.
    """
    path = Path(path)
    header = (
        "# GENERATED by best-engine-ai-helper — do NOT commit.\n"
        "# Hardware-specific: the backend and models chosen for THIS machine.\n"
        "# Regenerate with:  best-engine-ai-helper resolve --brief "
        f"{BRIEF_NAME} --out {path.name}\n\n"
    )
    body = yaml.safe_dump(engine, sort_keys=False, allow_unicode=True)
    _atomic_write_text(path, header + body)
    osh.info(f"Wrote engine descriptor:\n\t{path}")
    return path


def load_engine(path: str | Path) -> dict[str, Any]:
    """Read an engine descriptor written by :func:`write_engine`."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Engine file {path} is not a YAML mapping: {data!r}")
    return data


def ensure(
    directory: str | Path = ".",
    *,
    brief: str = BRIEF_NAME,
    engine: str = ENGINE_NAME,
    backend: str = "auto",
    endpoint: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """
    Return the engine descriptor for a repo, resolving it on first use.

    Missing-file policy (the suite contract):

    - the **engine** file exists  -> load and return it (fast path, no detection);
    - it is missing but the **brief** exists -> resolve from the brief, write the
      engine file (unless ``write=False``), and return it;
    - **both** are missing -> raise. A committed brief is mandatory; its absence
      is a real bug, not a machine that has not run detection yet.

    Parameters
    ----------
    directory : str | Path
        Repo directory holding the two contract files.
    brief, engine : str
        Filenames within ``directory`` (default to the suite canonical names).
    backend, endpoint : see :func:`resolve`.
    write : bool
        Persist a freshly resolved engine file. ``False`` resolves in-memory only.
    """
    directory = Path(directory)
    engine_path = directory / engine
    brief_path = directory / brief

    if engine_path.is_file():
        osh.debug(f"Using existing engine file:\n\t{engine_path}")
        return load_engine(engine_path)

    if not brief_path.is_file():
        raise RuntimeError(
            f"No engine file ({engine_path}) and no brief ({brief_path}) to "
            f"resolve one from. Commit a {brief} describing this repo's LLM/VLM "
            f"usage, then run: best-engine-ai-helper resolve --brief {brief} "
            f"--out {engine}"
        )

    osh.info(f"No engine file yet; resolving from brief:\n\t{brief_path}")
    resolved = resolve(brief_path, backend=backend, endpoint=endpoint)
    if write:
        write_engine(resolved, engine_path)
    return resolved


def model_for(engine: dict[str, Any], kind: str) -> tuple[str, str, str]:
    """Return ``(backend, base_url, model)`` for ``kind`` from an engine descriptor.

    Raises ``KeyError`` if the descriptor has no entry for ``kind`` (e.g. asking
    for a VLM from an engine resolved for an ``llm``-only brief).

    Examples
    --------
    >>> engine = {"backend": "ollama", "base_url": "http://localhost:11434",
    ...           "llm": {"model": "qwen3:14b"}}
    >>> model_for(engine, "llm")
    ('ollama', 'http://localhost:11434', 'qwen3:14b')
    >>> # A kind that fell back to streaming carries its own backend.
    >>> engine["vlm"] = {"model": "Qwen/Qwen2.5-VL-72B-Instruct", "backend": "lightweight"}
    >>> model_for(engine, "vlm")
    ('lightweight', '', 'Qwen/Qwen2.5-VL-72B-Instruct')
    """
    section = engine.get(kind)
    if not section or not section.get("model"):
        raise KeyError(
            f"Engine has no usable '{kind}' model; the brief may not request it, "
            f"or resolution found none for this machine."
        )
    # A kind may override the descriptor's backend. That happens when nothing
    # fit this machine for THAT kind and resolution fell back to layer
    # streaming for it alone — a mixed descriptor (Ollama for the LLM, lightweight
    # for the VLM) is the honest outcome, and a consumer reading the top-level
    # backend for every kind would send a streaming model to an Ollama URL.
    backend = str(section.get("backend") or engine["backend"])
    base_url = section.get("base_url", engine["base_url"] if backend == engine["backend"] else "")
    return backend, str(base_url), section["model"]


def diagnose(
    directory: str | Path = ".",
    *,
    engine: str = ENGINE_NAME,
    timeout: float = 1.5,
) -> dict[str, Any]:
    """
    Compare what the engine file *resolved* against what the daemon can *serve*.

    These are two different claims and they drift apart quietly. An engine file
    is written once, on the machine and catalog of that moment; the daemon it
    names is mutable, and `ollama rm` leaves no trace in the descriptor. Today
    the gap surfaces at the first inference call, which is typically in the
    middle of a job rather than at resolution — the worst possible moment to
    learn that a model name was never pullable.

    So this asks both sides and reports the difference. It diagnoses only: a
    command that silently re-resolved would hide the very drift it exists to
    show.

    Parameters
    ----------
    directory : str | Path
        Repo directory holding the engine file.
    engine : str
        Engine filename within ``directory``.
    timeout : float
        Seconds to wait on the daemon. Short: an unreachable daemon is a
        finding here, not a reason to hang.

    Returns
    -------
    dict
        ``{"engine_path", "backend", "daemon_reachable", "served",
        "findings": [{kind, model, message}], "ok"}``. ``ok`` is True only when
        every model the file names can be served right now.
    """
    directory = Path(directory)
    engine_path = directory / engine
    report: dict[str, Any] = {
        "engine_path": str(engine_path),
        "backend": None,
        "daemon_reachable": False,
        "served": [],
        "findings": [],
        "ok": False,
    }

    if not engine_path.is_file():
        report["findings"].append(
            {
                "kind": None,
                "model": None,
                "message": (
                    f"No engine file at {engine_path}. Run `resolve` first, or point "
                    "`--directory` at the repo that holds one."
                ),
            }
        )
        return report

    descriptor = load_engine(engine_path)
    backend = str(descriptor.get("backend") or "ollama")
    report["backend"] = backend

    # Only Ollama can be asked what it holds. For anything else the honest
    # answer is "cannot tell from here", which is a finding rather than a pass.
    if backend != "ollama":
        report["findings"].append(
            {
                "kind": None,
                "model": None,
                "message": (
                    f"Backend is {backend!r}, which this check cannot interrogate; "
                    "only an Ollama daemon reports the tags it serves."
                ),
            }
        )
        return report

    from .pull import installed_tags

    served = installed_tags(str(descriptor.get("base_url") or "") or None, timeout=timeout)
    report["served"] = sorted(served)
    report["daemon_reachable"] = bool(served)

    if not served:
        report["findings"].append(
            {
                "kind": None,
                "model": None,
                "message": (
                    f"No Ollama daemon answered at {descriptor.get('base_url')}. "
                    "Nothing the file names can be served until it is running."
                ),
            }
        )
        return report

    named = 0
    for kind in ("llm", "vlm"):
        block = descriptor.get(kind)
        if not isinstance(block, dict):
            continue
        model = str(block.get("model") or "")
        if not model:
            continue
        named += 1
        # Plain membership is both necessary and sufficient: `pull.installed_tags`
        # already adds the bare form for a `:latest` tag and only for that, so a
        # looser `name.split(":")[0]` test would call `gemma3:12b` installed when
        # the daemon holds nothing but `gemma3:latest` -- a different model.
        if model in served:
            continue
        report["findings"].append(
            {
                "kind": kind,
                "model": model,
                "message": (
                    f"{kind}: the engine file names {model!r}, which this daemon does "
                    f"not serve. Run `ollama pull {model}`, or re-resolve."
                ),
            }
        )

    if named == 0:
        report["findings"].append(
            {
                "kind": None,
                "model": None,
                "message": "The engine file names no model for either kind.",
            }
        )

    report["ok"] = not report["findings"]
    return report
