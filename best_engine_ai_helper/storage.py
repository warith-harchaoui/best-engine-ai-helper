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


class _Set:
    """One candidate set, ordered weakest-first.

    The ranking is score, then memory, then model id — but the id reads
    *backwards* from the other two: a larger id is the weaker tiebreak, since
    the published order is ids ascending. A plain tuple would therefore put
    the wrong member of a tie at the top of the min-heap below, and the set
    that should have been published would be the one discarded. Found by the
    differential test rather than by reading: the heap and the final sort
    agreed on score and on memory, and disagreed only when both tied.
    """

    __slots__ = ("ids", "ram", "score")

    def __init__(self, score: float, ram: float, ids: tuple[str, ...]) -> None:
        self.score = score
        self.ram = ram
        self.ids = ids

    def __lt__(self, other: _Set) -> bool:
        """True when this set is the weaker of the two."""
        if self.score != other.score:
            return self.score < other.score
        if self.ram != other.ram:
            return self.ram < other.ram
        return self.ids > other.ids


def _quality(entry: dict[str, Any], kind: str) -> float:
    """
    The benchmark score this kind is judged on, or 0.0 when it carries none.

    The three kinds are not scored on the same axis: a text model is read on
    ``general``, a vision model on ``vision``, an embedder on
    :data:`score.EMBED_SCORE_KEY`. Asking an embedder for a general score
    returns nothing, which would rank every embedder identically.

    A missing score reads as 0.0 rather than being guessed at, which puts
    unscored entries below every scored one — the same rule the catalog
    follows for the hundreds of library entries that publish sizes but no
    leaderboard results.
    """
    from .score import EMBED_SCORE_KEY, _benchmark_score

    if kind == "embed":
        return float((entry.get("benchmarks") or {}).get(EMBED_SCORE_KEY) or 0.0)
    return float(_benchmark_score(entry, "vlm" if kind == "vlm" else "llm"))


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

    Ranked on **quality first**, memory second. Earlier versions ordered on
    total memory alone, on the argument that among sets that fit, the one
    using the most is the most capable. That is a proxy, and a weak one: a
    20 GB model scoring 60 is not a better companion than an 18 GB model
    scoring 85. Benchmark score is the thing actually meant, so it is the
    thing sorted on; total memory stays as the tiebreak, which keeps the old
    order exactly when nothing is scored — the normal state for the hundreds
    of library entries that publish sizes but no leaderboard results.

    Searched by branch and bound over kinds sorted best-first, not by
    enumerating every combination. Two bounds do the work: a set whose
    remaining kinds cannot fit even at their lightest is skipped, and once
    ``limit`` results are in hand, a branch that cannot beat the weakest of
    them even at its best ends the scan of that kind. Both are exact -- the
    result is identical to an exhaustive product, which `tests/test_storage.py`
    pins differentially against this function.

    The score is a **sum across kinds of figures from different leaderboards**,
    so it ranks sets against each other and is not a measurement of anything.
    It is reported as ``total_score`` so the ordering is visible rather than
    being an invisible key the reader has to take on trust.

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
        ``[{"models": {kind: id}, "total_score": float, "total_ram_gb": float,
        "headroom_gb": float}]``, best total score first among those that fit,
        then largest total memory, then model id so repeated runs agree.
    """
    from .score import model_footprint_gb, sizeable_only

    if limit <= 0:
        return []

    # Size every candidate ONCE. The exhaustive version called this inside the
    # product, so a 420-entry catalog cost 230,850 calls to compute 76,950
    # sums -- three quarters of the time went to re-deriving the same numbers.
    sizeable = sizeable_only(list(entries), backend, where="resident set planning")
    pools: list[tuple[str, list[tuple[float, float, str]]]] = []
    for kind in kinds:
        # Best first, on the same composite the answer is ranked by: score,
        # then memory. Every bound below depends on this order, because a
        # bound may only `break` out of a scan whose objective cannot rise
        # again.
        sized = sorted(
            (
                (_quality(e, kind), model_footprint_gb(e, backend), str(e.get("id")))
                for e in sizeable
                if e.get("kind") == kind
            ),
            key=lambda row: (-row[0], -row[1], row[2]),
        )
        if sized:
            pools.append((kind, sized))

    if not pools:
        return []

    # What the remaining kinds can contribute at best, and what they cost at
    # their lightest. These are the whole trick: they turn "try every
    # combination" into "try the ones that could still matter".
    n = len(pools)
    cheapest_rest = [0.0] * (n + 1)
    best_score_rest = [0.0] * (n + 1)
    best_ram_rest = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        sized = pools[i][1]
        cheapest_rest[i] = cheapest_rest[i + 1] + min(row[1] for row in sized)
        best_score_rest[i] = best_score_rest[i + 1] + sized[0][0]
        best_ram_rest[i] = best_ram_rest[i + 1] + max(row[1] for row in sized)

    # A min-heap of the best `limit` sets found so far, keyed by the ranking
    # composite, so the weakest kept set is always heap[0] and the bound below
    # can consult it in O(1).
    best: list[_Set] = []

    def _walk(i: int, score: float, ram: float, chosen: tuple[str, ...]) -> None:
        if i == n:
            found = _Set(score, ram, chosen)
            if len(best) < limit:
                heapq.heappush(best, found)
            elif best[0] < found:
                heapq.heapreplace(best, found)
            return

        for entry_score, footprint, ident in pools[i][1]:
            run_score = score + entry_score
            run_ram = ram + footprint

            # Bound 1 -- budget. Even paired with the lightest of every
            # remaining kind this overruns, so the set cannot fit. Entries
            # further down this kind may still be light enough, so this skips
            # rather than stops.
            if run_ram + cheapest_rest[i + 1] > budget_gb:
                continue

            # Bound 2 -- the answer is only `limit` rows. Even paired with the
            # best of every remaining kind, this branch cannot reach the
            # weakest set already kept; and the scan is ordered best-first on
            # the same composite, so nothing further down can either. Strictly
            # worse, not merely equal: an equal branch can still win on the id
            # tiebreak, and pruning it would make the answer depend on search
            # order. That strictness is also why this still prunes hard when
            # nothing is scored at all -- the comparison then falls through to
            # memory, which is exactly the old behaviour.
            if len(best) == limit and (
                run_score + best_score_rest[i + 1],
                run_ram + best_ram_rest[i + 1],
            ) < (best[0].score, best[0].ram):
                break

            _walk(i + 1, run_score, run_ram, chosen + (ident,))

    _walk(0, 0.0, 0.0, ())

    # Best first: the strongest set you can hold, with memory breaking ties
    # and the model ids breaking those, so repeated runs give the same answer.
    kind_names = [kind for kind, _ in pools]
    return [
        {
            "models": dict(zip(kind_names, found.ids)),
            "total_score": round(found.score, 1),
            "total_ram_gb": round(found.ram, 1),
            "headroom_gb": round(budget_gb - found.ram, 1),
        }
        # `_Set` orders weakest-first, so strongest-first is that reversed.
        for found in sorted(best, reverse=True)
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
