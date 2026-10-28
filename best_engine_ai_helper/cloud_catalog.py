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
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import os_helper as osh
import yaml

from .score import _benchmark_score

# pricing.yaml sits next to pyproject.toml, same convention as models.yaml /
# hardware.yaml / usages.yaml (see catalog.py) and observe.py's _PRICING_PATH.
# Data lives INSIDE the package. These files used to sit beside it, next to
# pyproject.toml, where `package-data` patterns — which resolve relative to a
# package directory — could never reach them: the wheel shipped none of them,
# and `load_catalog()` returned an EMPTY catalogue on any machine without a
# populated user cache. A repo checkout and a populated cache both hid it.
_PACKAGE_ROOT = Path(__file__).resolve().parent / "data"
_PRICING_PATH = _PACKAGE_ROOT / "pricing.yaml"

# Refreshed prices land beside the local catalogue's cache, under the same
# contract: the bundled seed is never modified, the cache is overlaid on top of
# it by id, and deleting the cache returns you to the seed.
_USER_DIR = Path.home() / ".best-engine-ai-helper"
_CLOUD_CACHE_PATH = _USER_DIR / "pricing_cache.yaml"

#: Public alias, so the CLI and tests can name the cache without reaching into
#: a private attribute (mirrors ``catalog.CACHE_PATH``).
CLOUD_CACHE_PATH = _CLOUD_CACHE_PATH

#: How old the effective price table may get before every cloud surface says
#: so. Providers reprice and retire models on a scale of months — the seed
#: shipped `gemini-1.5-pro` long after Google retired the 1.5 line — so half a
#: year is already generous. It is a warning, never a refusal: an old price is
#: still better than no price, and the user may have no network.
STALE_AFTER_DAYS: int = 180

#: Fields a refresh is allowed to overwrite. Everything else on a seed entry —
#: `benchmarks` above all — survives, because the price source carries no
#: quality scores and blanking them would silently disarm the ranker.
REPRICEABLE: frozenset[str] = frozenset(
    {
        "input_per_1m",
        "output_per_1m",
        "context_length",
        "kind",
        "structured_output",
        "source",
        "fetched_at",
    }
)

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

    # Overlay the refreshed cache, same contract as the local catalogue: the
    # bundled seed is never modified, the cache wins field by field, and
    # deleting the cache returns you to the seed. A cached entry only ever
    # carries repriceable fields (see `reprice`), so the seed's benchmark
    # scores survive a refresh that has none of its own.
    cached = _read_models(_CLOUD_CACHE_PATH) if path is None else {}
    if cached:
        osh.info(f"Overlaying {len(cached)} repriced cloud entry(ies):\n\t{_CLOUD_CACHE_PATH}")

    entries = []
    for model_id, spec in models.items():
        merged = {"id": model_id, **spec}
        overlay = cached.get(model_id)
        if isinstance(overlay, dict):
            merged.update({k: v for k, v in overlay.items() if k in REPRICEABLE})
        entries.append(merged)

    osh.info(f"Loaded {len(entries)} cloud model(s) from:\n\t{catalog_path}")
    _warn_if_stale_once()
    return entries


def _read_models(path: Path) -> dict[str, dict[str, Any]]:
    """Read a ``{models: {id: spec}}`` YAML file, or {} when it is absent.

    Parameters
    ----------
    path : Path
        File to read.

    Returns
    -------
    dict[str, dict[str, Any]]
        The ``models`` mapping, or an empty dict.

    Examples
    --------
    >>> _read_models(Path("/nonexistent/pricing.yaml"))
    {}
    """
    if not osh.file_exists(str(path)):
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — a corrupt cache must not break resolution
        osh.warning(f"Ignoring unreadable cloud price file:\n\t{path}\n\t{exc}")
        return {}
    models = data.get("models") or {}
    return models if isinstance(models, dict) else {}


