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


def test_observers_receive_success_and_failure_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
    events: list[dict[str, Any]] = []
    _llm.add_observer(events.append)
    try:
        with patch("requests.post", return_value=_resp({"response": "hi"})):
            _llm.chat("say hi", model="qwen3:8b")
        assert len(events) == 1
        ok_event = events[0]
        assert ok_event["ok"] is True and ok_event["error"] is None
        assert ok_event["backend"] == "ollama" and ok_event["model"] == "qwen3:8b"
        assert ok_event["kind"] == "llm" and ok_event["in_chars"] == len("say hi")
        assert ok_event["out_chars"] == len("hi") and ok_event["latency_ms"] >= 0

        with patch("requests.post", side_effect=requests.ConnectionError("down")):
            with pytest.raises(RuntimeError):
                _llm.chat("x", images=[b"png"])
        assert len(events) == 2
        fail_event = events[1]
        assert fail_event["ok"] is False and "down" in fail_event["error"]
        assert fail_event["kind"] == "vlm" and fail_event["out_chars"] == 0

        # A raising observer must not break the caller.
        _llm.add_observer(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        with patch("requests.post", return_value=_resp({"response": "ok"})):
            assert _llm.chat("y") == "ok"
    finally:
        _llm.clear_observers()


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
            "SetTitle": {
                "type": "object",
                "properties": {"op": {"const": "set_title"}, "title": {"type": "string"}},
                "required": ["op", "title"],
            },
            "SortRows": {
                "type": "object",
                "properties": {"op": {"const": "sort_rows"}, "ascending": {"type": "boolean"}},
                "required": ["op", "ascending"],
            },
        },
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "oneOf": [{"$ref": "#/$defs/SetTitle"}, {"$ref": "#/$defs/SortRows"}],
                    "discriminator": {"propertyName": "op"},
                },
            }
        },
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
        {
            "type": "object",
            "properties": {"goal": {"type": "string", "enum": ["a", "b"]}},
            "required": ["goal"],
        }
    )
    assert plain["properties"]["goal"]["enum"] == ["a", "b"] and plain["required"] == ["goal"]
    nullable = _llm._shape_schema_for_ollama(
        {
            "type": "object",
            "properties": {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        }
    )
    assert nullable["properties"]["note"]["type"] == "string"


# ---------------------------------------------------------------------------
# Cloud transports: Anthropic, Gemini, Mistral (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_chat_anthropic_builds_payload_and_extracts_usage() -> None:
    resp = _resp({
        "content": [{"type": "text", "text": "bonjour"}],
        "usage": {"input_tokens": 12, "output_tokens": 3},
    })
    with patch("requests.post", return_value=resp) as post:
        text, usage = _llm._chat_anthropic(
            "salut", system="Be brief", images=None, json_schema=None,
            model="claude-3-5-sonnet-20241022", temperature=0.2,
            api_key="sk-ant-test",
        )
    assert text == "bonjour" and usage == {"in_tokens": 12, "out_tokens": 3}
    url, kw = post.call_args[0][0], post.call_args[1]
    assert url == "https://api.anthropic.com/v1/messages"
    assert kw["headers"]["x-api-key"] == "sk-ant-test"
    assert kw["headers"]["anthropic-version"]
    assert kw["json"]["system"] == "Be brief"
    assert kw["json"]["messages"][0]["content"] == "salut"


def test_chat_anthropic_with_images_and_malformed_response() -> None:
    resp = _resp({
        "content": [{"type": "text", "text": "described"}],
        "usage": {"input_tokens": 5, "output_tokens": 2},
    })
    with patch("requests.post", return_value=resp) as post:
        _llm._chat_anthropic(
            "describe", system=None, images=[b"\xff\xd8fakejpeg"], json_schema=None,
            model="claude-3-5-sonnet-20241022", temperature=0.2, api_key="k",
        )
    content = post.call_args[1]["json"]["messages"][0]["content"]
    assert content[0]["type"] == "text" and content[1]["source"]["media_type"] == "image/jpeg"

    with patch("requests.post", return_value=_resp({"content": []})):
        with pytest.raises(RuntimeError, match="Malformed Anthropic"):
            _llm._chat_anthropic(
                "x", system=None, images=None, json_schema=None,
                model="claude-3-5-sonnet-20241022", temperature=0.2, api_key="k",
            )


def test_chat_gemini_builds_payload_and_extracts_usage() -> None:
    resp = _resp({
        "candidates": [{"content": {"parts": [{"text": "hola"}]}}],
        "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 4},
    })
    schema = {"type": "object", "properties": {"k": {"type": "string"}}, "$defs": {}, "title": "X"}
    with patch("requests.post", return_value=resp) as post:
        text, usage = _llm._chat_gemini(
            "hi", system="persona", images=[b"png"], json_schema=schema,
            model="gemini-1.5-pro", temperature=0.2, api_key="g-key",
        )
    assert text == "hola" and usage == {"in_tokens": 7, "out_tokens": 4}
    url, kw = post.call_args[0][0], post.call_args[1]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
    assert kw["params"] == {"key": "g-key"}
    assert kw["json"]["systemInstruction"]["parts"][0]["text"] == "persona"
    parts = kw["json"]["contents"][0]["parts"]
    assert parts[0]["text"] == "hi" and "inlineData" in parts[1]
    # $defs/title are stripped from the schema Gemini receives.
    resp_schema = kw["json"]["generationConfig"]["responseSchema"]
    assert "$defs" not in resp_schema and "title" not in resp_schema


def test_chat_gemini_malformed_response_raises() -> None:
    with patch("requests.post", return_value=_resp({"candidates": []})):
        with pytest.raises(RuntimeError, match="Malformed Gemini"):
            _llm._chat_gemini(
                "x", system=None, images=None, json_schema=None,
                model="gemini-1.5-pro", temperature=0.2, api_key="k",
            )


def test_mistral_routes_through_openai_compatible_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mistral speaks the OpenAI Chat Completions wire format, so it never needs
    # its own transport function — only membership in _OPENAI_COMPATIBLE.
    assert "mistral" in _llm._OPENAI_COMPATIBLE
    resp = _resp({
        "choices": [{"message": {"content": "bonjour"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    })
    eng = {
        "backend": "mistral", "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "llm": {"model": "mistral-large-latest", "cloud": True},
    }
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-secret")
    with patch("requests.post", return_value=resp) as post:
        out = _llm.chat("salut", engine=eng, kind="llm")
    assert out == "bonjour"
    url, kw = post.call_args[0][0], post.call_args[1]
    assert url == "https://api.mistral.ai/v1/chat/completions"
    assert kw["headers"]["Authorization"] == "Bearer mistral-secret"
    assert kw["json"]["model"] == "mistral-large-latest"


# ---------------------------------------------------------------------------
# Cloud API key resolution
# ---------------------------------------------------------------------------


def test_cloud_api_key_env_var_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY_ENV", "from-env")
    assert _llm._cloud_api_key({"api_key_env": "MY_KEY_ENV"}) == "from-env"


def test_cloud_api_key_falls_back_to_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    monkeypatch.delenv("MY_KEY_ENV", raising=False)
    fake_keyring = ModuleType("keyring")
    fake_keyring.get_password = lambda service, key: "from-keyring"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    assert _llm._cloud_api_key({"api_key_env": "MY_KEY_ENV"}) == "from-keyring"


def test_cloud_api_key_empty_when_nothing_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.delenv("MY_KEY_ENV", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)  # simulate not installed
    assert _llm._cloud_api_key({"api_key_env": "MY_KEY_ENV"}) == ""
    assert _llm._cloud_api_key(None) == ""
    assert _llm._cloud_api_key({}) == ""


# ---------------------------------------------------------------------------
# Retry and cache
# ---------------------------------------------------------------------------


def test_chat_retries_without_tenacity_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def _flaky(*a: Any, **kw: Any) -> MagicMock:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise requests.ConnectionError("flaky")
        return _resp({"response": "ok"})

    monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
    with patch("requests.post", side_effect=_flaky):
        out = _llm.chat("hi", model="qwen3:8b", retries=3)
    assert out == "ok" and attempts["n"] == 3


def test_chat_cache_uses_wallet_helper_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    calls = {"n": 0}

    class _FakeWallet:
        def call(self, key: str, payload: dict, fn: Any) -> tuple[Any, bool]:
            calls["n"] += 1
            return fn(), False  # never actually cached in this fake

    fake_wallet_helper = ModuleType("wallet_helper")
    fake_wallet_helper.default_wallet = lambda: _FakeWallet()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "wallet_helper", fake_wallet_helper)

    eng = {"backend": "ollama", "base_url": "http://localhost:11434", "llm": {"model": "qwen3:8b"}}
    with patch("requests.post", return_value=_resp({"response": "cached-path"})):
        out = _llm.chat("hi", engine=eng, kind="llm", cache=True)
    assert out == "cached-path" and calls["n"] == 1


def test_chat_cache_warns_and_runs_uncached_without_wallet_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "wallet_helper", None)  # simulate not installed
    eng = {"backend": "ollama", "base_url": "http://localhost:11434", "llm": {"model": "qwen3:8b"}}
    with patch("requests.post", return_value=_resp({"response": "uncached"})):
        out = _llm.chat("hi", engine=eng, kind="llm", cache=True)
    assert out == "uncached"


# ---------------------------------------------------------------------------
# Privacy (pseudonymization) and safety wiring
# ---------------------------------------------------------------------------


def test_chat_pseudonymizes_cloud_prompt_and_restores_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from best_engine_ai_helper import privacy

    def _fake_pseudonymize(text: str, engine: Any, **kw: Any) -> tuple[str, dict[str, str]]:
        return text.replace("Marie", "Claudine"), {"Claudine": "Marie"}

    monkeypatch.setattr(privacy, "pseudonymize", _fake_pseudonymize)
    monkeypatch.setattr(privacy, "restore", lambda text, mapping: text.replace("Claudine", "Marie"))

    captured: dict[str, Any] = {}

    def _fake_openai(prompt: str, **kw: Any) -> tuple[str, dict[str, Any]]:
        captured["prompt"] = prompt
        return "Bonjour Claudine", {"in_tokens": None, "out_tokens": None}

    monkeypatch.setattr(_llm, "_chat_openai", _fake_openai)
    eng = {
        "backend": "openai", "base_url": "https://api.openai.com/v1",
        "llm": {"model": "gpt-4o", "cloud": True},
        "fallback": {"backend": "ollama", "base_url": "http://localhost:11434",
                     "llm": {"model": "qwen3:8b"}},
    }
    out = _llm.chat("Bonjour Marie", engine=eng, kind="llm", pseudonymize=True, safety=False)
    assert captured["prompt"] == "Bonjour Claudine"  # the CLOUD call saw the scrubbed prompt
    assert out == "Bonjour Marie"  # the caller sees the restored response


def test_chat_pseudonymize_warns_without_a_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_llm, "_chat_openai", lambda prompt, **kw: (prompt, {}))
    eng = {"backend": "openai", "base_url": "https://api.openai.com/v1",
           "llm": {"model": "gpt-4o", "cloud": True}}  # no "fallback" key
    out = _llm.chat("hi", engine=eng, kind="llm", pseudonymize=True, safety=False)
    assert out == "hi"  # sent unscrubbed, no crash


def test_chat_safety_defaults_on_for_cloud_off_for_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from best_engine_ai_helper import safety

    calls: list[str] = []

    def _fake_check_text(text: str, *, direction: str, **kw: Any) -> dict[str, Any]:
        calls.append(direction)
        return {"text": text}

    monkeypatch.setattr(safety, "check_text", _fake_check_text)
    monkeypatch.setattr(_llm, "_chat_openai", lambda prompt, **kw: ("ok", {}))
    cloud_eng = {"backend": "openai", "base_url": "https://api.openai.com/v1",
                 "llm": {"model": "gpt-4o", "cloud": True}}
    _llm.chat("hi", engine=cloud_eng, kind="llm")
    assert calls == ["outbound", "inbound"]  # scanned both ways, no explicit safety= needed

    calls.clear()
    monkeypatch.setattr(_llm, "_chat_ollama", lambda prompt, **kw: ("ok", {}))
    local_eng = {
        "backend": "ollama", "base_url": "http://localhost:11434",
        "llm": {"model": "qwen3:8b"},
    }
    _llm.chat("hi", engine=local_eng, kind="llm")
    assert calls == []  # local engine: safety scanning stays off by default


def test_chat_safety_block_propagates_as_safetyviolation(monkeypatch: pytest.MonkeyPatch) -> None:
    from best_engine_ai_helper import safety

    def _blocking_check(text: str, *, direction: str, **kw: Any) -> dict[str, Any]:
        raise safety.SafetyViolation(direction, "text", 0.99, "toxicity")

    monkeypatch.setattr(safety, "check_text", _blocking_check)
    monkeypatch.setattr(_llm, "_chat_ollama", lambda prompt, **kw: ("ok", {}))
    eng = {"backend": "ollama", "base_url": "http://localhost:11434", "llm": {"model": "qwen3:8b"}}
    with pytest.raises(safety.SafetyViolation):
        _llm.chat("hi", engine=eng, kind="llm", safety=True)
