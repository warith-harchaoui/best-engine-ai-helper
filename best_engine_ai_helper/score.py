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
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

from typing import Any, Literal

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
# sampling pull the achieved rate down to roughly 50-80%. 0.65 is a mid,
# deliberately conservative point. Source: llama.cpp / MLX community benchmarks;
# see references/CODING.md.
_DECODE_EFFICIENCY = 0.65


def effective_budget(hw: dict[str, float | None], headroom: float = 0.85) -> float:
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
        room for the OS, the caller's workload, and KV growth. Default 0.85.

    Returns
    -------
    float
        Effective memory budget in GB.

    Examples
    --------
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0})
    61.2
    >>> effective_budget({'unified_gb': None, 'vram_gb': 24.0, 'ram_gb': 64.0})
    18.768
    """
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
    entry: dict[str, Any], bandwidth_gbs: float | None
) -> float | None:
    """
    Estimate local decode throughput (tokens/s) for a model on this machine.

    Token generation is memory-bandwidth bound: each new token requires reading
    the model's active weights from memory once, so the ceiling is
    ``bandwidth / model_bytes``. The estimate derates that ceiling by
    :data:`_DECODE_EFFICIENCY` to reflect KV-cache reads, kernel overhead, and
    sampling. It describes steady-state generation, not the compute-bound
    prefill of a long prompt.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; uses ``ram_gb`` as the active-model size proxy.
    bandwidth_gbs : float or None
        Memory bandwidth in GB/s from :func:`detect.compute_profile`. When None
        (unknown hardware) the estimate is not computable and None is returned.

    Returns
    -------
    float or None
        Estimated tokens/s, rounded to one decimal, or None when bandwidth or
        model size is unavailable.
    """
    if not bandwidth_gbs:
        return None
    ram = float(entry.get("ram_gb", 0) or 0)
    if ram <= 0:
        return None
    return round(bandwidth_gbs / ram * _DECODE_EFFICIENCY, 1)


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
    headroom: float = 0.85,
    application: str | None = None,
) -> dict[str, Any]:
    """
    Pick the best-scoring model that fits in available memory.

    Candidates for a 'vlm' selection include both VLMs and LLMs with vision
    capability (kind == 'vlm'). Candidates for a 'llm' selection include
    text-only LLMs and VLMs (since a VLM handles text-only prompts equally).

    Selection order:
    1. Filter: keep entries whose ``ram_gb`` fits within the effective budget.
    2. Rank: sort by benchmark score (application-specific if given, else
       vision for VLM or general for LLM).
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
        Extra safety on top of the accelerator cap. Default 0.85.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Selects the benchmark
        axis used for scoring.  ``None`` uses the default kind-based rule.

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
    >>> import catalog, detect
    >>> hw = detect.available_memory()
    >>> entries = catalog.load_catalog()
    >>> best = select(hw, entries, kind='vlm')
    >>> best['kind'] == 'vlm'
    True
    """
    if not catalog:
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

    # Keep only models that fit within the safety budget
    fitting = [e for e in candidates if float(e.get("ram_gb", 0)) <= budget]

    if fitting:
        return max(fitting, key=lambda e: _benchmark_score(e, kind, application))

    # Nothing fits: return the smallest model as a last resort so the caller
    # can surface a useful warning rather than crashing entirely
    return min(candidates, key=lambda e: float(e.get("ram_gb", 0)))


def rank(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = 0.85,
    application: str | None = None,
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
        Extra safety on top of the accelerator cap. Default 0.85.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Drives which benchmark
        column is used for ranking.

    Returns
    -------
    list[dict[str, Any]]
        Candidates sorted descending by benchmark score, each with ``_fits``.

    Examples
    --------
    >>> ranked = rank({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0},
    ...               load_catalog(), 'vlm')
    >>> ranked[0]['_fits']
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
        copy["_fits"] = float(entry.get("ram_gb", 0)) <= budget
        annotated.append(copy)

    return sorted(annotated, key=lambda e: _benchmark_score(e, kind, application), reverse=True)
