"""
Tests for the OpenAI-compatible surface (``best_engine_ai_helper.openai_api``).

The contract under test is not "does it answer" but "does it answer in the
shape an OpenAI SDK parses" — ids, object strings, usage, the error envelope,
the SSE framing — because every one of those is a thing a client reads and a
thing that is silently wrong if nobody asserts it.

Inference itself is monkeypatched out: these tests are about the protocol
layer. The model-choosing underneath it is tested in test_recommend /
test_offload / test_imagine, and running a real model is what `validate` does.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from best_engine_ai_helper import llm, openai_api
from best_engine_ai_helper.api import app

PNG_DATA_URI = "data:image/png;base64," + base64.b64encode(b"not-a-real-png").decode()


@pytest.fixture()
def client() -> TestClient:
    openai_api.reset_engine_cache()
    return TestClient(app)


@pytest.fixture()
def canned_engine(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """An engine descriptor, so no test depends on this machine's hardware."""
    descriptor = {
        "backend": "ollama",
        "base_url": "http://localhost:11434",
        "llm": {"model": "qwen3:14b", "structured_output": True},
        "vlm": {"model": "gemma3:12b", "structured_output": True},
    }
    monkeypatch.setattr(openai_api, "_engine_for", lambda kind, task, mode="local": descriptor)
    return descriptor


@pytest.fixture()
def recorded_chat(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture every llm.chat call and answer with a fixed string."""
    calls: list[dict[str, Any]] = []

    def _chat(prompt: str, **kwargs: Any) -> str:
        calls.append({"prompt": prompt, **kwargs})
        return "a local answer"

    monkeypatch.setattr(llm, "chat", _chat)
    return calls


# ---------------------------------------------------------------------------
# The virtual model names, which are the actual product
# ---------------------------------------------------------------------------


def test_the_model_name_grammar_is_small_and_total() -> None:
    """Every name either resolves to a kind or passes through untouched.

    The grammar is the API: a caller types one string and it has to be
    obvious what they get. Nothing here may fall through to a guess.
    """
    assert openai_api.parse_model("best")["kind"] == "llm"
    # The same name means a vision model when the request carries an image,
    # which is why `best` is the name worth sending.
    assert openai_api.parse_model("best", has_images=True)["kind"] == "vlm"
    assert openai_api.parse_model("best-vlm")["kind"] == "vlm"
    assert openai_api.parse_model("best-embed")["kind"] == "embed"
    assert openai_api.parse_model("best-image")["kind"] == "image"
    assert openai_api.parse_model("best:write SQL")["task"] == "write SQL"

    # A concrete tag is a concrete tag: the colon belongs to the tag, not to a
    # task, or `qwen3:14b` would resolve to "best model for the task 14b".
    literal = openai_api.parse_model("qwen3:14b")
    assert literal["virtual"] is False
    assert literal["literal"] == "qwen3:14b"
    assert literal["task"] is None

    # An SDK always sends a model; a caller who does not care should not have
    # to invent one.
    assert openai_api.parse_model(None)["virtual"] is True
    assert openai_api.parse_model("")["virtual"] is True


def test_models_lists_the_aliases_and_only_what_fits(client: TestClient) -> None:
    """A client's model picker should not offer a 72B model to a laptop."""
    from best_engine_ai_helper import catalog, detect, score

    payload = client.get("/v1/models").json()
    assert payload["object"] == "list"
    ids = [row["id"] for row in payload["data"]]

    for alias in ("best", "best-llm", "best-vlm", "best-embed", "best-image"):
        assert alias in ids
    for row in payload["data"]:
        assert row["object"] == "model"
        assert row["created"] > 0

    # Every concrete entry offered has to fit this machine's budget — the
    # filter is the point of the endpoint, not decoration.
    budget = score.effective_budget(detect.available_memory())
    by_id = {str(e.get("id")): e for e in catalog.load_catalog()}
    for ident in ids:
        entry = by_id.get(ident)
        if entry is None or entry.get("kind") == "image":
            continue
        assert score.model_footprint_gb(entry) <= budget, ident


# ---------------------------------------------------------------------------
# Chat completions
# ---------------------------------------------------------------------------


def test_a_chat_completion_comes_back_in_the_shape_an_sdk_parses(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """Every field here is one a client reads; a missing one is a crash there."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["created"] > 0
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "a local answer"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert set(body["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}
    # No backend reported counts here, so the fingerprint says the usage is an
    # estimate instead of letting it pass for measured.
    assert body["system_fingerprint"] == openai_api.FINGERPRINT_ESTIMATED

    # And the request reached llm.chat with the engine this machine resolved,
    # rather than a hardcoded model name.
    assert recorded_chat[0]["engine"] is canned_engine
    assert recorded_chat[0]["prompt"] == "hello"


def test_a_multi_turn_conversation_is_sent_as_a_transcript(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """Keeping only the last message is the classic way to lose the context.

    `llm.chat` takes one prompt, so a conversation has to be rendered into it.
    Rendered as a labelled transcript it survives; truncated to the last turn
    it does not, and the caller cannot tell.
    """
    client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "what is 2+2"},
                {"role": "assistant", "content": "4"},
                {"role": "user", "content": "and times 3?"},
            ],
        },
    )
    call = recorded_chat[0]
    assert call["system"] == "Be brief."
    assert call["prompt"] == "user: what is 2+2\nassistant: 4\nuser: and times 3?"


def test_an_image_part_switches_the_request_to_a_vision_model(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """The one piece of routing a caller should never have to think about."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is in this?"},
                        {"type": "image_url", "image_url": {"url": PNG_DATA_URI}},
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    call = recorded_chat[0]
    assert call["kind"] == "vlm"
    assert call["images"] == [b"not-a-real-png"]
    assert call["prompt"] == "what is in this?"


def test_asking_a_text_alias_to_look_at_an_image_is_refused(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """Answering a vision question from the text alone is the silent failure."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "best-llm",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is in this?"},
                        {"type": "image_url", "image_url": {"url": PNG_DATA_URI}},
                    ],
                }
            ],
        },
    )
    assert response.status_code == 400
    assert "best-vlm" in response.json()["error"]["message"]
    assert recorded_chat == []


def test_response_format_becomes_a_real_schema_constraint(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """Ollama enforces a JSON schema natively, so this is not a prompt trick."""
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_schema", "json_schema": {"schema": schema}},
        },
    )
    assert recorded_chat[0]["json_schema"] == schema

    # `json_object` has no schema of its own; the loosest honest translation is
    # "an object", which is exactly what it promises.
    recorded_chat.clear()
    client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object"},
        },
    )
    assert recorded_chat[0]["json_schema"] == {"type": "object"}


def test_a_structured_answer_is_serialised_rather_than_stringified(
    client: TestClient, canned_engine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`llm.chat` returns a dict under a schema; the wire carries JSON text."""
    monkeypatch.setattr(llm, "chat", lambda prompt, **kw: {"answer": "oui"})
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object"},
        },
    )
    content = response.json()["choices"][0]["message"]["content"]
    assert json.loads(content) == {"answer": "oui"}


