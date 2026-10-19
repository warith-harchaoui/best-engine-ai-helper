"""Measure how much of each bundled catalog the LM Arena axis can actually rate.

README and LISEZMOI both state a coverage figure for the Arena axis — 6/10
cloud models, 3/20 local ones. This script is how that figure is obtained, so
the claim stays checkable instead of becoming folklore that nobody can
re-derive once the mirrors shift again.

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
from pathlib import Path
from typing import Any

import yaml

from best_engine_ai_helper.sources import arena

#: Repository root, so the script works from anywhere.
_ROOT = Path(__file__).resolve().parent.parent


def _local_ids() -> list[str]:
    """Model ids from the bundled local seed catalog."""
    entries = yaml.safe_load((_ROOT / "models.yaml").read_text(encoding="utf-8"))
    return [str(e["id"]) for e in entries]


def _cloud_ids() -> list[str]:
    """Model ids from the bundled cloud price list."""
    data = yaml.safe_load((_ROOT / "pricing.yaml").read_text(encoding="utf-8"))
    return [str(k) for k in data["models"]]


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

    return 0


if __name__ == "__main__":
    sys.exit(main())
