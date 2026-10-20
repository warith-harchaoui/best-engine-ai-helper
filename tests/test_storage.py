"""
Tests for best_engine_ai_helper.storage.

Two questions are being answered and they must not be confused: what fits on
disk (file sizes), and what can be held in memory at the same time (working
sets). The cases below pin the difference, the headroom the planner keeps
clear, and the gate that stops it proposing models the backend cannot load.
"""

from __future__ import annotations

from best_engine_ai_helper import storage

_DISK = {"free_gb": 100.0, "total_gb": 500.0, "percent_used": 80.0}


def _catalog() -> list[dict]:
    return [
        {"id": "big:32b", "kind": "llm", "ram_gb": 20.0, "disk_gb": 18.0},
        {"id": "small:8b", "kind": "llm", "ram_gb": 6.0, "disk_gb": 5.0},
        {"id": "eyes:8b", "kind": "vlm", "ram_gb": 7.0, "disk_gb": 6.0},
        {"id": "embed:small", "kind": "embed", "ram_gb": 1.0, "disk_gb": 0.5},
    ]


# ---------------------------------------------------------------------------
# What can be held at once
# ---------------------------------------------------------------------------


def test_the_best_set_that_fits_is_reported_first() -> None:
    sets = storage.resident_sets(_catalog(), budget_gb=40.0)

    assert sets[0]["models"] == {"llm": "big:32b", "vlm": "eyes:8b", "embed": "embed:small"}
    assert sets[0]["total_ram_gb"] == 28.0
    assert sets[0]["headroom_gb"] == 12.0


def test_a_budget_that_fits_each_alone_but_not_together_says_so() -> None:
    """The case a per-model view can never surface."""
    # 20 + 7 + 1 = 28, so a 25 GB budget holds any single model but not the trio
    # with the big one in it.
    sets = storage.resident_sets(_catalog(), budget_gb=25.0)

    assert all(s["models"]["llm"] != "big:32b" for s in sets)
    assert sets[0]["models"]["llm"] == "small:8b"


def test_no_combination_fitting_is_an_empty_list_not_a_guess() -> None:
    assert storage.resident_sets(_catalog(), budget_gb=2.0) == []


def test_a_missing_kind_does_not_empty_the_answer() -> None:
    """A catalog with no embedder should still plan an llm plus a vlm."""
    entries = [e for e in _catalog() if e["kind"] != "embed"]

    sets = storage.resident_sets(entries, budget_gb=40.0)

    assert sets
    assert set(sets[0]["models"]) == {"llm", "vlm"}


# ---------------------------------------------------------------------------
# What fits on disk
# ---------------------------------------------------------------------------


def test_models_already_here_are_not_counted_as_downloads() -> None:
    report = storage.report(_catalog(), budget_gb=40.0, installed={"big:32b"}, disk=dict(_DISK))

    assert [r["id"] for r in report["already_here"]] == ["big:32b"]
    assert "big:32b" not in [r["id"] for r in report["pullable_now"]]


def test_the_planner_keeps_a_floor_clear_for_the_os() -> None:
    """Filling a disk to the last gigabyte breaks the machine, not just the pull."""
    report = storage.report(
        _catalog(), budget_gb=40.0, disk={"free_gb": 8.0, "total_gb": 500.0, "percent_used": 98.0}
    )

    # 8 GB free minus the 5 GB floor leaves 3 GB, so only the embedder fits.
    assert [r["id"] for r in report["pullable_now"]] == ["embed:small"]
    assert report["disk"]["spendable_gb"] == 3.0


def test_a_disk_under_the_floor_warns_and_offers_nothing() -> None:
    report = storage.report(
        _catalog(), budget_gb=40.0, disk={"free_gb": 2.0, "total_gb": 500.0, "percent_used": 99.0}
    )

    assert report["pullable_now"] == []
    assert any("under the 5 GB floor" in w for w in report["warnings"])


def test_a_model_the_backend_cannot_load_is_not_proposed() -> None:
    """An ApXML slug is not an `ollama pull` tag; planning around one is useless."""
    entries = _catalog() + [
        {"id": "qwen36-35b-a3b", "kind": "llm", "ram_gb": 2.0, "disk_gb": 1.0, "source": "apxml"}
    ]

    report = storage.report(entries, budget_gb=40.0, disk=dict(_DISK), backend="ollama")

    offered = {r["id"] for r in report["pullable_now"]}
    assert "qwen36-35b-a3b" not in offered
    assert all("qwen36-35b-a3b" not in s["models"].values() for s in report["resident_sets"])


