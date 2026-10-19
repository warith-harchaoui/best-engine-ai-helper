"""
storage — what fits on the disk, and what fits in memory *at the same time*.

Two questions, and the second is the one people actually mean.

"How many models fit on my SSD" is easy and worth answering: disk is finite,
model files are large, and a 20 GB pull that fails halfway is a bad way to find
out. That part is a subtraction.

The question behind it is usually different. A working setup is rarely one
model: it is a text model, a vision model and an embedder, and the thing that
decides whether the day goes well is whether those can sit in memory
*together* rather than taking turns. Each one on its own may fit comfortably
while the trio does not, and nothing in a per-model view would ever say so.
This module answers both, and keeps them clearly apart.

Disk and memory are deliberately not the same budget here. ``disk_gb`` is the
file on disk; ``ram_gb`` is the peak working set while serving, which includes
the KV cache and runtime buffers. A model costs both, and confusing the two is
how a plan that looked fine runs out of memory.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from itertools import product
from typing import Any

import os_helper as osh

#: The kinds a working setup usually wants resident at once: something to
#: write with, something to look at images with, something to embed with.
RESIDENT_KINDS = ("llm", "vlm", "embed")

#: Free space below which pulling anything is likely to end badly. Not a
#: catalog figure -- it is headroom for the OS, logs and temporary files, which
#: need somewhere to go whatever the model does.
_DISK_FLOOR_GB = 5.0


def _disk_gb(entry: dict[str, Any]) -> float:
    """On-disk size of an entry, falling back to the memory figure when absent."""
    value = entry.get("disk_gb")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    # An entry refreshed from a directory may carry only a memory estimate. The
    # file is smaller than the working set, so this over-states rather than
    # under-states, which is the safe direction for a capacity plan.
    fallback = entry.get("ram_gb")
    return float(fallback) if isinstance(fallback, (int, float)) and fallback > 0 else 0.0


def resident_sets(
    entries: list[dict[str, Any]],
    budget_gb: float,
    *,
    kinds: tuple[str, ...] = RESIDENT_KINDS,
    backend: str = "ollama",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Best combinations, one model per kind, that fit in memory simultaneously.

    Takes the strongest candidate of each kind first and works down, so the
    answer is "the best set you can hold", not merely "a set that fits".

    Parameters
    ----------
    entries : list of dict
        Catalog entries, already ranked best-first within each kind if the
        caller has an opinion about ordering.
    budget_gb : float
        Memory available for models together, from
        :func:`score.effective_budget`.
    kinds : tuple of str
        Which kinds must be present. A kind with no candidate is skipped
        rather than making the whole answer empty.
    backend : str
        Serving backend, so footprints are sized the way they will load.
    limit : int
        How many combinations to return.

    Returns
    -------
    list of dict
        ``[{"models": {kind: id}, "total_ram_gb": float, "headroom_gb": float}]``,
        largest total first among those that fit.
    """
    from .score import model_footprint_gb

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for kind in kinds:
        pool = [e for e in entries if e.get("kind") == kind]
        if pool:
            by_kind[kind] = pool

    if not by_kind:
        return []

    present_kinds = list(by_kind)
    combos: list[dict[str, Any]] = []
    # The catalog is small (tens of entries), so an exhaustive product is both
    # exact and instant. If it ever grows to thousands this wants a bound, but
    # pretending to need one now would be guessing at a problem nobody has.
    for choice in product(*(by_kind[k] for k in present_kinds)):
        total = sum(model_footprint_gb(e, backend) for e in choice)
        if total > budget_gb:
            continue
        combos.append(
            {
                "models": {k: str(e.get("id")) for k, e in zip(present_kinds, choice)},
                "total_ram_gb": round(total, 1),
                "headroom_gb": round(budget_gb - total, 1),
            }
        )

    # Largest first: among sets that fit, the one using the most memory is the
    # most capable, which is what a reader of this list is choosing between.
    combos.sort(key=lambda c: c["total_ram_gb"], reverse=True)
    return combos[:limit]


def report(
    entries: list[dict[str, Any]],
    budget_gb: float,
    *,
    installed: set[str] | None = None,
    backend: str = "ollama",
    disk: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Answer both capacity questions for this machine.

    Parameters
    ----------
    entries : list of dict
        Catalog entries to plan against.
    budget_gb : float
        Memory available to models, from :func:`score.effective_budget`.
    installed : set of str or None
        Tags already on disk; those are not counted as future downloads.
    backend : str
        Serving backend.
    disk : dict or None
        Override for :func:`os_helper.disk_usage_gb`, for tests.

    Returns
    -------
    dict
        ``{"disk", "memory_budget_gb", "already_here", "pullable_now",
        "too_big_for_disk", "resident_sets", "warnings"}``.
    """
    from .catalog import servable_only

    # Plan only against models this backend could actually load. Without this
    # the report happily proposes an ApXML directory slug, which `ollama pull`
    # cannot resolve -- the same defect the recommender was fixed for, and a
    # capacity plan built on unpullable names is worse than no plan.
    entries = servable_only(entries, backend)

    usage = disk if disk is not None else osh.disk_usage_gb()
    free = float(usage.get("free_gb") or 0.0)
    present = installed or set()

    already: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        ident = str(entry.get("id") or "")
        if not ident:
            continue
        row = {"id": ident, "kind": entry.get("kind"), "disk_gb": round(_disk_gb(entry), 1)}
        # Plain membership is both necessary and sufficient: `pull.installed_tags`
        # already adds the bare form for a `:latest` tag and only for that, so a
        # looser `name.split(":")[0]` test would call `gemma3:12b` installed when
        # the daemon holds nothing but `gemma3:latest` -- a different model.
        if ident in present:
            already.append(row)
        else:
            candidates.append(row)

    # Spend only what is left above the floor: filling a disk to the last
    # gigabyte breaks the machine, not just the next pull.
    spendable = max(0.0, free - _DISK_FLOOR_GB)
    pullable: list[dict[str, Any]] = []
    running = 0.0
    for row in sorted(candidates, key=lambda r: r["disk_gb"]):
        if row["disk_gb"] <= 0:
            continue
        if running + row["disk_gb"] > spendable:
            continue
        running += row["disk_gb"]
        pullable.append(row)

    warnings: list[str] = []
    if free < _DISK_FLOOR_GB:
        warnings.append(
            f"Only {free:.1f} GB free, under the {_DISK_FLOOR_GB:.0f} GB floor this keeps "
            "clear for the OS. Nothing should be pulled until space is freed."
        )
    too_big = [r for r in candidates if r["disk_gb"] > spendable and r["disk_gb"] > 0]

    sets = resident_sets(entries, budget_gb, backend=backend)
    if not sets:
        warnings.append(
            f"No combination of one model per kind fits in {budget_gb:.1f} GB together; "
            "they would have to be loaded and unloaded in turn."
        )

    return {
        "disk": {
            "free_gb": round(free, 1),
            "total_gb": round(float(usage.get("total_gb") or 0.0), 1),
            "percent_used": round(float(usage.get("percent_used") or 0.0), 1),
            "spendable_gb": round(spendable, 1),
        },
        "memory_budget_gb": round(budget_gb, 1),
        "already_here": already,
        "pullable_now": pullable,
        "too_big_for_disk": too_big,
        "resident_sets": sets,
        "warnings": warnings,
    }
