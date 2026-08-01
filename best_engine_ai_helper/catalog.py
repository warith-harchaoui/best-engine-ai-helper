"""
catalog — load and merge the bundled model catalog with the user's cache.

The catalog lives in two layers:

1. The **bundled seed** (`models.yaml` in the package root). Hand-maintained,
   always present, never deleted by auto-refresh.
2. The **user cache** (`~/.best-engine-ai-helper/catalog_cache.yaml`). Written
   by `catalog update`; entries keyed by `id` overwrite matching seed entries.
   Absent on first run; load_catalog silently skips it in that case.

Keeping the seed immutable and the cache additive means offline machines always
have a usable catalog and updates never lose hand-curated data.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

# Root of the installed package; models.yaml sits next to pyproject.toml
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Default path for the bundled seed catalog
_SEED_PATH = _PACKAGE_ROOT / "models.yaml"

# User-writable runtime directory; created on first run
_USER_DIR = Path.home() / ".best-engine-ai-helper"
_CACHE_PATH = _USER_DIR / "catalog_cache.yaml"

# Public alias so callers (the CLI, tests) can name the cache without reaching
# into a private attribute.
CACHE_PATH = _CACHE_PATH

# Quant-specific overhead factors for estimating peak inference RAM.
# Values are empirically derived: KV cache at 4K context adds ~10-20%
# beyond on-disk size depending on quantization precision.
_QUANT_OVERHEAD: dict[str, float] = {
    "Q4_K_M": 1.12,
    "Q8_0": 1.10,
    "FP16": 1.05,
    "Q2_K": 1.20,
}
_DEFAULT_OVERHEAD = 1.15  # fallback for unknown quant identifiers


def estimate_ram(disk_gb: float, quant: str) -> float:
    """
    Estimate peak inference RAM from on-disk model size.

    The estimate covers the model weights plus KV cache at the default context
    length (4K tokens). For models with very large context windows (256K+),
    actual RAM may exceed this estimate significantly; treat it as a lower bound.

    Parameters
    ----------
    disk_gb : float
        On-disk footprint of the model in GB.
    quant : str
        Quantization identifier, e.g. 'Q4_K_M', 'Q8_0', 'FP16', 'Q2_K'.

    Returns
    -------
    float
        Estimated peak RAM in GB.

    Examples
    --------
    >>> estimate_ram(6.1, 'Q4_K_M')
    6.832
    >>> estimate_ram(10.0, 'FP16')
    10.5
    """
    overhead = _QUANT_OVERHEAD.get(quant, _DEFAULT_OVERHEAD)
    return round(disk_gb * overhead, 3)


def _load_yaml_file(path: Path) -> list[dict[str, Any]]:
    """
    Load a YAML file and return its contents as a list of dicts.

    Returns an empty list on FileNotFoundError so callers can treat the
    absence of the cache file as a no-op rather than an error.

    Parameters
    ----------
    path : Path
        Absolute path to the YAML file.

    Returns
    -------
    list[dict[str, Any]]
        Parsed entries, or [] if the file is absent or empty.
    """
    if not osh.file_exists(str(path)):
        osh.debug(f"YAML file absent, treating as empty:\n\t{path}")
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        osh.warning(f"Malformed YAML, ignoring:\n\t{path}\n\t{exc}")
        return []
    # yaml.safe_load returns None for empty files
    if raw is None:
        osh.debug(f"YAML file empty, treating as empty:\n\t{path}")
        return []
    return list(raw)


def load_catalog(catalog_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load the bundled seed catalog merged with the user's local cache.

    Cache entries whose `id` matches a seed entry overwrite the seed entry.
    New cache entries (no matching seed id) are appended. The seed is never
    modified on disk.

    Parameters
    ----------
    catalog_path : Path or None
        Path to the seed `models.yaml`. Defaults to the bundled file next to
        `pyproject.toml`. Pass an explicit path in tests to use a fixture.

    Returns
    -------
    list[dict[str, Any]]
        Merged model entries. Each entry is guaranteed to have at minimum:
        ``id``, ``kind``, ``ram_gb``, ``benchmarks``.

    Raises
    ------
    FileNotFoundError
        If ``catalog_path`` is given explicitly and does not exist.

    Examples
    --------
    >>> entries = load_catalog()
    >>> len(entries) > 0
    True
    >>> all('id' in e for e in entries)
    True
    """
    seed_path = catalog_path if catalog_path is not None else _SEED_PATH

    # Start with the bundled seed; this must exist
    seed = _load_yaml_file(seed_path)
    if not seed and catalog_path is not None:
        osh.error(f"Catalog not found:\n\t{seed_path}")
        raise FileNotFoundError(f"Catalog not found: {seed_path}")
    osh.info(f"Loaded {len(seed)} model(s) from seed catalog:\n\t{seed_path}")

    # Build a lookup by id so cache entries can overwrite in O(1)
    merged: dict[str, dict[str, Any]] = {e["id"]: e for e in seed}

    # Overlay user cache entries; absent cache is silently ignored
    cache_entries = _load_yaml_file(_CACHE_PATH)
    if cache_entries:
        osh.info(f"Overlaying {len(cache_entries)} cached entry(ies):\n\t{_CACHE_PATH}")
    for entry in cache_entries:
        merged[entry["id"]] = entry

    # Preserve seed ordering; append cache-only entries at the end
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in seed:
        result.append(merged[e["id"]])
        seen.add(e["id"])
    for eid, entry in merged.items():
        if eid not in seen:
            result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Cache refresh (`catalog update`)
