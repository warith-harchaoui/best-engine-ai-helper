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
) -> dict[str, Any]:
    """
    Resolve a usage brief into a concrete engine descriptor.

    The brief's ``mode`` selects local vs cloud (default ``local``):

    - ``local`` (default) -> a hardware-specific descriptor: the backend chosen
      for this machine (Ollama/vLLM) plus the model per kind.
    - ``cloud`` -> **not available on this branch.** Cloud providers (with a
      paid → local fallback), plus cost, failover, pseudonymization and NSFW
      safety, ship on the ``cloud`` branch (experimental); ``mode: cloud``
      raises ``NotImplementedError`` here. The field is recognised now so
      briefs can declare intent forward-compatibly.

    Parameters
    ----------
    brief : str | Path | dict
        The input brief (path to ``llm.brief.yaml`` or an already-loaded dict).
        Keys: ``mode`` (``local``/``cloud``, default ``local``), ``kind``
        (``llm``/``vlm``/``both``), ``headroom``, ``min_tps``,
        ``structured_output``, ``task`` (free text).
    backend : {'auto', 'ollama', 'vllm'}
        ``auto`` picks per :func:`default_backend`; an explicit value forces it.
    endpoint : str or None
        Override the server base URL (defaults to the local endpoint for the
        backend).
    catalog, hw, compute : optional
        Injectable for tests; default to the live catalog and detected hardware.

    Returns
    -------
    dict
        The engine descriptor (see :func:`write_engine` for the on-disk shape).
    """
    spec = load_brief(brief)
    mode = str(spec.get("mode", "local")).strip().lower()
    if mode == "cloud":
        raise NotImplementedError(
            "mode: cloud is not available on this branch. Cloud providers "
            "(paid -> local fallback), cost accounting, failover, "
            "pseudonymization and NSFW safety ship on the 'cloud' branch."
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
    path.write_text(header + body, encoding="utf-8")
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