def test_reported_token_counts_are_preferred_over_estimates(
    client: TestClient, canned_engine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama reports real counts; passing an estimate off as one is the lie."""

    def _chat_with_usage(prompt: str, **kwargs: Any) -> str:
        # The observer channel is how `llm` publishes what the backend said.
        llm._emit({"model": "qwen3:14b", "in_tokens": 7, "out_tokens": 13})
        return "ok"

    monkeypatch.setattr(llm, "chat", _chat_with_usage)
    body = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hello"}]},
    ).json()

    assert body["usage"] == {"prompt_tokens": 7, "completion_tokens": 13, "total_tokens": 20}
    assert body["system_fingerprint"] == openai_api.FINGERPRINT_MEASURED
    assert body["model"] == "qwen3:14b"


def test_streaming_is_server_sent_events_in_openais_framing(
    client: TestClient, canned_engine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An SDK parses `data:` lines and stops at [DONE]; both have to be there."""
    monkeypatch.setattr(llm, "chat_stream", lambda prompt, **kw: iter(["a ", "local ", "answer"]))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in response.iter_lines() if line.startswith("data: ")]

    payloads = [line[len("data: ") :] for line in lines]
    assert payloads[-1] == "[DONE]"
    chunks = [json.loads(p) for p in payloads[:-1]]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    # The first chunk opens the message, the last closes it, the middle carries
    # the text — which must arrive in pieces, or it is not streaming.
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == "a local answer"


