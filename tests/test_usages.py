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
    {
        "id": "tiny",
        "kind": "llm",
        "size_b": 3,
        "ram_gb": 2.2,
        "benchmarks": {"general": 62},
        "structured_output": True,
        "vllm_id": "org/Tiny",
    },
    {
        "id": "coder",
        "kind": "llm",
        "size_b": 7,
        "ram_gb": 5.0,
        "benchmarks": {"general": 66, "code": 88},
        "structured_output": True,
        "vllm_id": "org/Coder",
    },
    {
        "id": "generalist",
        "kind": "llm",
        "size_b": 14,
        "ram_gb": 10.0,
        "benchmarks": {"general": 78},
        "structured_output": True,
        "vllm_id": "org/Gen",
    },
    {"id": "emb-small", "kind": "embed", "ram_gb": 0.5, "benchmarks": {"mteb": 62}},
    {"id": "emb-best", "kind": "embed", "ram_gb": 1.2, "benchmarks": {"mteb": 66}},
]
_HW = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
_COMPUTE = {"accelerator": "apple", "chip": "Apple M2", "bandwidth_gbs": None}
_TINY_HW = {"unified_gb": None, "vram_gb": None, "ram_gb": 1.0}  # budget ~0.25 GB


def test_catalog_structure_and_lookup_errors() -> None:
    names = [p["name"] for p in usages.load_usages()]
    # The eight sev7n workloads the catalog must cover.
    for expected in (
        "text2sql",
        "rag-answer",
        "embeddings",
        "text2sql-figures",
        "report-bluf",
        "classification",
        "pii-rgpd",
        "persona",
    ):
        assert expected in names
    assert [f["id"] for f in usages.load_families()] == ["F1", "F2", "F3"]
    # Every profile carries a resolvable brief and names its family.
    for p in usages.load_usages():
        assert "kind" in p["brief"] and "task" in p["brief"]
        assert p["family"] in {"F1", "F2", "F3"}

    # The hard rule: the usage catalog describes needs, never a concrete model.
    for spec in usages.load_usages() + usages.load_families():
        assert "prefer" not in spec and "models" not in spec
        assert "model" not in spec.get("brief", {})

    with pytest.raises(KeyError, match="text2sql"):
        usages.get_usage("text2sq")  # close typo -> suggestion mentions the real name
    with pytest.raises(KeyError, match="Known families"):
        usages.get_family("F9")

    brief = usages.usage_brief("text2sql")
    assert brief["mode"] == "local" and brief["kind"] == "llm"
    assert brief["structured_output"] is True


def test_resolve_usage_and_family_with_synthetic_catalog() -> None:
    # text2sql's task maps to the code axis, so the coder (code 88) wins on it.
    text2sql = usages.resolve_usage(
        "text2sql", backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    assert text2sql["llm"]["model"] == "coder"
    assert text2sql["usage"] == "text2sql" and text2sql["status"] == "stable"
    assert "do not commit" in text2sql["generated_by"]

    # rag-answer's task is generalist prose: the 78-general model wins its axis.
    rag = usages.resolve_usage(
        "rag-answer", backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    assert rag["llm"]["model"] == "generalist"
    assert rag["local_strict"] is True

    vllm_pick = usages.resolve_usage(
        "text2sql", backend="vllm", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    assert vllm_pick["backend"] == "vllm" and vllm_pick["llm"]["model"] == "org/Coder"

    # F3 is not a generative pick: highest MTEB embedder that fits wins.
    embeddings = usages.resolve_usage("embeddings", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert embeddings["kind"] == "embed" and embeddings["embed"]["model"] == "emb-best"
    assert embeddings["embed"]["fits"] is True
    assert embeddings["serve"] == ["ollama pull emb-best"]

    # Nothing fits the ~0.25 GB budget: smallest embedder, flagged not-fitting.
    no_fit = usages.resolve_usage("embeddings", catalog=_CATALOG, hw=_TINY_HW, compute=_COMPUTE)
    assert no_fit["embed"]["model"] == "emb-small" and no_fit["embed"]["fits"] is False

    f1 = usages.resolve_family("F1", backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert f1["family"] == "F1" and f1["llm"]["model"] == "coder"
    f3 = usages.resolve_family("F3", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert f3["family"] == "F3" and f3["embed"]["model"] == "emb-best"

    scaffold = usages.resolve_usage(
        "text2sql-figures", backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    assert scaffold["status"] == "scaffold"

    # A catalog whose only fitting model scores below the profile floor: the
    # pick is flagged (below_min_quality), never blocked.
    weak = [
        {
            "id": "weak",
            "kind": "llm",
            "size_b": 3,
            "ram_gb": 2.0,
            "benchmarks": {"general": 40, "code": 40},
            "structured_output": True,
            "vllm_id": "org/Weak",
        }
    ]
    weak_pick = usages.resolve_usage(
        "text2sql", backend="ollama", catalog=weak, hw=_HW, compute=_COMPUTE
    )
    assert weak_pick["llm"]["model"] == "weak"
    assert weak_pick["llm"].get("below_min_quality") is True

    # Over the REAL bundled catalog + injected hardware, every profile must
    # resolve to some model (or a clean no-fit fallback) without raising.
    for profile in usages.load_usages():
        eng = usages.resolve_usage(profile["name"], backend="ollama", hw=_HW, compute=_COMPUTE)
        section = eng.get("llm") or eng.get("vlm") or eng.get("embed")
        assert section is not None and section.get("model"), profile["name"]
