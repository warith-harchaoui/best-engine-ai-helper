"""
Tests for best_engine_ai_helper.llm.

Every backend call is mocked (requests.post or a fake LangChain class), so no
Ollama or OpenAI server is needed. Covers the three backends' payload shapes,
JSON-mode parsing and its fallback, error translation, embeddings, and the
Ollama schema shaper that flattens discriminated unions.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from best_engine_ai_helper import llm as _llm


def _resp(json_value: dict[str, Any]) -> MagicMock:
    r = MagicMock()
    r.json.return_value = json_value
    r.raise_for_status.return_value = None
    return r


def test_chat_ollama_builds_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
    monkeypatch.setenv("SPREZZATURE_LLM_TEXT", "qwen3:8b")
    monkeypatch.setenv("SPREZZATURE_LLM_VISION", "qwen3-vl:72b")

    with patch("requests.post", return_value=_resp({"response": "hello"})) as post:
        assert _llm.chat("say hello", system="be brief") == "hello"
    url, payload = post.call_args[0][0], post.call_args[1]["json"]
    assert "/api/generate" in url
    assert payload["model"] == "qwen3:8b" and payload["prompt"] == "say hello"
    assert payload["stream"] is False and payload["system"] == "be brief"

    # Images with no explicit model select the vision model; json_schema is
    # passed through as Ollama's grammar-constrained `format`.
    schema = {"type": "object", "properties": {"k": {"type": "integer"}}}
    with patch("requests.post", return_value=_resp({"response": '{"k": 1}'})) as post2:
        assert _llm.chat("describe", images=[b"\x89PNG"], json_schema=schema) == {"k": 1}
    p2 = post2.call_args[1]["json"]
    assert p2["model"] == "qwen3-vl:72b" and p2["format"] == schema


def test_chat_openai_builds_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")
    resp = _resp({"choices": [{"message": {"content": "hi"}}]})

    with patch("requests.post", return_value=resp) as post:
        assert _llm.chat("hi there") == "hi"
    assert "/v1/chat/completions" in post.call_args[0][0]

    # Images become data-URI content parts; json_schema becomes a structured
    # response_format.
    with patch("requests.post", return_value=resp) as post2:
        _llm.chat("describe", images=[b"\x89PNG"], json_schema={"type": "object"})
    payload = post2.call_args[1]["json"]
    user = next(m for m in payload["messages"] if m["role"] == "user")
    part = next(p for p in user["content"] if p.get("type") == "image_url")
    assert part["image_url"]["url"].startswith("data:image/png;base64,")
    assert payload["response_format"]["type"] == "json_schema"


def test_chat_langchain_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "langchain")
    monkeypatch.delenv("SPREZZATURE_LLM_BASE_URL", raising=False)  # default -> :11434 -> ChatOllama

    class _FakeLLM:
        def __init__(self, **kw: Any) -> None: ...
        def invoke(self, msgs: Any) -> Any:
            return type("Msg", (), {"content": "hi from langchain"})()

    # langchain_ollama is an optional extra not installed here; inject a stub so
    # the default-URL branch is covered without depending on the real package
    # (mirrors the langchain_openai stub below).
    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = _FakeLLM  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)
    assert _llm.chat("hello", system="sys") == "hi from langchain"


def test_chat_langchain_openai_branch_and_image_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "langchain")
    monkeypatch.setenv("SPREZZATURE_LLM_BASE_URL", "http://remote-host:9000")  # -> ChatOpenAI

    class _FakeOpenAI:
        def __init__(self, **kw: Any) -> None: ...
        def invoke(self, msgs: Any) -> Any:
            return type("Msg", (), {"content": '{"ok": true}'})()

    # langchain_openai is an optional extra not installed here; inject a stub so
    # the OpenAI-URL branch is covered without depending on the real package.
    fake_module = types.ModuleType("langchain_openai")
    fake_module.ChatOpenAI = _FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    # json_schema on langchain is a portable system-prompt hint; the JSON parses.
    assert _llm.chat("q", json_schema={"type": "object"}) == {"ok": True}
    # Images aren't uniform across langchain backends -> a clear RuntimeError.
    with pytest.raises(RuntimeError, match="Images"):
        _llm.chat("q", images=[b"\x89PNG"])


def test_chat_openai_auth_and_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")
    monkeypatch.setenv("SPREZZATURE_LLM_API_KEY", "secret")  # -> Authorization header
    captured: dict[str, Any] = {}

    def _capture(*a: Any, **k: Any) -> MagicMock:
        captured.update(k)
        return _resp({"choices": []})  # malformed: no message -> RuntimeError

    with patch("requests.post", _capture):
        with pytest.raises(RuntimeError):
            _llm.chat("x")
    assert captured["headers"]["Authorization"] == "Bearer secret"
    # A transport failure is also translated to RuntimeError.
    with patch("requests.post", side_effect=requests.Timeout("slow")):
        with pytest.raises(RuntimeError):
            _llm.chat("x")


def test_chat_json_fallback_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
    # JSON mode but the model returns non-JSON -> raw string, not a crash.
    with patch("requests.post", return_value=_resp({"response": "not json"})):
        assert _llm.chat("x", json_schema={"type": "object"}) == "not json"
    # A transport failure is translated to RuntimeError.
    with patch("requests.post", side_effect=requests.ConnectionError("no server")):
        with pytest.raises(RuntimeError):
            _llm.chat("x")
    # An unknown backend is a configuration error.
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "bogus")
    with pytest.raises(ValueError, match="Unknown"):
        _llm.chat("x")


def test_embed_ollama_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
    with patch("requests.post", return_value=_resp({"embedding": [0.1, 0.2]})):
        assert _llm.embed("hi") == [0.1, 0.2]
    # Missing field is a RuntimeError.
    with patch("requests.post", return_value=_resp({})):
        with pytest.raises(RuntimeError):
            _llm.embed("hi")
    # Other backends aren't supported for embeddings.
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")
    with pytest.raises(NotImplementedError):
        _llm.embed("hi")


def test_shape_schema_for_ollama() -> None:
    # A discriminated union of $ref branches is inlined and flattened into one
    # tagged object (Ollama's grammar can't build a oneOf of refs).
    schema = {
        "$defs": {
            "SetTitle": {"type": "object", "properties": {
                "op": {"const": "set_title"}, "title": {"type": "string"}},
                "required": ["op", "title"]},
            "SortRows": {"type": "object", "properties": {
                "op": {"const": "sort_rows"}, "ascending": {"type": "boolean"}},
                "required": ["op", "ascending"]},
        },
        "type": "object",
        "properties": {"ops": {"type": "array", "items": {
            "oneOf": [{"$ref": "#/$defs/SetTitle"}, {"$ref": "#/$defs/SortRows"}],
            "discriminator": {"propertyName": "op"}}}},
        "required": ["ops"],
    }
    items = _llm._shape_schema_for_ollama(schema)["properties"]["ops"]["items"]
    assert "$defs" not in _llm._shape_schema_for_ollama(schema)
    assert set(items["properties"]) == {"op", "title", "ascending"}
    assert set(items["properties"]["op"]["enum"]) == {"set_title", "sort_rows"}
    assert "op" in items["required"] and "discriminator" not in items

    # A plain schema is essentially unchanged; a nullable union keeps its
    # concrete branch rather than being flattened away.
    plain = _llm._shape_schema_for_ollama(
        {"type": "object", "properties": {"goal": {"type": "string", "enum": ["a", "b"]}},
         "required": ["goal"]})
    assert plain["properties"]["goal"]["enum"] == ["a", "b"] and plain["required"] == ["goal"]
    nullable = _llm._shape_schema_for_ollama(
        {"type": "object",
         "properties": {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}}})
    assert nullable["properties"]["note"]["type"] == "string"
