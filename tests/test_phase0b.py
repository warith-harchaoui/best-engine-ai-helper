"""
Tests for best_engine_ai_helper Phase 0b modules.

All tests are unit tests that mock the Ollama/OpenAI endpoints using
pytest-monkeypatch or unittest.mock.patch. No live Ollama process is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from best_engine_ai_helper import llm as _llm
from best_engine_ai_helper import pull as _pull
from best_engine_ai_helper import ralph as _ralph

# ---------------------------------------------------------------------------
# llm.py — chat() mock tests
# ---------------------------------------------------------------------------

class TestChatOllamaMock:
    """Verify that chat() sends the right URL and payload to Ollama."""

    def test_chat_ollama_url_and_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """chat() must POST to /api/generate with the correct model tag."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
        monkeypatch.setenv("SPREZZATURE_LLM_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("SPREZZATURE_LLM_TEXT", "qwen3-vl:8b")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "hello"}
        mock_resp.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _llm.chat("say hello")

        # The URL must point at /api/generate on the configured base
        call_kwargs = mock_post.call_args
        assert "/api/generate" in call_kwargs[0][0]

        # The payload must include the correct model and prompt
        payload = call_kwargs[1]["json"]
        assert payload["model"] == "qwen3-vl:8b"
        assert payload["prompt"] == "say hello"
        assert payload["stream"] is False
        assert result == "hello"

    def test_chat_ollama_json_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """json_schema must be passed through as Ollama's ``format`` (the schema
        itself, for structured outputs) -- not the old free-JSON ``"json"``."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": '{"key": 1}'}
        mock_resp.raise_for_status.return_value = None

        schema = {"type": "object", "properties": {"key": {"type": "integer"}}}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _llm.chat("return json", json_schema=schema)

        payload = mock_post.call_args[1]["json"]
        assert payload.get("format") == schema
        # When json_schema is set, the string result should be parsed into a dict
        assert isinstance(result, dict)
        assert result["key"] == 1

    def test_chat_ollama_vision_model_selected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When images are provided and model is None, the vision model is used."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")
        monkeypatch.setenv("SPREZZATURE_LLM_VISION", "qwen3-vl:72b")
        monkeypatch.setenv("SPREZZATURE_LLM_TEXT", "qwen3:8b")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "image desc"}
        mock_resp.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_resp) as mock_post:
            _llm.chat("describe this", images=[b"\x89PNG\r\n"])

        payload = mock_post.call_args[1]["json"]
        # Images present, no explicit model => vision model
        assert payload["model"] == "qwen3-vl:72b"

    def test_chat_ollama_system_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """System prompt must appear in the payload when provided."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "ollama")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "ok"}
        mock_resp.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_resp) as mock_post:
            _llm.chat("hello", system="You are a test assistant.")

        payload = mock_post.call_args[1]["json"]
        assert payload.get("system") == "You are a test assistant."


