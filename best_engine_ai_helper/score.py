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


def effective_budget(hw: dict[str, float | None], headroom: float = 0.80) -> float:
    """
    Compute the effective RAM budget for model loading.

    Applies the safety headroom to the highest-priority memory pool detected
    on the current machine.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`. Expected keys:
        ``unified_gb``, ``vram_gb``, ``ram_gb``.
    headroom : float
        Fraction of the available pool to treat as usable. Defaults to 0.80,
        leaving 20% as a safety margin for OS overhead and peak spikes.

    Returns
    -------
    float
        Effective memory budget in GB.

    Examples
    --------
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0})
    76.8
    >>> effective_budget({'unified_gb': None, 'vram_gb': 24.0, 'ram_gb': 64.0})
    19.2
    """
    if hw.get("unified_gb"):
        # Apple Silicon: entire unified pool is available to Ollama
        available = float(hw["unified_gb"])  # type: ignore[arg-type]
    elif hw.get("vram_gb"):
        # Discrete GPU: VRAM is the inference budget
        available = float(hw["vram_gb"])  # type: ignore[arg-type]
    else:
        # CPU-only: use half of system RAM as a conservative estimate
        available = float(hw.get("ram_gb") or 8.0) * 0.5

    return round(available * headroom, 3)


def _benchmark_score(entry: dict[str, Any], kind: Literal["llm", "vlm"]) -> float:
    """
    Extract the relevant benchmark score for ranking.

    VLMs are ranked by vision score; LLMs by general score. Falls back to 0
    when the score is missing so models with absent benchmarks rank last.

    Parameters
    ----------
    entry : dict[str, Any]
        A catalog entry dict.
    kind : {'llm', 'vlm'}
        The inference kind being selected.

    Returns
    -------
    float
        Benchmark score, or 0.0 if absent.
    """
    benchmarks = entry.get("benchmarks") or {}
    if kind == "vlm":
        # Vision score is the primary axis for VLMs; fall back to general
        score = benchmarks.get("vision") or benchmarks.get("general") or 0
    else:
        score = benchmarks.get("general") or 0
    return float(score)


def select(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = 0.80,
) -> dict[str, Any]:
    """
    Pick the best-scoring model that fits in available memory.

    Candidates for a 'vlm' selection include both VLMs and LLMs with vision
    capability (kind == 'vlm'). Candidates for a 'llm' selection include
    text-only LLMs and VLMs (since a VLM handles text-only prompts equally).

    Selection order:
    1. Filter: keep entries whose ``ram_gb`` fits within the effective budget.
    2. Rank: sort by benchmark score (vision for VLM, general for LLM).
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
        Safety margin applied to available memory. Default 0.80.

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
        # Pick highest benchmark score among models that fit
        return max(fitting, key=lambda e: _benchmark_score(e, kind))

    # Nothing fits: return the smallest model as a last resort so the caller
    # can surface a useful warning rather than crashing entirely
    return min(candidates, key=lambda e: float(e.get("ram_gb", 0)))


def rank(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = 0.80,
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
        Safety margin. Default 0.80.

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

    # Annotate with fit status before sorting so the flag travels with the entry
    annotated = []
    for entry in candidates:
        copy = dict(entry)
        copy["_fits"] = float(entry.get("ram_gb", 0)) <= budget
        annotated.append(copy)

    return sorted(annotated, key=lambda e: _benchmark_score(e, kind), reverse=True)
