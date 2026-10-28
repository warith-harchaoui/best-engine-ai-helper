"""
Tests for the Arena source adapter.

Two things are being guarded here. The adapter must never merge a stale
snapshot -- a rating fourteen months old ranks a previous generation of models
first, which is strictly worse than having no rating. And it must never
attribute one model's reputation to another: a wrong match is acted on by the
ranker, where a missing axis is simply skipped.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import datetime as dt

import pytest
import requests

from best_engine_ai_helper.score import _APP_BENCH_PRIORITY, _benchmark_score
from best_engine_ai_helper.sources import arena

# ---------------------------------------------------------------------------
# The 0-100 conversion.
# ---------------------------------------------------------------------------


def test_the_reference_rating_maps_to_fifty():
    """50 means "wins about half its comparisons against a mid-board model"."""
    assert arena.elo_to_score(arena.REFERENCE_ELO) == 50.0


def test_the_conversion_is_monotone():
    scores = [arena.elo_to_score(e) for e in range(800, 1700, 50)]
    assert scores == sorted(scores)


def test_a_four_hundred_point_gap_is_a_ten_to_one_expectation():
    """The Elo scale's own definition, so the formula cannot drift."""
    high = arena.elo_to_score(1600, reference=1200)
    assert high == pytest.approx(100 * 10 / 11, abs=0.1)


def test_the_conversion_stays_inside_the_scale():
    for elo in (0, 500, 1200, 2000, 5000):
        assert 0.0 <= arena.elo_to_score(elo) <= 100.0


def test_the_conversion_does_not_rescale_with_the_board():
    """A min-max would: yesterday's 100 becomes today's 94 and a cached catalog
    silently disagrees with a fresh one."""
    assert arena.elo_to_score(1300) == arena.elo_to_score(1300)
    assert arena.elo_to_score(1300, reference=1200) != arena.elo_to_score(1300, reference=1300)


# ---------------------------------------------------------------------------
# Staleness: the guard that matters most.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot, expected",
    [("20250522", 515), ("2025-05-22", 515), ("nonsense", None)],
)
def test_snapshot_age_reads_both_spellings(snapshot, expected):
    assert arena.snapshot_age_days(snapshot, today=dt.date(2026, 10, 19)) == expected


def test_a_stale_snapshot_is_refused_with_its_age(monkeypatch):
    """Not merged quietly: a stale rating is worse than no rating."""
    monkeypatch.setattr(
        arena, "SOURCES", (("mirror", lambda s, t: ("20250522", {"arena": {"m": 1300.0}})),)
    )
    result = arena.fetch_arena_ratings(today=dt.date(2026, 10, 19))
    assert result["stale"] is True
    assert result["scores"] == {}
    assert "515 days old" in result["note"]


def test_a_fresh_snapshot_is_accepted_and_converted(monkeypatch):
    monkeypatch.setattr(
        arena, "SOURCES", (("mirror", lambda s, t: ("2026-10-01", {"arena": {"m": 1200.0}})),)
    )
    result = arena.fetch_arena_ratings(today=dt.date(2026, 10, 19))
    assert result["stale"] is False
    assert result["age_days"] == 18
    assert result["scores"]["arena"]["m"] == 50.0
    assert result["ratings"]["arena"]["m"] == 1200.0, "the raw rating is kept too"


def test_the_staleness_check_can_be_disabled_deliberately(monkeypatch):
    monkeypatch.setattr(
        arena, "SOURCES", (("mirror", lambda s, t: ("20200101", {"arena": {"m": 1300.0}})),)
    )
    result = arena.fetch_arena_ratings(today=dt.date(2026, 10, 19), max_age_days=0)
    assert result["stale"] is False, "0 means 'I know what I am doing'"


def test_a_broken_mirror_does_not_sink_the_refresh(monkeypatch):
    def broken(_s, _t):
        raise RuntimeError("mirror is down")

    monkeypatch.setattr(
        arena,
        "SOURCES",
        (
            ("broken", broken),
            ("working", lambda s, t: ("2026-10-01", {"arena": {"m": 1250.0}})),
        ),
    )
    result = arena.fetch_arena_ratings(today=dt.date(2026, 10, 19))
    assert result["source"] == "working"


