"""
Tests for best_engine_ai_helper.engine — the brief -> engine resolution flow.

Synthetic catalog + injected hardware, so nothing depends on the real machine,
Ollama, or the network. Covers the backend rule, the headroom clamp, the
Ollama-tag vs vLLM-HuggingFace-id split, the file round-trip, and the
``ensure`` missing-file policy.
"""

from __future__ import annotations

import pytest

import best_engine_ai_helper.detect as detect
from best_engine_ai_helper import engine, llm

# Two structured-capable models with both an Ollama tag and a vLLM HF id.
_CATALOG = [
    {"id": "small-llm", "kind": "llm", "size_b": 3, "ram_gb": 2.5,
     "benchmarks": {"general": 70}, "structured_output": True,
     "vllm_id": "org/Small-LLM"},
    {"id": "mid-vlm", "kind": "vlm", "size_b": 8, "ram_gb": 6.0,
     "benchmarks": {"general": 74, "vision": 80}, "structured_output": True,
     "vllm_id": "org/Mid-VLM"},
]
# Unified 64 GB -> budget 64 * 0.75 * 0.5 = 24 GB; both models fit on either
# backend. No bandwidth, so throughput is not estimated and the comfort gate
# cannot fire — memory fit alone decides, keeping the picks deterministic.
_HW = {"unified_gb": 64.0, "vram_gb": None, "ram_gb": 64.0}
_COMPUTE = {"accelerator": "gpu-metal", "chip": "Apple M2", "bandwidth_gbs": None}

_BRIEF = {"kind": "both", "headroom": 0.9, "min_tps": 15,
          "task": "summarize a transcript and read a chart image"}


def test_default_backend_rule(monkeypatch) -> None:
    # vLLM only on a real discrete GPU; Ollama for Apple, Intel iGPU, and CPU.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    assert engine.default_backend() == "vllm"
    monkeypatch.setattr(detect, "chip_vendor", lambda: "amd")
    assert engine.default_backend() == "vllm"
    for cpu_like in ("apple", "intel", "cpu"):
        monkeypatch.setattr(detect, "chip_vendor", lambda v=cpu_like: v)
        assert engine.default_backend() == "ollama"


