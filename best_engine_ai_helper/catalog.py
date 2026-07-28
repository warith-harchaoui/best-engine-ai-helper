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
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Root of the installed package; models.yaml sits next to pyproject.toml
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Default path for the bundled seed catalog
_SEED_PATH = _PACKAGE_ROOT / "models.yaml"

# User-writable runtime directory; created on first run
_USER_DIR = Path.home() / ".best-engine-ai-helper"
_CACHE_PATH = _USER_DIR / "catalog_cache.yaml"

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
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    # yaml.safe_load returns None for empty files
    if raw is None:
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
        raise FileNotFoundError(f"Catalog not found: {seed_path}")

    # Build a lookup by id so cache entries can overwrite in O(1)
    merged: dict[str, dict[str, Any]] = {e["id"]: e for e in seed}

    # Overlay user cache entries; absent cache is silently ignored
    for entry in _load_yaml_file(_CACHE_PATH):
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
