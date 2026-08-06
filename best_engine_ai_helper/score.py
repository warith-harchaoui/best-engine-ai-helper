"""
score — select the best model for the current hardware.

Given the detected memory pool and the merged catalog, this module picks the
highest-scoring model that fits within a safety headroom. The algorithm is
intentionally simple: filter, then sort by benchmark score, then take the max.

Memory priority mirrors what Ollama uses at runtime:
  unified_gb (Apple Silicon) > vram_gb (discrete GPU) > ram_gb * 0.5 (CPU)

The 0.5 factor for CPU RAM is conservative; a model loader competes with the
OS, background daemons, and the inference server itself for RAM.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from typing import Any, Literal

import os_helper as osh

# Maps an application keyword to an ordered list of benchmark keys to try.
# The first non-null value found in a catalog entry is used as the score.
_APP_BENCH_PRIORITY: dict[str, list[str]] = {
    "code":       ["code", "general"],
    "math":       ["math", "general"],
    "ocr":        ["ocr", "vision", "general"],
    "vision":     ["vision", "general"],
    "chat":       ["general"],
    "generalist": ["general"],
}


# Fraction of an Apple Silicon unified-memory pool the GPU (Metal) may use
# before allocations spill to CPU and inference slows sharply. macOS sets this
# recommendedMaxWorkingSetSize at ~66% for pools of 36 GB or less and ~75%
# above that. Treating the *whole* pool as usable (the old behaviour) over-
# promises: it steers you to a model that technically loads but leaves no room
# for the OS, your own application, or KV-cache growth. Source: apple-specs /
# Metal working-set docs; see references/CODING.md.
_APPLE_GPU_FRACTION_SMALL = 0.66
_APPLE_GPU_FRACTION_LARGE = 0.75
_APPLE_SMALL_POOL_GB = 36.0

# Discrete-GPU VRAM is almost entirely usable; leave a small margin for the
# driver context. CPU-only inference is bounded by system RAM, but you never
# want to hand all of it to a model, so treat half as the working budget.
_DISCRETE_VRAM_FRACTION = 0.92
_CPU_RAM_FRACTION = 0.5

# Real-world decode throughput as a fraction of the memory-bandwidth ceiling.
# Token generation reads the active model once per token, so the ceiling is
# bandwidth / model-bytes; attention over the KV cache, kernel launches, and
# sampling pull the achieved rate down to roughly 50-80%.
#
# The achieved fraction is NOT the same across backends, even on identical
# hardware (confirmed on Ubuntu + discrete GPU: Ollama and vLLM do not decode
# at the same speed for the same model). Two per-backend figures, both
# deliberately conservative:
#
# - Ollama (llama.cpp/GGML runtime): 0.65, a mid-conservative point across
#   Apple Metal and CUDA. Source: llama.cpp / MLX community benchmarks; see
#   references/CODING.md.
# - vLLM (CUDA/ROCm only — see engine.default_backend): 0.75. PagedAttention
#   avoids the KV-cache fragmentation and per-token allocation overhead that
#   pulls llama.cpp's achieved rate down, and vLLM's CUDA-graph capture
#   removes most Python/kernel-launch overhead from the decode step, so a
#   single-stream vLLM decode tracks closer to the bandwidth ceiling. Source:
#   vLLM project benchmarks (PagedAttention paper, vLLM blog); see
#   references/CODING.md. This figure describes single-request decode, not
#   vLLM's much larger *aggregate* throughput advantage under concurrent
#   batched requests, which this single-model estimator does not model.
_DECODE_EFFICIENCY = 0.65
_VLLM_DECODE_EFFICIENCY = 0.75

_DECODE_EFFICIENCY_BY_BACKEND: dict[str, float] = {
    "ollama": _DECODE_EFFICIENCY,
    "vllm": _VLLM_DECODE_EFFICIENCY,
}

# Comfort floor: a model can fit in memory yet decode too slowly to be usable
# interactively. This is the minimum estimated decode rate (tokens/s) below which
# a model is flagged "not comfortable" and is NOT auto-recommended even though it
# fits — the missing half of "fits your hardware" (fits in memory AND runs at a
# tolerable speed). 15 tok/s is a bit faster than a brisk reader, roughly the
# point below which local chat starts to feel like waiting. On an M2 Max
# (400 GB/s) it draws the line just under the 14B class, exactly where a 32B
# model drops to ~7 tok/s. Source: MLX / llama.cpp community UX benchmarks.
COMFORT_TPS: float = 15.0

# Hard ceiling on the safety headroom. Headroom is the fraction of the
# accelerator's *usable* pool a model may occupy; anything above 0.5 leaves too
# little room for the OS, the caller's own workload, and KV-cache growth as the
# context fills, and steers the picker toward models that technically load but
# feel starved in practice. Any caller-supplied headroom is clamped down to this;
# it is never exceeded. This is the primary "don't be greedy" guard.
MAX_HEADROOM: float = 0.5

# Bytes per parameter for an unquantised (FP16/BF16) weight — what vLLM loads by
# default from a HuggingFace checkpoint, in contrast to Ollama's Q4 GGUF tags.
_FP16_BYTES_PER_PARAM: float = 2.0

# Multiplier over raw FP16 weights to account for the KV cache, activations, and
# CUDA-graph/runtime buffers vLLM allocates alongside the weights. Deliberately
# conservative: a model that only *just* fits its weights will OOM once a real
# context fills the KV cache.
_VLLM_OVERHEAD: float = 1.15


def model_footprint_gb(entry: dict[str, Any], backend: str = "ollama") -> float:
    """
    Estimate a model's peak inference memory (GB) on a given serving backend.

    The catalog's ``ram_gb`` is an **Ollama Q4** estimate. vLLM instead loads the
    full FP16/BF16 HuggingFace weights (~2 bytes/param) plus KV cache and runtime
    buffers, so the same model is markedly heavier there. Sizing a vLLM pick
    against ``ram_gb`` would over-promise and pick a model that will not actually
    fit — the "unrealistic recommendation" this guards against.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; uses ``ram_gb`` (Ollama) or ``size_b`` (vLLM).
    backend : {'ollama', 'vllm'}
        Serving backend the footprint is estimated for. Unknown values are
        treated as ``'ollama'`` (the conservative catalog figure).

    Returns
    -------
    float
        Estimated peak memory in GB.
    """
    ram = float(entry.get("ram_gb", 0) or 0)
    if backend != "vllm":
        return ram
    size_b = float(entry.get("size_b", 0) or 0)
    if size_b <= 0:
        # No parameter count to size FP16 weights from: fall back to the Ollama
        # figure rather than pretend it is free.
        return ram
    fp16 = size_b * _FP16_BYTES_PER_PARAM * _VLLM_OVERHEAD
    # Never report a vLLM footprint smaller than the Q4 estimate — FP16 is always
    # heavier, so the Ollama number is a hard floor.
    return round(max(fp16, ram), 3)


def effective_budget(hw: dict[str, float | None], headroom: float = MAX_HEADROOM) -> float:
    """
    Compute the memory budget (GB) a model may occupy at run time.

    The budget is the accelerator's usable memory pool, scaled by an extra
    ``headroom`` margin left for the operating system, your own application, and
    KV-cache growth as context fills. On Apple Silicon the usable pool is *not*
    the whole unified memory: Metal caps GPU allocations at about 66% of the
    pool at or below 36 GB and about 75% above it, beyond which inference spills
    to CPU. Compare a catalog entry's ``ram_gb`` (already a peak-inference
    estimate, weights plus a moderate KV cache) against this budget.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`. Expected keys:
        ``unified_gb``, ``vram_gb``, ``ram_gb``.
    headroom : float
        Extra safety fraction applied on top of the accelerator cap, reserving
        room for the OS, the caller's workload, and KV growth. Defaults to
        :data:`MAX_HEADROOM` (0.5) and is **clamped** down to it — a larger value
        is never honoured, to keep picks realistic.

    Returns
    -------
    float
        Effective memory budget in GB.

    Examples
    --------
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0})
    36.0
    >>> effective_budget({'unified_gb': None, 'vram_gb': 24.0, 'ram_gb': 64.0})
    11.04
    >>> # headroom above the 0.5 ceiling is clamped, not honoured
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}, headroom=0.85)
    36.0
    """
    # Clamp to the hard ceiling: an over-generous headroom is the main source of
    # unrealistically large picks, so it is silently reduced, never exceeded.
    headroom = min(headroom, MAX_HEADROOM)
    if hw.get("unified_gb"):
        pool = float(hw["unified_gb"])  # type: ignore[arg-type]
        cap = (
            _APPLE_GPU_FRACTION_LARGE
            if pool > _APPLE_SMALL_POOL_GB
            else _APPLE_GPU_FRACTION_SMALL
        )
        available = pool * cap
    elif hw.get("vram_gb"):
        available = float(hw["vram_gb"]) * _DISCRETE_VRAM_FRACTION  # type: ignore[arg-type]
    else:
        available = float(hw.get("ram_gb") or 8.0) * _CPU_RAM_FRACTION

    return round(available * headroom, 3)


def estimated_tokens_per_second(
    entry: dict[str, Any], bandwidth_gbs: float | None, backend: str = "ollama"
) -> float | None:
    """
    Estimate local decode throughput (tokens/s) for a model on this machine.

    Token generation is memory-bandwidth bound: each new token requires reading
    the model's active weights from memory once, so the ceiling is
    ``bandwidth / model_bytes``. The estimate derates that ceiling by a
    backend-specific decode efficiency (see
    :data:`_DECODE_EFFICIENCY_BY_BACKEND`) to reflect KV-cache reads, kernel
    overhead, and sampling. It describes steady-state generation, not the
    compute-bound prefill of a long prompt.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; its :func:`model_footprint_gb` is the active-model size.
    bandwidth_gbs : float or None
        Memory bandwidth in GB/s from :func:`detect.compute_profile`. When None
        (unknown hardware, e.g. an unrecognised discrete-GPU model) the
        estimate is not computable and None is returned.
    backend : {'ollama', 'vllm'}
        Serving backend. Affects both the size proxy (heavier FP16 weights
        under vLLM decode more slowly than the Q4 Ollama figure) AND the
        decode efficiency (vLLM's PagedAttention + CUDA-graph decode tracks
        closer to the bandwidth ceiling than llama.cpp's — confirmed to
        differ on identical Ubuntu + discrete-GPU hardware, not just a
        cross-platform artifact).

    Returns
    -------
    float or None
        Estimated tokens/s, rounded to one decimal, or None when bandwidth or
        model size is unavailable.
    """
    if not bandwidth_gbs:
        return None
    ram = model_footprint_gb(entry, backend)
    if ram <= 0:
        return None
    efficiency = _DECODE_EFFICIENCY_BY_BACKEND.get(backend, _DECODE_EFFICIENCY)
    return round(bandwidth_gbs / ram * efficiency, 1)


def _benchmark_score(
    entry: dict[str, Any],
    kind: Literal["llm", "vlm"],
    application: str | None = None,
) -> float:
    """
    Extract the relevant benchmark score for ranking.

    When *application* is given it is looked up in ``_APP_BENCH_PRIORITY`` and
    the first non-null benchmark in that priority list is used.  When absent
    (or unknown) the legacy rule applies: vision score for VLMs, general for
    LLMs.  Falls back to 0 when no matching score is found.

    Parameters
    ----------
    entry : dict[str, Any]
        A catalog entry dict.
    kind : {'llm', 'vlm'}
        The inference kind being selected.
    application : str or None
        Optional use-case keyword (e.g. ``"code"``, ``"math"``, ``"ocr"``).
        ``None`` or ``"generalist"`` use the default kind-based rule.

    Returns
    -------
    float
        Benchmark score, or 0.0 if absent.
    """
    benchmarks = entry.get("benchmarks") or {}

    if application:
        priority = _APP_BENCH_PRIORITY.get(application.lower())
        if priority:
            for key in priority:
                val = benchmarks.get(key)
                if val is not None:
                    return float(val)
            return 0.0

    # Default: vision axis for VLMs, general for LLMs
    if kind == "vlm":
        score = benchmarks.get("vision") or benchmarks.get("general") or 0
    else:
        score = benchmarks.get("general") or 0
    return float(score)


def select(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = MAX_HEADROOM,
    application: str | None = None,
    backend: str = "ollama",
) -> dict[str, Any]:
    """
    Pick the best-scoring model that fits in available memory.

    Candidates for a 'vlm' selection include both VLMs and LLMs with vision
    capability (kind == 'vlm'). Candidates for a 'llm' selection include
    text-only LLMs and VLMs (since a VLM handles text-only prompts equally).

    Selection order:
    1. Filter: keep entries whose ``ram_gb`` fits within the effective budget.
    2. Rank: structured-output capability first (a model that cannot honour
       Ollama structured output is never chosen over one that can), then
       benchmark score (application-specific if given, else vision for VLM or
       general for LLM). This matches :func:`rank`, so ``rank(...)[0]`` and
       ``select(...)`` agree.
    3. Last resort: if nothing fits, return the smallest model in the catalog
       rather than raising; the caller decides whether to warn the user.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`.
    catalog : list[dict[str, Any]]
        Merged model entries from :func:`catalog.load_catalog`.
    kind : {'llm', 'vlm'}
        The type of model to select.
    headroom : float
        Extra safety on top of the accelerator cap. Clamped to
        :data:`MAX_HEADROOM` (0.5); default 0.5.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Selects the benchmark
        axis used for scoring.  ``None`` uses the default kind-based rule.
    backend : {'ollama', 'vllm'}
        Serving backend, so memory fit is checked against the footprint that
        actually loads (FP16 for vLLM, Q4 ``ram_gb`` for Ollama).

    Returns
    -------
    dict[str, Any]
        The selected catalog entry.

    Raises
    ------
    ValueError
        If the catalog is empty.

    Examples
    --------
    >>> hw = {'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}
    >>> catalog = [{'id': 'v', 'kind': 'vlm', 'ram_gb': 9.0,
    ...             'benchmarks': {'vision': 80}}]
    >>> select(hw, catalog, kind='vlm')['id']
    'v'
    """
    if not catalog:
        osh.error("Catalog is empty; cannot select a model.")
        raise ValueError("Catalog is empty; cannot select a model.")

    # VLMs can answer text-only queries, so they count as valid LLM candidates too
    if kind == "vlm":
        candidates = [e for e in catalog if e.get("kind") == "vlm"]
    else:
        # LLM selection accepts both pure LLMs and VLMs (VLMs subsume LLMs)
        candidates = [e for e in catalog if e.get("kind") in {"llm", "vlm"}]

    if not candidates:
        candidates = list(catalog)

    budget = effective_budget(hw, headroom=headroom)

    # Keep only models whose backend-specific footprint fits the safety budget
    fitting = [e for e in candidates if model_footprint_gb(e, backend) <= budget]

    if fitting:
        # Structured-output capability is the primary key, exactly as in rank():
        # a model that can't honour Ollama structured output is never chosen over
        # a capable one, however high its raw score. This keeps select() and
        # rank()[0] in agreement, so the library and the CLI recommend the same
        # model. Absent field defaults to capable.
        def _sort_key(e: dict[str, Any]) -> tuple[bool, float]:
            structured_ok = e.get("structured_output", True) is not False
            return (structured_ok, _benchmark_score(e, kind, application))

        return max(fitting, key=_sort_key)

    # Nothing fits: return the smallest model as a last resort so the caller
    # can surface a useful warning rather than crashing entirely
    smallest = min(candidates, key=lambda e: model_footprint_gb(e, backend))
    osh.warning(
        f"No {kind} model fits the {budget:.1f} GB budget; "
        f"falling back to smallest: {smallest.get('id')}"
    )
    return smallest


def rank(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = MAX_HEADROOM,
    application: str | None = None,
    backend: str = "ollama",
) -> list[dict[str, Any]]:
    """
    Return all candidates sorted by benchmark score, annotated with fit status.

    Each entry in the result gets a ``_fits`` key (bool) indicating whether it
    fits within the effective budget. The top entry is identical to what
    :func:`select` would return.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`.
    catalog : list[dict[str, Any]]
        Merged model entries from :func:`catalog.load_catalog`.
    kind : {'llm', 'vlm'}
        The inference kind to filter and rank by.
    headroom : float
        Extra safety on top of the accelerator cap. Clamped to
        :data:`MAX_HEADROOM` (0.5); default 0.5.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Drives which benchmark
        column is used for ranking.
    backend : {'ollama', 'vllm'}
        Serving backend, so ``_fits`` reflects the footprint that actually
        loads (FP16 for vLLM, Q4 ``ram_gb`` for Ollama).

    Returns
    -------
    list[dict[str, Any]]
        Candidates sorted descending by benchmark score, each with ``_fits``.

    Examples
    --------
    >>> catalog = [{'id': 'v', 'kind': 'vlm', 'ram_gb': 9.0,
    ...             'benchmarks': {'vision': 80}}]
    >>> rank({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}, catalog, 'vlm')[0]['_fits']
    True
    """
    if kind == "vlm":
        candidates = [e for e in catalog if e.get("kind") == "vlm"]
    else:
        candidates = [e for e in catalog if e.get("kind") in {"llm", "vlm"}]

    if not candidates:
        candidates = list(catalog)

    budget = effective_budget(hw, headroom=headroom)

    annotated = []
    for entry in candidates:
        copy = dict(entry)
        copy["_fits"] = model_footprint_gb(entry, backend) <= budget
        annotated.append(copy)

    # Structured-output capability is a primary sort key, ahead of raw benchmark
    # score: the helper routes every task through a JSON schema, so a model that
    # can't honour Ollama structured output (the Qwen3-VL family returns empty)
    # is disqualified from auto-selection no matter how high it scores. It still
    # appears in the ranked list -- just never above a structured-capable peer --
    # so a caller who explicitly wants it for a non-structured task can find it.
    # Absent field defaults to True (assume capable) for forward compatibility.
    def _sort_key(e: dict[str, Any]) -> tuple[bool, float]:
        structured_ok = e.get("structured_output", True) is not False
        return (structured_ok, _benchmark_score(e, kind, application))

    return sorted(annotated, key=_sort_key, reverse=True)
