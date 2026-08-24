"""
engine — resolve a repo's LLM/VLM usage brief into a concrete serving engine.

The suite's model-selection contract has two YAML files per consumer repo:

1. an **input brief** (committed, hardware-independent) describing what the repo
   needs from an LLM/VLM — the kinds, memory headroom, comfort floor, and a
   free-text ``task``; and
2. an **output engine** file (gitignored, machine-specific) this module writes:
   the backend chosen for the current machine plus the concrete model per kind,
   sized realistically for that backend.

Backend rule (``resolve(..., backend="auto")``): **vLLM only when a real
discrete GPU (NVIDIA/AMD) is detected; otherwise Ollama** — so macOS, CPU-only
Linux, and Intel-iGPU machines all use Ollama, and only a CUDA/ROCm box gets
vLLM. This keeps picks realistic (vLLM on plain CPU is the weak path). When vLLM
gains an Apple-Silicon runtime, widening this rule is the only change needed.

No ``DEFAULT_MODEL`` constant lives in any consumer: the model is always read
from the resolved engine file. :func:`ensure` is the missing-file policy — a
missing engine file is auto-resolved from the brief; a missing *brief* is a hard
error, because the brief is committed and its absence is a real bug.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
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

_VALID_BACKENDS = ("ollama", "vllm")

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


# Accelerator vendors that have a real (fast) vLLM runtime today. A discrete
# CUDA (NVIDIA) or ROCm (AMD) GPU gets vLLM; Apple Silicon, Intel iGPUs, and
# CPU-only machines fall back to Ollama, where vLLM is either unsupported or too
# slow to be realistic.
_VLLM_VENDORS = frozenset({"nvidia", "amd"})


def default_backend() -> str:
    """Return the backend for the current machine.

    **vLLM** only when a real discrete GPU (NVIDIA/AMD) is detected; **Ollama**
    everywhere else (macOS, CPU-only Linux, Intel iGPU). Endgame: when vLLM runs
    well on Mac and CPU-only Linux too, replace this whole body with
    ``return "vllm"`` and the suite is fully on vLLM.
    """
    from .detect import chip_vendor

    return "vllm" if chip_vendor() in _VLLM_VENDORS else "ollama"


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
    return _OLLAMA_URL if backend == "ollama" else _VLLM_URL


def _serve_command(backend: str, model: str, base_url: str) -> str:
    """The shell command that brings ``model`` up on ``backend`` for this machine."""
    if backend == "ollama":
        return f"ollama pull {model}"
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
        auto-picking).
    backend : {'auto', 'ollama', 'vllm'}
        ``auto`` picks per :func:`default_backend`; an explicit value forces it.
        Local mode only.
    endpoint : str or None
        Override the server base URL (defaults to the local endpoint for the
        backend, or the provider's default API root for cloud mode).
    catalog, hw, compute : optional
        Injectable for tests; default to the live local catalog and detected
        hardware.
    cloud_catalog : optional
        Injectable for tests; defaults to the live ``pricing.yaml`` catalog.
        Cloud mode only, and only consulted when the brief omits ``model``.

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
        spec, backend=backend, endpoint=endpoint, catalog=catalog, hw=hw, compute=compute
    )


def _resolve_local(
    spec: dict[str, Any],
    *,
    backend: str = "auto",
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a ``mode: local`` brief into a hardware-specific descriptor."""
    from . import catalog as _catalog
    from . import detect as _detect
    from .recommend import recommend as _recommend

    if backend == "auto":
        backend = default_backend()
    if backend not in _VALID_BACKENDS:
        raise ValueError(f"backend must be one of {_VALID_BACKENDS} or 'auto', got {backend!r}")

    headroom = min(float(spec.get("headroom", MAX_HEADROOM)), MAX_HEADROOM)
    min_tps = float(spec.get("min_tps", COMFORT_TPS))
    kinds = _kinds_from_brief(spec.get("kind", "both"))
    task = spec.get("task")

    hw = hw if hw is not None else _detect.available_memory()
    compute = compute if compute is not None else _detect.compute_profile()
    catalog = catalog if catalog is not None else _catalog.load_catalog()
    base_url = _base_url(backend, endpoint)

    report = _recommend(
        hw,
        catalog,
        task,
        headroom=headroom,
        compute=compute,
        min_tps=min_tps,
        backend=backend,
        kinds=kinds,
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
            "structured_output": chosen["structured_output"],
            "score": chosen["score"],
            "fits": chosen["fits"],
            "comfortable": chosen["comfortable"],
        }
        cmd = _serve_command(backend, model, base_url)
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
    """
    section = engine.get(kind)
    if not section or not section.get("model"):
        raise KeyError(
            f"Engine has no usable '{kind}' model; the brief may not request it, "
            f"or resolution found none for this machine."
        )
    return engine["backend"], engine["base_url"], section["model"]
