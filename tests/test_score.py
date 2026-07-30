"""
Tests for best_engine_ai_helper.score.

Uses synthetic catalogs so tests never depend on disk files or network access.
"""

from __future__ import annotations

import pytest

from best_engine_ai_helper import score

# ---------------------------------------------------------------------------
# Fixtures — synthetic catalog entries
# ---------------------------------------------------------------------------

def _make_vlm(id_: str, ram_gb: float, vision: float, general: float) -> dict:
    return {
        "id": id_,
        "kind": "vlm",
        "ram_gb": ram_gb,
        "benchmarks": {"general": general, "vision": vision},
    }


def _make_llm(id_: str, ram_gb: float, general: float) -> dict:
    return {
        "id": id_,
        "kind": "llm",
        "ram_gb": ram_gb,
        "benchmarks": {"general": general, "vision": None},
    }


SMALL_VLM = _make_vlm("small-vlm", 3.5, vision=70.0, general=65.0)
MID_VLM   = _make_vlm("mid-vlm",   9.0, vision=80.0, general=75.0)
LARGE_VLM = _make_vlm("large-vlm", 52.0, vision=91.0, general=88.0)

SMALL_LLM = _make_llm("small-llm", 2.2, general=62.0)
MID_LLM   = _make_llm("mid-llm",  10.5, general=78.0)
LARGE_LLM = _make_llm("large-llm", 48.0, general=87.0)

ALL_MODELS = [SMALL_LLM, SMALL_VLM, MID_LLM, MID_VLM, LARGE_LLM, LARGE_VLM]


# ---------------------------------------------------------------------------
# effective_budget
# ---------------------------------------------------------------------------

def test_effective_budget_uses_unified_first() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": 24.0, "ram_gb": 96.0}
    # Unified takes priority; >36 GB so Metal cap 0.75, then headroom 0.85:
    # 96 * 0.75 * 0.85 = 61.2
    assert score.effective_budget(hw) == pytest.approx(61.2)


def test_effective_budget_falls_back_to_vram() -> None:
    hw = {"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0}
    # No unified; VRAM budget: 24 * 0.92 * 0.85 = 18.768
    assert score.effective_budget(hw) == pytest.approx(18.768)


def test_effective_budget_falls_back_to_half_ram() -> None:
    hw = {"unified_gb": None, "vram_gb": None, "ram_gb": 32.0}
    # CPU-only: half of RAM, then headroom: 32 * 0.5 * 0.85 = 13.6
    assert score.effective_budget(hw) == pytest.approx(13.6)


def test_effective_budget_custom_headroom() -> None:
    hw = {"unified_gb": 64.0, "vram_gb": None, "ram_gb": 64.0}
    # >36 GB so cap 0.75; 64 * 0.75 * 0.90 = 43.2
    assert score.effective_budget(hw, headroom=0.90) == pytest.approx(43.2)


# ---------------------------------------------------------------------------
# select — VLM
# ---------------------------------------------------------------------------

def test_select_vlm_picks_best_vision_that_fits() -> None:
    # 24 GB unified: budget = 24 * 0.66 * 0.85 = 13.46 GB; large-vlm (52) no fit
    hw = {"unified_gb": 24.0, "vram_gb": None, "ram_gb": 24.0}
    result = score.select(hw, ALL_MODELS, kind="vlm")
    # mid-vlm (9.0 GB, vision 80) fits and beats small-vlm (3.5 GB, vision 70)
    assert result["id"] == "mid-vlm"


def test_select_vlm_on_large_machine_picks_top() -> None:
    # 96 GB: budget = 61.2 GB; large-vlm (52) fits and wins
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    result = score.select(hw, ALL_MODELS, kind="vlm")
    assert result["id"] == "large-vlm"


def test_select_vlm_last_resort_when_nothing_fits() -> None:
    # 2 GB VRAM: budget = 1.6 GB; nothing fits → last resort (smallest)
    hw = {"unified_gb": None, "vram_gb": 2.0, "ram_gb": 8.0}
    result = score.select(hw, ALL_MODELS, kind="vlm")
    # smallest VLM by ram_gb is small-vlm (3.5 GB)
    assert result["id"] == "small-vlm"


# ---------------------------------------------------------------------------
# select — LLM
# ---------------------------------------------------------------------------

def test_select_llm_picks_by_general_score() -> None:
    # 24 GB budget = 13.46 GB; large-llm (48) and large-vlm (52) don't fit
    hw = {"unified_gb": 24.0, "vram_gb": None, "ram_gb": 24.0}
    result = score.select(hw, ALL_MODELS, kind="llm")
    # mid-llm (10.5 GB, general 78) beats mid-vlm (9.0 GB, general 75)
    # and small-llm (2.2 GB, general 62) and small-vlm (3.5 GB, general 65)
    assert result["id"] == "mid-llm"


def test_select_llm_vlm_counts_as_candidate() -> None:
    # VLMs are valid LLM candidates; on a large machine the best LLM by
    # general score might be a VLM
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    result = score.select(hw, ALL_MODELS, kind="llm")
    # large-llm general=87, large-vlm general=88 → large-vlm wins as LLM too
    assert result["id"] == "large-vlm"


def test_select_raises_on_empty_catalog() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    with pytest.raises(ValueError, match="empty"):
        score.select(hw, [], kind="llm")


# ---------------------------------------------------------------------------
# rank
# ---------------------------------------------------------------------------

def test_rank_all_fit_on_large_machine() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    ranked = score.rank(hw, ALL_MODELS, kind="vlm")
    # All VLMs should fit on 96 GB (budget = 76.8 GB; large-vlm = 52 GB fits)
    fitting = [r for r in ranked if r["_fits"]]
    assert len(fitting) == 3  # small, mid, large VLMs all fit


def test_rank_descending_vision_score() -> None:
    hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    ranked = score.rank(hw, ALL_MODELS, kind="vlm")
    scores = [r["benchmarks"]["vision"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_first_entry_matches_select() -> None:
    # The first entry in rank() should match what select() returns
    hw = {"unified_gb": 16.0, "vram_gb": None, "ram_gb": 16.0}
    ranked = score.rank(hw, ALL_MODELS, kind="vlm")
    selected = score.select(hw, ALL_MODELS, kind="vlm")
    # First fitting entry should match
    fitting = [r for r in ranked if r["_fits"]]
    assert fitting[0]["id"] == selected["id"]


# ---------------------------------------------------------------------------
# estimated_tokens_per_second
# ---------------------------------------------------------------------------

def test_tps_scales_inverse_with_size() -> None:
    # tok/s = bandwidth / ram * 0.65; smaller model → faster
    fast = score.estimated_tokens_per_second({"ram_gb": 8.0}, 400.0)
    slow = score.estimated_tokens_per_second({"ram_gb": 52.0}, 400.0)
    assert fast is not None and slow is not None
    assert fast > slow
    assert score.estimated_tokens_per_second({"ram_gb": 10.0}, 400.0) == pytest.approx(26.0)


def test_tps_none_without_bandwidth() -> None:
    assert score.estimated_tokens_per_second({"ram_gb": 8.0}, None) is None
    assert score.estimated_tokens_per_second({"ram_gb": 0}, 400.0) is None