def test_no_usable_source_explains_itself_and_does_not_raise(monkeypatch):
    """Every community mirror can rot; the caller gets a reason, not a crash."""
    monkeypatch.setattr(arena, "SOURCES", (("empty", lambda s, t: None),))
    result = arena.fetch_arena_ratings(today=dt.date(2026, 10, 19))
    assert result["scores"] == {}
    assert "no usable data" in result["note"]
    assert "worse than none" in result["note"], "the reasoning must be in the message"


# ---------------------------------------------------------------------------
# Matching: a wrong match is worse than no match.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "catalog_id, ratings, expected",
    [
        ("qwen3-32b", {"qwen3-32b": 1.0}, "qwen3-32b"),
        ("qwen3:32b", {"qwen3-32b": 1.0}, "qwen3-32b"),
        ("qwen3:32b-q4_k_m", {"qwen3-32b": 1.0}, "qwen3-32b"),
        ("qwen3:32b-fp16", {"qwen3-32b": 1.0}, "qwen3-32b"),
        ("qwen3:32b", {"qwen3-32b-instruct": 1.0}, "qwen3-32b-instruct"),
    ],
)
def test_the_runtime_tag_resolves_to_the_leaderboard_name(catalog_id, ratings, expected):
    assert arena.match_model(catalog_id, ratings) == expected


@pytest.mark.parametrize(
    "catalog_id, ratings, expected",
    [
        ("gpt-4o", {"gpt-4o-2024-05-13": 1.0, "gpt-4o-2024-08-06": 2.0}, "gpt-4o-2024-08-06"),
        (
            "mistral-large-latest",
            {"mistral-large-2407": 1.0, "mistral-large-2411": 2.0},
            "mistral-large-2411",
        ),
        (
            "claude-3-5-sonnet",
            {"claude-3-5-sonnet-20240620": 1.0, "claude-3-5-sonnet-20241022": 2.0},
            "claude-3-5-sonnet-20241022",
        ),
    ],
)
def test_an_alias_resolves_to_its_newest_dated_release(catalog_id, ratings, expected):
    """Not a heuristic: resolving to the newest release is what an alias means."""
    assert arena.match_model(catalog_id, ratings) == expected


def test_a_different_serving_mode_is_not_the_same_model():
    """`-thinking-32k` after the date is a different thing to rate."""
    assert (
        arena.match_model("claude-3-5-sonnet", {"claude-3-5-sonnet-20250219-thinking-32k": 1.0})
        is None
    )


def test_an_ambiguous_prefix_is_declined():
    """The ranker acts on a wrong axis; it merely skips a missing one."""
    assert arena.match_model("qwen3:32b", {"qwen3-32b-a": 1.0, "qwen3-32b-b": 2.0}) is None


def test_a_different_size_is_not_a_match():
    """The commonest way to attribute the wrong model's reputation."""
    assert arena.match_model("qwen2.5-coder:7b", {"qwen2.5-coder-32b-instruct": 1.0}) is None


def test_date_spellings_are_not_mixed_when_picking_the_newest():
    """`2407` against `20241022` would order by string length, not by time."""
    picked = arena.match_model(
        "mistral-large", {"mistral-large-2407": 1.0, "mistral-large-20231101": 2.0}
    )
    assert picked == "mistral-large-20231101"


# ---------------------------------------------------------------------------
# Merging.
# ---------------------------------------------------------------------------


def _result(**over):
    base = {
        "source": "mirror",
        "snapshot": "2026-10-01",
        "scores": {"arena": {"qwen3-32b": 67.1}},
        "note": "ok",
    }
    base.update(over)
    return base


def test_merging_adds_the_axis_and_records_the_snapshot():
    entries = [{"id": "qwen3:32b", "benchmarks": {"general": 70}}]
    merged, report = arena.merge_into(entries, _result())
    assert merged[0]["benchmarks"] == {"general": 70, "arena": 67.1}
    assert merged[0]["arena_snapshot"] == "2026-10-01"
    assert report["matched"] == ["qwen3:32b"]


