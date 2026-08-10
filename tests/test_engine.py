"""
Tests for best_engine_ai_helper.engine — the brief -> engine resolution flow.

Synthetic catalog + injected hardware, so nothing depends on the real machine,
Ollama, or the network. Covers the backend rule, the headroom clamp, the
Ollama-tag vs vLLM-HuggingFace-id split, mode: cloud, the file round-trip, and
the ``ensure`` missing-file policy.
"""

from __future__ import annotations

import pytest

import best_engine_ai_helper.detect as detect
from best_engine_ai_helper import engine, llm

# Two structured-capable models with both an Ollama tag and a vLLM HF id.
_CATALOG = [
    {
        "id": "small-llm",
        "kind": "llm",
        "size_b": 3,
        "ram_gb": 2.5,
        "benchmarks": {"general": 70},
        "structured_output": True,
        "vllm_id": "org/Small-LLM",
    },
    {
        "id": "mid-vlm",
        "kind": "vlm",
        "size_b": 8,
        "ram_gb": 6.0,
        "benchmarks": {"general": 74, "vision": 80},
        "structured_output": True,
        "vllm_id": "org/Mid-VLM",
    },
]
# Unified 64 GB -> budget 64 * 0.75 * 0.5 = 24 GB; both models fit on either
# backend. No bandwidth, so throughput is not estimated and the comfort gate
# cannot fire — memory fit alone decides, keeping the picks deterministic.
_HW = {"unified_gb": 64.0, "vram_gb": None, "ram_gb": 64.0}
_COMPUTE = {"accelerator": "gpu-metal", "chip": "Apple M2", "bandwidth_gbs": None}

_BRIEF = {
    "kind": "both",
    "headroom": 0.9,
    "min_tps": 15,
    "task": "summarize a transcript and read a chart image",
}


