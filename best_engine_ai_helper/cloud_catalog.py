"""
cloud_catalog — pick the best PAID model for a task, the cloud counterpart of
:mod:`best_engine_ai_helper.score`.

Local mode (:mod:`score`, :mod:`recommend`) auto-picks the best model from a
catalog by weighing benchmark quality against memory fit — free, since the
hardware is already paid for. Cloud mode auto-picks the best model from a
different catalog by weighing benchmark quality against **price**: every
candidate fits on any machine (the provider owns the hardware), so cost is
the resource being budgeted instead of memory.

The catalog is ``pricing.yaml`` at the package root: the same table
:mod:`best_engine_ai_helper.observe` already reads to price a completed call,
extended with ``provider``, ``kind`` (``llm``/``vlm``), ``structured_output``,
and ``benchmarks`` per entry. One file, two consumers — pricing after the
call, ranking before it — so cost and quality can never drift apart into two
different numbers for the same model.

Author
------
Warith Harchaoui <warith@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import os_helper as osh
import yaml

from .score import _benchmark_score

# pricing.yaml sits next to pyproject.toml, same convention as models.yaml /
# hardware.yaml / usages.yaml (see catalog.py) and observe.py's _PRICING_PATH.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_PRICING_PATH = _PACKAGE_ROOT / "pricing.yaml"

# A quality_vs_cost outside [0, 1] is silently clamped, mirroring score.py's
# MAX_HEADROOM clamp discipline: a caller-supplied knob is never honoured past
# its meaningful range.
_MIN_WEIGHT = 0.0
_MAX_WEIGHT = 1.0

# Default weight when a brief/caller does not set quality_vs_cost: quality
# leads, price only breaks a near-tie. Matches local mode's own anti-greed
# default (score._SUFFICIENT_MARGIN picks the leanest model among near-ties,
# not blindly the cheapest).
DEFAULT_QUALITY_VS_COST: float = 0.7


def load_cloud_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load the bundled paid-model catalog (``pricing.yaml``).

    Parameters
    ----------
    path : Path or None
        Override the catalog file (tests use a fixture). Defaults to the
        bundled ``pricing.yaml`` next to ``pyproject.toml``.

    Returns
    -------
    list[dict[str, Any]]
        One dict per model, each carrying its YAML key as ``id`` plus
        ``provider``, ``kind``, ``structured_output``, ``benchmarks``,
        ``input_per_1m``, ``output_per_1m``.

    Raises
    ------
    FileNotFoundError
        If ``path`` is given explicitly and does not exist.

    Examples
    --------
    >>> entries = load_cloud_catalog()
    >>> all({"id", "provider", "kind"} <= e.keys() for e in entries)
    True
    """
    catalog_path = path if path is not None else _PRICING_PATH
    if not osh.file_exists(str(catalog_path)):
        if path is not None:
            osh.error(f"Cloud catalog not found:\n\t{catalog_path}")
            raise FileNotFoundError(f"Cloud catalog not found: {catalog_path}")
        osh.warning(f"No pricing.yaml found:\n\t{catalog_path}\n\tCloud auto-pick disabled.")
        return []

    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    models = data.get("models") or {}
    if not isinstance(models, dict):
        raise ValueError(f"{catalog_path}: 'models' must be a mapping, got {type(models)!r}")

    entries = [{"id": model_id, **spec} for model_id, spec in models.items()]
    osh.info(f"Loaded {len(entries)} cloud model(s) from:\n\t{catalog_path}")
    return entries


def blended_price_per_1m(entry: dict[str, Any]) -> float:
    """
    A single $/1M-token comparability figure for one catalog entry.

    A real workload's input/output ratio varies by task (a long-document
    summary is input-heavy; an open-ended generation is output-heavy), so this
    is a simple average of the two list prices, not a workload-specific
    estimate — the same "rough estimate, not a bill" honesty ``pricing.yaml``
    already documents for the ledger side.

    Parameters
    ----------
    entry : dict[str, Any]
        A catalog entry with ``input_per_1m``/``output_per_1m`` (USD).

    Returns
    -------
    float
        ``(input_per_1m + output_per_1m) / 2``. ``0.0`` when both are absent.

    Examples
    --------
    >>> blended_price_per_1m({"input_per_1m": 2.0, "output_per_1m": 10.0})
    6.0
    """
    lo = float(entry.get("input_per_1m", 0.0) or 0.0)
    hi = float(entry.get("output_per_1m", 0.0) or 0.0)
    return (lo + hi) / 2.0


def _clamp_weight(quality_vs_cost: float) -> float:
    """Clamp a quality_vs_cost knob into [0, 1] (0 = cheapest wins, 1 = best score wins)."""
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, float(quality_vs_cost)))


def _normalize(value: float, lo: float, hi: float, *, invert: bool = False) -> float:
    """Min-max normalize ``value`` into [0, 1]; a flat pool (lo == hi) normalizes to 1.0."""
    if hi <= lo:
        return 1.0
    n = (value - lo) / (hi - lo)
    return (1.0 - n) if invert else n


