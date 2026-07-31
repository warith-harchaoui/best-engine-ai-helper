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
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SEED_PATH = _PACKAGE_ROOT / "hardware.yaml"

_USER_DIR = Path.home() / ".best-engine-ai-helper"
_HW_CACHE_PATH = _USER_DIR / "hardware_cache.yaml"


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
