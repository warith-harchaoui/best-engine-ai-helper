"""
Tests for the Ollama-library catalog source, and the merge it exposed.

This source exists because the catalog was stuck at twenty *servable* models:
ApXML can add hundreds, but it names them by the paper's slug, which
`ollama pull` cannot resolve. A family plus a size from the official library is
a real pull tag, so these entries widen the pool that can actually be served.

What must stay true: widening reach must never cost ranking quality. These
entries carry no benchmarks, and an entry with no score must never displace a
hand-curated one.
"""

from __future__ import annotations

from best_engine_ai_helper import catalog
from best_engine_ai_helper.sources import ollama_library as lib

# One <li> per family, trimmed to the parts the parser reads.
_PAGE = """
<ul>
  <li class="flex">
    <a href="/library/qwen3"><h2>qwen3</h2></a>
    <span>tools</span><span>thinking</span>
    <span>0.6b</span><span>8b</span><span>14b</span>
  </li>
  <li class="flex">
    <a href="/library/llava"><h2>llava</h2></a>
    <span>vision</span>
    <span>7b</span><span>13b</span>
  </li>
  <li class="flex">
    <a href="/library/bge-m3"><h2>bge-m3</h2></a>
    <span>embedding</span>
  </li>
  <li class="flex">
    <a href="/library/mixtral"><h2>mixtral</h2></a>
    <span>tools</span>
    <span>8x7b</span>
  </li>
</ul>
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_each_family_keeps_its_own_capabilities() -> None:
    """A document-wide regex would smear vision onto every model on the page."""
    by_name = {f["name"]: f for f in lib.parse_library(_PAGE)}

    assert by_name["llava"]["capabilities"] == ["vision"]
    assert by_name["bge-m3"]["capabilities"] == ["embedding"]
    assert "vision" not in by_name["qwen3"]["capabilities"]


def test_a_family_and_a_size_make_a_real_pull_tag() -> None:
    """`qwen3` + `8b` is `qwen3:8b`, the spelling the seed already uses."""
    ids = {s["id"] for s in lib.to_specs(lib.parse_library(_PAGE))}

    assert "qwen3:8b" in ids
    assert "llava:7b" in ids


def test_capabilities_decide_the_kind() -> None:
    by_id = {s["id"]: s for s in lib.to_specs(lib.parse_library(_PAGE))}

    assert by_id["qwen3:8b"]["kind"] == "llm"
    assert by_id["llava:7b"]["kind"] == "vlm"


def test_a_mixture_of_experts_counts_all_its_parameters() -> None:
    """`8x7b` is 56B of weights to hold, not 7B."""
    by_id = {s["id"]: s for s in lib.to_specs(lib.parse_library(_PAGE))}

    assert by_id["mixtral:8x7b"]["size_b"] == 56.0


def test_a_family_with_no_size_is_skipped_rather_than_sized_as_zero() -> None:
    """An entry whose footprint is unknown would otherwise 'fit' every machine."""
    ids = {s["id"] for s in lib.to_specs(lib.parse_library(_PAGE))}

    assert not any(i.startswith("bge-m3") for i in ids)


def test_vision_models_are_sized_heavier_per_parameter() -> None:
    """Measured on the seed: an image tower costs ~0.714 GB/B against ~0.646."""
    by_id = {s["id"]: s for s in lib.to_specs(lib.parse_library(_PAGE))}

    llm_ratio = by_id["qwen3:14b"]["disk_gb"] / 14.0
    vlm_ratio = by_id["llava:13b"]["disk_gb"] / 13.0
    assert vlm_ratio > llm_ratio


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_entries_are_servable_by_ollama_unlike_apxml_ones() -> None:
    """The entire reason this source exists."""
    specs = lib.to_specs(lib.parse_library(_PAGE))
    entries = catalog.normalize_ollama_specs(specs, "2026-10-19")

    assert entries
    assert all(catalog.servable(e, "ollama") for e in entries)
    assert all(e["source"] == "ollama-library" for e in entries)


def test_entries_carry_no_invented_benchmarks() -> None:
    """The library publishes sizes, not leaderboard results."""
    entries = catalog.normalize_ollama_specs(lib.to_specs(lib.parse_library(_PAGE)), "2026-10-19")

    assert all(v is None for e in entries for v in e["benchmarks"].values())


def test_a_spec_with_no_usable_size_is_dropped() -> None:
    assert catalog.normalize_ollama_spec({"id": "x:8b", "disk_gb": 0}, "2026-10-19") is None
    assert catalog.normalize_ollama_spec({"id": "", "disk_gb": 5.0}, "2026-10-19") is None


# ---------------------------------------------------------------------------
# The merge this source exposed
# ---------------------------------------------------------------------------


def test_a_refresh_without_scores_does_not_erase_curated_ones() -> None:
    """Widening the catalog must not degrade it.

    Latent while ApXML was the only source — its slugs never collide with the
    seed's pull tags. A source that emits real tags collides constantly.
    """
    seed = {"id": "gemma3:12b", "benchmarks": {"general": 77, "vision": 69}, "disk_gb": 8.4}
    fresh = {
        "id": "gemma3:12b",
        "benchmarks": {"general": None, "vision": None},
        "disk_gb": 8.57,
        "source": "ollama-library",
    }

    merged = catalog._overlay(seed, fresh)

    assert merged["benchmarks"]["general"] == 77  # curated score survives
    assert merged["disk_gb"] == 8.57  # fresh spec lands
    assert merged["source"] == "ollama-library"


def test_a_real_score_from_a_refresh_does_win() -> None:
    """Preserving the old value must not mean refusing a new one."""
    seed = {"id": "m", "benchmarks": {"general": 60}}
    fresh = {"id": "m", "benchmarks": {"general": 72}}

    assert catalog._overlay(seed, fresh)["benchmarks"]["general"] == 72


def test_an_axis_the_refresh_is_silent_about_is_kept() -> None:
    seed = {"id": "m", "benchmarks": {"general": 60, "code": 55}}
    fresh = {"id": "m", "benchmarks": {"general": 72}}

    merged = catalog._overlay(seed, fresh)
    assert merged["benchmarks"] == {"general": 72, "code": 55}


def test_a_brand_new_entry_passes_through_unchanged() -> None:
    fresh = {"id": "new:8b", "benchmarks": {"general": None}}
    assert catalog._overlay(None, fresh) == fresh


# ---------------------------------------------------------------------------
# Fetching: wiring, limit, and the page's own quirks
# ---------------------------------------------------------------------------


class _FakePage:
    """A requests-like response carrying a fixed page."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.asked: dict = {}

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, text: str) -> None:
        self.page = _FakePage(text)
        self.calls: list[tuple] = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append((url, timeout, headers))
        return self.page