# ---------------------------------------------------------------------------

# The default quant we pull, and the quant whose VRAM ApXML's headline figure
# mirrors, so disk_gb is estimated back out of ram_gb through its overhead.
_REFRESH_QUANT = "Q4_K_M"

# Empty benchmark block: ApXML's static pages carry specs and memory-fit
# figures but no numeric leaderboard scores, so refreshed entries rank at the
# bottom until a scored source fills these axes.
_EMPTY_BENCHMARKS: dict[str, float | None] = {
    "general": None,
    "vision": None,
    "ocr": None,
    "code": None,
    "math": None,
}


def _today() -> str:
    """Return today's date as an ISO 8601 string (UTC), for the ``fetched_at`` stamp."""
    return datetime.now(timezone.utc).date().isoformat()


def normalize_apxml_spec(spec: dict[str, Any], fetched_at: str) -> dict[str, Any] | None:
    """
    Map one ApXML spec dict onto a catalog entry.

    The ApXML adapter (:mod:`best_engine_ai_helper.sources.apxml`) yields spec
    and memory-fit metadata but no numeric benchmarks, so the ``benchmarks``
    block is left null. ``disk_gb`` is estimated from the Q4 VRAM figure by
    dividing out the quant overhead — the inverse of :func:`estimate_ram`.

    Parameters
    ----------
    spec : dict[str, Any]
        A normalized spec as returned by ``apxml.parse_model_page``.
    fetched_at : str
        ISO 8601 date recorded on the entry as its refresh timestamp.

    Returns
    -------
    dict[str, Any] or None
        A catalog entry, or None when the spec lacks the ``slug`` needed to key
        it (such an entry could never be merged or pulled).
    """
    slug = spec.get("slug")
    if not slug:
        osh.debug(f"ApXML spec without a slug, skipping:\n\t{spec.get('name')!r}")
        return None

    ram_gb = spec.get("ram_gb")
    # Invert estimate_ram: disk ≈ ram / overhead. Estimate only, like the seed.
    disk_gb = (
        round(float(ram_gb) / _QUANT_OVERHEAD[_REFRESH_QUANT], 2)
        if ram_gb is not None
        else None
    )

    return {
        "id": slug,
        "kind": spec.get("kind", "llm"),
        "size_b": spec.get("size_b"),
        "quant": _REFRESH_QUANT,
        "disk_gb": disk_gb,
        "ram_gb": ram_gb,
        "benchmarks": dict(_EMPTY_BENCHMARKS),
        "vllm_id": spec.get("vllm_id"),
        "context_length": spec.get("context_length"),
        "license": spec.get("license"),
        "url": spec.get("url"),
        "source": "apxml",
        "fetched_at": fetched_at,
    }


def normalize_apxml_specs(
    specs: list[dict[str, Any]], fetched_at: str | None = None
) -> list[dict[str, Any]]:
    """
    Normalize a batch of ApXML specs into catalog entries, dropping unusable ones.

    Parameters
    ----------
    specs : list[dict[str, Any]]
        Specs as returned by ``apxml.fetch_open_weight_models``.
    fetched_at : str or None
        Refresh timestamp for every entry; defaults to today (UTC).

    Returns
    -------
    list[dict[str, Any]]
        Catalog entries, in input order, minus specs with no slug.
    """
    stamp = fetched_at or _today()
    entries = [normalize_apxml_spec(spec, stamp) for spec in specs]
    return [e for e in entries if e is not None]


def write_cache(
    entries: list[dict[str, Any]], cache_path: Path | None = None
) -> Path:
    """
    Merge ``entries`` into the user catalog cache by ``id`` and write it to disk.

    Existing cache entries are preserved; an incoming entry whose ``id`` matches
    one already cached overwrites it, so a refresh is idempotent and never loses
    previously cached models. The bundled seed is untouched.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Catalog entries to add or update, e.g. from :func:`normalize_apxml_specs`.
    cache_path : Path or None
        Destination cache file. Defaults to :data:`CACHE_PATH`; override in tests.

    Returns
    -------
    Path
        The path written.
    """
    path = cache_path if cache_path is not None else _CACHE_PATH

    merged: dict[str, dict[str, Any]] = {e["id"]: e for e in _load_yaml_file(path)}
    for entry in entries:
        merged[entry["id"]] = entry

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(list(merged.values()), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    osh.info(f"Wrote {len(merged)} cached model(s):\n\t{path}")
    return path