def test_streaming_degrades_honestly_when_the_transport_cannot_stream(
    client: TestClient, canned_engine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema has no streaming path, so it arrives whole rather than faked.

    Emitting a word-by-word drip over an already-complete answer would look
    like streaming and tell the caller nothing true about progress.
    """
    monkeypatch.setattr(llm, "chat", lambda prompt, **kw: {"answer": "whole"})

    def _must_not_stream(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("chat_stream must not be used for a schema request")

    monkeypatch.setattr(llm, "chat_stream", _must_not_stream)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "response_format": {"type": "json_object"},
        },
    ) as response:
        payloads = [
            line[len("data: ") :] for line in response.iter_lines() if line.startswith("data: ")
        ]

    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    content = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert json.loads(content) == {"answer": "whole"}


# ---------------------------------------------------------------------------
# Refusals: a parameter ignored is worse than one refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"n": 2}, "n must be 1"),
        ({"logprobs": True}, "logprobs"),
        ({"tools": [{"type": "function"}]}, "tool calling"),
    ],
)
def test_unsupported_parameters_are_named_rather_than_dropped(
    client: TestClient, canned_engine: dict[str, Any], body: dict[str, Any], expected: str
) -> None:
    """A caller who relies on one has to hear about it, not get a plain answer."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hi"}], **body},
    )
    assert response.status_code == 400
    assert expected in response.json()["error"]["message"]


def test_errors_use_openais_envelope(client: TestClient) -> None:
    """An SDK unwraps error.message; FastAPI's default `detail` renders as nothing."""
    response = client.post("/v1/chat/completions", json={"model": "best", "messages": []})
    assert response.status_code == 400
    error = response.json()["error"]
    assert set(error) == {"message", "type", "param", "code"}
    assert error["type"] == "invalid_request_error"
    assert "messages" in error["message"]


def test_a_remote_image_url_is_refused_by_default(client: TestClient) -> None:
    """Fetching a caller-chosen address is a request-forgery primitive.

    This server usually runs on a developer's machine, which can reach a
    private network a public client should not be able to probe through it.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "http://169.254.169.254/x"}}
                    ],
                }
            ],
        },
    )
    assert response.status_code == 400
    assert openai_api.FETCH_IMAGE_URLS_ENV in response.json()["error"]["message"]


def test_an_unresolvable_virtual_name_is_a_503_that_explains_itself(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "No model fits this machine" is a server condition, with a next step."""
    monkeypatch.setattr(openai_api, "_engine_for", lambda kind, task, mode="local": None)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 503
    assert "recommend" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# The legacy, the vectors and the pixels
# ---------------------------------------------------------------------------


