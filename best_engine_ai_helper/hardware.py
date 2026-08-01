"""
hardware — load and query the bundled chip lookup table.

The hardware database records the usable memory for each known GPU or Apple
Silicon chip. 'Usable' means the pool available to Ollama after the OS,
display driver, and kernel pages have reserved their share. The 80% safety
headroom in score.py applies on top of this value.

Like the model catalog, the hardware table has two layers:

1. The **bundled seed** (`hardware.yaml` in the package root).
2. The **user cache** (`~/.best-engine-ai-helper/hardware_cache.yaml`), written
   by `hardware update`. Cache entries overwrite seed entries on the same
   (chip, memory_gb) pair.

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

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SEED_PATH = _PACKAGE_ROOT / "hardware.yaml"

_USER_DIR = Path.home() / ".best-engine-ai-helper"
_HW_CACHE_PATH = _USER_DIR / "hardware_cache.yaml"

# Public alias so callers (the CLI, tests) can name the cache directly.
CACHE_PATH = _HW_CACHE_PATH

# Share of the memory pool the OS, display driver, and kernel keep for
# themselves before Ollama sees it. Matches the bundled seed's ratios
# (8 GB → 7 usable, 16 GB → 14), on top of which score.py's 80% headroom
# still applies.
_OS_RESERVATION = 0.125


def _load_yaml_file(path: Path) -> list[dict[str, Any]]:
    """
    Load a YAML file as a list of dicts; return [] on absence or empty file.

    Parameters
    ----------
    path : Path
        Absolute path to the YAML file.

    Returns
    -------
    list[dict[str, Any]]
        Parsed entries, or [] if the file is missing or empty.
    """
    if not osh.file_exists(str(path)):
        osh.debug(f"Hardware YAML absent, treating as empty:\n\t{path}")
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        osh.warning(f"Malformed hardware YAML, ignoring:\n\t{path}\n\t{exc}")
        return []
    return list(raw) if raw else []


def load_hardware(hardware_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load the bundled hardware chip table merged with the user's local cache.

    Cache entries whose (chip, memory_gb) pair matches a seed entry overwrite
    it. New entries are appended. The seed file is never modified.

    Parameters
    ----------
    hardware_path : Path or None
        Path to the seed `hardware.yaml`. Defaults to the bundled file.
        Pass an explicit path in tests to use a fixture.

    Returns
    -------
    list[dict[str, Any]]
        Merged hardware entries. Each entry has at minimum: ``chip``,
        ``vendor``, ``memory_gb``, ``ollama_usable_gb``.

    Examples
    --------
    >>> entries = load_hardware()
    >>> len(entries) > 0
    True
    >>> all('chip' in e for e in entries)
    True
    """
    seed_path = hardware_path if hardware_path is not None else _SEED_PATH
    seed = _load_yaml_file(seed_path)
    osh.info(f"Loaded {len(seed)} hardware entry(ies) from seed:\n\t{seed_path}")

    # Composite key: chip name + memory tier (multiple tiers per chip are common)
    def _key(e: dict[str, Any]) -> tuple[str, float]:
        return (e["chip"], float(e.get("memory_gb", 0)))

    merged: dict[tuple[str, float], dict[str, Any]] = {_key(e): e for e in seed}

    for entry in _load_yaml_file(_HW_CACHE_PATH):
        merged[_key(entry)] = entry

    # Preserve seed ordering, append cache-only entries at the end
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for e in seed:
        k = _key(e)
        result.append(merged[k])
        seen.add(k)
    for k, entry in merged.items():
        if k not in seen:
            result.append(entry)

    return result