def test_fetch_reads_the_library_index_once_and_bounded() -> None:
    """One request, with a timeout: a hung index read would stall a command
    somebody is sitting in front of."""
    session = _FakeSession(_PAGE)

    families = lib.fetch_library(session=session, timeout=12.0)

    assert len(session.calls) == 1
    url, timeout, headers = session.calls[0]
    assert url == lib.LIBRARY_URL
    assert timeout == 12.0
    assert "User-Agent" in headers
    assert [f["name"] for f in families] == ["qwen3", "llava", "bge-m3", "mixtral"]


def test_limit_keeps_the_most_popular_families() -> None:
    """The page orders by popularity, so a partial refresh should take the
    models people actually use rather than an arbitrary slice."""
    session = _FakeSession(_PAGE)

    families = lib.fetch_library(session=session, limit=2)

    assert [f["name"] for f in families] == ["qwen3", "llava"]


def test_a_family_listed_twice_is_recorded_once() -> None:
    """The real index repeats some families (nomic-embed-text appears twice);
    a duplicate entry would be a duplicate catalog id."""
    doubled = (
        _PAGE
        + """
      <li class="flex"><a href="/library/qwen3"><h2>qwen3</h2></a><span>8b</span></li>
    """
    )
    families = lib.parse_library(doubled)

    assert [f["name"] for f in families].count("qwen3") == 1


def test_list_items_that_are_not_models_are_ignored() -> None:
    """The page's <li> elements include navigation and footer entries."""
    noisy = '<li class="nav"><a href="/blog">Blog</a></li>' + _PAGE

    assert [f["name"] for f in lib.parse_library(noisy)] == [
        "qwen3",
        "llava",
        "bge-m3",
        "mixtral",
    ]


def test_fetch_pullable_models_returns_tags_not_families() -> None:
    """The end-to-end shape callers use: one spec per concrete pull tag."""
    session = _FakeSession(_PAGE)

    specs = lib.fetch_pullable_models(session=session)

    ids = {s["id"] for s in specs}
    assert "qwen3:8b" in ids and "llava:13b" in ids
    assert all(":" in s["id"] for s in specs), "a family alone is not pullable at a size"
