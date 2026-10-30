"""
The compatibility claim, tested with the real OpenAI client library.

Every other test of this surface asserts a shape *we* chose to assert. This one
hands the responses to the actual SDK and lets it parse them, which is the only
way to find out whether a field we got subtly wrong — a missing ``object``, an
``index`` of the wrong type, an SSE frame without its blank line — breaks the
client people will really use.

Routed through Starlette's ``TestClient`` — which is an ``httpx.Client``
subclass with a synchronous ASGI transport, so the SDK can be handed it
directly as its ``http_client``. No port, no background thread, no flake.
(``httpx.ASGITransport`` looks like the obvious choice and is not: it only
implements the async side, so a synchronous SDK call lands on a missing
``handle_request``.) Inference is faked, because the claim under test is the
protocol and not the model.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient

openai = pytest.importorskip("openai", reason="the OpenAI SDK is a dev dependency")

from best_engine_ai_helper import imagine, llm, openai_api  # noqa: E402
from best_engine_ai_helper.api import app  # noqa: E402


@pytest.fixture()
def sdk(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A real `OpenAI` client, talking to this app in-process."""
    openai_api.reset_engine_cache()
    monkeypatch.setattr(
        openai_api,
        "_engine_for",
        lambda kind, task, mode="local": {
            "backend": "ollama",
            "base_url": "http://localhost:11434",
            "llm": {"model": "qwen3:14b"},
            "vlm": {"model": "gemma3:12b"},
        },
    )
    monkeypatch.setattr(llm, "chat", lambda prompt, **kw: "a local answer")
    monkeypatch.setattr(llm, "chat_stream", lambda prompt, **kw: iter(["a ", "local ", "answer"]))
    monkeypatch.setattr(llm, "embed", lambda text, model=None: [0.25, 0.5])
    monkeypatch.setattr(imagine, "generate", lambda prompt, **kw: b"\x89PNG\r\n\x1a\nbytes")

    return openai.OpenAI(
        base_url="http://testserver/v1",
        api_key="not-needed",
        http_client=TestClient(app),
    )


def test_the_sdk_lists_models(sdk: Any) -> None:
    """`models.list()` is the first call most clients make, often on startup."""
    ids = [model.id for model in sdk.models.list().data]

    assert "best" in ids
    assert "best-image" in ids


def test_the_sdk_completes_a_chat_and_reads_the_usage(sdk: Any) -> None:
    """The whole point, in one call: no model name, and an answer anyway."""
    done = sdk.chat.completions.create(
        model="best", messages=[{"role": "user", "content": "name three colours"}]
    )

    assert done.choices[0].message.content == "a local answer"
    assert done.choices[0].finish_reason == "stop"
    assert done.usage.total_tokens > 0
    # The model that actually ran, which is what a virtual name buys back.
    assert done.model == "qwen3:14b"


def test_the_sdk_streams(sdk: Any) -> None:
    """Parsed by the SDK's own SSE reader, not by a regex of ours."""
    deltas = [
        chunk.choices[0].delta.content
        for chunk in sdk.chat.completions.create(
            model="best", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        if chunk.choices[0].delta.content
    ]

    assert len(deltas) >= 3
    assert "".join(deltas) == "a local answer"


def test_the_sdk_sends_an_image_the_way_its_docs_say(sdk: Any) -> None:
    """The content-parts shape every vision example on the internet uses."""
    encoded = base64.b64encode(b"fake-png").decode()
    done = sdk.chat.completions.create(
        model="best",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ],
            }
        ],
    )

    assert done.choices[0].message.content == "a local answer"


def test_the_sdk_gets_embeddings_and_images(sdk: Any) -> None:
    """Two different response envelopes, both parsed by the client."""
    vectors = sdk.embeddings.create(model="best-embed", input=["one", "two"])
    assert [row.index for row in vectors.data] == [0, 1]
    assert vectors.data[0].embedding == [0.25, 0.5]

    picture = sdk.images.generate(model="best-image", prompt="a red bicycle", n=1)
    assert base64.b64decode(picture.data[0].b64_json).startswith(b"\x89PNG")


def test_the_sdk_raises_its_own_error_type_with_our_message(sdk: Any) -> None:
    """The error envelope's only real test: does the client unwrap it?

    A FastAPI-shaped `{"detail": ...}` body reaches the user as "unknown
    error", throwing away the sentence that would have told them what to do.
    """
    with pytest.raises(openai.BadRequestError) as caught:
        sdk.chat.completions.create(model="best", messages=[{"role": "user", "content": "x"}], n=3)

    assert "n must be 1" in str(caught.value)


def test_v1_models_publishes_a_measured_window_when_the_catalogue_declares_none(
    tmp_path, monkeypatch
) -> None:
    """The local half of the catalogue has no context_length, and should not.

    A window belongs to a particular quantisation of a particular checkpoint,
    so a figure typed into models.yaml would describe a file nobody opened. A
    model that has actually been pulled reported its real one, though, and
    `pull` wrote it down — so `/v1/models` publishes that instead of nothing.
    """
    from best_engine_ai_helper import openai_api, throughput

    store = tmp_path / "m.yaml"
    monkeypatch.setattr(throughput, "_STORE_PATH", store)
    throughput.record_context_length("gemma3:12b", 131072, store)

    # Declared wins, when there is one.
    assert openai_api._context_length({"id": "gpt-4o", "context_length": 128000}) == 128000

    # Otherwise the measured figure stands in.
    assert openai_api._context_length({"model": "gemma3:12b"}) == 131072

    # A model this machine does not hold still publishes nothing.
    assert openai_api._context_length({"model": "never-pulled:70b"}) is None