def rank_cloud(
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    application: str | None = None,
    quality_vs_cost: float = DEFAULT_QUALITY_VS_COST,
    provider: str | None = None,
) -> list[dict[str, Any]]:
    """
    Rank paid catalog candidates by a quality/price trade-off.

    Mirrors :func:`score.rank`'s shape (structured-output capability first,
    then a combined score), so the local and cloud pickers read the same way.
    Each candidate gets ``score`` (raw benchmark), ``price_per_1m``
    (:func:`blended_price_per_1m`), and ``combined`` — a 0..1 blend of
    min-max-normalized quality and (inverted) price across the candidate pool.

    Parameters
    ----------
    catalog : list[dict[str, Any]]
        Entries from :func:`load_cloud_catalog`.
    kind : {'llm', 'vlm'}
        ``vlm`` keeps only vision-capable entries; ``llm`` keeps both ``llm``
        and ``vlm`` entries (a VLM answers text-only prompts too — same rule
        as :func:`score.rank`).
    application : str or None
        Benchmark axis keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``), forwarded to
        :func:`score._benchmark_score`. ``None`` uses the default kind-based
        rule (vision axis for a VLM, general for an LLM).
    quality_vs_cost : float
        0..1 weight on quality vs. price; clamped into range. ``1.0`` picks
        purely on benchmark score (price ignored); ``0.0`` picks purely on
        price (quality ignored, subject to the structured-output gate).
        Defaults to :data:`DEFAULT_QUALITY_VS_COST`.
    provider : str or None
        Restrict candidates to one provider (e.g. ``"openai"``), case-
        insensitive. ``None`` ranks across every provider in the catalog.

    Returns
    -------
    list[dict[str, Any]]
        Candidates sorted best-first. Empty when nothing matches ``kind``
        (and ``provider``, if given).

    Examples
    --------
    >>> catalog = [
    ...     {"id": "cheap", "provider": "p", "kind": "llm", "structured_output": True,
    ...      "benchmarks": {"general": 70}, "input_per_1m": 0.1, "output_per_1m": 0.1},
    ...     {"id": "strong", "provider": "p", "kind": "llm", "structured_output": True,
    ...      "benchmarks": {"general": 90}, "input_per_1m": 5.0, "output_per_1m": 15.0},
    ... ]
    >>> rank_cloud(catalog, "llm", quality_vs_cost=1.0)[0]["id"]  # quality only
    'strong'
    >>> rank_cloud(catalog, "llm", quality_vs_cost=0.0)[0]["id"]  # price only
    'cheap'
    """
    if kind == "vlm":
        candidates = [e for e in catalog if e.get("kind") == "vlm"]
    else:
        candidates = [e for e in catalog if e.get("kind") in {"llm", "vlm"}]

    if provider:
        p = provider.strip().lower()
        candidates = [e for e in candidates if str(e.get("provider", "")).strip().lower() == p]

    if not candidates:
        return []

    weight = _clamp_weight(quality_vs_cost)
    scores = [_benchmark_score(e, kind, application) for e in candidates]
    prices = [blended_price_per_1m(e) for e in candidates]
    lo_s, hi_s = min(scores), max(scores)
    lo_p, hi_p = min(prices), max(prices)

    annotated = []
    for entry, score, price in zip(candidates, scores, prices, strict=True):
        row = dict(entry)
        row["score"] = score
        row["price_per_1m"] = price
        quality_n = _normalize(score, lo_s, hi_s)
        price_n = _normalize(price, lo_p, hi_p, invert=True)
        row["combined"] = weight * quality_n + (1.0 - weight) * price_n
        annotated.append(row)

    # Structured-output capability first, exactly like score.rank: a model
    # that can't honour a JSON schema is never auto-chosen over one that can,
    # however attractive its quality/price trade-off. Absent -> assume capable.
    def _sort_key(e: dict[str, Any]) -> tuple[bool, float]:
        structured_ok = e.get("structured_output", True) is not False
        return (structured_ok, e["combined"])

    return sorted(annotated, key=_sort_key, reverse=True)


def pick_cloud(
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    application: str | None = None,
    quality_vs_cost: float = DEFAULT_QUALITY_VS_COST,
    provider: str | None = None,
) -> dict[str, Any] | None:
    """
    Return the single best paid candidate, or None if nothing matches.

    Thin wrapper over :func:`rank_cloud` — ``rank_cloud(...)[0]``, or None on
    an empty ranking, so callers do not need an ``IndexError`` guard.

    Parameters
    ----------
    catalog, kind, application, quality_vs_cost, provider : see :func:`rank_cloud`.

    Returns
    -------
    dict[str, Any] or None
        The top-ranked entry, or None when no candidate matches ``kind``
        (and ``provider``, if given).

    Examples
    --------
    >>> catalog = [{"id": "m", "provider": "p", "kind": "llm",
    ...             "structured_output": True, "benchmarks": {"general": 80},
    ...             "input_per_1m": 1.0, "output_per_1m": 2.0}]
    >>> pick_cloud(catalog, "llm")["id"]
    'm'
    >>> pick_cloud(catalog, "vlm") is None
    True
    """
    ranked = rank_cloud(catalog, kind, application, quality_vs_cost, provider)
    return ranked[0] if ranked else None