def test_the_legacy_completions_endpoint_answers_too(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """Old clients exist, and routing their prompt through chat is honest.

    Every backend here is instruction-tuned: there is no separate raw
    completion mode to expose, so this is a differently-shaped chat call and
    says so in its docstring rather than pretending to be something else.
    """
    body = client.post("/v1/completions", json={"model": "best", "prompt": "once upon"}).json()

    assert body["object"] == "text_completion"
    assert body["choices"][0]["text"] == "a local answer"
    assert recorded_chat[0]["prompt"] == "once upon"


def test_embeddings_return_one_vector_per_input(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Including the indices, which is how a caller re-pairs them with inputs."""
    monkeypatch.setattr(llm, "embed", lambda text, model=None: [0.5, -0.25, 0.125])
    body = client.post(
        "/v1/embeddings", json={"model": "best-embed", "input": ["one", "two"]}
    ).json()

    assert body["object"] == "list"
    assert [row["index"] for row in body["data"]] == [0, 1]
    assert body["data"][0]["embedding"] == [0.5, -0.25, 0.125]
    assert body["usage"]["total_tokens"] > 0


def test_embeddings_can_come_back_base64_like_openais_own(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The format OpenAI's own client asks for by default in recent versions."""
    import struct

    monkeypatch.setattr(llm, "embed", lambda text, model=None: [1.0, 2.0])
    body = client.post(
        "/v1/embeddings",
        json={"model": "best-embed", "input": "one", "encoding_format": "base64"},
    ).json()

    raw = base64.b64decode(body["data"][0]["embedding"])
    assert struct.unpack("<2f", raw) == (1.0, 2.0)


def test_an_image_request_returns_base64_png_and_says_what_it_used(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local server has nowhere to host a file, so bytes are the answer."""
    from best_engine_ai_helper import imagine

    calls: list[dict[str, Any]] = []

    def _generate(prompt: str, **kwargs: Any) -> bytes:
        calls.append({"prompt": prompt, **kwargs})
        return b"\x89PNG\r\n\x1a\nfake"

    monkeypatch.setattr(imagine, "generate", _generate)
    body = client.post(
        "/v1/images/generations",
        json={"model": "best-image", "prompt": "a red bicycle", "n": 2, "seed": 7},
    ).json()

    assert len(body["data"]) == 2
    assert base64.b64decode(body["data"][0]["b64_json"]).startswith(b"\x89PNG")
    # The model and size actually used are reported: with a virtual name the
    # caller did not choose them and cannot otherwise know.
    assert "/" in body["model"]
    assert "x" in body["size"]
    # A seed plus n=2 must not return the same picture twice.
    assert calls[0]["seed"] != calls[1]["seed"]
    # The native resolution came from the catalogue, not from a house default.
    assert calls[0]["width"] > 0 and calls[0]["steps"] >= 1


def test_an_unknown_image_size_is_refused_with_the_list(client: TestClient) -> None:
    """A silently-substituted size would be charged for in seconds of GPU."""
    response = client.post(
        "/v1/images/generations",
        json={"model": "best-image", "prompt": "x", "size": "123x456"},
    )
    assert response.status_code == 400
    assert "1024x1024" in response.json()["error"]["message"]


def test_the_image_endpoint_caps_n(client: TestClient) -> None:
    """Each image is a full sampling run here, not a batched datacentre call."""
    response = client.post(
        "/v1/images/generations", json={"model": "best-image", "prompt": "x", "n": 9}
    )
    assert response.status_code == 400
    assert "capped at 4" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# What the MCP surface must NOT have gained
# ---------------------------------------------------------------------------


def test_the_mcp_surface_still_only_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its description promises no model call happens inside its tools.

    Mounting an OpenAI-compatible surface on the same app would have made that
    false by default — fastapi-mcp publishes every route it finds — so the
    `/v1` operations are excluded, and this is the test that keeps them out.
    """
    from best_engine_ai_helper import mcp as mcp_module

    names = [tool.name for tool in mcp_module.mcp.tools]
    assert names, "the MCP surface should still publish the decision tools"
    assert not [n for n in names if "v1" in n], names
    assert any("recommend" in n for n in names)
    assert mcp_module._INFERENCE_OPERATIONS, "the exclusion list must not be silently empty"


# ---------------------------------------------------------------------------
# The failure paths a user actually meets
# ---------------------------------------------------------------------------


def test_a_backend_failure_is_a_502_with_the_reason(
    client: TestClient, canned_engine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead Ollama is the most common failure here, and a traceback helps nobody."""

    def _boom(prompt: str, **kwargs: Any) -> str:
        raise RuntimeError("connection refused to http://localhost:11434")

    monkeypatch.setattr(llm, "chat", _boom)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["type"] == "server_error"
    assert "connection refused" in error["message"]


def test_naming_a_concrete_model_bypasses_the_chooser(
    client: TestClient, recorded_chat: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`best` is the product, not a cage: a literal tag still means that tag."""
    monkeypatch.setattr(
        openai_api,
        "_engine_for",
        lambda kind, task, mode="local": pytest.fail("a literal model must not resolve an engine"),
    )
    response = client.post(
        "/v1/chat/completions",
        json={"model": "qwen3:14b", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200, response.text
    assert recorded_chat[0]["model"] == "qwen3:14b"
    assert recorded_chat[0]["engine"] is None


def test_a_failing_embedder_is_a_502_too(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same contract as chat: the reason travels, the traceback does not."""

    def _boom(text: str, model: str | None = None) -> list[float]:
        raise RuntimeError("no embedding model pulled")

    monkeypatch.setattr(llm, "embed", _boom)
    response = client.post("/v1/embeddings", json={"model": "best-embed", "input": "x"})

    assert response.status_code == 502
    assert "no embedding model pulled" in response.json()["error"]["message"]


def test_an_empty_embedding_input_is_refused(client: TestClient) -> None:
    """An empty list would otherwise return an empty success, which is a lie."""
    response = client.post("/v1/embeddings", json={"model": "best-embed", "input": []})

    assert response.status_code == 400
    assert "input" in response.json()["error"]["message"]


def test_a_malformed_data_uri_is_named_as_such(client: TestClient) -> None:
    """ "Undecodable image" is actionable; a 500 from base64 is not."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "best",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,!!!!"}}
                    ],
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "undecodable data URI" in response.json()["error"]["message"]


def test_a_validation_error_names_the_field(client: TestClient) -> None:
    """FastAPI's native 422 body is unparseable to an OpenAI client."""
    response = client.post("/v1/chat/completions", json={"model": "best"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert "messages" in error["message"]
    assert set(error) == {"message", "type", "param", "code"}


def test_the_other_api_keeps_fastapis_own_error_shape(client: TestClient) -> None:
    """The envelope is scoped to /v1 — /api callers expect FastAPI's conventions.

    Changing those to suit a compatibility layer would be the tail wagging the
    dog, so the handler delegates for every path outside /v1.
    """
    response = client.post("/api/recommend", json={"headroom": "not-a-float"})

    assert response.status_code == 422
    assert "detail" in response.json()
    assert "error" not in response.json()


def test_the_response_names_the_model_that_actually_ran(
    client: TestClient, canned_engine: dict[str, Any], recorded_chat: list[dict[str, Any]]
) -> None:
    """A virtual name only works if the real choice comes back.

    `model: "best"` in, `model: "qwen3:14b"` out — otherwise the caller has no
    way to know what answered, which is the one thing they gave up by not
    naming a model themselves.
    """
    body = client.post(
        "/v1/chat/completions",
        json={"model": "best", "messages": [{"role": "user", "content": "hi"}]},
    ).json()

    assert body["model"] == "qwen3:14b"
    assert body["model"] not in ("best", "llm")


# ---------------------------------------------------------------------------
# Mode: the free half and the paid half, on one server
# ---------------------------------------------------------------------------


def test_the_name_can_pin_a_mode_and_silence_means_the_server_default() -> None:
    """One deployment serves both halves, which is what makes "all modes" real.

    A gateway in front of this can keep a free route on `best-local-llm` and a
    paid one on `best-cloud-llm` against the SAME process, instead of running
    two servers or restarting to change its mind.
    """
    assert openai_api.parse_model("best-cloud-llm")["mode"] == "cloud"
    assert openai_api.parse_model("best-cloud-llm")["kind"] == "llm"
    assert openai_api.parse_model("best-local-vlm")["mode"] == "local"
    assert openai_api.parse_model("best-local-vlm")["kind"] == "vlm"
    # The bare alias says nothing, so the server decides rather than the name.
    assert openai_api.parse_model("best")["mode"] is None
    assert openai_api.parse_model("best-llm")["mode"] is None
    # The infix composes with both the auto name and the free-text task.
    assert openai_api.parse_model("best-cloud", has_images=True)["kind"] == "vlm"
    assert openai_api.parse_model("best-cloud:write SQL")["task"] == "write SQL"
    assert openai_api.parse_model("best-cloud:write SQL")["mode"] == "cloud"
    # A concrete name is the caller's own choice; a mode cannot apply to it.
    assert openai_api.parse_model("qwen3:14b")["mode"] is None


def test_an_unrecognised_default_mode_serves_local_rather_than_spending() -> None:
    """The failure direction matters when one of the two bills somebody."""
    assert openai_api.default_mode({}) == "local"
    assert openai_api.default_mode({"BEST_OPENAI_MODE": "cloud"}) == "cloud"
    assert openai_api.default_mode({"BEST_OPENAI_MODE": " CLOUD "}) == "cloud"
    assert openai_api.default_mode({"BEST_OPENAI_MODE": "typo"}) == "local"


def test_the_mode_reaches_resolution_and_is_cached_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cloud answer must never be served from a local cache entry, or back.

    The cache key used to be (kind, task). With two modes behind one server
    that would hand a paid caller the free model — the kind of mix-up that is
    invisible until the bill or the quality says so.
    """
    seen: list[dict] = []

    def _resolve(brief, **_kwargs):
        seen.append(dict(brief))
        return {"backend": "ollama", "llm": {"model": f"model-for-{brief['mode']}"}}

    monkeypatch.setattr("best_engine_ai_helper.engine.resolve", _resolve)
    openai_api.reset_engine_cache()

    local = openai_api._engine_for("llm", None, "local")
    cloud = openai_api._engine_for("llm", None, "cloud")

    assert [b["mode"] for b in seen] == ["local", "cloud"]
    assert local["llm"]["model"] == "model-for-local"
    assert cloud["llm"]["model"] == "model-for-cloud"
    # Asking again is served from the cache, per mode, not re-resolved.
    assert openai_api._engine_for("llm", None, "cloud")["llm"]["model"] == "model-for-cloud"
    assert len(seen) == 2


def test_a_paid_embedder_is_refused_instead_of_quietly_served_for_free() -> None:
    """The cloud catalogue prices text and vision only.

    `engine._kinds_from_brief` answers an unknown kind by warning and resolving
    BOTH, so a paid embedding request would come back with a chat model — or
    silently with the local embedder the caller did not ask for. Refusing is
    the behaviour this module's docstring commits to.
    """
    for endpoint in ("/v1/embeddings", "/v1/images/generations"):
        with pytest.raises(Exception) as excinfo:
            openai_api._refuse_cloud_kind({"mode": "cloud", "kind": "embed"}, endpoint)
        assert excinfo.value.status_code == 400
        assert "no paid route" in str(excinfo.value.detail)

    # Without the explicit `cloud`, the local answer is a real answer.
    assert openai_api._refuse_cloud_kind({"mode": None, "kind": "embed"}, "/v1/embeddings") is None