def test_merging_does_not_mutate_the_caller_s_catalog():
    """A refresh that half-applies then fails must leave the input as it was."""
    entries = [{"id": "qwen3:32b", "benchmarks": {"general": 70}}]
    arena.merge_into(entries, _result())
    assert entries[0]["benchmarks"] == {"general": 70}


def test_an_unmatched_entry_is_reported_not_guessed_at():
    entries = [{"id": "gemma3:12b", "benchmarks": {}}]
    merged, report = arena.merge_into(entries, _result())
    assert merged[0]["benchmarks"] == {}
    assert report["unmatched"] == ["gemma3:12b"]


def test_no_scores_leaves_the_catalog_untouched_and_says_why():
    entries = [{"id": "qwen3:32b", "benchmarks": {"general": 70}}]
    merged, report = arena.merge_into(entries, _result(scores={}, note="no fresh source"))
    assert merged == entries
    assert report["note"] == "no fresh source"


# ---------------------------------------------------------------------------
# Where the axis sits, which is where its weight is decided.
# ---------------------------------------------------------------------------


def test_an_execution_benchmark_outranks_a_preference_vote_for_code():
    """The whole caveat, as an assertion.

    An Arena rating comes from humans preferring one anonymous answer over
    another. For code that is a weak proxy: a model that writes agreeable
    prose outranks one that emits a schema-valid query, because nobody voting
    was asked to run the query.
    """
    entry = {"benchmarks": {"code": 88, "arena": 95, "arena_code": 93}}
    assert _benchmark_score(entry, "llm", "code") == 88


def test_even_a_generalist_score_outranks_a_coding_preference_vote():
    entry = {"benchmarks": {"general": 70, "arena_code": 95}}
    assert _benchmark_score(entry, "llm", "code") == 70


def test_the_coding_board_outranks_the_undifferentiated_one():
    entry = {"benchmarks": {"arena_code": 80, "arena": 95}}
    assert _benchmark_score(entry, "llm", "code") == 80


def test_a_preference_vote_leads_for_conversation():
    """It is the best public measure of exactly that, so here it goes first."""
    entry = {"benchmarks": {"general": 70, "arena": 85}}
    assert _benchmark_score(entry, "llm", "chat") == 85


def test_a_vision_benchmark_outranks_a_vision_preference_vote():
    entry = {"benchmarks": {"vision": 87, "arena_vision": 90}}
    assert _benchmark_score(entry, "vlm", "vision") == 87


def test_arena_fills_a_gap_rather_than_replacing_a_measurement():
    entry = {"benchmarks": {"arena": 85}}
    assert _benchmark_score(entry, "llm", "generalist") == 85


def test_arena_is_last_on_every_execution_axis():
    """A positional claim, asserted so a future edit cannot quietly reorder it."""
    for application in ("code", "math"):
        priority = _APP_BENCH_PRIORITY[application]
        arena_axes = [i for i, k in enumerate(priority) if k.startswith("arena")]
        others = [i for i, k in enumerate(priority) if not k.startswith("arena")]
        assert min(arena_axes) > max(others), f"{application}: arena is not last"


# ---------------------------------------------------------------------------
# The history mirror: the only one that still answers
# ---------------------------------------------------------------------------