def test_an_entry_without_a_disk_figure_falls_back_to_the_memory_one() -> None:
    """Over-stating the file size is the safe direction for a capacity plan."""
    entries = [{"id": "nodisk:8b", "kind": "llm", "ram_gb": 6.0}]

    report = storage.report(entries, budget_gb=40.0, disk=dict(_DISK))

    assert report["pullable_now"][0]["disk_gb"] == 6.0


# ---------------------------------------------------------------------------
# The search is pruned, and pruning must not change the answer
# ---------------------------------------------------------------------------
#
# `resident_sets` used to enumerate the full cartesian product, on the stated
# premise that "the catalog is small (tens of entries), so an exhaustive
# product is both exact and instant". `catalog update --ollama`, shipped in the
# same release, makes it 420 entries: 342 x 75 x 3 = 76,950 combinations,
# measured at 2.8 s and 230,850 calls to `model_footprint_gb`. The cost is
# cubic, so it was the premise that died, not merely the timing.
#
# The replacement is a branch-and-bound over kinds sorted heaviest-first. It is
# exact, so the first test here is differential: same answers as the product,
# across shapes chosen to exercise the bounds (budgets that admit everything,
# nothing, and a little; limits above and below the number of feasible sets).


def _brute_force(entries: list[dict], budget: float, limit: int = 5) -> list[tuple]:
    """Every combination, scored and sorted. The oracle the pruned search must match."""
    from itertools import product

    from best_engine_ai_helper.score import model_footprint_gb

    by_kind: dict[str, list[dict]] = {}
    for kind in storage.RESIDENT_KINDS:
        pool = [e for e in entries if e.get("kind") == kind]
        if pool:
            by_kind[kind] = pool
    if not by_kind:
        return []
    present = list(by_kind)
    rows = []
    for choice in product(*(by_kind[k] for k in present)):
        ram = sum(model_footprint_gb(e) for e in choice)
        if ram > budget:
            continue
        score = sum(storage._quality(e, k) for k, e in zip(present, choice))
        rows.append((score, ram, tuple(str(e["id"]) for e in choice)))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [(round(s, 1), round(r, 1), ids) for s, r, ids in rows[:limit]]


def _random_catalog(rng) -> list[dict]:
    """A catalog with scores on roughly two entries in three, as the real one is."""
    axis = {"llm": "general", "vlm": "vision", "embed": "mteb"}
    return [
        {
            "id": f"{kind}-{j}",
            "kind": kind,
            "ram_gb": round(rng.uniform(0.3, 30.0), 1),
            "benchmarks": {} if rng.random() < 0.3 else {axis[kind]: rng.randint(30, 95)},
        }
        for kind, count in (
            ("llm", rng.randint(0, 10)),
            ("vlm", rng.randint(0, 7)),
            ("embed", rng.randint(0, 4)),
        )
        for j in range(count)
    ]


def test_pruning_returns_exactly_what_the_exhaustive_product_returned() -> None:
    import random

    rng = random.Random(11)
    for _ in range(300):
        entries = _random_catalog(rng)
        budget = rng.uniform(1.0, 60.0)
        limit = rng.choice([1, 3, 5])
        got = [
            (c["total_score"], c["total_ram_gb"], tuple(c["models"].values()))
            for c in storage.resident_sets(entries, budget, limit=limit)
        ]
        assert got == _brute_force(entries, budget, limit)


def test_a_better_set_wins_even_when_it_uses_less_memory() -> None:
    """The point of ranking on quality: the old rule picked the heavier, weaker set.

    Taken from the bundled catalog at a 48 GB budget, where ordering on memory
    alone put `qwen3:32b-q8_0` + `qwen3-vl:14b` (score 232.7, 47.9 GB) above
    `qwen3:32b-q4_k_m` + `qwen3-vl:32b` (score 236.0, 47.2 GB) — a better set
    that happened to weigh less. Reproduced in miniature so the assertion does
    not depend on catalog contents.
    """
    entries = [
        {"id": "heavy-weak", "kind": "llm", "ram_gb": 20.0, "benchmarks": {"general": 70}},
        {"id": "light-strong", "kind": "llm", "ram_gb": 16.0, "benchmarks": {"general": 85}},
        {"id": "eyes", "kind": "vlm", "ram_gb": 6.0, "benchmarks": {"vision": 80}},
    ]
    rows = storage.resident_sets(entries, 30.0, limit=2)
    assert rows[0]["models"]["llm"] == "light-strong"
    assert rows[0]["total_ram_gb"] < rows[1]["total_ram_gb"]
    assert rows[0]["total_score"] > rows[1]["total_score"]


