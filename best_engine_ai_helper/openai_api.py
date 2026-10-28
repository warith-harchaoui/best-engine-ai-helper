"""
openai_api — speak OpenAI on the wire, choose the model locally.

From the outside this package becomes an **OpenAI-compatible endpoint**: point
any OpenAI SDK at ``http://127.0.0.1:8000/v1``, ask for chat completions,
embeddings or images, and get them. Inside, the model is not a name the caller
had to know — it is whatever this machine should actually run, chosen by the
same ranking every other surface here uses.

That inversion is the whole point. The usual OpenAI-compatible server (vLLM,
Ollama's ``/v1``, LM Studio) asks *you* which model to load; the hard part —
which model fits this hardware, whether it is fast enough, whether a bigger one
is worth the wait — is left to the person writing the config. Here the wire
protocol is the familiar one and the choice is the product:

    client.chat.completions.create(model="best", messages=[...])

``best`` is a **virtual model name**. It resolves, per request, to the
highest-ranked model that fits this machine's memory budget for the kind the
request needs — and a request carrying an image needs a VLM, so the same name
resolves differently depending on what is in it. The grammar is small:

=====================  ====================================================
``best`` / ``auto``    Best text model; best vision model if the request
                       carries images.
``best-llm``           Best text model, images refused rather than ignored.
``best-vlm``           Best vision-language model.
``best-embed``         Best embedding model (``/v1/embeddings``).
``best-image``         Best text-to-image model (``/v1/images/generations``).
``best:<task>``        Best model *for that task*, free text:
                       ``best:write SQL``, ``best:read screenshots``. The task
                       picks the benchmark axis, exactly as ``report --task``
                       does.
anything else          Passed through verbatim, so ``qwen3:14b`` still means
                       ``qwen3:14b``.
=====================  ====================================================

What is deliberately NOT faked
------------------------------
A compatibility layer earns trust by refusing rather than pretending:

- **Token counts are real where the backend reports them.** Ollama returns
  ``prompt_eval_count``/``eval_count``, and those are what ``usage`` carries.
  Where a backend reports nothing, the counts are a character-based estimate —
  flagged in ``system_fingerprint`` rather than passed off as measured.
- **Streaming is real streaming** for a plain text request, over
  ``llm.chat_stream``. For a request that also needs a schema or an image it
  degrades to one chunk, because the underlying stream carries neither, and
  saying so beats emitting a fake token-by-token drip.
- **Unsupported parameters are errors, not silence.** ``n > 1``,
  ``logprobs`` and friends return a 400 naming themselves. A parameter quietly
  ignored is worse than one refused: the caller believes they got what they
  asked for.
- **Remote image URLs are off by default.** ``image_url`` with a ``data:`` URI
  always works. An ``http(s)`` URL makes the server fetch a caller-chosen
  address, which is a server-side request forgery primitive, so it needs
  ``BEST_OPENAI_FETCH_IMAGE_URLS=1`` to be switched on.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
import time
from collections.abc import Callable, Iterator
from typing import Any, Literal

import os_helper as osh
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["openai-compatible"])

#: Virtual model names, and the kind each one pins. ``best``/``auto`` are
#: deliberately absent: they depend on the request (an image in it means a VLM),
#: so they resolve in :func:`parse_model` rather than in a table.
_VIRTUAL_KINDS: dict[str, str] = {
    "best-llm": "llm",
    "best-text": "llm",
    "best-vlm": "vlm",
    "best-vision": "vlm",
    "best-embed": "embed",
    "best-embedding": "embed",
    "best-image": "image",
}

#: Names meaning "you choose, based on what I sent".
_AUTO_NAMES = frozenset({"best", "auto", "default", "best-auto"})

#: Which mode a virtual name pins, as an infix after ``best-``:
#: ``best-cloud-llm``, ``best-local-vlm``, ``best-cloud:write SQL``. A name
#: that says nothing takes the server default (:func:`default_mode`), so one
#: deployment can serve both halves of the product at once: a gateway can keep
#: a free route on ``best-local-llm`` and a paid one on ``best-cloud-llm``
#: against the SAME server, which is what makes "all modes" a deployment fact
#: rather than a restart.
_MODE_NAMES = frozenset({"local", "cloud"})

#: Environment switch for the default mode of a ``best*`` name that does not
#: pin one. ``local`` (free, this machine) unless set to ``cloud`` (paid
#: provider, with the local fallback the cloud descriptor already carries).
MODE_ENV = "BEST_OPENAI_MODE"

#: Environment switch for fetching ``http(s)`` image URLs. Off by default: a
#: server that fetches a caller-supplied address on request is an SSRF
#: primitive, and this one usually runs on a developer's machine with access to
#: a private network a public client should not be able to probe.
FETCH_IMAGE_URLS_ENV = "BEST_OPENAI_FETCH_IMAGE_URLS"

#: Cap on a fetched image, when fetching is switched on at all.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: Characters per token for the fallback usage estimate, matching
#: ``observe._CHARS_PER_TOKEN`` so the two ledgers agree.
_CHARS_PER_TOKEN = 4.0

#: Marks a response whose token counts are estimated rather than reported by
#: the backend. ``system_fingerprint`` is the only field in the OpenAI response
#: shape that can carry this honestly, which is why it is used for it.
FINGERPRINT_ESTIMATED = "best-engine-ai-helper:usage=estimated"
FINGERPRINT_MEASURED = "best-engine-ai-helper:usage=reported"


def _oid(prefix: str) -> str:
    """
    Build an OpenAI-shaped object id.

    Parameters
    ----------
    prefix : str
        Object prefix, e.g. ``chatcmpl``.

    Returns
    -------
    str
        ``<prefix>-<24 hex chars>``.

    Examples
    --------
    >>> ident = _oid("chatcmpl")
    >>> ident.startswith("chatcmpl-"), len(ident)
    (True, 33)
    """
    return f"{prefix}-{secrets.token_hex(12)}"


def _fail(status: int, message: str, *, kind: str = "invalid_request_error") -> HTTPException:
    """
    Build an error in OpenAI's own envelope.

    An SDK unwraps ``error.message`` and shows it; anything else is rendered as
    "unknown error", so a compatibility layer that returns FastAPI's default
    ``{"detail": ...}`` throws its own diagnostics away.

    Parameters
    ----------
    status : int
        HTTP status.
    message : str
        Human-readable explanation.
    kind : str
        OpenAI error ``type``.

    Returns
    -------
    HTTPException
        Ready to raise.

    Examples
    --------
    >>> exc = _fail(400, "n must be 1")
    >>> exc.status_code, exc.detail["error"]["message"]
    (400, 'n must be 1')
    """
    return HTTPException(
        status_code=status,
        detail={"error": {"message": message, "type": kind, "param": None, "code": None}},
    )


def default_mode(env: dict[str, str] | None = None) -> str:
    """
    The mode a ``best*`` name takes when it does not pin one.

    Read from :data:`MODE_ENV` rather than baked in, so the same build serves a
    free deployment and a paid one. Anything unrecognised is ``local``, with a
    warning: the failure direction matters here, because the other one bills
    somebody.

    Parameters
    ----------
    env : dict[str, str] or None
        Environment to read; None uses ``os.environ``. Injectable so this stays
        a pure function under test — the thing it reports on is exactly the
        kind of ambient state a test must not inherit from the host.

    Returns
    -------
    str
        ``'local'`` or ``'cloud'``.

    Examples
    --------
    >>> default_mode({})
    'local'
    >>> default_mode({"BEST_OPENAI_MODE": "cloud"})
    'cloud'
    >>> default_mode({"BEST_OPENAI_MODE": "CLOUD"})
    'cloud'
    >>> default_mode({"BEST_OPENAI_MODE": "nonsense"})   # unrecognised -> free
    'local'
    """
    source = os.environ if env is None else env
    raw = str(source.get(MODE_ENV, "") or "").strip().lower()
    if not raw:
        return "local"
    if raw in _MODE_NAMES:
        return raw
    osh.warning(
        f"{MODE_ENV}={raw!r} is not one of {sorted(_MODE_NAMES)}; serving local. "
        "The unrecognised value is not treated as 'cloud' on purpose: that "
        "direction spends money on a typo."
    )
    return "local"


def parse_model(name: str | None, *, has_images: bool = False) -> dict[str, Any]:
    """
    Resolve a requested model name into what to actually run.

    The name may pin a **mode** as an infix after ``best-``: ``best-cloud-llm``
    is the best paid text model, ``best-local-vlm`` the best free one that fits
    this machine. A name that pins nothing reports ``mode: None``, meaning "the
    server decides" — :func:`default_mode` does, at call time. The mode is
    deliberately NOT resolved here: this function is pure, and a resolution
    that silently read the environment would make its own doctests depend on
    the host that happened to run them.

    Parameters
    ----------
    name : str or None
        The ``model`` field. None or empty is treated as ``best``, because an
        OpenAI SDK always sends one and a caller who does not care should not
        have to invent a value.
    has_images : bool
        Whether the request carries images. Only consulted for the auto names,
        where it is the difference between needing a VLM and not.

    Returns
    -------
    dict[str, Any]
        ``virtual`` (bool), ``kind`` (``llm``/``vlm``/``embed``/``image``),
        ``task`` (free text or None), ``literal`` (the model name to pass
        through, or None when the choice is ours) and ``mode``
        (``'local'``/``'cloud'``, or None when the name did not say).

    Examples
    --------
    >>> parse_model("best") == {
    ...     'virtual': True, 'kind': 'llm', 'task': None, 'literal': None, 'mode': None}
    True
    >>> parse_model("best", has_images=True)["kind"]
    'vlm'
    >>> parse_model("best-image")["kind"]
    'image'
    >>> parse_model("best:write SQL for a warehouse")["task"]
    'write SQL for a warehouse'
    >>> parse_model("best-vlm:read screenshots") == {
    ...     'virtual': True, 'kind': 'vlm', 'task': 'read screenshots',
    ...     'literal': None, 'mode': None}
    True

    The mode infix, on a pinned kind and on an auto name alike:

    >>> parse_model("best-cloud-llm")["mode"]
    'cloud'
    >>> parse_model("best-cloud-llm")["kind"]
    'llm'
    >>> parse_model("best-local-vlm") == {
    ...     'virtual': True, 'kind': 'vlm', 'task': None,
    ...     'literal': None, 'mode': 'local'}
    True
    >>> parse_model("best-cloud", has_images=True)["kind"]
    'vlm'
    >>> parse_model("best-cloud:write SQL")["task"]
    'write SQL'

    A concrete name still passes through untouched, colon and all:

    >>> parse_model("qwen3:14b") == {
    ...     'virtual': False, 'kind': 'llm', 'task': None,
    ...     'literal': 'qwen3:14b', 'mode': None}
    True
    >>> parse_model(None)["virtual"]
    True
    """
    raw = (name or "best").strip()
    head, _, tail = raw.partition(":")
    head = head.strip().lower()
    task: str | None = tail.strip() or None

    head, mode = _split_mode(head)

    if head in _AUTO_NAMES:
        return {
            "virtual": True,
            "kind": "vlm" if has_images else "llm",
            "task": task,
            "literal": None,
            "mode": mode,
        }
    if head in _VIRTUAL_KINDS:
        return {
            "virtual": True,
            "kind": _VIRTUAL_KINDS[head],
            "task": task,
            "literal": None,
            "mode": mode,
        }
    # Not a virtual name: the colon belongs to the tag (`qwen3:14b`), so the
    # whole string is the model and nothing was a task. A mode infix cannot
    # apply either -- the caller named a model, which IS the choice.
    return {
        "virtual": False,
        "kind": "vlm" if has_images else "llm",
        "task": None,
        "literal": raw,
        "mode": None,
    }


def _split_mode(head: str) -> tuple[str, str | None]:
    """
    Pull a ``local``/``cloud`` infix out of a ``best-…`` name.

    Returns the name with the infix removed (so the existing tables can be
    looked up unchanged) and the mode, or None when there was none.

    Examples
    --------
    >>> _split_mode("best-cloud-llm")
    ('best-llm', 'cloud')
    >>> _split_mode("best-cloud")
    ('best', 'cloud')
    >>> _split_mode("best-llm")
    ('best-llm', None)
    >>> _split_mode("qwen3-cloud-7b")          # not a `best-` name, untouched
    ('qwen3-cloud-7b', None)
    """
    if not head.startswith("best-"):
        return head, None
    rest = head[len("best-") :]
    for mode in _MODE_NAMES:
        if rest == mode:
            return "best", mode
        if rest.startswith(f"{mode}-"):
            return f"best-{rest[len(mode) + 1 :]}", mode
    return head, None


def _engine_for(kind: str, task: str | None, mode: str = "local") -> dict[str, Any] | None:
    """
    Resolve an engine descriptor for a kind, the way ``resolve`` would.

    Cached per ``(kind, task)`` in :data:`_ENGINE_CACHE`: ranking the catalogue
    against detected hardware costs tens of milliseconds, which is nothing once
    and everything on every token of a streamed reply.

    Parameters
    ----------
    kind : {'llm', 'vlm'}
        Model kind to resolve.
    task : str or None
        Free-text task, selecting the benchmark axis.

    mode : {'local', 'cloud'}
        Which half of the product answers. ``cloud`` returns a paid-provider
        descriptor that already embeds a local ``fallback``, so a failed paid
        call degrades to the free model instead of to an error — the direction
        ``engine._resolve_cloud`` chose, and the reason this surface can offer
        the paid route without becoming less reliable than the free one.

    Returns
    -------
    dict[str, Any] or None
        The descriptor, or None when nothing could be resolved for this
        machine.

    Examples
    --------
    >>> _engine_for("llm", None) is None or "backend" in _engine_for("llm", None)
    True
    """
    key = (kind, task or "", mode)
    if key in _ENGINE_CACHE:
        return _ENGINE_CACHE[key]

    from . import engine as _engine

    brief: dict[str, Any] = {"kind": kind, "structured_output": False, "mode": mode}
    if task:
        brief["task"] = task
    try:
        descriptor = _engine.resolve(brief)
    except Exception as exc:  # noqa: BLE001 — a failed resolution is a 503, not a crash
        osh.warning(f"OpenAI surface could not resolve a {kind} {mode} engine: {exc!r}")
        _ENGINE_CACHE[key] = None
        return None
    _ENGINE_CACHE[key] = descriptor
    return descriptor


#: Resolved descriptors, keyed by (kind, task, mode). Cleared by
#: :func:`reset_engine_cache`, which the tests and a long-running server both
#: need: hardware does not change under a process, but a freshly pulled model
#: does.
_ENGINE_CACHE: dict[tuple[str, str, str], dict[str, Any] | None] = {}


def reset_engine_cache() -> None:
    """
    Forget every resolved engine, so the next request re-ranks.

    Examples
    --------
    >>> reset_engine_cache()
    >>> _ENGINE_CACHE
    {}
    """
    _ENGINE_CACHE.clear()


def _decode_image(url: str) -> bytes:
    """
    Turn an OpenAI ``image_url`` into raw bytes.

    Parameters
    ----------
    url : str
        A ``data:`` URI, or an ``http(s)`` URL when fetching is switched on.

    Returns
    -------
    bytes
        The image payload.

    Raises
    ------
    HTTPException
        For a malformed data URI, or an http(s) URL with fetching off.

    Examples
    --------
    >>> _decode_image("data:image/png;base64,aGVsbG8=")
    b'hello'
    >>> # An http(s) URL needs the switch, and says so rather than fetching.
    >>> try:
    ...     _decode_image("http://example.invalid/x.png")
    ... except Exception as exc:
    ...     print(exc.status_code, "server-side request forgery" in str(exc.detail))
    400 True
    """
    if url.startswith("data:"):
        _, _, payload = url.partition(",")
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _fail(400, f"image_url carries an undecodable data URI: {exc}") from exc

    if not os.environ.get(FETCH_IMAGE_URLS_ENV):
        raise _fail(
            400,
            "Fetching an http(s) image_url is off by default: the server would "
            "request an address the caller chose, which is a server-side request "
            f"forgery primitive. Set {FETCH_IMAGE_URLS_ENV}=1 to allow it, or send a "
            "data: URI.",
        )

    import requests

    try:
        response = requests.get(url, timeout=10, stream=True)
        response.raise_for_status()
        # Read one byte past the cap so an oversized image is detected without
        # buffering all of it.
        fetched: bytes = bytes(response.raw.read(_MAX_IMAGE_BYTES + 1, decode_content=True))
    except requests.RequestException as exc:
        raise _fail(400, f"could not fetch image_url: {exc}") from exc
    if len(fetched) > _MAX_IMAGE_BYTES:
        raise _fail(413, f"image at {url} exceeds the {_MAX_IMAGE_BYTES // 1024 // 1024} MB cap")
    return fetched


def flatten_messages(messages: list[dict[str, Any]]) -> tuple[str | None, str, list[bytes]]:
    """
    Collapse an OpenAI message list into what ``llm.chat`` takes.

    ``chat`` has one prompt, one optional system preamble and a list of images,
    which is the shape every backend here actually supports. A multi-turn
    conversation is therefore rendered as a transcript — labelled by role, in
    order — rather than silently reduced to its last message, which is how a
    compatibility layer loses the context a caller carefully sent.

    Parameters
    ----------
    messages : list of dict
        OpenAI ``messages``. Content may be a string or a list of parts
        (``{"type": "text"}`` / ``{"type": "image_url"}``).

    Returns
    -------
    tuple[str | None, str, list[bytes]]
        ``(system, prompt, images)``.

    Raises
    ------
    HTTPException
        When the list is empty or carries no usable content.

    Examples
    --------
    >>> flatten_messages([{"role": "user", "content": "hello"}])
    (None, 'hello', [])
    >>> flatten_messages([
    ...     {"role": "system", "content": "Be brief."},
    ...     {"role": "user", "content": "hi"},
    ...     {"role": "assistant", "content": "hello"},
    ...     {"role": "user", "content": "and now?"},
    ... ])
    ('Be brief.', 'user: hi\\nassistant: hello\\nuser: and now?', [])
    >>> system, prompt, images = flatten_messages([{
    ...     "role": "user",
    ...     "content": [
    ...         {"type": "text", "text": "what is this?"},
    ...         {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGk="}},
    ...     ],
    ... }])
    >>> system, prompt, images
    (None, 'what is this?', [b'hi'])
    """
    if not messages:
        raise _fail(400, "messages must not be empty")

    systems: list[str] = []
    turns: list[tuple[str, str]] = []
    images: list[bytes] = []

    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        content = message.get("content")
        texts: list[str] = []

        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type") or "").strip()
                if part_type in ("text", "input_text"):
                    texts.append(str(part.get("text") or ""))
                elif part_type in ("image_url", "input_image"):
                    holder = part.get("image_url") or part
                    url = holder.get("url") if isinstance(holder, dict) else None
                    if url:
                        images.append(_decode_image(str(url)))
        elif content is not None:
            texts.append(str(content))

        joined = "\n".join(t for t in texts if t).strip()
        if role in ("system", "developer"):
            if joined:
                systems.append(joined)
        elif joined:
            turns.append((role, joined))

    if not turns and not images:
        raise _fail(400, "messages carry no text and no image")

    if len(turns) == 1:
        # The common case: one user message. Send it as itself rather than
        # prefixing "user:", which some small models echo back.
        prompt = turns[0][1]
    else:
        prompt = "\n".join(f"{role}: {text}" for role, text in turns)

    return ("\n\n".join(systems) or None), prompt, images


def _schema_from_response_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Extract a JSON schema from OpenAI's ``response_format``.

    Parameters
    ----------
    response_format : dict or None
        ``{"type": "json_object"}`` or
        ``{"type": "json_schema", "json_schema": {"schema": {...}}}``.

    Returns
    -------
    dict or None
        A schema to constrain generation with, or None for free text.

    Examples
    --------
    >>> _schema_from_response_format(None) is None
    True
    >>> _schema_from_response_format({"type": "text"}) is None
    True
    >>> _schema_from_response_format({"type": "json_object"})
    {'type': 'object'}
    >>> _schema_from_response_format(
    ...     {"type": "json_schema",
    ...      "json_schema": {"schema": {"type": "object", "properties": {"a": {}}}}}
    ... )
    {'type': 'object', 'properties': {'a': {}}}
    """
    if not response_format:
        return None
    kind = str(response_format.get("type") or "").strip()
    if kind == "json_object":
        # Ollama's structured output needs *a* schema; the loosest honest one
        # is "an object", which is exactly what json_object promises.
        return {"type": "object"}
    if kind == "json_schema":
        holder = response_format.get("json_schema") or {}
        schema = holder.get("schema") if isinstance(holder, dict) else None
        if isinstance(schema, dict):
            return schema
        raise _fail(400, "response_format.json_schema must carry a `schema` object")
    return None


def _usage(in_chars: int, out_chars: int, reported: dict[str, Any]) -> tuple[dict[str, int], str]:
    """
    Build the ``usage`` block, preferring what the backend actually counted.

    Parameters
    ----------
    in_chars, out_chars : int
        Prompt and completion lengths, for the fallback estimate.
    reported : dict
        The last observer event, which carries ``in_tokens``/``out_tokens``
        when the backend reported them.

    Returns
    -------
    tuple[dict[str, int], str]
        The usage block, and the fingerprint saying whether it was measured.

    Examples
    --------
    >>> block, fingerprint = _usage(40, 80, {"in_tokens": 11, "out_tokens": 22})
    >>> block
    {'prompt_tokens': 11, 'completion_tokens': 22, 'total_tokens': 33}
    >>> fingerprint == FINGERPRINT_MEASURED
    True
    >>> block, fingerprint = _usage(40, 80, {})
    >>> block, fingerprint == FINGERPRINT_ESTIMATED
    ({'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}, True)
    """
    prompt_tokens = reported.get("in_tokens")
    completion_tokens = reported.get("out_tokens")
    measured = prompt_tokens is not None and completion_tokens is not None
    if not measured:
        prompt_tokens = int(in_chars / _CHARS_PER_TOKEN)
        completion_tokens = int(out_chars / _CHARS_PER_TOKEN)
    block = {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(prompt_tokens or 0) + int(completion_tokens or 0),
    }
    return block, (FINGERPRINT_MEASURED if measured else FINGERPRINT_ESTIMATED)


class ChatMessage(BaseModel):
    """One message in an OpenAI chat request."""

    role: str = "user"
    # A string, or a list of content parts. Typed loosely on purpose: the
    # part shapes differ between the chat and responses APIs, and rejecting an
    # unfamiliar one at the schema boundary would fail requests that
    # `flatten_messages` handles perfectly well.
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    """Body for ``POST /v1/chat/completions``."""

    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    stream: bool = False
    response_format: dict[str, Any] | None = None
    n: int = 1
    # Accepted and refused explicitly in the handler rather than dropped, so a
    # caller relying on one hears about it.
    logprobs: bool | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    # Not forwarded: every backend here has its own stop handling, and the one
    # that does not (lightweight) would silently ignore it.
    stop: str | list[str] | None = None


class CompletionRequest(BaseModel):
    """Body for the legacy ``POST /v1/completions``."""

    prompt: str | list[str]
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    stream: bool = False
    n: int = 1


class EmbeddingRequest(BaseModel):
    """Body for ``POST /v1/embeddings``."""

    input: str | list[str]
    model: str | None = None
    encoding_format: Literal["float", "base64"] = "float"


class ImageRequest(BaseModel):
    """Body for ``POST /v1/images/generations``."""

    prompt: str
    model: str | None = None
    n: int = 1
    size: str = "auto"
    response_format: Literal["b64_json", "url"] = "b64_json"
    # Beyond OpenAI's own fields, and documented as such: a local pipeline has
    # knobs a hosted one hides, and refusing to expose them would make the
    # endpoint worse than the library behind it.
    steps: int | None = None
    guidance: float | None = Field(default=None, description="Classifier-free guidance scale.")
    negative_prompt: str | None = None
    seed: int | None = None


def _refuse_cloud_kind(parsed: dict[str, Any], endpoint: str) -> None:
    """
    Refuse ``best-cloud-embed`` / ``best-cloud-image`` instead of serving local.

    The paid catalogue (``data/pricing.yaml``) carries ``llm`` and ``vlm`` and
    nothing else, and ``engine._kinds_from_brief`` answers an unknown kind by
    warning and resolving BOTH — so a cloud request for an embedder would come
    back with a chat model, or silently with the free local one. Either is the
    failure this module's docstring singles out as the worst kind: the caller
    believes they got what they asked for.

    Only an EXPLICIT ``cloud`` in the name is refused. A server whose default
    mode is cloud still serves ``best-embed`` locally, because that name asked
    for an embedder rather than for a paid one, and the free answer is a real
    answer.

    Raises
    ------
    HTTPException
        400, naming the kind and the reason.

    Examples
    --------
    >>> _refuse_cloud_kind({"mode": None, "kind": "embed"}, "/v1/embeddings") is None
    True
    >>> try:
    ...     _refuse_cloud_kind({"mode": "cloud", "kind": "embed"}, "/v1/embeddings")
    ... except Exception as exc:
    ...     print(exc.status_code, "no paid embed" in str(exc.detail))
    400 True
    """
    if parsed.get("mode") != "cloud":
        return
    raise _fail(
        400,
        f"{endpoint} has no paid route: the cloud catalogue prices text and "
        f"vision models only, so there is no paid {parsed['kind']} model to "
        f"pick. Drop the `cloud` from the name to use the local one, which is "
        f"a real answer rather than a degraded one.",
    )


def _target(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """
    Turn a parsed model name into ``(engine, literal_model)`` for ``llm.chat``.

    Parameters
    ----------
    parsed : dict[str, Any]
        Output of :func:`parse_model`.

    This is where the server default is applied: :func:`parse_model` reports
    the mode the *name* asked for, which is None whenever the name did not say,
    and :func:`default_mode` turns that into a concrete one.

    Returns
    -------
    tuple[dict | None, str | None]
        An engine descriptor when the choice is ours, else None and the literal
        model name to pass through.

    Raises
    ------
    HTTPException
        503 when a virtual name could not be resolved on this machine.

    Examples
    --------
    >>> _target({"virtual": False, "kind": "llm", "task": None,
    ...          "literal": "qwen3:8b", "mode": None})
    (None, 'qwen3:8b')
    """
    if not parsed["virtual"]:
        return None, parsed["literal"]

    mode = parsed.get("mode") or default_mode()
    descriptor = _engine_for(parsed["kind"], parsed["task"], mode)
    if descriptor is None or not descriptor.get(parsed["kind"]):
        where = (
            "for this machine"
            if mode == "local"
            else "from the paid catalogue (`catalog show --cloud` lists it)"
        )
        raise _fail(
            503,
            f"No {mode} {parsed['kind']} model could be resolved {where}. Run "
            "`best-engine-ai-helper recommend` to see why, or name a model "
            "explicitly instead of a `best*` alias.",
            kind="server_error",
        )
    return descriptor, None


@router.get("/models")
def list_models() -> dict[str, Any]:
    """
    List the virtual names and every catalogue model that fits this machine.

    Both halves matter. The ``best*`` aliases are what a caller should use —
    they are the product — and the concrete ids are what makes the list useful
    in a client's model picker: they are filtered to what this hardware can
    actually run, so the dropdown stops offering a 72B model to a laptop.

    Returns
    -------
    dict[str, Any]
        OpenAI's ``{"object": "list", "data": [...]}``.
    """
    from . import catalog as _catalog
    from . import detect as _detect
    from . import score as _score

    created = int(time.time())
    mode = default_mode()
    by_id = {str(e.get("id")): e for e in _catalog.load_catalog()}

    def _section(kind: str, alias_mode: str) -> dict[str, Any]:
        """What a chat/vision request for *kind* would resolve to, right now.

        A cloud descriptor whose ``api_key_present`` is False answers nothing
        useful: the pick is advisory, and publishing it as ``resolves_to``
        would hand a gateway a model this server cannot call. Empty, so the
        alias is listed without a resolution rather than with a wrong one.
        """
        descriptor = _engine_for(kind, None, alias_mode) or {}
        if alias_mode == "cloud" and not descriptor.get("api_key_present"):
            return {}
        return descriptor.get(kind) or {}

    def _embed_section() -> dict[str, Any]:
        """What ``/v1/embeddings`` would pick, through the same usage profile."""
        from . import usages as _usages

        resolved = _usages.resolve_usage("embeddings")
        return resolved.get("embed") or resolved.get("llm") or {}

    def _image_section() -> dict[str, Any]:
        """What ``/v1/images/generations`` would pick, through the same ranking."""
        from . import imagine as _imagine

        plan = _imagine.pick(
            _imagine.rank(_catalog.load_catalog(), budget_gb=_score.effective_budget(hw))
        )
        return {"model": (plan or {}).get("model"), "catalog_id": (plan or {}).get("id")}

    def _alias(
        name: str,
        description: str,
        resolve: Callable[[], dict[str, Any]] | None,
        alias_mode: str,
    ) -> dict[str, Any]:
        """One virtual name, carrying what it resolves to *right now*.

        ``resolves_to`` exists for the gateway case. A budget in front of this
        server is counted against one model's tokenizer and one served
        context, so a name that re-resolves per request is a moving target and
        the advice has been "ask which model, then pin it by hand". Publishing
        the answer makes that automatic instead of manual: read it, pin it.

        Every alias that *can* be resolved is resolved here, through the same
        path the matching endpoint uses — including ``best-embed`` and
        ``best-image``, whose per-request pick is the most opaque of the lot,
        and the mode-prefixed names, which a caller cannot otherwise predict
        without knowing ``BEST_OPENAI_MODE``. Absent only when the resolution
        genuinely fails — a cloud alias with no usable provider key, say —
        and never guessed.
        """
        entry: dict[str, Any] = {
            "id": name,
            "object": "model",
            "created": created,
            "owned_by": "best-engine-ai-helper",
            "description": description,
            "mode": alias_mode,
        }
        if resolve is None:
            return entry
        try:
            section = resolve()
        except Exception as exc:  # noqa: BLE001 — listing models must not 500
            osh.debug(f"Could not resolve {name} for the model list: {exc!r}")
            return entry
        resolved = section.get("model")
        if resolved:
            entry["resolves_to"] = resolved
            context = _context_length(by_id.get(str(section.get("catalog_id") or resolved)))
            if context:
                entry["context_length"] = context
        return entry

    hw = _detect.available_memory()

    data: list[dict[str, Any]] = [
        _alias(name, description, resolve, alias_mode)
        for name, description, resolve, alias_mode in (
            (
                "best",
                "Best model for this machine; a VLM when the request carries images",
                lambda: _section("llm", mode),
                mode,
            ),
            (
                "best-llm",
                "Best text model for this machine",
                lambda: _section("llm", mode),
                mode,
            ),
            (
                "best-vlm",
                "Best vision-language model for this machine",
                lambda: _section("vlm", mode),
                mode,
            ),
            (
                "best-embed",
                "Best embedding model for this machine",
                _embed_section,
                "local",
            ),
            (
                "best-image",
                "Best text-to-image model for this machine",
                _image_section,
                "local",
            ),
            (
                "best-local-llm",
                "Best text model that runs on this machine (never paid)",
                lambda: _section("llm", "local"),
                "local",
            ),
            (
                "best-cloud-llm",
                "Best paid text model from the pricing catalogue",
                lambda: _section("llm", "cloud"),
                "cloud",
            ),
            (
                "best-cloud-vlm",
                "Best paid vision-language model",
                lambda: _section("vlm", "cloud"),
                "cloud",
            ),
            (
                "best:<task>",
                "Best model for a free-text task, e.g. best:write SQL",
                None,
                mode,
            ),
        )
    ]

    budget = _score.effective_budget(hw)
    for entry in _catalog.load_catalog():
        kind = str(entry.get("kind") or "llm")
        if kind == "image":
            from . import imagine as _imagine

            fits = (
                _imagine.footprint_gb(entry) <= budget
                or _imagine.footprint_gb(entry, offload=True) <= budget
            )
        else:
            fits = _score.model_footprint_gb(entry) <= budget
        if not fits:
            continue
        published: dict[str, Any] = {
            "id": str(entry.get("id")),
            "object": "model",
            "created": created,
            "owned_by": str(entry.get("source") or "catalog"),
            "description": str(entry.get("notes") or "")[:160],
        }
        # Published when the catalogue knows it, omitted when it does not --
        # never a default. A gateway in front of this sizes its budget on this
        # number, and inventing one would be worse than leaving it out: the
        # founding incident of the project downstream was a served context
        # that was hoped for rather than known. `catalog update` is what fills
        # it in; the hand-maintained seed carries none.
        context = _context_length(entry)
        if context:
            published["context_length"] = context
        data.append(published)
    return {"object": "list", "data": data}


def _context_length(entry: dict[str, Any] | None) -> int | None:
    """
    A catalogue entry's context length, when it declares a usable one.

    Examples
    --------
    >>> _context_length({"context_length": 32768})
    32768
    >>> _context_length({"context_length": "131072"})
    131072
    >>> _context_length({}) is None
    True
    >>> _context_length({"context_length": 0}) is None
    True
    >>> _context_length({"context_length": "lots"}) is None
    True
    >>> _context_length(None) is None
    True
    """
    if not entry:
        return None
    try:
        value = int(entry.get("context_length") or 0)
    except (TypeError, ValueError):
        return None
    return value or None


def _chat_once(
    request: ChatCompletionRequest,
) -> tuple[str | dict[str, Any], dict[str, int], str, str]:
    """
    Run one non-streaming chat request.

    Returns
    -------
    tuple
        ``(answer, usage, fingerprint, model_name)``.
    """
    from . import llm as _llm

    system, prompt, images = flatten_messages([m.model_dump() for m in request.messages])
    parsed = parse_model(request.model, has_images=bool(images))
    if images and parsed["kind"] == "llm" and parsed["virtual"]:
        raise _fail(
            400,
            "this request carries images but asks for `best-llm`, a text model. Use "
            "`best` (which switches to a VLM on its own) or `best-vlm`.",
        )
    engine, literal = _target(parsed)
    schema = _schema_from_response_format(request.response_format)

    captured: dict[str, Any] = {}

    def _observe(event: dict[str, Any]) -> None:
        captured.update(event)

    _llm.add_observer(_observe)
    try:
        answer = _llm.chat(
            prompt,
            system=system,
            images=images or None,
            json_schema=schema,
            model=literal,
            temperature=request.temperature,
            engine=engine,
            kind=parsed["kind"],
        )
    except Exception as exc:  # noqa: BLE001 — a backend failure is a 502, not a traceback
        osh.error(f"OpenAI chat completion failed:\n\t{exc}")
        raise _fail(502, f"the backend failed: {exc}", kind="server_error") from exc
    finally:
        _llm.remove_observer(_observe)

    text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    usage, fingerprint = _usage(len(prompt) + len(system or ""), len(text), captured)
    # What actually ran, in order of authority: what the backend reported, the
    # literal name the caller sent, then the model the resolved engine names.
    # The kind is NOT a fallback — answering `model: "llm"` tells a caller
    # nothing, and the whole point of a virtual name is that the real choice
    # comes back in the response.
    resolved = (engine or {}).get(parsed["kind"]) or {}
    model_name = str(
        captured.get("model") or literal or resolved.get("model") or f"best-{parsed['kind']}"
    )
    return answer, usage, fingerprint, model_name


def _stream_chat(request: ChatCompletionRequest) -> Iterator[str]:
    """
    Yield an OpenAI SSE stream for a chat request.

    Real streaming where the transport has it (plain text through
    ``llm.chat_stream``); one chunk where it does not (a schema or an image,
    neither of which the streaming path carries). A fake token-by-token drip
    over an already-complete answer would look better and tell the caller less.
    """
    from . import llm as _llm

    system, prompt, images = flatten_messages([m.model_dump() for m in request.messages])
    parsed = parse_model(request.model, has_images=bool(images))
    engine, literal = _target(parsed)
    schema = _schema_from_response_format(request.response_format)
    ident = _oid("chatcmpl")
    created = int(time.time())
    model_name = str(literal or f"best-{parsed['kind']}")

    def _chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        payload = {
            "id": ident,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield _chunk({"role": "assistant", "content": ""})
    try:
        if images or schema:
            answer, _usage_block, _fingerprint, resolved = _chat_once(request)
            text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
            yield _chunk({"content": text})
        else:
            for piece in _llm.chat_stream(
                prompt,
                system=system,
                model=literal,
                temperature=request.temperature,
                engine=engine,
                kind=parsed["kind"],
            ):
                if piece:
                    yield _chunk({"content": piece})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — mid-stream, the only channel is the stream
        osh.error(f"OpenAI chat stream failed:\n\t{exc}")
        yield f"data: {json.dumps({'error': {'message': str(exc)}})}\n\n"
    yield _chunk({}, finish="stop")
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
def chat_completions(request: ChatCompletionRequest) -> Any:
    """
    OpenAI's chat completions, with the model chosen for this machine.

    Text and vision both land here: a request carrying ``image_url`` parts
    resolves to a VLM on its own, which is why ``best`` is usually the right
    name to send.
    """
    if request.n != 1:
        raise _fail(400, "n must be 1: this server runs one local model per request")
    if request.logprobs:
        raise _fail(400, "logprobs is not available from the backends behind this server")
    if request.tools or request.tool_choice:
        raise _fail(
            400,
            "tool calling is not implemented here. Ask for a JSON schema instead "
            "(response_format), which every Ollama model enforces natively and which "
            "covers the same ground for a single call.",
        )

    if request.stream:
        return StreamingResponse(
            _stream_chat(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    answer, usage, fingerprint, model_name = _chat_once(request)
    text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return {
        "id": _oid("chatcmpl"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "system_fingerprint": fingerprint,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


@router.post("/completions")
def completions(request: CompletionRequest) -> Any:
    """
    The legacy completions endpoint, for clients that still speak it.

    Implemented by routing the prompt through the chat path, because every
    backend here is instruction-tuned: there is no separate raw-completion mode
    to expose, and pretending otherwise would just be a differently-shaped
    chat call.
    """
    if request.n != 1:
        raise _fail(400, "n must be 1: this server runs one local model per request")
    prompt = request.prompt if isinstance(request.prompt, str) else "\n".join(request.prompt)
    chat_request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=False,
    )
    answer, usage, fingerprint, model_name = _chat_once(chat_request)
    text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return {
        "id": _oid("cmpl"),
        "object": "text_completion",
        "created": int(time.time()),
        "model": model_name,
        "system_fingerprint": fingerprint,
        "choices": [{"index": 0, "text": text, "logprobs": None, "finish_reason": "stop"}],
        "usage": usage,
    }


@router.post("/embeddings")
def embeddings(request: EmbeddingRequest) -> dict[str, Any]:
    """
    OpenAI's embeddings endpoint, over the best local embedder.

    ``best-embed`` resolves among the catalogue's ``kind: embed`` entries,
    which are ranked on retrieval quality (MTEB) rather than on the
    general-knowledge axis a chat model is judged by — a distinction the
    ``usages`` catalogue already draws and this endpoint inherits.
    """
    from . import llm as _llm
    from . import usages as _usages

    texts = [request.input] if isinstance(request.input, str) else list(request.input)
    if not texts:
        raise _fail(400, "input must not be empty")

    parsed = parse_model(request.model)
    _refuse_cloud_kind(parsed, "/v1/embeddings")
    model: str | None = parsed["literal"]
    if parsed["virtual"]:
        try:
            resolved = _usages.resolve_usage("embeddings")
            section = resolved.get("embed") or resolved.get("llm") or {}
            model = section.get("model")
        except Exception as exc:  # noqa: BLE001 — fall through to llm.embed's own default
            osh.debug(f"Could not resolve an embedder through the usage catalogue: {exc!r}")
            model = None

    vectors: list[dict[str, Any]] = []
    total_chars = 0
    for index, text in enumerate(texts):
        total_chars += len(text)
        try:
            vector = _llm.embed(text, model=model)
        except Exception as exc:  # noqa: BLE001
            osh.error(f"OpenAI embeddings failed:\n\t{exc}")
            raise _fail(502, f"the embedding backend failed: {exc}", kind="server_error") from exc
        payload: Any = vector
        if request.encoding_format == "base64":
            import struct

            payload = base64.b64encode(
                b"".join(struct.pack("<f", value) for value in vector)
            ).decode()
        vectors.append({"object": "embedding", "index": index, "embedding": payload})

    return {
        "object": "list",
        "data": vectors,
        "model": model or "best-embed",
        "usage": {
            "prompt_tokens": int(total_chars / _CHARS_PER_TOKEN),
            "total_tokens": int(total_chars / _CHARS_PER_TOKEN),
        },
    }


@router.post("/images/generations")
def images_generations(request: ImageRequest) -> dict[str, Any]:
    """
    OpenAI's image endpoint, over a local diffusion pipeline.

    ``size: "auto"`` (the default here) resolves to the chosen model's **native
    resolution**, which is the one it is good at: a 512px model asked for
    1024x1024 duplicates subjects rather than adding detail. Name a size
    explicitly to override that, and expect the quality to follow the model
    rather than the number.

    ``response_format`` defaults to ``b64_json`` rather than OpenAI's ``url``,
    because a local server has nowhere to host a file; asking for ``url``
    returns a ``data:`` URI, which every client that follows a URL can read.
    """
    from . import detect as _detect
    from . import imagine as _imagine

    if request.n < 1:
        raise _fail(400, "n must be at least 1")
    if request.n > 4:
        raise _fail(
            400,
            "n is capped at 4 here: each image is a full sampling run on this "
            "machine, not a batched call to a datacentre.",
        )

    parsed = parse_model(request.model)
    _refuse_cloud_kind(parsed, "/v1/images/generations")
    width: int | None = None
    height: int | None = None
    if request.size and request.size != "auto":
        if request.size not in _imagine.OPENAI_SIZES:
            raise _fail(
                400,
                f"unsupported size {request.size!r}; use one of "
                f"{', '.join(sorted(_imagine.OPENAI_SIZES))} or 'auto'",
            )
        width, height = _imagine.OPENAI_SIZES[request.size]

    model = parsed["literal"]
    plan: dict[str, Any] | None = None
    if parsed["virtual"]:
        from . import catalog as _catalog
        from . import score as _score

        hw = _detect.available_memory()
        compute = _detect.compute_profile()
        plan = _imagine.pick(
            _imagine.rank(
                _catalog.load_catalog(),
                budget_gb=_score.effective_budget(hw),
                bandwidth_gbs=compute.get("bandwidth_gbs"),
                width=width,
                height=height,
            )
        )
        if plan is None:
            raise _fail(
                503,
                "No image model fits this machine's memory budget. Run "
                "`best-engine-ai-helper imagine plan` to see the figures.",
                kind="server_error",
            )
        model = plan["model"]
        width, height = plan["width"], plan["height"]

    steps = request.steps or (plan["steps"] if plan else None) or 28
    created = int(time.time())
    data: list[dict[str, Any]] = []
    pipeline: Any = None
    for index in range(request.n):
        try:
            png = _imagine.generate(
                request.prompt,
                model=str(model),
                width=width or 1024,
                height=height or 1024,
                steps=steps,
                guidance=request.guidance,
                negative_prompt=request.negative_prompt,
                # A seed plus several images would return the same picture
                # n times, so it advances per image — reproducible AND distinct.
                seed=None if request.seed is None else request.seed + index,
                offload=bool(plan and plan["offload"]),
                loaded=pipeline,
            )
        except ImportError as exc:
            raise _fail(503, str(exc), kind="server_error") from exc
        except Exception as exc:  # noqa: BLE001
            osh.error(f"OpenAI image generation failed:\n\t{exc}")
            raise _fail(502, f"the image backend failed: {exc}", kind="server_error") from exc
        encoded = base64.b64encode(png).decode()
        if request.response_format == "url":
            data.append({"url": f"data:image/png;base64,{encoded}", "revised_prompt": None})
        else:
            data.append({"b64_json": encoded, "revised_prompt": None})

    return {"created": created, "data": data, "model": str(model), "size": f"{width}x{height}"}


def install_error_handlers(app: Any) -> None:
    """
    Make every ``/v1`` failure come back in OpenAI's error envelope.

    Raising ``HTTPException(detail={"error": ...})`` is not enough on its own:
    FastAPI serialises the detail under a ``detail`` key, so the envelope ends
    up nested one level too deep and an SDK that reads ``error.message`` finds
    nothing. This unwraps it — and does the same for FastAPI's own 422
    validation errors, which an OpenAI client cannot parse at all in their
    native shape.

    Scoped to ``/v1`` on purpose. ``/api/*`` is this package's own surface and
    its callers already expect FastAPI's conventions; changing those to suit a
    compatibility layer would be the tail wagging the dog, so anything outside
    ``/v1`` is handed straight back to the default handler.

    Parameters
    ----------
    app : Any
        The FastAPI application to register the handlers on.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> install_error_handlers(FastAPI()) is None
    True
    """
    from fastapi.exception_handlers import (
        http_exception_handler,
        request_validation_exception_handler,
    )
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)  # type: ignore[untyped-decorator]
    async def _openai_http_error(request: Any, exc: StarletteHTTPException) -> Any:
        if not str(request.url.path).startswith("/v1"):
            return await http_exception_handler(request, exc)
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": str(detail),
                    "type": "invalid_request_error" if exc.status_code < 500 else "server_error",
                    "param": None,
                    "code": None,
                }
            },
        )

    @app.exception_handler(RequestValidationError)  # type: ignore[untyped-decorator]
    async def _openai_validation_error(request: Any, exc: RequestValidationError) -> Any:
        if not str(request.url.path).startswith("/v1"):
            return await request_validation_exception_handler(request, exc)
        # Name the offending field: "body.messages: field required" is
        # actionable where "422 Unprocessable Entity" is not.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg')}"
            for err in exc.errors()
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": problems or "the request body is not valid",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": None,
                }
            },
        )