class _FakeJSON:
    """A requests-like session returning a fixed payload per URL."""

    def __init__(self, payload, *, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append((url, timeout))
        if self.raises:
            raise self.raises
        return self

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


_HISTORY = {
    "20250101": {"overall": {"overall": {"old-model": 1100.0}}},
    "20250522": {
        "overall": {"overall": {"gpt-4o-2024-08-06": 1300.0}},
        "coding": {"overall": {"gpt-4o-2024-08-06": 1280.0}},
        "vision": {"overall": {"gpt-4o-2024-08-06": 1250.0}},
    },
}


def test_the_newest_snapshot_wins_over_older_ones() -> None:
    """A mirror carries many dates; only the freshest is worth reading."""
    snapshot, boards = arena._from_history(_FakeJSON(_HISTORY), 5.0)

    assert snapshot == "20250522"
    assert "old-model" not in boards["arena"]


def test_each_board_lands_on_the_axis_it_measures() -> None:
    _, boards = arena._from_history(_FakeJSON(_HISTORY), 5.0)

    assert set(boards) == {"arena", "arena_code", "arena_vision"}
    assert boards["arena_code"]["gpt-4o-2024-08-06"] == 1280.0


def test_a_board_nobody_mapped_is_left_out() -> None:
    """ "Overall with style control" and friends answer a different question,
    so an unmapped board contributes nothing rather than guessing an axis."""
    payload = {"20250522": {"overall-style-control": {"overall": {"m": 1200.0}}}}

    assert arena._from_history(_FakeJSON(payload), 5.0) is None


def test_a_dead_mirror_is_none_rather_than_an_exception() -> None:
    """Every source here is somebody else's scrape; one rotting must not raise."""
    import requests

    assert arena._from_history(_FakeJSON(None, raises=requests.RequestException()), 5.0) is None


def test_a_mirror_answering_with_nonsense_is_none() -> None:
    assert arena._from_history(_FakeJSON([]), 5.0) is None
    assert arena._from_history(_FakeJSON({}), 5.0) is None


def test_a_malformed_board_is_skipped_not_fatal() -> None:
    """A board whose value is not a mapping should cost that board, not the lot."""
    payload = {
        "20250522": {
            "overall": {"overall": {"m": 1200.0}},
            "coding": "not-a-mapping",
        }
    }

    snapshot, boards = arena._from_history(_FakeJSON(payload), 5.0)

    assert snapshot == "20250522"
    assert set(boards) == {"arena"}


# ---------------------------------------------------------------------------
# The snapshot mirror: reading the index instead of guessing it
# ---------------------------------------------------------------------------


def _snapshot_server(pages: dict[str, object]):
    """Return a `_fetch_json` stand-in serving *pages*, 404ing on anything else."""

    def fetch(url, session, timeout):  # noqa: ANN001, ARG001
        for suffix, payload in pages.items():
            if url.endswith(suffix):
                return payload
        raise requests.RequestException(f"404 {url}")

    return fetch


def test_the_board_names_come_from_the_index_not_from_a_guess(monkeypatch):
    """Two of the four names this table carried could never have matched.

    The mirror's own `_index.json` lists `code`, `text` and `vision` (among
    others). The adapter asked for `overall`, which does not exist, and
    `coding`, which is spelled `code` there -- so the code axis, the one this
    project's SQL and review profiles care about most, was silently empty
    against a mirror that was publishing it.
    """
    assert arena._BOARD_AXES["code"] == "arena_code"
    assert arena._BOARD_AXES["text"] == "arena"
    assert arena._BOARD_AXES["vision"] == "arena_vision"


def test_a_dated_but_empty_snapshot_is_walked_past(monkeypatch):
    """The newest directory is not the newest directory *with data*.

    The mirror runs daily and keeps producing a directory even when its own
    scrape returns nothing: `_index.json` then lists no leaderboards and every
    board 404s. Trusting `latest.json` meant reporting "no usable data" while
    a perfectly good snapshot sat three weeks back.
    """
    today, older = "2026-10-28", "2026-10-07"
    monkeypatch.setattr(
        arena,
        "_fetch_json",
        _snapshot_server(
            {
                "/contents/data": [
                    {"name": today, "type": "dir"},
                    {"name": older, "type": "dir"},
                    {"name": "not-a-date", "type": "dir"},
                    {"name": "README.md", "type": "file"},
                ],
                f"{today}/_index.json": {"date": today, "leaderboards": {}},
                f"{older}/_index.json": {
                    "date": older,
                    "leaderboards": {"text": {}, "code": {}, "document": {}},
                },
                f"{older}/text.json": {"models": [{"model": "a-model", "score": 1400}]},
                f"{older}/code.json": {"models": [{"model": "a-model", "score": 1500}]},
            }
        ),
    )

    result = arena._from_snapshots(None, 5.0)

    assert result is not None
    date, boards = result
    assert date == older
    # `document` is published and deliberately unmapped; `code` now is.
    assert set(boards) == {"arena", "arena_code"}
    assert boards["arena_code"]["a-model"] == 1500.0


def test_the_walk_back_stops_at_the_staleness_limit(monkeypatch):
    """A long-dead mirror still reports dead rather than serving old ratings."""
    monkeypatch.setattr(
        arena,
        "_fetch_json",
        _snapshot_server(
            {
                "/contents/data": [
                    {"name": "2026-10-28", "type": "dir"},
                    {"name": "2020-01-01", "type": "dir"},
                ],
                "2026-10-28/_index.json": {"leaderboards": {}},
                "2020-01-01/_index.json": {"leaderboards": {"text": {}}},
                "2020-01-01/text.json": {"models": [{"model": "ancient", "score": 1400}]},
            }
        ),
    )

    assert arena._from_snapshots(None, 5.0) is None


# ---------------------------------------------------------------------------
# One model, several reasoning efforts
# ---------------------------------------------------------------------------
#
# The board rates serving modes; a price list bills models. `claude-opus-5.5-max`
# and `claude-opus-5.5-high` are one billable id at one rate per token, so both
# ratings belong to the same catalogue entry — and the one taken is the floor,
# because the higher rating describes a mode the caller has to ask for and pay
# more output tokens for.


def test_effort_variants_resolve_to_the_lowest_rating() -> None:
    ratings = {"claude-opus-5.5-max": 97.2, "claude-opus-5.5-high": 85.2}
    assert arena.match_model("claude-opus-5-5", ratings) == "claude-opus-5.5-high"


def test_the_bare_name_wins_when_the_board_carries_it() -> None:
    """The unsuffixed entry IS the default mode; no discount is needed."""
    ratings = {"claude-opus-4-6": 84.7, "claude-opus-4-6-high": 85.3}
    assert arena.match_model("claude-opus-4-6", ratings) == "claude-opus-4-6"


def test_a_serving_mode_is_not_a_different_product() -> None:
    """`-thinking-32k` changes what you get; `-xhigh` changes a dial.

    The first stays unmatched on purpose — rating a different serving product
    under this id would attribute another thing's reputation to it.
    """
    assert arena.match_model("gpt-5.6-sol", {"gpt-5.6-sol-xhigh": 83.7}) == "gpt-5.6-sol-xhigh"
    assert (
        arena.match_model("claude-3-5-sonnet", {"claude-3-5-sonnet-20250219-thinking-32k": 1.0})
        is None
    )


def test_a_merged_entry_cites_the_board_name_behind_each_axis() -> None:
    """A rating that can decide what a caller is billed needs provenance.

    "85.2" is a number; "85.2, from claude-opus-5.5-high on the 2026-10-07
    snapshot" is a claim somebody can check.
    """
    result = {
        "snapshot": "2026-10-07",
        "scores": {
            "arena": {"claude-opus-5.5-high": 85.2},
            "arena_code": {"claude-opus-5.5-max": 97.2},
        },
    }
    merged, report = arena.merge_into([{"id": "claude-opus-5-5"}], result)

    assert merged[0]["benchmarks"] == {"arena": 85.2, "arena_code": 97.2}
    assert merged[0]["arena_matched"] == {
        "arena": "claude-opus-5.5-high",
        "arena_code": "claude-opus-5.5-max",
    }
    assert merged[0]["arena_snapshot"] == "2026-10-07"
    assert report["matched"] == ["claude-opus-5-5"]


def test_an_unmatched_entry_carries_no_provenance_either() -> None:
    """No rating, no snapshot stamp: the absence must stay visible."""
    result = {"snapshot": "2026-10-07", "scores": {"arena": {"something-else": 80.0}}}
    merged, report = arena.merge_into([{"id": "gpt-4o"}], result)

    assert "arena_matched" not in merged[0]
    assert "arena_snapshot" not in merged[0]
    assert report["unmatched"] == ["gpt-4o"]