def test_with_nothing_scored_the_order_is_the_memory_one_it_always_was() -> None:
    """Hundreds of library entries publish sizes and no leaderboard results.

    Quality cannot order those, so memory — the old rule — must still do it,
    rather than the answer collapsing into an arbitrary tie.
    """
    entries = [{"id": f"llm-{j}", "kind": "llm", "ram_gb": float(j)} for j in range(1, 6)] + [
        {"id": "eyes", "kind": "vlm", "ram_gb": 1.0}
    ]
    rows = storage.resident_sets(entries, 20.0, limit=3)
    assert all(r["total_score"] == 0.0 for r in rows)
    assert [r["total_ram_gb"] for r in rows] == [6.0, 5.0, 4.0]


def test_every_candidate_is_sized_once_rather_than_once_per_combination(monkeypatch) -> None:
    """The bound is the point; so is not re-deriving the same number 230,850 times."""
    from best_engine_ai_helper import score as _score

    calls = {"n": 0}
    real = _score.model_footprint_gb

    def counted(entry, backend="ollama"):
        calls["n"] += 1
        return real(entry, backend)

    monkeypatch.setattr(_score, "model_footprint_gb", counted)

    entries = [
        {"id": f"{kind}-{j}", "kind": kind, "ram_gb": 1.0 + j}
        for kind, count in (("llm", 20), ("vlm", 10), ("embed", 4))
        for j in range(count)
    ]
    storage.resident_sets(entries, budget_gb=40.0, limit=5)

    # 20 x 10 x 4 = 800 combinations, 2,400 sizings under the old code. The
    # bound is linear in the catalog: each entry is sized to be filtered, then
    # to be sorted.
    assert calls["n"] <= 2 * len(entries)


def test_a_catalog_the_product_could_never_enumerate_still_answers(monkeypatch) -> None:
    """200 x 200 x 200 is 8 million combinations; the oracle cannot run this.

    Counted rather than timed. An earlier version of this test asserted
    ``elapsed < 1.0``, passed in 0.25 s in isolation, and failed under the
    pre-push gate, where the same work runs with coverage instrumentation on a
    busy machine. A wall clock measures the machine as much as the code, and a
    gate that fires wrongly is how people learn to reach for ``--no-verify``.

    ``_Set`` is built exactly once per feasible complete set the search
    reaches, so counting its construction counts the leaves visited — which is
    the thing actually claimed, and it does not move with the load.
    """
    created = {"n": 0}
    real = storage._Set

    class _Counting(real):  # type: ignore[misc,valid-type]
        __slots__ = ()

        def __init__(self, *args: object) -> None:
            created["n"] += 1
            super().__init__(*args)

    monkeypatch.setattr(storage, "_Set", _Counting)

    entries = [
        {"id": f"{kind}-{j}", "kind": kind, "ram_gb": 0.5 + j * 0.37}
        for kind in ("llm", "vlm", "embed")
        for j in range(200)
    ]
    rows = storage.resident_sets(entries, budget_gb=120.0, limit=5)

    assert len(rows) == 5
    assert all(r["total_ram_gb"] <= 120.0 for r in rows)
    # Descending, which is the documented order.
    assert [r["total_ram_gb"] for r in rows] == sorted(
        (r["total_ram_gb"] for r in rows), reverse=True
    )
    # 8,000,000 combinations exist. Anything of that order means the bounds
    # stopped working; the generous ceiling is deliberate, since the claim is
    # "not exponential", not a particular node count.
    assert created["n"] < 10_000


def test_a_limit_of_zero_or_less_asks_for_nothing() -> None:
    assert storage.resident_sets(_catalog(), 100.0, limit=0) == []
    assert storage.resident_sets(_catalog(), 100.0, limit=-1) == []


def test_equal_totals_come_back_in_a_stable_order() -> None:
    """Two sets of identical weight must not swap between runs."""
    entries = [
        {"id": "llm-b", "kind": "llm", "ram_gb": 4.0},
        {"id": "llm-a", "kind": "llm", "ram_gb": 4.0},
        {"id": "vlm-only", "kind": "vlm", "ram_gb": 2.0},
    ]
    rows = storage.resident_sets(entries, 10.0, limit=5)
    assert [r["models"]["llm"] for r in rows] == ["llm-a", "llm-b"]
