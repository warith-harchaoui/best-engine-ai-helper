"""
Tests for best_engine_ai_helper.cloud_catalog — the paid-model picker.

Synthetic catalog, no network, no API key. Covers loading (real bundled
pricing.yaml + a missing/explicit path), the kind filter (vlm-only vs
llm-accepts-both), the provider filter, the quality_vs_cost trade-off at its
extremes, the structured-output gate, and pick_cloud's None-on-empty case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from best_engine_ai_helper import cloud_catalog

_CATALOG = [
    {
        "id": "cheap-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": True,
        "benchmarks": {"general": 60, "code": 55},
        "input_per_1m": 0.10,
        "output_per_1m": 0.10,
    },
    {
        "id": "strong-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": True,
        "benchmarks": {"general": 90, "code": 92},
        "input_per_1m": 5.00,
        "output_per_1m": 15.00,
    },
    {
        "id": "vision-model",
        "provider": "other",
        "kind": "vlm",
        "structured_output": True,
        "benchmarks": {"general": 80, "vision": 85},
        "input_per_1m": 2.00,
        "output_per_1m": 6.00,
    },
    {
        "id": "unstructured-text",
        "provider": "acme",
        "kind": "llm",
        "structured_output": False,
        "benchmarks": {"general": 99},
        "input_per_1m": 0.01,
        "output_per_1m": 0.01,
    },
]


def test_load_cloud_catalog_real_bundle_and_missing_path(tmp_path: Path) -> None:
    # The real bundled pricing.yaml loads and every entry has the fields
    # rank_cloud/pick_cloud need.
    entries = cloud_catalog.load_cloud_catalog()
    assert entries
    for e in entries:
        assert {"id", "provider", "kind", "benchmarks", "input_per_1m", "output_per_1m"} <= e.keys()

    # An explicit missing path is a real error, not a silent empty result.
    with pytest.raises(FileNotFoundError):
        cloud_catalog.load_cloud_catalog(tmp_path / "nope.yaml")


def test_load_cloud_catalog_default_path_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cloud_catalog, "_PRICING_PATH", tmp_path / "nope.yaml")
    assert cloud_catalog.load_cloud_catalog() == []


def test_rank_and_pick_cloud_kind_provider_and_weight() -> None:
    # kind="vlm" keeps only vlm entries.
    vlm_ranked = cloud_catalog.rank_cloud(_CATALOG, "vlm")
    assert [e["id"] for e in vlm_ranked] == ["vision-model"]

    # kind="llm" accepts both llm and vlm entries (a VLM answers text too) --
    # same rule as score.rank.
    llm_ids = {e["id"] for e in cloud_catalog.rank_cloud(_CATALOG, "llm")}
    assert "vision-model" in llm_ids and "cheap-text" in llm_ids

    # Provider filter narrows the pool.
    acme_only = cloud_catalog.rank_cloud(_CATALOG, "llm", provider="ACME")  # case-insensitive
    assert all(e["provider"] == "acme" for e in acme_only)
    assert "vision-model" not in {e["id"] for e in acme_only}

    # Structured-output capability is checked before the quality/price blend:
    # unstructured-text scores highest (99) and is cheapest, yet never wins.
    top = cloud_catalog.pick_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=1.0)
    assert top is not None and top["id"] == "strong-text"

    # quality_vs_cost=0.0 (pure price) picks the cheapest STRUCTURED candidate.
    cheapest = cloud_catalog.pick_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=0.0)
    assert cheapest is not None and cheapest["id"] == "cheap-text"

    # An out-of-range weight is clamped, not rejected.
    clamped = cloud_catalog.rank_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=5.0)
    assert (
        clamped[0]["id"]
        == cloud_catalog.rank_cloud(_CATALOG, "llm", provider="acme", quality_vs_cost=1.0)[0]["id"]
    )

    # No match -> pick_cloud returns None, never an IndexError.
    assert cloud_catalog.pick_cloud(_CATALOG, "vlm", provider="acme") is None


def test_blended_price_per_1m() -> None:
    assert cloud_catalog.blended_price_per_1m({"input_per_1m": 2.0, "output_per_1m": 10.0}) == 6.0
    # An entry with no prices used to blend to 0.0, which the cost axis then
    # inverted into the best possible score -- an unpriced model looked free.
    # It now says it does not know. See the tests below the next banner.
    assert cloud_catalog.blended_price_per_1m({}) is None


# ---------------------------------------------------------------------------
# An unpriced model is not a free model
# ---------------------------------------------------------------------------


def test_no_price_is_not_the_same_as_a_price_of_zero() -> None:
    """Collapsing both to 0.0 is what made an unpriced model look free."""
    assert cloud_catalog.blended_price_per_1m({"id": "nobody-priced-this"}) is None
    assert cloud_catalog.blended_price_per_1m({"input_per_1m": 0.0, "output_per_1m": 0.0}) == 0.0


def test_billing_on_one_side_only_is_a_real_arrangement() -> None:
    """A provider that charges for output and not input is priced, not unpriced."""
    assert cloud_catalog.blended_price_per_1m({"output_per_1m": 10.0}) == 5.0


def test_an_unpriced_model_never_wins_the_cost_axis() -> None:
    """The defect: inverted normalisation turned an absent price into the best score."""
    catalog = [
        {
            "id": "priced-cheap",
            "kind": "llm",
            "benchmarks": {"general": 70.0},
            "input_per_1m": 1.0,
            "output_per_1m": 1.0,
        },
        {
            "id": "priced-dear",
            "kind": "llm",
            "benchmarks": {"general": 70.0},
            "input_per_1m": 50.0,
            "output_per_1m": 50.0,
        },
        {"id": "unpriced", "kind": "llm", "benchmarks": {"general": 70.0}},
    ]

    # Rank on cost alone so the price axis is the only thing deciding.
    ranked = cloud_catalog.rank_cloud(catalog, "llm", quality_vs_cost=0.0)
    order = [r["id"] for r in ranked]

    assert order[0] == "priced-cheap"
    assert order[-1] == "unpriced"  # unknown cost is pessimistic, not optimistic


def test_an_unpriced_entry_carries_none_through_to_the_caller() -> None:
    catalog = [{"id": "unpriced", "kind": "llm", "benchmarks": {"general": 70.0}}]

    ranked = cloud_catalog.rank_cloud(catalog, "llm")

    assert ranked[0]["price_per_1m"] is None


def test_a_catalog_with_no_prices_at_all_still_ranks() -> None:
    """Every price unknown must not divide by an empty range."""
    catalog = [
        {"id": "a", "kind": "llm", "benchmarks": {"general": 90.0}},
        {"id": "b", "kind": "llm", "benchmarks": {"general": 50.0}},
    ]

    ranked = cloud_catalog.rank_cloud(catalog, "llm")

    assert [r["id"] for r in ranked] == ["a", "b"]  # falls back to quality order


# ---------------------------------------------------------------------------
# Which providers are usable, and why the rest are not
# ---------------------------------------------------------------------------


def test_provider_status_names_the_variable_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A silently shorter list of options is not actionable; a variable name is."""
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: "")

    rows = cloud_catalog.provider_status(_CATALOG)

    by_name = {r["provider"]: r for r in rows}
    assert set(by_name) == {"acme", "other"}
    assert by_name["acme"]["available"] is False
    assert "ACME_API_KEY" in by_name["acme"]["reason"]
    assert by_name["acme"]["key_env"] == "ACME_API_KEY"


