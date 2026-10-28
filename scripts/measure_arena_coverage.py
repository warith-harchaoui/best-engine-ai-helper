"""Measure how much of each bundled catalog the LM Arena axis can actually rate.

README and LISEZMOI both state a coverage figure for the Arena axis. This
script is how that figure is obtained, so the claim stays checkable instead of
becoming folklore that nobody can re-derive once the mirrors shift again.

It also measures the figure that matters more now: how many models the *price
source* prices and the leaderboard *also* rates. That intersection is what
``catalog update --cloud --arena`` adopts, and it is the only way the paid
catalog grows without someone typing in a score.

**Read through the package's own loaders, never from a hardcoded path.** This
script used to open ``models.yaml`` and ``pricing.yaml`` at the repository
root, and it stopped working the day those files moved inside the package —
silently, because nothing runs it in a test lane. A measurement a reader is
invited to re-run has to actually run.

The measurement deliberately passes ``max_age_days=0``. The adapter's default
behaviour is to *refuse* a snapshot past its staleness bar, which is correct
for merging: a year-old Elo would rank a previous generation of models first.
But the question here is not "are these ratings current", it is "which of our
model ids does the Arena name at all" — and name coverage is a property of the
leaderboard's roster, not of its freshness. Inspecting an old snapshot on
purpose is exactly the case the ``max_age_days=0`` escape hatch exists for.

What the numbers mean is in the two READMEs; the short version is that the
Arena rates large conversational models, which describes most of a cloud price
list and a minority of a local catalog.

Run it from the repository root::

    python scripts/measure_arena_coverage.py

It needs network access and downloads a sizeable mirror (tens of MB), so it is
a manual tool rather than part of any test lane.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import sys
from typing import Any

from best_engine_ai_helper import catalog, cloud_catalog
from best_engine_ai_helper.sources import arena, litellm_prices


def _local_ids() -> list[str]:
    """Model ids from the bundled local seed catalog."""
    return [str(e["id"]) for e in catalog.load_catalog()]


def _cloud_ids() -> list[str]:
    """Model ids from the bundled cloud price list."""
    return [str(e["id"]) for e in cloud_catalog.load_cloud_catalog()]


def _coverage(ids: list[str], scores: dict[str, dict[str, float]]) -> tuple[list[str], list[str]]:
    """
    Split `ids` into those the Arena rates on any axis and those it does not.

    A model counts as covered as soon as one axis matches, since a single
    rating is enough to populate the axis for that entry.

    Parameters
    ----------
    ids : list of str
        Catalog model ids to test.
    scores : dict
        ``{axis: {arena_model_name: score}}`` as returned by the adapter.

    Returns
    -------
    (matched, missed)
        Both in input order.
    """
    matched: list[str] = []
    for ident in ids:
        if any(arena.match_model(ident, rows) is not None for rows in scores.values()):
            matched.append(ident)
    missed = [i for i in ids if i not in matched]
    return matched, missed


def main() -> int:
    """Print the coverage measurement. Returns a process exit code."""
    result: dict[str, Any] = arena.fetch_arena_ratings(timeout=60.0, max_age_days=0)
    scores = result.get("scores") or {}

    print(f"source   : {result.get('source')}")
    print(f"snapshot : {result.get('snapshot')}  (age {result.get('age_days')} days)")
    print(f"note     : {result.get('note')}")
    print(f"axes     : { {axis: len(rows) for axis, rows in scores.items()} }")
    print()

    if not scores:
        # Every mirror can rot at once; that is the documented steady state as
        # of 2026-10, and it is a finding rather than a crash.
        print("No ratings available from any mirror -- nothing to measure.")
        return 1

    for label, ids in (("local  models.yaml", _local_ids()), ("cloud  pricing.yaml", _cloud_ids())):
        matched, missed = _coverage(ids, scores)
        print(f"{label}: {len(matched)}/{len(ids)} matched")
        print(f"   matched: {matched}")
        print(f"   missed : {missed}")
        print()

    # The intersection that `catalog update --cloud --arena` turns into entries.
    # Coverage of what the catalog already holds answers "can the models I have
    # be scored"; this answers "which models could I have at all", which is the
    # question the paid catalog was stuck on.
    print("--- adoptable: priced by the source AND rated by the board ---")
    try:
        priced = litellm_prices.fetch_cloud_prices(timeout=60.0)
    except Exception as exc:  # noqa: BLE001 — a dead source is a finding, not a crash
        print(f"price source unavailable: {exc}")
        return 0

    known = set(_cloud_ids())
    adoptable = cloud_catalog.adopt_rated(priced, result, known)
    rankable = [
        e for e in priced if e.get("kind") in {"llm", "vlm"} and (e.get("input_per_1m") or 0) > 0
    ]
    print(f"priced and callable : {len(rankable)} (of {len(priced)} rows the source returned)")
    print(f"already in catalog  : {len(known)}")
    print(
        f"adoptable right now : {len(adoptable)}"
        + ("  (nothing the board rates that the catalog lacks)" if not adoptable else "")
    )
    # Counted against the EFFECTIVE catalog, cache included. Run it once and
    # the number drops to zero, which is the mechanism working rather than the
    # measurement failing: `rm ~/.best-engine-ai-helper/pricing_cache.yaml`
    # returns you to the seed and to the figure a first run would see.
    for entry in adoptable:
        cited = ", ".join(f"{a}={n}" for a, n in (entry.get("arena_matched") or {}).items())
        price = f"{entry['input_per_1m']}/{entry['output_per_1m']}"
        print(f"   {entry['id']:<26} {entry['provider']:<10} {price:<12} {cited}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