def test_resolve_ollama_uses_tags_and_clamps_headroom() -> None:
    eng = engine.resolve(_BRIEF, backend="ollama", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    assert eng["backend"] == "ollama"
    assert eng["base_url"] == "http://localhost:11434"
    # Brief asked for 0.9 headroom; the resolver clamps it to the 0.5 ceiling.
    assert eng["headroom"] == 0.5
    # Ollama uses the pull tag (not the HF id). mid-vlm (general 74) is the
    # leanest model within 3 points of the best, so it wins the text slot too.
    assert eng["llm"]["model"] == "mid-vlm"
    assert eng["vlm"]["model"] == "mid-vlm"
    assert eng["serve"] == ["ollama pull mid-vlm"]


def test_resolve_vllm_uses_huggingface_ids() -> None:
    eng = engine.resolve(_BRIEF, backend="vllm", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    assert eng["backend"] == "vllm"
    assert eng["base_url"] == "http://localhost:8000/v1"
    # vLLM serves the HuggingFace id, not the Ollama tag.
    assert eng["llm"]["model"] == "org/Mid-VLM"
    assert eng["serve"] == ["vllm serve org/Mid-VLM --port 8000"]


def test_resolve_endpoint_override() -> None:
    eng = engine.resolve(_BRIEF, backend="vllm", endpoint="http://gpu-box:8001/v1",
                         catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert eng["base_url"] == "http://gpu-box:8001/v1"
    assert eng["serve"] == ["vllm serve org/Mid-VLM --port 8001"]


def test_write_and_load_engine_roundtrip(tmp_path) -> None:
    eng = engine.resolve(_BRIEF, backend="ollama", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    path = engine.write_engine(eng, tmp_path / engine.ENGINE_NAME)
    text = path.read_text()
    assert "do NOT commit" in text  # the gitignore reminder header is present
    loaded = engine.load_engine(path)
    assert loaded["backend"] == "ollama"
    assert loaded["llm"]["model"] == "mid-vlm"


def test_ensure_loads_existing_engine(tmp_path, monkeypatch) -> None:
    # An engine file already on disk is used as-is; resolve must NOT run.
    eng = engine.resolve(_BRIEF, backend="ollama", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    engine.write_engine(eng, tmp_path / engine.ENGINE_NAME)

    def _boom(*a, **k):
        raise AssertionError("resolve() must not be called when the engine exists")

    monkeypatch.setattr(engine, "resolve", _boom)
    got = engine.ensure(tmp_path)
    assert got["backend"] == "ollama"


def test_ensure_resolves_from_brief_when_engine_missing(tmp_path, monkeypatch) -> None:
    (tmp_path / engine.BRIEF_NAME).write_text("kind: llm\ntask: write copy\n")
    stub = {"backend": "ollama", "base_url": "x", "llm": {"model": "qwen3:8b"}}
    monkeypatch.setattr(engine, "resolve", lambda *a, **k: stub)
    got = engine.ensure(tmp_path)
    assert got["llm"]["model"] == "qwen3:8b"
    # It persisted the resolved engine file for next time.
    assert (tmp_path / engine.ENGINE_NAME).is_file()


def test_ensure_raises_loudly_without_brief(tmp_path) -> None:
    # No engine and no committed brief: a real bug, so fail loud (not a default).
    with pytest.raises(RuntimeError, match="no brief"):
        engine.ensure(tmp_path)


def test_model_for_returns_backend_url_model() -> None:
    eng = engine.resolve(_BRIEF, backend="vllm", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    backend, base_url, model = engine.model_for(eng, "llm")
    assert backend == "vllm" and base_url.endswith("/v1") and model == "org/Mid-VLM"
    with pytest.raises(KeyError):
        engine.model_for({"backend": "ollama", "base_url": "x"}, "vlm")


def test_resolve_defaults_to_local_mode() -> None:
    eng = engine.resolve(_BRIEF, backend="ollama", catalog=_CATALOG,
                         hw=_HW, compute=_COMPUTE)
    assert eng["mode"] == "local"


def test_resolve_cloud_mode_is_deferred() -> None:
    # The `mode` field is recognised (forward-compatible), but cloud resolution
    # ships on the 'cloud' branch — asking for it now fails loudly, not silently.
    with pytest.raises(NotImplementedError, match="cloud"):
        engine.resolve({"kind": "llm", "mode": "cloud", "task": "x"},
                       catalog=_CATALOG, hw=_HW, compute=_COMPUTE)


def test_chat_engine_routes_backend_and_base_url(monkeypatch) -> None:
    # chat(engine=...) must read backend/base_url/model from the descriptor and
    # map a vLLM backend to the OpenAI-compatible transport.
    captured: dict = {}

    def _fake_ollama(prompt, **kw):
        captured.clear()
        captured.update(kw)
        captured["fn"] = "ollama"
        return "ok"

    def _fake_openai(prompt, **kw):
        captured.clear()
        captured.update(kw)
        captured["fn"] = "openai"
        return "ok"

    monkeypatch.setattr(llm, "_chat_ollama", _fake_ollama)
    monkeypatch.setattr(llm, "_chat_openai", _fake_openai)

    vllm_eng = {"backend": "vllm", "base_url": "http://gpu:8000/v1",
                "llm": {"model": "org/Text"}, "vlm": {"model": "org/Vision"}}
    llm.chat("hi", engine=vllm_eng, kind="llm")
    assert captured["fn"] == "openai"
    assert captured["model"] == "org/Text"
    assert captured["base_url"] == "http://gpu:8000/v1"

    ollama_eng = {"backend": "ollama", "base_url": "http://localhost:11434",
                  "llm": {"model": "qwen3:8b"}}
    llm.chat("hi", engine=ollama_eng)
    assert captured["fn"] == "ollama"
    assert captured["model"] == "qwen3:8b"
    assert captured["base_url"] == "http://localhost:11434"