def lookup_chip(chip_name: str, hardware: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Find a hardware entry by a case-insensitive substring match on the chip name.

    When multiple entries share the same chip name (for example, an Apple M2 Max
    at 32 GB and at 96 GB), this returns the first match in the list order. The
    caller should supply the most specific chip string available to avoid ambiguity.

    Parameters
    ----------
    chip_name : str
        Chip name or substring to search for, e.g. ``'Apple M2 Max'``.
    hardware : list[dict[str, Any]]
        Hardware entries as returned by :func:`load_hardware`.

    Returns
    -------
    dict[str, Any] or None
        The first matching entry, or None if no entry contains ``chip_name``
        as a case-insensitive substring.

    Examples
    --------
    >>> hw = load_hardware()
    >>> entry = lookup_chip('Apple M2 Max', hw)
    >>> entry is not None
    True
    >>> entry['vendor']
    'apple'
    """
    needle = chip_name.lower()
    for entry in hardware:
        # Substring match lets 'M2 Max' match 'Apple M2 Max' without
        # requiring the caller to know the exact prefix
        if needle in entry.get("chip", "").lower():
            osh.debug(f"Chip '{chip_name}' matched entry '{entry.get('chip')}'")
            return entry
    osh.warning(f"Chip not found in hardware table:\n\t{chip_name}")
    return None


# ---------------------------------------------------------------------------
# Cache refresh (`hardware update`)
# ---------------------------------------------------------------------------

# Which detected memory pool is the inference budget, per compute vendor.
_VENDOR_MEMORY_KEY: dict[str, str] = {
    "apple": "unified_gb",  # unified pool shared with the CPU
    "nvidia": "vram_gb",
    "amd": "vram_gb",
}


def _today() -> str:
    """Return today's date as an ISO 8601 string (UTC), for the ``fetched_at`` stamp."""
    return datetime.now(timezone.utc).date().isoformat()


def detect_local_entry(fetched_at: str | None = None) -> dict[str, Any] | None:
    """
    Build a hardware entry for the machine this runs on, from live detection.

    There is no public specs API for the full GPU/Apple-Silicon universe, so a
    refresh records ground truth for the current machine instead: the detected
    chip, its memory pool, and the Ollama-usable share after the OS reservation.
    Repeated runs upsert the same row (keyed on chip + memory tier), keeping the
    table correct for whatever hardware the user actually has.

    Parameters
    ----------
    fetched_at : str or None
        Refresh timestamp for the entry; defaults to today (UTC).

    Returns
    -------
    dict[str, Any] or None
        A hardware entry, or None when no usable memory figure could be detected
        (nothing worth writing).
    """
    from . import detect

    vendor = detect.chip_vendor()
    profile = detect.compute_profile()
    memory = detect.available_memory()

    # Pick the pool that bounds inference for this vendor; CPU-only falls back to
    # system RAM, which available_memory always populates.
    mem_key = _VENDOR_MEMORY_KEY.get(vendor, "ram_gb")
    memory_gb = memory.get(mem_key) or memory.get("ram_gb")
    if not memory_gb:
        osh.warning("No usable memory detected; nothing to record for this machine.")
        return None

    # Prefer the detected chip label; fall back to a vendor tag when the platform
    # does not expose a specific name (discrete GPUs on Linux, plain CPUs).
    chip = profile.get("chip") or f"{vendor.upper()} ({profile.get('accelerator')})"

    memory_gb = round(float(memory_gb), 1)
    return {
        "chip": chip,
        "vendor": vendor,
        "memory_gb": memory_gb,
        "ollama_usable_gb": round(memory_gb * (1.0 - _OS_RESERVATION), 1),
        "source": "detected",
        "fetched_at": fetched_at or _today(),
    }


def write_cache(
    entries: list[dict[str, Any]], cache_path: Path | None = None
) -> Path:
    """
    Merge ``entries`` into the hardware cache by (chip, memory_gb) and write it.

    Existing cache rows are preserved; an incoming row on the same chip and
    memory tier overwrites it, so a refresh is idempotent. The bundled seed is
    untouched.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Hardware entries to add or update, e.g. from :func:`detect_local_entry`.
    cache_path : Path or None
        Destination cache file. Defaults to :data:`CACHE_PATH`; override in tests.

    Returns
    -------
    Path
        The path written.
    """
    path = cache_path if cache_path is not None else _HW_CACHE_PATH

    def _key(e: dict[str, Any]) -> tuple[str, float]:
        return (e["chip"], float(e.get("memory_gb", 0)))

    merged: dict[tuple[str, float], dict[str, Any]] = {
        _key(e): e for e in _load_yaml_file(path)
    }
    for entry in entries:
        merged[_key(entry)] = entry

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(list(merged.values()), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    osh.info(f"Wrote {len(merged)} cached hardware entry(ies):\n\t{path}")
    return path