class TestChatOpenAIMock:
    """Verify chat() builds the correct OpenAI-compat payload."""

    def test_chat_openai_url_and_messages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """chat() must POST to /v1/chat/completions with messages array."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")
        monkeypatch.setenv("SPREZZATURE_LLM_BASE_URL", "http://localhost:8000")
        monkeypatch.setenv("SPREZZATURE_LLM_TEXT", "qwen3-vl:8b")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hi"}}]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _llm.chat("hi there")

        url = mock_post.call_args[0][0]
        assert "/v1/chat/completions" in url

        payload = mock_post.call_args[1]["json"]
        assert any(m["role"] == "user" for m in payload["messages"])
        assert result == "hi"

    def test_chat_openai_image_as_data_uri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Images must be sent as data URI content parts in the user message."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "a red square"}}]
        }
        mock_resp.raise_for_status.return_value = None

        # Minimal 1-byte fake PNG
        fake_png = b"\x89PNG"
        with patch("requests.post", return_value=mock_resp) as mock_post:
            _llm.chat("describe", images=[fake_png])

        messages = mock_post.call_args[1]["json"]["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        # Content must be a list for multi-modal messages
        assert isinstance(user_msg["content"], list)
        image_part = next(p for p in user_msg["content"] if p.get("type") == "image_url")
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")

    def test_chat_openai_json_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """json_schema triggers a structured response_format: json_schema, with
        the schema carried in the payload (not the old bare json_object)."""
        monkeypatch.setenv("SPREZZATURE_LLM_BACKEND", "openai")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"x": 1}'}}]
        }
        mock_resp.raise_for_status.return_value = None

        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _llm.chat("give json", json_schema=schema)

        response_format = mock_post.call_args[1]["json"].get("response_format", {})
        assert response_format.get("type") == "json_schema"
        assert response_format["json_schema"]["schema"] == schema
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# ralph.py — generic loop tests
# ---------------------------------------------------------------------------

class TestRalphLoopConverges:
    """The generic loop must stop as soon as the verdict says ship."""

    def test_converges_on_second_iter(self) -> None:
        """Loop stops when verdict['ship'] becomes True on iteration 1."""
        call_count = {"n": 0}

        def render(s: str) -> str:
            return s + "_rendered"

        def inspect(a: str) -> str:
            return "minor issue"

        def apply_fix(s: str, c: str) -> str:
            # Returns a new source so the loop does not detect a no-op
            return s + "_fixed"

        def verdict(c: str) -> dict[str, Any]:
            call_count["n"] += 1
            # Ship on the second call (after one fix)
            return {"ship": call_count["n"] >= 2, "blocking": [], "score": 0.9}

        src, history = _ralph.ralph_loop(
            "source",
            render=render,
            inspect=inspect,
            apply_fix=apply_fix,
            verdict=verdict,
        )
        # Two iterations: one to produce the critique, one after the fix
        assert len(history) == 2
        assert history[-1][2]["ship"] is True
        assert src == "source_fixed"

    def test_respects_max_iters(self) -> None:
        """Loop must not run more than max_iters iterations."""
        src, history = _ralph.ralph_loop(
            "x",
            render=lambda s: s,
            inspect=lambda a: "always broken",
            apply_fix=lambda s, c: s + "+",  # always a new source
            verdict=lambda c: {"ship": False, "blocking": ["broken"], "score": 0},
            max_iters=3,
        )
        assert len(history) == 3


class TestRalphLoopNoOp:
    """Loop must stop when apply_fix returns the same source (no-op guard)."""

    def test_stops_on_noop_fix(self) -> None:
        """If apply_fix is a no-op, the loop exits after the first iteration."""
        src, history = _ralph.ralph_loop(
            "same",
            render=lambda s: s,
            inspect=lambda a: "problem found",
            apply_fix=lambda s, c: s,   # no-op: source never changes
            verdict=lambda c: {"ship": False, "blocking": ["x"], "score": 0},
            max_iters=6,
        )
        # The loop should exit after one iteration because the fix is a no-op
        assert len(history) == 1
        assert src == "same"

    def test_on_iteration_callback_called(self) -> None:
        """on_iteration callback must be called once per iteration."""
        calls: list[int] = []

        def on_iter(i: int, *args: Any) -> None:
            calls.append(i)

        _ralph.ralph_loop(
            "x",
            render=lambda s: s,
            inspect=lambda a: "ok",
            apply_fix=lambda s, c: s,   # no-op so loop stops after 1
            verdict=lambda c: {"ship": False},
            max_iters=4,
            on_iteration=on_iter,
        )
        assert calls == [0]


# ---------------------------------------------------------------------------
# pull.py — write_env
# ---------------------------------------------------------------------------

class TestWriteEnv:
    """write_env must create both env.sh and config.json in the target dir."""

    def test_env_sh_and_config_json_written(self, tmp_path: Path) -> None:
        """Both files must be created with the correct content."""
        env_path = _pull.write_env(
            "qwen3-vl:8b",
            "qwen3-vl:8b",
            "ollama",
            "http://localhost:11434",
            user_dir=tmp_path,
        )
        assert env_path.name == "env.sh"
        assert env_path.exists()

        sh_content = env_path.read_text()
        assert "BEST_LLM_TEXT=qwen3-vl:8b" in sh_content
        assert "BEST_LLM_BACKEND=ollama" in sh_content
        assert "do not edit by hand" in sh_content

        config_path = tmp_path / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["BEST_LLM_TEXT"] == "qwen3-vl:8b"
        assert config["BEST_LLM_BACKEND"] == "ollama"

    def test_directory_created_if_absent(self, tmp_path: Path) -> None:
        """write_env must create the target directory if it does not exist."""
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()
        _pull.write_env("m", "m", "ollama", "http://x", user_dir=nested)
        assert nested.exists()
        assert (nested / "env.sh").exists()


# ---------------------------------------------------------------------------
# ralph.py — prose_loop
# ---------------------------------------------------------------------------

class TestProseLoop:
    """prose_loop must iterate over paragraph pairs and apply fixes."""

    def test_noop_model_returns_original(self) -> None:
        """When the model reports no seam issues, output equals input."""
        def noop(p: str, **kw: Any) -> Any:
            if kw.get("json_schema"):
                return {"needs_fix": False, "reasons": []}
            return ""

        text = "Paragraph one.\n\nParagraph two."
        result = _ralph.prose_loop(text, charter="No dashes.", llm_chat=noop)
        assert result == text

    def test_single_paragraph_unchanged(self) -> None:
        """A single-paragraph text has no seam to check and is returned as-is."""
        def noop(p: str, **kw: Any) -> Any:
            return {"needs_fix": False, "reasons": []}

        text = "Only one paragraph here."
        result = _ralph.prose_loop(text, charter="charter", llm_chat=noop)
        assert result == text

    def test_fix_applied_to_seam(self) -> None:
        """When the model reports a seam issue, the fix must be applied."""
        # Track which paragraphs the model sees and return a fix on first call
        calls: list[str] = []

        def model(p: str, **kw: Any) -> Any:
            calls.append(p)
            schema = kw.get("json_schema")
            if schema:
                # First call: seam check; second call: fix
                if "needs_fix" in p or len(calls) <= 2:
                    return {"needs_fix": True, "reasons": ["bolted-on-transition"]}
                return {"a": "Fixed para one.", "b": "Fixed para two."}
            return ""

        # Provide a chat function that responds correctly to seam and fix calls
        seam_count = {"n": 0}

        def smart_model(p: str, **kw: Any) -> Any:
            seam_count["n"] += 1
            schema = kw.get("json_schema")
            if not schema:
                return ""
            system = kw.get("system", "")
            if "needs_fix" in system or "seam" in system.lower():
                return {"needs_fix": True, "reasons": ["bolted-on-transition"]}
            return {"a": "Revised A.", "b": "Revised B."}

        text = "Para one.\n\nPara two."
        result = _ralph.prose_loop(text, charter="No machine tics.", llm_chat=smart_model)
        # The text must have been modified by the fix
        assert result != text


# ---------------------------------------------------------------------------
# llm.py — _shape_schema_for_ollama (discriminated-union flattening)
# ---------------------------------------------------------------------------

class TestShapeSchemaForOllama:
    """Ollama's structured-output grammar cannot build a oneOf/anyOf of $ref
    branches (it then emits only empty values); the shaper inlines refs and
    flattens such unions into one tagged object so the grammar can produce a
    real value, which the caller's Pydantic re-validates against the true union.
    """

    def test_inlines_refs_and_flattens_discriminated_union(self) -> None:
        schema = {
            "$defs": {
                "SetTitle": {
                    "type": "object",
                    "properties": {
                        "op": {"const": "set_title"},
                        "title": {"type": "string"},
                    },
                    "required": ["op", "title"],
                },
                "SortRows": {
                    "type": "object",
                    "properties": {
                        "op": {"const": "sort_rows"},
                        "ascending": {"type": "boolean"},
                    },
                    "required": ["op", "ascending"],
                },
            },
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"$ref": "#/$defs/SetTitle"},
                            {"$ref": "#/$defs/SortRows"},
                        ],
                        "discriminator": {"propertyName": "op"},
                    },
                }
            },
            "required": ["ops"],
        }
        shaped = _llm._shape_schema_for_ollama(schema)

        assert "$defs" not in shaped
        items = shaped["properties"]["ops"]["items"]
        assert items["type"] == "object"
        # Both branches' fields are present, all optional except the tag...
        assert set(items["properties"]) == {"op", "title", "ascending"}
        # ...the discriminator became an enum of every branch's tag...
        assert set(items["properties"]["op"]["enum"]) == {"set_title", "sort_rows"}
        # ...and the tag is forced required so the model can't omit it.
        assert "op" in items["required"]
        assert "discriminator" not in items

    def test_leaves_plain_schema_essentially_unchanged(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "enum": ["a", "b"]},
                "n": {"type": "integer"},
            },
            "required": ["goal"],
        }
        shaped = _llm._shape_schema_for_ollama(schema)
        assert shaped["properties"]["goal"]["enum"] == ["a", "b"]
        assert shaped["required"] == ["goal"]

    def test_nullable_union_keeps_the_concrete_branch(self) -> None:
        # str | None schemas (anyOf: [string, null]) must not be flattened away
        # to nothing -- keep the concrete branch so the field stays usable.
        schema = {
            "type": "object",
            "properties": {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        }
        shaped = _llm._shape_schema_for_ollama(schema)
        assert shaped["properties"]["note"]["type"] == "string"