def test_a_provider_with_a_key_is_available_and_gives_no_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: "sk-whatever")

    rows = cloud_catalog.provider_status(_CATALOG)

    assert all(r["available"] for r in rows)
    assert all(r["reason"] == "" for r in rows)


def test_provider_status_never_returns_a_key_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of storing the variable NAME is that the secret stays out."""
    secret = "sk-this-must-never-appear"
    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", lambda _e: secret)

    rows = cloud_catalog.provider_status(_CATALOG)

    assert secret not in repr(rows)


def test_a_lookup_that_raises_is_a_finding_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_entry):
        raise RuntimeError("keyring is locked")

    monkeypatch.setattr("best_engine_ai_helper.llm._cloud_api_key", _boom)

    rows = cloud_catalog.provider_status(_CATALOG)

    assert all(r["available"] is False for r in rows)
    assert "keyring is locked" in rows[0]["reason"]


def test_providers_carry_the_models_they_serve() -> None:
    rows = cloud_catalog.provider_status(_CATALOG)

    by_name = {r["provider"]: r for r in rows}
    assert by_name["other"]["models"] == ["vision-model"]
    assert "cheap-text" in by_name["acme"]["models"]


# ---------------------------------------------------------------------------
# What ships must be documented where the reader is told to look
# ---------------------------------------------------------------------------
#
# The bundled catalog carries four providers; `settings.yaml.example` — the
# file README tells you to copy — listed one. The mechanism was never broken
# (any `api_key_env` name resolves, and `provider_status` names it at runtime),
# but someone holding an OpenAI key had to read an internal map in `engine.py`
# to learn what to call it. These two tests make the example file's
# completeness an invariant rather than something to remember when a provider
# is added to `pricing.yaml`.


def _documented_keys() -> set[str]:
    example = Path(__file__).resolve().parent.parent / "settings.yaml.example"
    return {
        line.split(":", 1)[0].strip()
        for line in example.read_text().splitlines()
        if ":" in line and not line.strip().startswith("#")
    }


def test_every_shipped_provider_resolves_a_key_variable_name() -> None:
    """A provider with no name to look up could never be authenticated."""
    from best_engine_ai_helper import engine

    providers = {entry["provider"] for entry in cloud_catalog.load_cloud_catalog()}
    assert providers, "the bundled catalog is empty; the test is broken, not the code"
    unnamed = sorted(p for p in providers if not engine._DEFAULT_API_KEY_ENV.get(p))
    assert not unnamed, f"shipped providers with no api_key_env default: {unnamed}"


def test_every_shipped_provider_is_documented_in_the_settings_example() -> None:
    from best_engine_ai_helper import engine

    providers = {entry["provider"] for entry in cloud_catalog.load_cloud_catalog()}
    needed = {engine._DEFAULT_API_KEY_ENV[p] for p in providers}
    documented = _documented_keys()
    assert needed <= documented, (
        "settings.yaml.example is the file the README tells the reader to copy; "
        f"these shipped providers have no entry there: {sorted(needed - documented)}"
    )


# ---------------------------------------------------------------------------
# Adoption — the rule that lets the paid catalogue grow
# ---------------------------------------------------------------------------
#
# The seed could be repriced from a source and never extended from one, because
# an entry needs a quality score to be rankable and a price table publishes
# none. So the catalogue could learn what a model cost and never that it
# existed, and sat at ten models from 2024 while the price source knew three
# hundred. An entry is adopted only where BOTH sources speak about the same
# model: a price, and a rating. Two citations or no entry.

_PRICED = [
    {
        "id": "claude-opus-5-5",
        "provider": "anthropic",
        "kind": "vlm",
        "input_per_1m": 4.0,
        "output_per_1m": 20.0,
        "context_length": 1000000,
        "source": "litellm",
        "fetched_at": "2026-10-28",
    },
    {
        "id": "nobody-rates-this",
        "provider": "openai",
        "kind": "llm",
        "input_per_1m": 1.0,
        "output_per_1m": 2.0,
        "source": "litellm",
        "fetched_at": "2026-10-28",
    },
    {
        "id": "free-preview",
        "provider": "gemini",
        "kind": "llm",
        "input_per_1m": 0.0,
        "output_per_1m": 0.0,
        "source": "litellm",
        "fetched_at": "2026-10-28",
    },
    {
        "id": "an-embedder",
        "provider": "openai",
        "kind": "embed",
        "input_per_1m": 0.02,
        "output_per_1m": 0.0,
        "source": "litellm",
        "fetched_at": "2026-10-28",
    },
]

_RATED = {
    "snapshot": "2026-10-07",
    "scores": {
        "arena": {"claude-opus-5.5-high": 85.2, "free-preview": 70.0, "an-embedder": 10.0},
        "arena_code": {"claude-opus-5.5-max": 97.2},
    },
}


def test_adoption_needs_a_price_and_a_rating_not_either() -> None:
    adopted = cloud_catalog.adopt_rated(_PRICED, _RATED, known=set())

    assert [e["id"] for e in adopted] == ["claude-opus-5-5"]


def test_adoption_never_invents_the_axes_it_has_no_source_for() -> None:
    """The leaderboard measures preference. It does not measure MMLU.

    Synthesising a `general` number from an `arena` one would put a
    measurement-shaped claim in a file that bills people.
    """
    adopted = cloud_catalog.adopt_rated(_PRICED, _RATED, known=set())[0]

    assert adopted["benchmarks"]["arena"] == 85.2
    assert adopted["benchmarks"]["arena_code"] == 97.2
    assert adopted["benchmarks"]["general"] is None
    assert adopted["benchmarks"]["vision"] is None
    assert adopted["source"] == "litellm+arena"
    assert adopted["arena_matched"]["arena"] == "claude-opus-5.5-high"


def test_a_model_already_in_the_catalogue_is_repriced_not_re_adopted() -> None:
    assert cloud_catalog.adopt_rated(_PRICED, _RATED, known={"claude-opus-5-5"}) == []


def test_nothing_is_adopted_when_no_mirror_answered() -> None:
    assert cloud_catalog.adopt_rated(_PRICED, {"scores": {}}, known=set()) == []


def test_one_id_one_entry_with_the_first_party_provider_winning() -> None:
    """A reseller's price carries its own margin, and its id is an alias.

    The catalogue is keyed by id, so a duplicate would make which price you are
    quoted depend on iteration order.
    """
    reseller = dict(_PRICED[0], provider="openrouter", input_per_1m=5.0)
    adopted = cloud_catalog.adopt_rated([reseller, _PRICED[0]], _RATED, known=set())

    assert len(adopted) == 1
    assert adopted[0]["provider"] == "anthropic"
    assert adopted[0]["input_per_1m"] == 4.0


# ---------------------------------------------------------------------------
# Loading — the cache is a source of entries, not only of overlays
# ---------------------------------------------------------------------------


def _seed_file(tmp_path: Path) -> Path:
    path = tmp_path / "pricing.yaml"
    path.write_text(
        "models:\n"
        "  seeded:\n"
        "    provider: acme\n"
        "    kind: llm\n"
        "    benchmarks: {general: 80, arena: null}\n"
        "    input_per_1m: 1.0\n"
        "    output_per_1m: 2.0\n",
        encoding="utf-8",
    )
    return path


def test_a_cached_entry_with_no_seed_counterpart_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`catalog update --cloud --arena` adopted eighteen models and loading
    walked only the seed's ids, so nothing ever read them back."""
    cache = tmp_path / "pricing_cache.yaml"
    cache.write_text(
        "models:\n"
        "  adopted:\n"
        "    provider: acme\n"
        "    kind: llm\n"
        "    benchmarks: {general: null, arena: 85.2}\n"
        "    input_per_1m: 4.0\n"
        "    output_per_1m: 20.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cloud_catalog, "_CLOUD_CACHE_PATH", cache)
    monkeypatch.setattr(cloud_catalog, "_PRICING_PATH", _seed_file(tmp_path))

    ids = {e["id"] for e in cloud_catalog.load_cloud_catalog()}
    assert ids == {"seeded", "adopted"}


def test_a_cached_entry_with_no_score_or_no_price_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Letting one in would drag the normalisation the adoption rule protects."""
    cache = tmp_path / "pricing_cache.yaml"
    cache.write_text(
        "models:\n"
        "  unscored:\n"
        "    provider: acme\n"
        "    kind: llm\n"
        "    benchmarks: {general: null, arena: null}\n"
        "    input_per_1m: 4.0\n"
        "  unpriced:\n"
        "    provider: acme\n"
        "    kind: llm\n"
        "    benchmarks: {arena: 85.2}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cloud_catalog, "_CLOUD_CACHE_PATH", cache)
    monkeypatch.setattr(cloud_catalog, "_PRICING_PATH", _seed_file(tmp_path))

    assert {e["id"] for e in cloud_catalog.load_cloud_catalog()} == {"seeded"}


def test_a_cached_rating_fills_a_hole_and_never_overrules_a_curated_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hand-written score has a provider's paper behind it; a leaderboard
    axis fills a null rather than replacing a judgement."""
    cache = tmp_path / "pricing_cache.yaml"
    cache.write_text(
        "models:\n"
        "  seeded:\n"
        "    benchmarks: {general: 12, arena: 85.2}\n"
        "    arena_snapshot: '2026-10-07'\n"
        "    input_per_1m: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cloud_catalog, "_CLOUD_CACHE_PATH", cache)
    monkeypatch.setattr(cloud_catalog, "_PRICING_PATH", _seed_file(tmp_path))

    entry = cloud_catalog.load_cloud_catalog()[0]
    assert entry["benchmarks"]["general"] == 80  # the seed's, not the cache's
    assert entry["benchmarks"]["arena"] == 85.2  # the hole, filled
    assert entry["arena_snapshot"] == "2026-10-07"
    assert entry["input_per_1m"] == 0.5  # repriceable, so the cache wins


# ---------------------------------------------------------------------------
# Ranking — an unscored candidate must not flatten the scale
# ---------------------------------------------------------------------------


def test_an_unscored_candidate_is_left_out_of_the_quality_range() -> None:
    """The leaderboard mirror publishes a top twenty per board, so a model can
    be rated for code and absent from text: censored, not weak.

    Left at a floor of zero it stretches the quality range's bottom, every real
    score compresses toward 1.0, and a quality-led weight starts behaving like
    a price-led one.
    """
    pool = [
        {
            "id": "good-and-dear",
            "provider": "acme",
            "kind": "llm",
            "benchmarks": {"general": 88},
            "input_per_1m": 5.0,
            "output_per_1m": 15.0,
        },
        {
            "id": "fair-and-cheap",
            "provider": "acme",
            "kind": "llm",
            "benchmarks": {"general": 68},
            "input_per_1m": 0.1,
            "output_per_1m": 0.3,
        },
    ]
    censored = {
        "id": "rated-elsewhere",
        "provider": "acme",
        "kind": "llm",
        "benchmarks": {"general": None, "arena_code": 96.1},
        "input_per_1m": 2.0,
        "output_per_1m": 10.0,
    }

    without = cloud_catalog.rank_cloud(pool, "llm", quality_vs_cost=0.7)
    with_it = cloud_catalog.rank_cloud([*pool, censored], "llm", quality_vs_cost=0.7)

    # Adding a candidate nobody scored on this axis must not reorder the two
    # that were scored, nor change what they were worth.
    assert [r["id"] for r in without] == [r["id"] for r in with_it][:2]
    assert without[0]["combined"] == pytest.approx(with_it[0]["combined"])

    unscored = next(r for r in with_it if r["id"] == "rated-elsewhere")
    assert unscored["scored"] is False
    assert unscored["score_axis"] is None
    assert unscored is with_it[-1]


def test_a_rank_row_says_which_ruler_measured_it() -> None:
    """88 from an MMLU-style suite and 86 from a preference leaderboard are
    both out of 100 and are not the same quantity."""
    pool = [
        {
            "id": "hand-scored",
            "provider": "acme",
            "kind": "llm",
            "benchmarks": {"general": 88},
            "input_per_1m": 5.0,
            "output_per_1m": 15.0,
        },
        {
            "id": "adopted",
            "provider": "acme",
            "kind": "llm",
            "benchmarks": {"general": None, "arena": 86.7},
            "input_per_1m": 2.0,
            "output_per_1m": 10.0,
        },
    ]
    axes = {r["id"]: r["score_axis"] for r in cloud_catalog.rank_cloud(pool, "llm")}
    assert axes == {"hand-scored": "general", "adopted": "arena"}
