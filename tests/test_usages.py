"""
Tests for best_engine_ai_helper.usages — the sev7n usage catalog.

The catalog states only NEEDS; best-engine chooses the model. These tests use a
synthetic catalog + injected hardware (no bandwidth, so the comfort gate cannot
fire and picks are decided by memory fit + score alone — fully deterministic,
no real machine / Ollama / network), plus a pass over the real bundled catalog
to prove every profile resolves to a model or a clean no-fit fallback.
"""

from __future__ import annotations

import pytest

from best_engine_ai_helper import usages

# Structured-capable generative models spanning the axes the profiles touch,
# plus two embedders for the F3 path. No bandwidth in _COMPUTE, so throughput is
# not estimated and the comfort floor never fires: memory + score decide.
_CATALOG = [
    {"id": "tiny", "kind": "llm", "size_b": 3, "ram_gb": 2.2,
     "benchmarks": {"general": 62}, "structured_output": True, "vllm_id": "org/Tiny"},
    {"id": "coder", "kind": "llm", "size_b": 7, "ram_gb": 5.0,
     "benchmarks": {"general": 66, "code": 88}, "structured_output": True,
     "vllm_id": "org/Coder"},
    {"id": "generalist", "kind": "llm", "size_b": 14, "ram_gb": 10.0,
     "benchmarks": {"general": 78}, "structured_output": True, "vllm_id": "org/Gen"},
    {"id": "emb-small", "kind": "embed", "ram_gb": 0.5, "benchmarks": {"mteb": 62}},
    {"id": "emb-best", "kind": "embed", "ram_gb": 1.2, "benchmarks": {"mteb": 66}},
]
_HW = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
_COMPUTE = {"accelerator": "apple", "chip": "Apple M2", "bandwidth_gbs": None}
_TINY_HW = {"unified_gb": None, "vram_gb": None, "ram_gb": 1.0}  # budget ~0.25 GB


def test_catalog_loads_profiles_and_families() -> None:
    names = [p["name"] for p in usages.load_usages()]
    # The eight sev7n workloads the catalog must cover.
    for expected in ("text2sql", "rag-answer", "embeddings", "text2sql-figures",
                     "report-bluf", "classification", "pii-rgpd", "persona"):
        assert expected in names
    assert [f["id"] for f in usages.load_families()] == ["F1", "F2", "F3"]
    # Every profile carries a resolvable brief and names its family.
    for p in usages.load_usages():
        assert "kind" in p["brief"] and "task" in p["brief"]
        assert p["family"] in {"F1", "F2", "F3"}


def test_catalog_never_names_a_model() -> None:
    # The hard rule: the usage catalog describes needs, never a concrete model.
    # No profile/family may carry a model-hint field.
    for spec in usages.load_usages() + usages.load_families():
        assert "prefer" not in spec and "models" not in spec
        assert "model" not in spec.get("brief", {})


def test_get_usage_unknown_suggests() -> None:
    with pytest.raises(KeyError, match="text2sql"):
        usages.get_usage("text2sq")  # close typo -> suggestion mentions the real name


def test_get_family_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Known families"):
        usages.get_family("F9")


def test_usage_brief_is_local_and_resolvable() -> None:
    brief = usages.usage_brief("text2sql")
    assert brief["mode"] == "local" and brief["kind"] == "llm"
    assert brief["structured_output"] is True


def test_resolve_text2sql_picks_a_code_model() -> None:
    # text2sql's task maps to the code axis, so the coder (code 88) wins on it.
    eng = usages.resolve_usage("text2sql", backend="ollama", catalog=_CATALOG,
                               hw=_HW, compute=_COMPUTE)
    assert eng["llm"]["model"] == "coder"
    assert eng["usage"] == "text2sql" and eng["status"] == "stable"
    assert "do not commit" in eng["generated_by"]


def test_resolve_rag_answer_picks_a_generalist() -> None:
    # rag-answer's task is generalist prose: the 78-general model wins its axis.
    eng = usages.resolve_usage("rag-answer", backend="ollama", catalog=_CATALOG,
                               hw=_HW, compute=_COMPUTE)
    assert eng["llm"]["model"] == "generalist"
    assert eng["local_strict"] is True


def test_resolve_vllm_uses_huggingface_id() -> None:
    eng = usages.resolve_usage("text2sql", backend="vllm", catalog=_CATALOG,
                               hw=_HW, compute=_COMPUTE)
    assert eng["backend"] == "vllm" and eng["llm"]["model"] == "org/Coder"


def test_resolve_embeddings_picks_best_that_fits() -> None:
    # F3 is not a generative pick: highest MTEB embedder that fits wins.
    eng = usages.resolve_usage("embeddings", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert eng["kind"] == "embed" and eng["embed"]["model"] == "emb-best"
    assert eng["embed"]["fits"] is True
    assert eng["serve"] == ["ollama pull emb-best"]


def test_resolve_embeddings_no_fit_falls_back_to_smallest() -> None:
    eng = usages.resolve_usage("embeddings", catalog=_CATALOG, hw=_TINY_HW,
                               compute=_COMPUTE)
    # Nothing fits the ~0.25 GB budget: smallest embedder, flagged not-fitting.
    assert eng["embed"]["model"] == "emb-small" and eng["embed"]["fits"] is False


def test_resolve_family_one_model_per_group() -> None:
    f1 = usages.resolve_family("F1", backend="ollama", catalog=_CATALOG,
                               hw=_HW, compute=_COMPUTE)
    assert f1["family"] == "F1" and f1["llm"]["model"] == "coder"
    f3 = usages.resolve_family("F3", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert f3["family"] == "F3" and f3["embed"]["model"] == "emb-best"


def test_scaffold_status_surfaced() -> None:
    eng = usages.resolve_usage("text2sql-figures", backend="ollama", catalog=_CATALOG,
                               hw=_HW, compute=_COMPUTE)
    assert eng["status"] == "scaffold"


def test_min_quality_flags_subpar_pick() -> None:
    # A catalog whose only fitting model scores below the profile floor: the pick
    # is flagged (below_min_quality), never blocked.
    weak = [{"id": "weak", "kind": "llm", "size_b": 3, "ram_gb": 2.0,
             "benchmarks": {"general": 40, "code": 40}, "structured_output": True,
             "vllm_id": "org/Weak"}]
    eng = usages.resolve_usage("text2sql", backend="ollama", catalog=weak,
                               hw=_HW, compute=_COMPUTE)
    assert eng["llm"]["model"] == "weak"
    assert eng["llm"].get("below_min_quality") is True


@pytest.mark.parametrize("name", [p["name"] for p in usages.load_usages()])
def test_every_profile_resolves_over_real_catalog(name: str) -> None:
    # Over the REAL bundled catalog + injected hardware, every profile must
    # resolve to some model (or a clean no-fit fallback) without raising.
    eng = usages.resolve_usage(name, backend="ollama", hw=_HW, compute=_COMPUTE)
    section = eng.get("llm") or eng.get("vlm") or eng.get("embed")
    assert section is not None and section.get("model")
