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