def test_resolve_local_mode_backend_and_headroom(monkeypatch: pytest.MonkeyPatch) -> None:
    # vLLM only on a real discrete GPU; Ollama for Apple, Intel iGPU, and CPU.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    assert engine.default_backend() == "vllm"
    monkeypatch.setattr(detect, "chip_vendor", lambda: "amd")
    assert engine.default_backend() == "vllm"
    for cpu_like in ("apple", "intel", "cpu"):
        monkeypatch.setattr(detect, "chip_vendor", lambda v=cpu_like: v)
        assert engine.default_backend() == "ollama"

    ollama_eng = engine.resolve(
        _BRIEF, backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    assert ollama_eng["backend"] == "ollama"
    assert ollama_eng["base_url"] == "http://localhost:11434"
    # Brief asked for 0.9 headroom; the resolver clamps it to the 0.5 ceiling.
    assert ollama_eng["headroom"] == 0.5
    # Ollama uses the pull tag (not the HF id). mid-vlm (general 74) is the
    # leanest model within 3 points of the best, so it wins the text slot too.
    assert ollama_eng["llm"]["model"] == "mid-vlm"
    assert ollama_eng["vlm"]["model"] == "mid-vlm"
    assert ollama_eng["serve"] == ["ollama pull mid-vlm"]
    assert ollama_eng["mode"] == "local"

    vllm_eng = engine.resolve(_BRIEF, backend="vllm", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    assert vllm_eng["backend"] == "vllm"
    assert vllm_eng["base_url"] == "http://localhost:8000/v1"
    # vLLM serves the HuggingFace id, not the Ollama tag.
    assert vllm_eng["llm"]["model"] == "org/Mid-VLM"
    assert vllm_eng["serve"] == ["vllm serve org/Mid-VLM --port 8000"]

    endpoint_eng = engine.resolve(
        _BRIEF,
        backend="vllm",
        endpoint="http://gpu-box:8001/v1",
        catalog=_CATALOG,
        hw=_HW,
        compute=_COMPUTE,
    )
    assert endpoint_eng["base_url"] == "http://gpu-box:8001/v1"
    assert endpoint_eng["serve"] == ["vllm serve org/Mid-VLM --port 8001"]


def test_engine_file_roundtrip_ensure_and_model_for(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eng = engine.resolve(_BRIEF, backend="ollama", catalog=_CATALOG, hw=_HW, compute=_COMPUTE)
    path = engine.write_engine(eng, tmp_path / engine.ENGINE_NAME)
    text = path.read_text()
    assert "do NOT commit" in text  # the gitignore reminder header is present
    loaded = engine.load_engine(path)
    assert loaded["backend"] == "ollama"
    assert loaded["llm"]["model"] == "mid-vlm"

    # An engine file already on disk is used as-is; resolve must NOT run.
    def _boom(*a: object, **k: object) -> None:
        raise AssertionError("resolve() must not be called when the engine exists")

    monkeypatch.setattr(engine, "resolve", _boom)
    got = engine.ensure(tmp_path)
    assert got["backend"] == "ollama"

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / engine.BRIEF_NAME).write_text("kind: llm\ntask: write copy\n")
    stub = {"backend": "ollama", "base_url": "x", "llm": {"model": "qwen3:8b"}}
    monkeypatch.setattr(engine, "resolve", lambda *a, **k: stub)
    resolved = engine.ensure(other_dir)
    assert resolved["llm"]["model"] == "qwen3:8b"
    assert (other_dir / engine.ENGINE_NAME).is_file()  # persisted for next time

    # No engine and no committed brief: a real bug, so fail loud (not a default).
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(RuntimeError, match="no brief"):
        engine.ensure(empty_dir)

    monkeypatch.undo()  # restore the real engine.resolve for model_for's own resolve call
    model_for_eng = engine.resolve(
        _BRIEF, backend="vllm", catalog=_CATALOG, hw=_HW, compute=_COMPUTE
    )
    backend, base_url, model = engine.model_for(model_for_eng, "llm")
    assert backend == "vllm" and base_url.endswith("/v1") and model == "org/Mid-VLM"
    with pytest.raises(KeyError):
        engine.model_for({"backend": "ollama", "base_url": "x"}, "vlm")


def test_resolve_cloud_mode() -> None:
    eng = engine.resolve(
        {
            "mode": "cloud",
            "provider": "mistral",
            "model": "mistral-large-latest",
            "kind": "llm",
            "task": "x",
        },
        catalog=_CATALOG,
        hw=_HW,
        compute=_COMPUTE,
    )
    assert eng["mode"] == "cloud" and eng["backend"] == "mistral"
    assert eng["base_url"] == "https://api.mistral.ai/v1"
    assert eng["llm"]["model"] == "mistral-large-latest" and eng["llm"]["cloud"] is True
    # A local fallback is resolved from the SAME brief (paid -> local direction).
    assert eng["fallback"] is not None and eng["fallback"]["backend"] in {"ollama", "vllm"}

    with pytest.raises(ValueError, match="model"):
        engine.resolve(
            {"mode": "cloud", "provider": "openai", "kind": "llm", "task": "x"},
            catalog=_CATALOG,
            hw=_HW,
            compute=_COMPUTE,
        )

    proxied = engine.resolve(
        {
            "mode": "cloud",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "base_url": "https://my-proxy.example.com",
            "api_key_env": "MY_ANTHROPIC_KEY",
            "kind": "llm",
            "task": "x",
        },
        catalog=_CATALOG,
        hw=_HW,
        compute=_COMPUTE,
    )
    assert proxied["base_url"] == "https://my-proxy.example.com"
    assert proxied["api_key_env"] == "MY_ANTHROPIC_KEY"


def test_chat_engine_routes_backend_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # chat(engine=...) must read backend/base_url/model from the descriptor and
    # map a vLLM backend to the OpenAI-compatible transport.
    captured: dict = {}

    def _fake_ollama(prompt, **kw):
        captured.clear()
        captured.update(kw)
        captured["fn"] = "ollama"
        return "ok", {"in_tokens": None, "out_tokens": None}

    def _fake_openai(prompt, **kw):
        captured.clear()
        captured.update(kw)
        captured["fn"] = "openai"
        return "ok", {"in_tokens": None, "out_tokens": None}

    monkeypatch.setattr(llm, "_chat_ollama", _fake_ollama)
    monkeypatch.setattr(llm, "_chat_openai", _fake_openai)

    vllm_eng = {
        "backend": "vllm",
        "base_url": "http://gpu:8000/v1",
        "llm": {"model": "org/Text"},
        "vlm": {"model": "org/Vision"},
    }
    llm.chat("hi", engine=vllm_eng, kind="llm")
    assert captured["fn"] == "openai"
    assert captured["model"] == "org/Text"
    assert captured["base_url"] == "http://gpu:8000/v1"

    ollama_eng = {
        "backend": "ollama",
        "base_url": "http://localhost:11434",
        "llm": {"model": "qwen3:8b"},
    }
    llm.chat("hi", engine=ollama_eng)
    assert captured["fn"] == "ollama"
    assert captured["model"] == "qwen3:8b"
    assert captured["base_url"] == "http://localhost:11434"
