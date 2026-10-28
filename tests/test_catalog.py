"""
Tests for best_engine_ai_helper.catalog.

Covers the bundled seed load and its invariants, the cache-overlay merge (cache
entries overwrite seed entries by id; a missing seed raises), the RAM estimator,
and the `catalog update` normalization path (ApXML spec -> catalog entry).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from best_engine_ai_helper import catalog


def test_load_catalog_seed_and_cache_overlay(tmp_path: Path, monkeypatch) -> None:
    entries = catalog.load_catalog()
    assert len(entries) > 0
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))  # ids are unique
    for e in entries:
        assert {"id", "kind", "ram_gb", "benchmarks"} <= e.keys()
        # Four kinds now, each with its own picker and its own idea of what
        # "fits": llm/vlm (score.rank), embed (text embedders for the
        # ann-router index, ranked on MTEB by the F3 usage) and image
        # (imagine.rank, sized per component and timed in seconds per image).
        # The generative picker ignores the last two.
        assert e["kind"] in ("llm", "vlm", "embed", "image")
        assert float(e["ram_gb"]) > 0

    def _entry(general: int, note: str, fetched: str | None) -> str:
        return textwrap.dedent(f"""\
            - id: test-model:1b
              kind: llm
              ram_gb: 1.1
              benchmarks: {{general: {general}, vision: null}}
              notes: "{note}"
              fetched_at: {fetched or "null"}
        """)

    seed = tmp_path / "models.yaml"
    seed.write_text(_entry(50, "seed", None))
    cache = tmp_path / "catalog_cache.yaml"
    cache.write_text(_entry(99, "cache override", "2026-07-28"))
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)

    overlaid = catalog.load_catalog(catalog_path=seed)
    assert len(overlaid) == 1  # same id -> overwritten, not duplicated
    assert overlaid[0]["benchmarks"]["general"] == 99
    assert overlaid[0]["notes"] == "cache override"

    with pytest.raises(FileNotFoundError):
        catalog.load_catalog(catalog_path=tmp_path / "does_not_exist.yaml")


def test_load_yaml_file_rejects_non_list_top_level(tmp_path: Path) -> None:
    # `list(a_dict)` would silently return only the dict's KEYS as "entries",
    # and `list(a_string)` would silently return one-character "entries" --
    # either way garbage instead of a clear, loggable skip. A bare scalar
    # used to crash `list(...)` outright (e.g. `list(42)` -> TypeError).
    a_mapping = tmp_path / "mapping.yaml"
    a_mapping.write_text("id: test-model:1b\nkind: llm\n")
    assert catalog._load_yaml_file(a_mapping) == []

    a_scalar = tmp_path / "scalar.yaml"
    a_scalar.write_text("42\n")
    assert catalog._load_yaml_file(a_scalar) == []

    a_string = tmp_path / "string.yaml"
    a_string.write_text("just a string\n")
    assert catalog._load_yaml_file(a_string) == []

    # The happy path -- a real list -- still works.
    a_list = tmp_path / "list.yaml"
    a_list.write_text("- id: test-model:1b\n  kind: llm\n")
    assert catalog._load_yaml_file(a_list) == [{"id": "test-model:1b", "kind": "llm"}]

    # Known quants use their overhead factor; unknown quants fall back to 1.15.
    for disk, quant, expected in [
        (6.1, "Q4_K_M", 6.832),
        (6.1, "Q8_0", 6.71),
        (10.0, "FP16", 10.5),
        (5.0, "Q2_K", 6.0),
        (10.0, "UNKNOWN", 11.5),
    ]:
        assert catalog.estimate_ram(disk, quant) == pytest.approx(expected, rel=1e-3)


def _apxml_spec() -> dict:
    return {
        "slug": "qwen3-8b",
        "name": "Qwen3 8B",
        "kind": "llm",
        "size_b": 8.0,
        "ram_gb": 6.0,
        "vllm_id": "Qwen/Qwen3-8B",
        "context_length": 32768,
        "license": "apache-2.0",
        "url": "https://apxml.com/models/qwen3-8b",
    }


def test_normalize_apxml_spec_and_write_cache(tmp_path: Path) -> None:
    entry = catalog.normalize_apxml_spec(_apxml_spec(), "2026-08-01")
    assert entry["id"] == "qwen3-8b" and entry["kind"] == "llm"
    assert entry["quant"] == "Q4_K_M" and entry["source"] == "apxml"
    assert entry["fetched_at"] == "2026-08-01"
    # disk_gb is the Q4 VRAM figure with the quant overhead divided back out.
    assert entry["disk_gb"] == pytest.approx(6.0 / 1.12, rel=1e-3)
    # ApXML carries no numeric benchmarks, so every axis stays null.
    assert all(v is None for v in entry["benchmarks"].values())
    # A spec with no slug can't be keyed, so it is dropped from a batch.
    assert catalog.normalize_apxml_spec({"name": "no slug"}, "2026-08-01") is None
    assert [
        e["id"]
        for e in catalog.normalize_apxml_specs(
            [_apxml_spec(), {"name": "no slug"}], fetched_at="2026-08-01"
        )
    ] == ["qwen3-8b"]

    cache = tmp_path / "catalog_cache.yaml"
    catalog.write_cache(
        catalog.normalize_apxml_specs([_apxml_spec()], fetched_at="2026-08-01"), cache_path=cache
    )
    # A second refresh: same id overwrites (new ram), a new id appends.
    spec_b = dict(_apxml_spec(), slug="gemma3-4b")
    updated = dict(_apxml_spec(), ram_gb=7.0)
    catalog.write_cache(
        catalog.normalize_apxml_specs([updated, spec_b], fetched_at="2026-08-02"), cache_path=cache
    )
    by_id = {e["id"]: e for e in yaml.safe_load(cache.read_text())}
    assert set(by_id) == {"qwen3-8b", "gemma3-4b"}
    assert by_id["qwen3-8b"]["ram_gb"] == 7.0


def test_servable_keeps_pull_tags_and_drops_directory_slugs() -> None:
    """The catalog's contract says ``id`` is the Ollama pull tag.

    The hand-maintained seed honours it; the ApXML adapter cannot, because the
    directory it scrapes names models after their paper. Recommending one of
    those to Ollama produces a descriptor naming a model that cannot be
    pulled — and the caller only finds out at its first inference call.
    """
    from best_engine_ai_helper.catalog import servable

    assert servable({"id": "qwen3-vl:8b"}, "ollama")
    # A bare name is a legal tag: Ollama resolves it to :latest.
    assert servable({"id": "gemma3"}, "ollama")
    assert not servable({"id": "qwen36-35b-a3b", "source": "apxml"}, "ollama")
    # vLLM is not gated: a missing vllm_id already falls back to the raw tag.
    assert servable({"id": "qwen36-35b-a3b", "source": "apxml"}, "vllm")
    # An entry may declare its own backends, and that wins.
    assert not servable({"id": "x:1", "backends": ["vllm"]}, "ollama")
    assert servable({"id": "x:1", "backends": ["ollama"]}, "ollama")
    # An unknown backend is trusted rather than guessed at.
    assert servable({"id": "whatever"}, "some-future-backend")


def test_servable_only_filters_in_order() -> None:
    from best_engine_ai_helper.catalog import servable_only

    rows = [
        {"id": "gemma3:12b"},
        {"id": "llama-3-70b", "source": "apxml"},
        {"id": "qwen3:8b"},
    ]

    assert [r["id"] for r in servable_only(rows, "ollama")] == ["gemma3:12b", "qwen3:8b"]
    assert len(servable_only(rows, "vllm")) == 3


def test_a_slug_only_catalog_warns_rather_than_raises() -> None:
    """Unresolved is a warning here, by the same rule as an empty catalog.

    ``lightweight: never`` because the subject is the conventional path. Leaving it
    out made the outcome depend on whether lightweight happened to import on the
    host: it does not on a Mac without mlx, so this passed locally, and it does
    on a Linux runner, where the streaming rescue fired and handed back a model
    rather than the None this asserts. The rescue has its own tests.
    """
    from best_engine_ai_helper import engine

    resolved = engine.resolve(
        {"kind": "llm", "task": "write copy", "lightweight": "never"},
        backend="ollama",
        catalog=[{"id": "llama-3-70b", "kind": "llm", "ram_gb": 36.7, "source": "apxml"}],
        hw={"unified_gb": 64.0, "vram_gb": None, "ram_gb": 64.0},
        compute={"chip": "Apple M2 Max", "accelerator": "gpu-metal"},
    )

    assert resolved["llm"] is None


# ---------------------------------------------------------------------------
# merge_arena_axes — the seam both CLI twins call
# ---------------------------------------------------------------------------


def _entries() -> list[dict]:
    return [
        {"id": "gpt-4o", "benchmarks": {"general": 80.0}},
        {"id": "qwen2.5:3b", "benchmarks": {"general": 40.0}},
    ]


def test_a_dead_mirror_leaves_the_catalog_intact(monkeypatch) -> None:
    """A third-party outage must not cost the user a good ApXML refresh."""

    def _boom(**_kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("best_engine_ai_helper.sources.arena.fetch_arena_ratings", _boom)

    entries, message, merged = catalog.merge_arena_axes(_entries())

    assert merged is False
    assert [e["id"] for e in entries] == ["gpt-4o", "qwen2.5:3b"]
    assert "connection reset" in message


def test_an_empty_axis_is_reported_not_swallowed(monkeypatch) -> None:
    """The expected 2026 outcome: every mirror is stale, and the user hears so."""
    monkeypatch.setattr(
        "best_engine_ai_helper.sources.arena.fetch_arena_ratings",
        lambda **_k: {
            "source": "lmarena-history",
            "snapshot": "2025-05-22",
            "age_days": 515,
            "ratings": {},
            "scores": {},
            "stale": True,
            "note": "newest snapshot is 515 days old",
        },
    )

    entries, message, merged = catalog.merge_arena_axes(_entries())

    assert merged is False
    assert entries == _entries()  # untouched, not half-enriched
    assert "515 days old" in message


def test_a_fresh_snapshot_enriches_and_counts_coverage(monkeypatch) -> None:
    """Coverage is reported as matched/total so the skew is visible, not folklore."""
    monkeypatch.setattr(
        "best_engine_ai_helper.sources.arena.fetch_arena_ratings",
        lambda **_k: {
            "source": "test",
            "snapshot": "2026-10-01",
            "age_days": 18,
            "ratings": {"arena": {"gpt-4o": 1300.0}},
            "scores": {"arena": {"gpt-4o": 64.0}},
            "stale": False,
            "note": "1 rating(s) from test, snapshot 2026-10-01",
        },
    )

    entries, message, merged = catalog.merge_arena_axes(_entries())

    assert merged is True
    by_id = {e["id"]: e for e in entries}
    assert by_id["gpt-4o"]["benchmarks"]["arena"] == 64.0
    assert "arena" not in by_id["qwen2.5:3b"]["benchmarks"]  # declined, not guessed
    assert "1/2" in message


# ---------------------------------------------------------------------------
# The ApXML adapter states its backend rather than leaving it to be inferred
# ---------------------------------------------------------------------------


def test_apxml_entries_declare_their_backends_explicitly() -> None:
    """The writer knows these are HuggingFace repo names, so it should say so.

    Both Hub-loading backends, not just vLLM: this directory catalogues the
    200B-and-up open-weight models that only layer streaming can run here, so
    leaving `lightweight` out hid the entries that backend exists for.
    """
    entry = catalog.normalize_apxml_spec({"slug": "qwen36-35b-a3b", "ram_gb": 20.0}, "2026-10-19")

    assert entry is not None
    assert entry["backends"] == ["vllm", "lightweight"]
    assert catalog.servable(entry, "lightweight") is True
    assert catalog.servable(entry, "ollama") is False


def test_apxml_mixture_of_experts_is_flagged_so_depth_is_never_guessed() -> None:
    """A MoE entry must carry `moe`, or its streaming footprint is wrong by 2x."""
    moe = catalog.normalize_apxml_spec(
        {"slug": "deepseek-v3", "size_b": 671.0, "ram_gb": 400.0, "num_of_experts": 256},
        "2026-10-19",
    )
    dense = catalog.normalize_apxml_spec(
        {"slug": "llama-3-70b", "size_b": 70.0, "ram_gb": 40.0, "num_of_experts": 1},
        "2026-10-19",
    )

    assert moe is not None and moe["moe"] is True
    assert dense is not None and "moe" not in dense

    # And the flag is what stops the depth interpolation from firing.
    from best_engine_ai_helper import offload

    assert offload.layer_count(moe) == (None, False)
    assert offload.layer_count(dense) == (80, True)


def test_the_declared_backend_is_what_gates_an_apxml_entry() -> None:
    """With `backends` present, servable() no longer has to infer from `source`."""
    entry = catalog.normalize_apxml_spec({"slug": "llama-3-70b", "ram_gb": 40.0}, "2026-10-19")
    assert entry is not None

    assert catalog.servable(entry, "ollama") is False
    assert catalog.servable(entry, "vllm") is True

    # Same verdict with `source` stripped: the entry now carries the fact itself.
    stated = {k: v for k, v in entry.items() if k != "source"}
    assert catalog.servable(stated, "ollama") is False


def test_the_source_rule_still_covers_entries_cached_before_this_change() -> None:
    """A cache written by an older version has no `backends` key; the net holds."""
    legacy = {"id": "qwen36-35b-a3b", "source": "apxml"}

    assert catalog.servable(legacy, "ollama") is False
    assert catalog.servable(legacy, "vllm") is True
