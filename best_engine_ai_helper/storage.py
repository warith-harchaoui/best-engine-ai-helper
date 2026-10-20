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

import heapq
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

    Searched by branch and bound over kinds sorted heaviest-first, not by
    enumerating every combination. Two bounds do the work: a set whose
    remaining kinds cannot fit even at their lightest is skipped, and once
    ``limit`` results are in hand, a branch that cannot beat the weakest of
    them even at its heaviest ends the scan of that kind. Both are exact --
    the result is identical to the exhaustive product, which `tests/
    test_storage.py` pins differentially against this function.

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
        largest total first among those that fit, ties broken on model id so
        repeated runs agree.
    """
    from .score import model_footprint_gb, sizeable_only

    if limit <= 0:
        return []

    # Size every candidate ONCE. The exhaustive version called this inside the
    # product, so a 420-entry catalog cost 230,850 calls to compute 76,950
    # sums -- three quarters of the time went to re-deriving the same numbers.
    sizeable = sizeable_only(list(entries), backend, where="resident set planning")
    pools: list[tuple[str, list[tuple[float, str]]]] = []
    for kind in kinds:
        # Heaviest first. Every bound below depends on this order.
        sized = sorted(
            (
                (model_footprint_gb(e, backend), str(e.get("id")))
                for e in sizeable
                if e.get("kind") == kind
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        if sized:
            pools.append((kind, sized))

    if not pools:
        return []

    # What the rest of the kinds cost at their lightest and at their heaviest.
    # These two numbers are the whole trick: they turn "try every combination"
    # into "try the ones that could still matter".
    n = len(pools)
    suffix_min = [0.0] * (n + 1)
    suffix_max = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        sized = pools[i][1]
        suffix_min[i] = suffix_min[i + 1] + sized[-1][0]
        suffix_max[i] = suffix_max[i + 1] + sized[0][0]

    # A min-heap of the best `limit` combinations found so far, so the K-th
    # best total is always heap[0] and the bound below can consult it in O(1).
    best: list[tuple[float, tuple[str, ...]]] = []

    def _walk(i: int, partial: float, chosen: tuple[str, ...]) -> None:
        if i == n:
            if len(best) < limit:
                heapq.heappush(best, (partial, chosen))
            elif partial > best[0][0]:
                heapq.heapreplace(best, (partial, chosen))
            return

        for footprint, ident in pools[i][1]:
            running = partial + footprint

            # Bound 1 -- budget. Even paired with the lightest of every
            # remaining kind this overruns, so the set cannot fit. Lighter
            # entries in this same kind still might, hence `continue`.
            if running + suffix_min[i + 1] > budget_gb:
                continue

            # Bound 2 -- the answer is only `limit` rows. Even paired with the
            # heaviest of every remaining kind this cannot beat the K-th best
            # total already found, and entries are heaviest-first, so nothing
            # further down this kind can either. That makes `break` safe, and
            # it is what collapses the cost: the search stops as soon as it
            # can prove the rest is unreachable rather than enumerating it.
            if len(best) == limit and running + suffix_max[i + 1] <= best[0][0]:
                break

            _walk(i + 1, running, chosen + (ident,))

    _walk(0, 0.0, ())

    # Largest first: among sets that fit, the one using the most memory is the
    # most capable, which is what a reader of this list is choosing between.
    # Ties break on the model ids, so repeated runs give the same answer --
    # the exhaustive version left equal totals in catalog order, which was
    # stable only by accident.
    kind_names = [kind for kind, _ in pools]
    return [
        {
            "models": dict(zip(kind_names, ids)),
            "total_ram_gb": round(total, 1),
            "headroom_gb": round(budget_gb - total, 1),
        }
        for total, ids in sorted(best, key=lambda pair: (-pair[0], pair[1]))
    ]


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