#: Set once the staleness note has been emitted, so a path that loads the
#: catalogue repeatedly (``report`` ranks llm and vlm separately; ``/v1``
#: resolves per kind and mode) says it once rather than once per call.
_WARNED_STALE = False


def _warn_if_stale_once() -> None:
    """Emit :func:`staleness_note` at most once per process."""
    global _WARNED_STALE
    if _WARNED_STALE:
        return
    _WARNED_STALE = True
    note = staleness_note()
    if note:
        osh.warning(note)


def reprice(
    seed: list[dict[str, Any]], fetched: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Overlay fetched prices onto the catalog we carry, and name what was missed.

    The merge is deliberately *narrow*. Only :data:`REPRICEABLE` fields are
    taken from the source; ``benchmarks`` and everything else stay as the seed
    has them, because the price table carries no quality scores and a refresh
    that blanked them would leave `rank_cloud` ranking every model at zero.

    Nothing new is added either. A model the source knows and the seed does not
    has a price but no score, so adding it would either flood the ranking with
    unscorable candidates or require inventing a number. Those ids come back as
    the second return value for a human to triage — see
    ``catalog update --cloud``, which prints them.

    Parameters
    ----------
    seed : list[dict[str, Any]]
        The catalog as loaded today.
    fetched : list[dict[str, Any]]
        Normalised source entries (:func:`sources.litellm_prices.fetch_cloud_prices`).

    Returns
    -------
    tuple[list[dict[str, Any]], list[str]]
        The repriced entries, and the ids of seed models the source did not
        know. An id in that second list is a model the source has never heard
        of: usually retired, occasionally renamed, and in both cases worth a
        look rather than an automatic deletion.

    Examples
    --------
    >>> seed = [{"id": "m", "provider": "p", "kind": "llm",
    ...          "benchmarks": {"general": 80}, "input_per_1m": 9.0,
    ...          "output_per_1m": 9.0}]
    >>> live = [{"id": "m", "provider": "p", "kind": "vlm",
    ...          "input_per_1m": 1.0, "output_per_1m": 2.0,
    ...          "context_length": 128000}]
    >>> merged, missing = reprice(seed, live)
    >>> merged[0]["input_per_1m"], merged[0]["context_length"], missing
    (1.0, 128000, [])
    >>> merged[0]["benchmarks"]          # never touched by a price source
    {'general': 80}
    >>> reprice(seed, [])[1]
    ['m']
    """
    by_id = {str(e.get("id")): e for e in fetched}
    merged: list[dict[str, Any]] = []
    missing: list[str] = []
    for entry in seed:
        model_id = str(entry.get("id"))
        live = by_id.get(model_id)
        if live is None:
            missing.append(model_id)
            merged.append(dict(entry))
            continue
        updated = dict(entry)
        updated.update({k: v for k, v in live.items() if k in REPRICEABLE})
        merged.append(updated)
    return merged, missing


def write_cloud_cache(entries: list[dict[str, Any]], cache_path: Path | None = None) -> Path:
    """
    Write repriced entries to the user cache, leaving the bundled seed alone.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Entries to persist, each carrying an ``id``.
    cache_path : Path or None
        Destination. Defaults to :data:`CLOUD_CACHE_PATH`; override in tests.

    Returns
    -------
    Path
        The path written.
    """
    path = cache_path if cache_path is not None else _CLOUD_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": {str(e["id"]): {k: v for k, v in e.items() if k != "id"} for e in entries}}
    path.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
    osh.info(f"Wrote {len(entries)} repriced cloud model(s):\n\t{path}")
    return path


def catalog_as_of(path: Path | None = None) -> str | None:
    """
    The date the effective price table was last known good, as ISO ``YYYY-MM-DD``.

    Reads the cache's newest ``fetched_at`` when a refresh has happened, and
    otherwise the seed's own ``as_of`` stamp. Returns None when neither exists,
    which is itself worth reporting: a table of prices with no date is one
    nobody can judge.

    Parameters
    ----------
    path : Path or None
        Override the seed file (tests use a fixture).

    Returns
    -------
    str or None
        ISO date, or None when the table carries no stamp at all.
    """
    stamps: list[str] = []
    cache = _read_models(_CLOUD_CACHE_PATH)
    stamps.extend(
        str(spec["fetched_at"])
        for spec in cache.values()
        if isinstance(spec.get("fetched_at"), str)
    )
    seed_path = path if path is not None else _PRICING_PATH
    if osh.file_exists(str(seed_path)):
        data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
        if isinstance(data.get("as_of"), str):
            stamps.append(str(data["as_of"]))
    return max(stamps) if stamps else None


def staleness_note(today: str | None = None, path: Path | None = None) -> str | None:
    """
    One sentence about how old the prices are, or None when they are fresh.

    Every cloud surface prints this rather than deciding for the user. An old
    price is still better than no price — and the machine may have no network —
    so this never refuses a resolution, it only stops a stale number from
    passing itself off as current.

    Parameters
    ----------
    today : str or None
        ISO date to measure against; defaults to today (UTC).
    path : Path or None
        Override the seed file (tests use a fixture).

    Returns
    -------
    str or None
        The note, or None when the table is within :data:`STALE_AFTER_DAYS`.

    Notes
    -----
    This has deliberately no doctest. The answer depends on machine-local
    state outside the repository -- `catalog_as_of` reads the user's price
    cache first, and that file exists only where somebody has run `catalog
    update --cloud`. A doctest asserting ``None`` therefore passed on the
    author's machine, where a cache supplies a stamp, and failed in CI, where
    the shipped seed carries none on purpose (see the test below for why).
    Both branches are pinned in `tests/test_cloud_prices.py`, which
    monkeypatches `_CLOUD_CACHE_PATH` away and writes its own seed, so the
    assertion reads the same on every machine.
    """
    from datetime import date

    as_of = catalog_as_of(path)
    if as_of is None:
        return (
            "The paid-model table carries no date, so there is no way to tell "
            "how current its prices are. `best-engine-ai-helper catalog update "
            "--cloud` stamps it from a live source."
        )
    try:
        stamped = date.fromisoformat(as_of)
        now = date.fromisoformat(today) if today else date.today()
    except ValueError:
        return None
    age = (now - stamped).days
    if age < STALE_AFTER_DAYS:
        return None
    return (
        f"Paid-model prices are from {as_of} ({age} days ago). Providers "
        "reprice and retire models on a scale of months, so treat the cost "
        "figures below as indicative. Refresh them with "
        "`best-engine-ai-helper catalog update --cloud`."
    )


def blended_price_per_1m(entry: dict[str, Any]) -> float | None:
    """
    A single $/1M-token comparability figure for one catalog entry.

    A real workload's input/output ratio varies by task (a long-document
    summary is input-heavy; an open-ended generation is output-heavy), so this
    is a simple average of the two list prices, not a workload-specific
    estimate — the same "rough estimate, not a bill" honesty ``pricing.yaml``
    already documents for the ledger side.

    Returns ``None`` when the entry carries no price at all, which is **not**
    the same as a price of zero. This used to collapse to ``0.0``, and the
    consequence was quiet and bad: the ranker inverts price into a cost score,
    so an entry nobody had priced came out looking *free* and won the cost axis
    outright. A model whose cost is unknown has not earned that; it has simply
    not been measured, and the two deserve different answers.

    Parameters
    ----------
    entry : dict[str, Any]
        A catalog entry with ``input_per_1m``/``output_per_1m`` (USD).

    Returns
    -------
    float or None
        ``(input_per_1m + output_per_1m) / 2``, or None when neither price is
        present. A single missing side is treated as zero for that side, since
        a provider that bills only for output is a real arrangement.

    Examples
    --------
    >>> blended_price_per_1m({"input_per_1m": 2.0, "output_per_1m": 10.0})
    6.0
    >>> blended_price_per_1m({"input_per_1m": 0.0, "output_per_1m": 0.0})
    0.0
    >>> blended_price_per_1m({"id": "nobody-priced-this"}) is None
    True
    """
    lo_raw = entry.get("input_per_1m")
    hi_raw = entry.get("output_per_1m")
    if lo_raw is None and hi_raw is None:
        return None
    lo = float(lo_raw) if isinstance(lo_raw, (int, float)) else 0.0
    hi = float(hi_raw) if isinstance(hi_raw, (int, float)) else 0.0
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

    # Normalise the cost axis over the entries that actually have a price. An
    # unpriced entry is deliberately left out of the range: letting a None
    # participate as a zero would both best the cheapest real model and drag
    # the scale, and the whole point here is that "nobody priced this" is not a
    # claim about cost.
    known = [p for p in prices if p is not None]
    lo_s, hi_s = min(scores), max(scores)
    lo_p, hi_p = (min(known), max(known)) if known else (0.0, 0.0)

    unpriced = [
        str(e.get("id") or "?") for e, p in zip(candidates, prices, strict=True) if p is None
    ]
    if unpriced:
        osh.warning(
            "No price for "
            + ", ".join(sorted(unpriced))
            + "; ranked as the most expensive option rather than as free, so an "
            "unpriced model never wins on cost. Add the figures to pricing.yaml."
        )

    annotated = []
    for entry, score, price in zip(candidates, scores, prices, strict=True):
        row = dict(entry)
        row["score"] = score
        row["price_per_1m"] = price
        quality_n = _normalize(score, lo_s, hi_s)
        # Unknown cost scores as the worst, not the best. This package's stance
        # elsewhere is that a figure without provenance is worth less than no
        # figure; the same applies to a price nobody supplied, and the safe
        # direction for something that might bill you is pessimism.
        price_n = 0.0 if price is None else _normalize(price, lo_p, hi_p, invert=True)
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


def provider_status(catalog: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Which cloud providers are usable right now, and for the unusable, why.

    This package claims to route on the keys you actually hold, and that claim
    is only worth something if a caller can see it being applied. A provider
    whose key is missing is not a candidate, and saying so plainly — with the
    name of the variable to set — turns a silently shorter list of options into
    an actionable one.

    Never returns, logs, or compares a key *value*: only whether one resolved,
    and the name of the variable it would come from. The whole point of storing
    ``api_key_env`` rather than the key is that the secret stays out of every
    descriptor, report and screen, and that holds here too.

    Parameters
    ----------
    catalog : list of dict or None
        Cloud entries to take providers from. Defaults to the bundled
        ``pricing.yaml``.

    Returns
    -------
    list of dict
        One row per provider, sorted by name:
        ``{"provider", "key_env", "available", "reason", "models"}``.
    """
    from .engine import _DEFAULT_API_KEY_ENV
    from .llm import _cloud_api_key

    entries = catalog if catalog is not None else load_cloud_catalog()

    providers: dict[str, list[str]] = {}
    for entry in entries:
        name = str(entry.get("provider") or "").strip().lower()
        if name:
            providers.setdefault(name, []).append(str(entry.get("id") or "?"))

    rows: list[dict[str, Any]] = []
    for name in sorted(providers):
        key_env = _DEFAULT_API_KEY_ENV.get(name, f"{name.upper()}_API_KEY")
        try:
            resolved = bool(_cloud_api_key({"api_key_env": key_env}))
        except Exception as exc:  # noqa: BLE001 — a lookup failure is a finding
            resolved = False
            reason = f"could not check {key_env}: {exc}"
        else:
            reason = (
                ""
                if resolved
                else (
                    f"no API key found. Set {key_env} in settings.yaml, a .env file, "
                    "the environment, or the OS keychain."
                )
            )
        rows.append(
            {
                "provider": name,
                "key_env": key_env,
                "available": resolved,
                "reason": reason,
                "models": sorted(providers[name]),
            }
        )
    return rows
