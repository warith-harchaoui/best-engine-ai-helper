"""
llm — pluggable local AND cloud model backend for best-engine-ai-helper.

Provides two public functions, ``chat`` and ``embed``, that route requests to
the backend named by a resolved engine descriptor (preferred) or the
``SPREZZATURE_LLM_BACKEND`` environment variable (legacy path). Callers use
only these two functions; the transport details (Ollama JSON API vs
OpenAI-compatible REST vs Anthropic/Gemini's own formats vs LangChain) stay
invisible to them.

Supported backends
------------------
ollama
    Default. POSTs to ``{SPREZZATURE_LLM_BASE_URL}/api/generate``.
    Works offline once the model is pulled.
openai
    Any OpenAI-compatible server: vLLM, llama.cpp, LM Studio, Text Generation
    Inference, OpenAI itself, Mistral, OpenRouter, Together, Azure OpenAI.
    POSTs to ``{base_url}/v1/chat/completions``.
anthropic
    Claude's own Messages API (``POST {base_url}/v1/messages``).
gemini
    Google's own generateContent API
    (``POST {base_url}/v1beta/models/{model}:generateContent``).
langchain
    Thin wrapper over ``ChatOllama`` or ``ChatOpenAI`` from LangChain.
    Only useful if you need LangChain retrievers or agent abstractions.

A cloud engine descriptor (``engine.resolve`` with ``mode: cloud``) carries an
embedded local ``fallback``; :func:`chat` tries the cloud primary first and
falls over to the local fallback on failure (paid -> local, the safe
direction) — see ``engine=`` below and :mod:`best_engine_ai_helper.engine`.

Environment variables
---------------------
SPREZZATURE_LLM_BACKEND
    ``ollama`` | ``openai`` | ``anthropic`` | ``gemini`` | ``langchain``.
    Defaults to ``ollama``. Only consulted on the legacy no-``engine`` path.
SPREZZATURE_LLM_BASE_URL
    Base URL of the server. Defaults to ``http://localhost:11434``.
BEST_LLM_TEXT (legacy alias: SPREZZATURE_LLM_TEXT)
    Model tag for text-only prompts. When unset, falls back to the selection
    persisted by ``pull`` in ``~/.best-engine-ai-helper/config.json``, then to
    the ``qwen3:8b`` default. Resolved by :func:`config.text_model`.
BEST_LLM_VISION (legacy alias: SPREZZATURE_LLM_VISION)
    Model tag for prompts that include images. Same precedence as the text
    model; resolved by :func:`config.vision_model`.
SPREZZATURE_LLM_API_KEY
    API key for servers that require one on the legacy path. Empty string by
    default (most local servers do not require authentication). On the
    ``engine=`` path, the key comes from the env var NAMED in the engine's
    ``api_key_env`` field instead (never the key value itself, never
    persisted) — see :func:`_cloud_api_key`.

Observability
-------------
Every :func:`chat` call fans a small event dict out to any observer registered
via :func:`add_observer` (backend, model, kind, char counts, real token counts
when the provider reports them, latency, success/error). No observer is
registered by default. :mod:`best_engine_ai_helper.observe` provides a
SQLite-backed sink (call ``observe.enable()``) that turns this into a
queryable local activity/cost ledger, surfaced by the ``activity`` CLI command
and the ``/api/activity`` endpoint.

Privacy and safety (cloud calls only)
--------------------------------------
``chat(..., pseudonymize=True)`` scrubs personal data from the prompt with a
local LLM before it reaches a cloud provider, and restores it in the response
— see :mod:`best_engine_ai_helper.privacy`. ``chat(..., safety=True)`` (the
default when the resolved engine is a cloud one) scans the prompt/images
before sending and the response after receiving for policy violations — see
:mod:`best_engine_ai_helper.safety`. Both are no-ops on a local engine.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import base64
import copy
import json
import os
import time
from collections.abc import Callable
from typing import Any, cast

import os_helper as osh

# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------

# Backends that speak the OpenAI Chat Completions wire format, so they route
# through ``_chat_openai``: a local vLLM server, and every OpenAI-compatible
# cloud provider (OpenAI itself, Mistral, OpenRouter, Together, Azure OpenAI).
# Anthropic and Gemini use their own wire formats (`_chat_anthropic` /
# `_chat_gemini`).
_OPENAI_COMPATIBLE = frozenset(
    {"vllm", "openai", "mistral", "openrouter", "together", "azure"}
)

# Backends that are never local — used to decide whether privacy/safety
# defaults apply and whether a backend can ever be "free" for cost purposes
# (see observe.py's `_FREE_BACKENDS`, the inverse list).
_CLOUD_BACKENDS = frozenset(
    {"openai", "mistral", "openrouter", "together", "azure", "anthropic", "gemini"}
)

# ---------------------------------------------------------------------------
# Observability seam
# ---------------------------------------------------------------------------
# Every call to `chat` funnels through here; registered observers get a small
# event dict so monitoring (the SQLite ledger in `observe.py`, a dashboard, a
# custom sink) can be built on top without changing `chat`'s behaviour. No
# observer is registered by default, so this is a no-op until something opts
# in (see `observe.enable()`).
_OBSERVERS: list[Callable[[dict[str, Any]], None]] = []


def add_observer(fn: Callable[[dict[str, Any]], None]) -> None:
    """
    Register a per-call observer; it receives the event dict :func:`chat` emits.

    Parameters
    ----------
    fn : callable
        Called with one event dict after every :func:`chat` call, success or
        failure. Must not raise — an exception is caught and logged, never
        propagated, so a broken observer can't take down inference.
    """
    _OBSERVERS.append(fn)


def clear_observers() -> None:
    """Remove all registered observers (chiefly for tests, or to disable)."""
    _OBSERVERS.clear()


def _emit(event: dict[str, Any]) -> None:
    """Fan an event out to every registered observer; a raising observer never breaks the caller."""
    for fn in _OBSERVERS:
        try:
            fn(event)
        except Exception as exc:  # noqa: BLE001 — observability must not break inference
            osh.warning(f"LLM observer raised, ignoring: {exc!r}")


def _backend() -> str:
    """Return the configured backend name, lower-cased."""
    return os.environ.get("SPREZZATURE_LLM_BACKEND", "ollama").lower()


def _base_url() -> str:
    """Return the server base URL, stripping any trailing slash."""
    return os.environ.get("SPREZZATURE_LLM_BASE_URL", "http://localhost:11434").rstrip("/")


def _text_model() -> str:
    """Return the configured text model tag.

    Delegates to :func:`config.text_model`, so the transport honours the same
    precedence as every other consumer — ``BEST_LLM_TEXT`` (or the legacy
    ``SPREZZATURE_LLM_TEXT``) env, then the ``config.json`` written by
    ``pull``, then the built-in default. This closes the old gap where the
    transport read only ``SPREZZATURE_LLM_TEXT`` and ignored a fresh `pull`
    selection persisted under ``BEST_LLM_TEXT``.
    """
    from .config import text_model

    return text_model()


def _vision_model() -> str:
    """Return the configured vision model tag.

    Mirror of :func:`_text_model` for image prompts; delegates to
    :func:`config.vision_model`.
    """
    from .config import vision_model

    return vision_model()


def _api_key() -> str:
    """Return the legacy-path API key; empty string means no authentication required."""
    return os.environ.get("SPREZZATURE_LLM_API_KEY", "")


def _cloud_api_key(engine_dict: dict[str, Any] | None) -> str:
    """
    Resolve a cloud provider's API key without ever persisting the value.

    Precedence: the env var NAMED in ``engine_dict["api_key_env"]`` (the
    engine descriptor stores only the variable's *name* — see
    :func:`engine._resolve_cloud`) — then, if the optional ``keyring``
    package is installed, the OS keychain entry
    ``("best-engine-ai-helper", api_key_env)`` — else empty.

    Parameters
    ----------
    engine_dict : dict or None
        The resolved engine descriptor for the kind in use, or None on the
        legacy path (falls back to :func:`_api_key`).

    Returns
    -------
    str
        The API key, or ``""`` when none is configured anywhere.
    """
    if not engine_dict:
        return _api_key()
    env_name = engine_dict.get("api_key_env")
    if not env_name:
        return _api_key()
    key = os.environ.get(env_name, "")
    if key:
        return key
    try:
        import keyring

        return keyring.get_password("best-engine-ai-helper", env_name) or ""
    except ImportError:
        return ""


def _timeout() -> float:
    """Per-request timeout in seconds (``SPREZZATURE_LLM_TIMEOUT``, default 120).

    A light local model answers a validation prompt in seconds; a bounded
    timeout keeps ``validate`` / ``pull`` from stalling forever on a model that
    is too heavy for the machine or a daemon that never responds. Set it higher
    only when you knowingly run a large model on modest hardware.
    """
    try:
        return float(os.environ.get("SPREZZATURE_LLM_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def _resolve_model(model: str | None, images: list[bytes] | None) -> str:
    """
    Pick the correct model tag for a request.

    The caller may pass an explicit model tag. When the tag is absent, the
    function selects the vision model if images are present and the text model
    otherwise. This matches how Ollama's own model selection works.

    Parameters
    ----------
    model : str or None
        Explicit model tag from the caller. Takes precedence over env vars.
    images : list[bytes] or None
        Image bytes attached to the prompt. Non-empty means a VLM is needed.

    Returns
    -------
    str
        The resolved model tag.
    """
    if model is not None:
        return model
    # Images require a vision-capable model
    if images:
        return _vision_model()
    return _text_model()


# ---------------------------------------------------------------------------
# Ollama structured-output schema shaping
# ---------------------------------------------------------------------------


def _merge_tag_property(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Combine one property seen in several union branches. When it is the
    discriminator (a ``const``/``enum`` string, e.g. ``operation_type``), fold
    every branch's value into a single ``enum`` so the model must pick one of
    them; otherwise keep the first definition."""
    values: list[Any] = []
    for node in (existing, incoming):
        if "const" in node:
            values.append(node["const"])
        elif "enum" in node:
            values.extend(node["enum"])
    if values:
        seen: list[Any] = []
        for v in values:
            if v not in seen:
                seen.append(v)
        return {"type": "string", "enum": seen}
    return existing


def _flatten_object_union(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse a discriminated union of object schemas into ONE permissive
    object: the union of all branches' properties (the discriminator becomes an
    enum of every tag), required = only what every branch requires (the tag).

    Ollama's structured-output grammar cannot build a ``oneOf``/``anyOf`` of
    ``$ref`` branches -- it then admits only an empty value -- but it handles a
    single tagged object fine. The caller's Pydantic model re-validates the
    result against the real discriminated union, so per-branch correctness is
    still enforced downstream; this only widens what the grammar will emit.
    """
    object_members = [m for m in members if m.get("type") == "object"]
    props: dict[str, Any] = {}
    tag_hits: dict[str, int] = {}  # key -> how many branches pin it to a const/enum
    required_sets: list[set[str]] = []
    for member in object_members:
        for key, sub in member.get("properties", {}).items():
            props[key] = _merge_tag_property(props[key], sub) if key in props else sub
            if "const" in sub or "enum" in sub:
                tag_hits[key] = tag_hits.get(key, 0) + 1
        required_sets.append(set(member.get("required", [])))
    required = set.intersection(*required_sets) if required_sets else set()
    # A property every branch pins to a const/enum is the discriminator (e.g.
    # operation_type / kind). Pydantic gives it a default so it is not in any
    # branch's "required", but the grammar MUST force it or the model omits it
    # and the union can't be resolved. Require it explicitly.
    n = len(object_members)
    required |= {key for key, hits in tag_hits.items() if hits == n}
    return {"type": "object", "properties": props, "required": sorted(required)}


def _shape_schema_for_ollama(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite a Pydantic JSON Schema into a form Ollama's structured-output
    grammar accepts: inline every ``$ref`` (Ollama ignores ``$defs``) and
    flatten each ``oneOf``/``anyOf`` of objects into a single tagged object.

    Non-union schemas (intent, plain models) pass through essentially
    unchanged. Returns a new dict; the input is never mutated.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any, seen: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [walk(item, seen) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            if name in seen or name not in defs:
                return {"type": "object"}  # cycle or dangling ref: permissive stub
            return walk(copy.deepcopy(defs[name]), seen + (name,))

        for union_key in ("oneOf", "anyOf"):
            if union_key in node:
                members = [walk(m, seen) for m in node[union_key]]
                object_members = [
                    m for m in members if isinstance(m, dict) and m.get("type") == "object"
                ]
                if len(object_members) >= 2:
                    return _flatten_object_union(object_members)
                # Not an object union (e.g. str | null): keep the first concrete
                # (non-null) branch so the grammar has a single shape to target.
                concrete = [m for m in members if isinstance(m, dict) and m.get("type") != "null"]
                return concrete[0] if concrete else members[0]

        return {
            key: walk(value, seen)
            for key, value in node.items()
            if key not in ("$defs", "discriminator")
        }

    shaped = walk(copy.deepcopy(schema), ())
    return shaped if isinstance(shaped, dict) else {"type": "object"}


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------


def _chat_ollama(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str,
    temperature: float,
    base_url: str | None = None,
) -> tuple[str, dict[str, int | None]]:
    """
    Send a chat request to the Ollama /api/generate endpoint.

    Parameters
    ----------
    prompt : str
        User prompt.
    system : str or None
        Optional system prompt prepended to the conversation.
    images : list[bytes] or None
        Raw PNG/JPEG bytes; encoded to base64 before sending.
    json_schema : dict or None
        When provided, passed as Ollama's ``format`` so generation is
        grammar-constrained to that JSON Schema (structured outputs, Ollama
        0.5+). This is stronger than the old ``format: "json"`` free-JSON mode:
        the response is guaranteed to match the schema's shape, not merely be
        valid JSON of an arbitrary shape.
    model : str
        Ollama model tag, e.g. ``"qwen3:8b"``.
    temperature : float
        Sampling temperature.

    Returns
    -------
    tuple[str, dict]
        The model's text response, and a usage dict (``in_tokens``/
        ``out_tokens``, from Ollama's ``prompt_eval_count``/``eval_count``
        when present, else None — Ollama omits them for some model/runtime
        combinations).

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the response lacks a ``response`` field.
    """
    import requests  # imported lazily; requests is a hard dep but keep imports local

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # Options dict carries temperature; Ollama ignores unknown keys
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    if images:
        # Ollama expects a list of base64-encoded strings, not raw bytes
        payload["images"] = [base64.b64encode(img).decode() for img in images]
    if json_schema is not None:
        # Pass the schema so Ollama constrains generation to match it (structured
        # outputs), shaped so its grammar can build: $refs inlined, discriminated
        # unions flattened to a tagged object (see _shape_schema_for_ollama).
        payload["format"] = _shape_schema_for_ollama(json_schema)

    url = f"{(base_url or _base_url()).rstrip('/')}/api/generate"
    try:
        resp = requests.post(url, json=payload, timeout=_timeout())
        resp.raise_for_status()
    except requests.RequestException as exc:
        osh.error(f"Ollama request failed:\n\t{url}\n\t{exc}")
        raise RuntimeError(f"Ollama request to {url} failed: {exc}") from exc

    data = resp.json()
    if "response" not in data:
        osh.error(f"Ollama response missing 'response' field: {data!r}")
        raise RuntimeError(f"Ollama response missing 'response' field: {data!r}")
    usage = {"in_tokens": data.get("prompt_eval_count"), "out_tokens": data.get("eval_count")}
    return str(data["response"]), usage


# ---------------------------------------------------------------------------
# OpenAI-compatible backend
# ---------------------------------------------------------------------------


def _chat_openai(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str,
    temperature: float,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, dict[str, int | None]]:
    """
    Send a chat request to an OpenAI-compatible /v1/chat/completions endpoint.

    Covers vLLM, llama.cpp in server mode, LM Studio, Text Generation
    Inference, OpenAI, Mistral, OpenRouter, Together, and Azure OpenAI — all
    speak the same Chat Completions wire format.

    Parameters
    ----------
    prompt : str
        User prompt.
    system : str or None
        Optional system message.
    images : list[bytes] or None
        Raw image bytes; encoded as data URIs in the ``image_url`` content part.
    json_schema : dict or None
        When provided, sets ``response_format`` to a ``json_schema`` object so
        servers that support it (vLLM, recent llama.cpp, OpenAI) constrain the
        output to the schema. Servers that only understand ``json_object`` still
        get a JSON-mode request via the same field's fallback shape.
    model : str
        Model ID, e.g. ``"qwen3:8b"`` or a HuggingFace model path.
    temperature : float
        Sampling temperature.
    api_key : str or None
        Bearer token. None/empty means no ``Authorization`` header (the
        legacy env path's ``_api_key()``; the ``engine=`` path passes
        :func:`_cloud_api_key`'s result explicitly instead).

    Returns
    -------
    tuple[str, dict]
        The model's text response from ``choices[0].message.content``, and a
        usage dict (``in_tokens``/``out_tokens`` from ``usage.prompt_tokens``/
        ``usage.completion_tokens`` when the server reports them, else None).

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the response is malformed.
    """
    import requests

    # Build the message list following the OpenAI multi-modal message format
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})

    # User content is either a plain string or a list of content parts (multi-modal)
    if images:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img_bytes in images:
            b64 = base64.b64encode(img_bytes).decode()
            # Data URI format required by the vision spec
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_schema is not None:
        # Prefer structured json_schema; a server that only knows json_object
        # will ignore the extra "json_schema" key and still return JSON.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": json_schema, "strict": True},
        }

    # Accept a base URL with or without a trailing ``/v1`` (an engine descriptor's
    # vLLM base_url may include it; the env default does not).
    base = (base_url or _base_url()).rstrip("/")
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = api_key if api_key is not None else _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout())
        resp.raise_for_status()
    except requests.RequestException as exc:
        osh.error(f"OpenAI-compat request failed:\n\t{url}\n\t{exc}")
        raise RuntimeError(f"OpenAI-compat request to {url} failed: {exc}") from exc

    data = resp.json()
    try:
        text = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError) as exc:
        osh.error(f"Malformed completion response: {data!r}")
        raise RuntimeError(f"Malformed completion response: {data!r}") from exc

    usage_obj = data.get("usage") or {}
    usage = {
        "in_tokens": usage_obj.get("prompt_tokens"),
        "out_tokens": usage_obj.get("completion_tokens"),
    }
    return text, usage


# ---------------------------------------------------------------------------
# LangChain backend
# ---------------------------------------------------------------------------


def _chat_langchain(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str,
    temperature: float,
) -> tuple[str, dict[str, int | None]]:
    """
    Send a chat request via LangChain wrappers.

    Selects ``ChatOllama`` when SPREZZATURE_LLM_BACKEND is ``langchain`` and
    the base URL points to an Ollama server; falls back to ``ChatOpenAI`` for
    any other base URL. Both wrappers share the same invoke signature.

    Parameters
    ----------
    prompt : str
        User prompt.
    system : str or None
        System message prepended as a SystemMessage.
    images : list[bytes] or None
        Images are not supported by all LangChain models; a RuntimeError is
        raised when images are supplied and the model does not accept them.
    json_mode : bool
        When True, instructs the model to respond in JSON. Implementation
        varies by LangChain version; a system hint is added as a fallback.
    model : str
        Model identifier passed to the LangChain wrapper.
    temperature : float
        Sampling temperature.

    Returns
    -------
    tuple[str, dict]
        The model's text response, and an empty usage dict (LangChain's usage
        metadata shape varies by wrapper/version; cost falls back to the
        char-count heuristic for this transport — see ``observe.py``).

    Raises
    ------
    ImportError
        If the required LangChain package is not installed.
    RuntimeError
        If images are supplied but the model does not support them.
    """
    base = _base_url()

    # Decide which LangChain wrapper to use based on the server URL
    if "11434" in base or "localhost" in base:
        try:
            from langchain_ollama import ChatOllama

            llm = ChatOllama(model=model, temperature=temperature, base_url=base)
        except ImportError as exc:
            raise ImportError(
                "langchain_ollama is not installed. Run: pip install langchain-ollama"
            ) from exc
    else:
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                base_url=f"{base}/v1",
                api_key=_api_key() or "none",
            )
        except ImportError as exc:
            raise ImportError(
                "langchain_openai is not installed. Run: pip install langchain-openai"
            ) from exc

    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

    msgs: list[BaseMessage] = []
    if system:
        msgs.append(SystemMessage(content=system))

    # LangChain multi-modal message support varies; raise clearly when unsupported
    if images:
        raise RuntimeError(
            "Images are not uniformly supported across LangChain backends. "
            "Use the 'ollama' or 'openai' backend for vision prompts."
        )

    if json_schema is not None:
        # Portable fallback across LangChain versions: instruct via the system
        # prompt and show the exact schema the JSON must satisfy.
        hint = (
            "Respond ONLY with valid JSON matching this JSON Schema. "
            "No prose, no markdown fences.\n" + json.dumps(json_schema)
        )
        msgs.append(SystemMessage(content=hint))

    msgs.append(HumanMessage(content=prompt))
    result = llm.invoke(msgs)
    # AIMessage.content is always a string in LangChain >= 0.2
    return str(result.content), {"in_tokens": None, "out_tokens": None}


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------


def _chat_anthropic(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str,
    temperature: float,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, dict[str, int | None]]:
    """
    Send a chat request to Anthropic's Messages API.

    Parameters
    ----------
    prompt : str
        User prompt.
    system : str or None
        Optional system prompt (a top-level ``system`` field, not a message
        with role ``system`` — Anthropic's Messages API keeps it separate).
    images : list[bytes] or None
        Raw image bytes; sent as base64 ``image`` content blocks (JPEG/PNG
        auto-detected by magic bytes, defaulting to PNG).
    json_schema : dict or None
        Anthropic has no native structured-output mode as of this writing;
        the schema is appended to the prompt as an instruction instead, and
        the response is parsed as JSON by the caller (:func:`chat`) same as
        every other backend — best-effort, not grammar-constrained.
    model : str
        Model ID, e.g. ``"claude-3-5-sonnet-20241022"``.
    temperature : float
        Sampling temperature.
    base_url : str or None
        Defaults to ``https://api.anthropic.com``.
    api_key : str or None
        Required — Anthropic rejects unauthenticated requests.

    Returns
    -------
    tuple[str, dict]
        The model's text response from ``content[0].text``, and a usage dict
        (``in_tokens``/``out_tokens`` from ``usage.input_tokens``/
        ``usage.output_tokens``).

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the response is malformed.
    """
    import requests

    user_prompt = prompt
    if json_schema is not None:
        user_prompt = (
            f"{prompt}\n\nRespond ONLY with valid JSON matching this JSON Schema. "
            f"No prose, no markdown fences.\n{json.dumps(json_schema)}"
        )

    content: str | list[dict[str, Any]]
    if images:
        parts: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for img_bytes in images:
            # JPEG starts with 0xFFD8; anything else is treated as PNG.
            media_type = "image/jpeg" if img_bytes[:2] == b"\xff\xd8" else "image/png"
            parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(img_bytes).decode(),
                },
            })
        content = parts
    else:
        content = user_prompt

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        payload["system"] = system

    base = (base_url or "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key or "",
        "anthropic-version": "2023-06-01",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout())
        resp.raise_for_status()
    except requests.RequestException as exc:
        osh.error(f"Anthropic request failed:\n\t{url}\n\t{exc}")
        raise RuntimeError(f"Anthropic request to {url} failed: {exc}") from exc

    data = resp.json()
    try:
        text = str(data["content"][0]["text"])
    except (KeyError, IndexError) as exc:
        osh.error(f"Malformed Anthropic response: {data!r}")
        raise RuntimeError(f"Malformed Anthropic response: {data!r}") from exc

    usage_obj = data.get("usage") or {}
    usage = {
        "in_tokens": usage_obj.get("input_tokens"),
        "out_tokens": usage_obj.get("output_tokens"),
    }
    return text, usage


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------


def _chat_gemini(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str,
    temperature: float,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, dict[str, int | None]]:
    """
    Send a chat request to Google's Gemini generateContent API.

    Parameters
    ----------
    prompt : str
        User prompt.
    system : str or None
        Optional system instruction (Gemini's ``systemInstruction`` field).
    images : list[bytes] or None
        Raw image bytes; sent as inline base64 ``inlineData`` parts (assumes
        PNG — Gemini also accepts JPEG/WebP but this suite only ever produces
        PNG screenshots for vision prompts).
    json_schema : dict or None
        When provided, sets ``generationConfig.responseMimeType`` to
        ``application/json`` and ``responseSchema`` to the (Gemini-flavoured
        subset of) JSON Schema — Gemini DOES support grammar-constrained JSON
        output, unlike Anthropic.
    model : str
        Model ID, e.g. ``"gemini-1.5-pro"``.
    temperature : float
        Sampling temperature.
    base_url : str or None
        Defaults to ``https://generativelanguage.googleapis.com/v1beta``.
    api_key : str or None
        Required — passed as the ``key`` query parameter (Gemini's own
        convention; not a bearer header).

    Returns
    -------
    tuple[str, dict]
        The model's text response from
        ``candidates[0].content.parts[0].text``, and a usage dict
        (``in_tokens``/``out_tokens`` from ``usageMetadata.promptTokenCount``/
        ``usageMetadata.candidatesTokenCount``).

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the response is malformed.
    """
    import requests

    parts: list[dict[str, Any]] = [{"text": prompt}]
    for img_bytes in images or []:
        parts.append({
            "inlineData": {"mimeType": "image/png", "data": base64.b64encode(img_bytes).decode()}
        })

    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if json_schema is not None:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = _strip_unsupported_schema_keys(json_schema)

    base = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base}/models/{model}:generateContent"

    try:
        resp = requests.post(
            url, json=payload, params={"key": api_key or ""}, timeout=_timeout()
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        osh.error(f"Gemini request failed:\n\t{url}\n\t{exc}")
        raise RuntimeError(f"Gemini request to {url} failed: {exc}") from exc

    data = resp.json()
    try:
        text = str(data["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError) as exc:
        osh.error(f"Malformed Gemini response: {data!r}")
        raise RuntimeError(f"Malformed Gemini response: {data!r}") from exc

    usage_obj = data.get("usageMetadata") or {}
    usage = {
        "in_tokens": usage_obj.get("promptTokenCount"),
        "out_tokens": usage_obj.get("candidatesTokenCount"),
    }
    return text, usage


def _strip_unsupported_schema_keys(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Drop JSON Schema keywords Gemini's ``responseSchema`` does not understand.

    Gemini accepts an OpenAPI-3.0-flavoured subset of JSON Schema; keys like
    ``$defs``/``$ref``/``additionalProperties``/``title`` make it reject the
    request outright. This is a shallow best-effort strip (recursive over
    ``properties``/``items``), not a full OpenAPI-schema converter — schemas
    with unresolved ``$ref``\\ s should go through :func:`_shape_schema_for_ollama`-
    style inlining first if they need to reach Gemini.

    Parameters
    ----------
    schema : dict
        A JSON Schema (typically Pydantic's ``model_json_schema()`` output).

    Returns
    -------
    dict
        A copy with unsupported keys removed at every level.
    """
    _DROP = {"$defs", "$ref", "additionalProperties", "title", "discriminator"}

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: strip(v) for k, v in node.items() if k not in _DROP}
            return out
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return cast(dict[str, Any], strip(copy.deepcopy(schema)))


# ---------------------------------------------------------------------------
# Failover chain + retry + cache
# ---------------------------------------------------------------------------
# A cloud engine embeds a local `fallback` (see engine._resolve_cloud); chat()
# tries each engine in the chain in order and only moves to the next on
# failure, so a paid-provider outage degrades to the always-available local
# model instead of raising.


def _load_engine(engine: Any) -> Any:
    """Load an engine path into a dict; pass a dict/list/None through unchanged."""
    if engine is None or isinstance(engine, (dict, list)):
        return engine
    from . import engine as _engine

    return _engine.load_engine(engine)


def _engine_capable(eng: Any, kind: str, needs_schema: bool) -> bool:
    """Whether an engine descriptor can serve ``kind`` (and a schema if needed)."""
    if not isinstance(eng, dict):
        return True  # env path / unknown — assume capable
    section = eng.get(kind)
    if not section or not section.get("model"):
        return False
    if needs_schema and section.get("structured_output") is False:
        return False
    return True


def _engine_chain(engine: Any, kind: str, needs_schema: bool) -> list[Any]:
    """
    Build the ordered failover chain from ``engine``.

    Parameters
    ----------
    engine : dict | str | list | None
        A resolved engine descriptor, a path to one, an explicit list of
        descriptors (caller-defined chain), or None (legacy env path).
    kind : str
        ``"llm"`` or ``"vlm"`` — which section of each engine to check.
    needs_schema : bool
        Whether the caller requested structured JSON output.

    Returns
    -------
    list
        A non-empty ordered list of engines to try. A single cloud engine's
        embedded ``fallback`` is appended after it (paid -> local). Engines
        that cannot serve ``kind`` (or a schema when required) are dropped
        unless that would empty the chain.
    """
    if engine is None:
        return [None]
    if isinstance(engine, list):
        chain = [_load_engine(e) for e in engine]
    else:
        eng = _load_engine(engine)
        chain = [eng]
        fb = eng.get("fallback") if isinstance(eng, dict) else None
        if fb:
            chain.append(fb)
    capable = [e for e in chain if _engine_capable(e, kind, needs_schema)]
    return capable or chain


def _resolve_target(
    eng: Any, model: str | None, images: list[bytes] | None, kind: str | None
) -> tuple[str, str | None, str, str, dict[str, Any] | None]:
    """Return ``(backend, base_url, model, transport, engine_kind_dict)`` for one engine."""
    if eng is not None:
        from . import engine as _engine

        k = kind or ("vlm" if images else "llm")
        backend, base_url, engine_model = _engine.model_for(eng, k)
        default_transport = "openai" if backend in _OPENAI_COMPATIBLE else backend
        transport = _TRANSPORT_BY_BACKEND.get(backend, default_transport)
        engine_kind_dict = eng.get(k) if isinstance(eng, dict) else None
        return backend, base_url, model or engine_model, transport, engine_kind_dict
    resolved = _resolve_model(model, images)
    backend = _backend()
    return backend, None, resolved, backend, None


# Wire-format transport per backend name, for backends whose transport name
# differs from the backend name itself (every OpenAI-compatible backend maps
# to "openai"; anthropic/gemini/ollama/langchain map to themselves).
_TRANSPORT_BY_BACKEND: dict[str, str] = {"anthropic": "anthropic", "gemini": "gemini"}


def _dispatch(
    transport: str, prompt: str, *,
    system: str | None, images: list[bytes] | None,
    json_schema: dict[str, Any] | None,
    model: str, temperature: float, base_url: str | None,
    api_key: str | None,
) -> tuple[str, dict[str, int | None]]:
    """Run one transport call. Raises on failure; performs no logging/emit."""
    if transport == "ollama":
        return _chat_ollama(prompt, system=system, images=images,
                            json_schema=json_schema, model=model,
                            temperature=temperature, base_url=base_url)
    if transport == "openai":
        return _chat_openai(prompt, system=system, images=images,
                           json_schema=json_schema, model=model,
                           temperature=temperature, base_url=base_url, api_key=api_key)
    if transport == "anthropic":
        return _chat_anthropic(prompt, system=system, images=images,
                              json_schema=json_schema, model=model,
                              temperature=temperature, base_url=base_url, api_key=api_key)
    if transport == "gemini":
        return _chat_gemini(prompt, system=system, images=images,
                           json_schema=json_schema, model=model,
                           temperature=temperature, base_url=base_url, api_key=api_key)
    if transport == "langchain":
        return _chat_langchain(prompt, system=system, images=images,
                              json_schema=json_schema, model=model,
                              temperature=temperature)
    raise ValueError(
        f"Unknown backend: {transport!r}. "
        "Valid values: 'ollama', 'openai', 'anthropic', 'gemini', 'langchain'."
    )


_RunResult = tuple[str, dict[str, int | None]]


def _with_retry(fn: Callable[[], _RunResult], retries: int) -> _RunResult:
    """Call ``fn``, retrying transient transport errors up to ``retries`` times.

    Uses tenacity (exponential backoff) when installed, else a light
    immediate-retry loop. Only ``RuntimeError`` (the transport's transient
    failure) is retried.
    """
    if retries <= 0:
        return fn()
    try:
        import tenacity
    except ImportError:
        last: Exception | None = None
        for _ in range(retries + 1):
            try:
                return fn()
            except RuntimeError as exc:
                last = exc
        raise last  # type: ignore[misc]
    retryer = tenacity.Retrying(
        stop=tenacity.stop_after_attempt(retries + 1),
        wait=tenacity.wait_exponential(multiplier=0.5, max=8),
        retry=tenacity.retry_if_exception_type(RuntimeError),
        reraise=True,
    )
    return retryer(fn)


def _cache_key_payload(
    backend: str, model: str, kind: str, prompt: str, system: str | None,
    json_schema: dict[str, Any] | None, temperature: float,
    images: list[bytes] | None,
) -> dict[str, Any]:
    """The semantic signature of a call — what determines its result.

    Excludes the machine-specific engine descriptor, so two machines calling the
    same model with the same prompt share a cache hit.
    """
    import hashlib

    return {
        "backend": backend, "model": model, "kind": kind, "prompt": prompt,
        "system": system, "temperature": temperature, "json_schema": json_schema,
        "images": [hashlib.sha256(i).hexdigest() for i in (images or [])],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat(
    prompt: str,
    *,
    system: str | None = None,
    images: list[bytes] | None = None,
    json_schema: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    engine: dict[str, Any] | str | list[Any] | None = None,
    kind: str | None = None,
    cache: bool = False,
    retries: int = 0,
    pseudonymize: bool = False,
    safety: bool | None = None,
) -> str | dict[str, Any]:
    """
    Send a prompt to the configured model (local or cloud) and return the response.

    The backend and model come from one of two sources. When ``engine`` is given
    (the suite's preferred path), it is read from a resolved engine descriptor —
    the gitignored ``llm.engine.yaml`` a repo gets from ``best-engine-ai-helper
    resolve``. A cloud engine's embedded local ``fallback`` is tried after the
    cloud primary on failure (paid -> local); pass a list of descriptors to
    define your own failover order instead. Otherwise the legacy env path
    applies: the backend is ``SPREZZATURE_LLM_BACKEND`` and the model resolves
    via env / persisted config.

    Parameters
    ----------
    prompt : str
        User-facing prompt text.
    system : str or None
        System-level instructions sent before the user prompt. Use for persona,
        output format constraints, or house style rules.
    images : list[bytes] or None
        Raw image bytes (PNG or JPEG). When provided, the vision model is used
        unless ``model`` is specified explicitly.
    json_schema : dict or None
        When provided, the response is constrained to this JSON Schema where the
        backend supports grammar-constrained output (Ollama, Gemini); other
        backends (OpenAI-compatible via ``response_format``, Anthropic via a
        prompt instruction) parse best-effort, same as every backend's fallback
        when the model still returns non-JSON.
    model : str or None
        Override the model tag/id. Wins over both the engine descriptor and the
        env default. When absent with no engine, defaults to the vision model
        when images are present, else the text model.
    temperature : float
        Sampling temperature. Lower values are more deterministic. Defaults to
        0.2 because structured extraction tasks benefit from low variance.
    engine : dict | str | list | None
        A resolved engine descriptor (dict from :func:`engine.resolve` /
        :func:`engine.ensure`, or a path to ``llm.engine.yaml``), or an explicit
        list of descriptors to try in order. When given, its ``backend`` /
        ``base_url`` and the per-kind ``model`` drive the request.
    kind : {'llm', 'vlm'} or None
        Which model to use from ``engine``. Defaults to ``vlm`` when images are
        present, else ``llm``. Ignored when ``engine`` is None.
    cache : bool
        Memoize identical calls (same backend/model/prompt/schema/images) via
        ``wallet-helper`` (the ``[cache]`` extra) so a repeated call never pays
        for the same cloud request twice. A no-op with a warning if the extra
        is not installed. Ignored on the legacy env path (no engine to key on).
    retries : int
        Retry a transient transport failure this many times (exponential
        backoff via ``tenacity`` when installed, immediate retry otherwise)
        before moving to the next engine in the failover chain.
    pseudonymize : bool
        Scrub personal data from ``prompt`` with a local LLM before it reaches
        a cloud engine, and restore it in the response — see
        :mod:`best_engine_ai_helper.privacy`. No-op on a local engine, or when
        the cloud engine has no local ``fallback`` to do the scrubbing with
        (warns in that case rather than silently skipping).
    safety : bool or None
        Scan the prompt/images before sending and the response after
        receiving for policy violations — see
        :mod:`best_engine_ai_helper.safety`. ``None`` (the default) resolves
        to True for a cloud engine, False for a local one; pass an explicit
        bool to override that default in either direction.

    Returns
    -------
    str or dict
        When ``json_schema`` is provided and the model returns valid JSON, the
        result is parsed and returned as a dict. Otherwise a plain string.

    Raises
    ------
    RuntimeError
        If every engine in the failover chain fails, or (with no ``engine``)
        the single legacy-path backend is unreachable or returns a malformed
        response.
    ValueError
        If a backend name (env path) or transport (engine path) is unrecognised.

    Examples
    --------
    >>> # Text prompt (no model running needed for this docstring to parse)
    >>> # result = chat("Summarise this paper in one sentence.")
    >>> # Vision prompt
    >>> # with open("chart.png", "rb") as f:
    >>> #     result = chat("Describe the chart.", images=[f.read()])
    """
    # json_schema presence is the signal to request structured JSON output
    json_mode = json_schema is not None
    resolved_kind = kind or ("vlm" if images else "llm")

    # Ordered failover chain: primary(s) first, a cloud engine's local fallback
    # after it (paid -> local). Try each until one succeeds.
    chain = _engine_chain(engine, resolved_kind, json_mode)
    last_exc: Exception | None = None

    for attempt, eng in enumerate(chain):
        backend, base_url, resolved_model, transport, kind_dict = _resolve_target(
            eng, model, images, kind
        )
        is_cloud = backend in _CLOUD_BACKENDS or bool(kind_dict and kind_dict.get("cloud"))
        # api_key_env lives on the TOP-LEVEL engine dict (see engine._resolve_cloud),
        # not the per-kind section `kind_dict` carries — never read the key from there.
        api_key = _cloud_api_key(eng if isinstance(eng, dict) else None) if is_cloud else None

        # Privacy: scrub personal data from the prompt before it leaves the
        # machine, using the engine's LOCAL fallback to do the scrubbing
        # (never the cloud engine itself). Restored on the response below.
        send_prompt = prompt
        restore_map: dict[str, str] | None = None
        if pseudonymize and is_cloud:
            fallback_eng = eng.get("fallback") if isinstance(eng, dict) else None
            if fallback_eng:
                from . import privacy as _privacy

                send_prompt, restore_map = _privacy.pseudonymize(prompt, fallback_eng)
            else:
                osh.warning(
                    "pseudonymize=True but this engine has no local fallback to "
                    "scrub with; sending the prompt unscrubbed"
                )

        # Safety: scan the (possibly scrubbed) prompt and any images before
        # sending. Defaults to on for a cloud engine, off for local.
        do_safety = safety if safety is not None else is_cloud
        if do_safety:
            from . import safety as _safety

            _safety.check_text(send_prompt, direction="outbound")
            for img in images or []:
                _safety.check_image(img, direction="outbound")

        osh.info(
            f"chat via {backend}: model={resolved_model}, "
            f"images={len(images) if images else 0}, json={json_mode}, attempt={attempt}"
        )
        t0 = time.perf_counter()
        cached = False

        def _run(
            _t: str = transport, _p: str = send_prompt, _m: str = resolved_model,
            _u: str | None = base_url, _k: str | None = api_key,
        ) -> tuple[str, dict[str, int | None]]:
            return _with_retry(
                lambda: _dispatch(
                    _t, _p, system=system, images=images,
                    json_schema=json_schema, model=_m, temperature=temperature,
                    base_url=_u, api_key=_k,
                ),
                retries,
            )

        try:
            if cache and eng is not None:
                try:
                    import wallet_helper as _wh
                except ImportError:
                    osh.warning("cache=True but wallet-helper is not installed; running uncached")
                    raw, usage = _run()
                else:
                    payload = _cache_key_payload(
                        backend, resolved_model, resolved_kind, send_prompt, system,
                        json_schema, temperature, images,
                    )
                    (raw, usage), cached = _wh.default_wallet().call(
                        f"beh-llm:{backend}", payload, _run
                    )
            else:
                raw, usage = _run()
        except Exception as exc:  # noqa: BLE001 — fail over to the next engine
            last_exc = exc
            _emit({
                "backend": backend, "model": resolved_model, "kind": resolved_kind,
                "in_chars": len(send_prompt), "images": len(images) if images else 0,
                "out_chars": 0, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "ok": False, "error": repr(exc), "attempt": attempt, "cached": False,
                "in_tokens": None, "out_tokens": None,
            })
            continue

        # Restore pseudonymized spans in the response before anything else sees it.
        if restore_map:
            from . import privacy as _privacy

            raw = _privacy.restore(raw, restore_map)

        if do_safety:
            from . import safety as _safety

            _safety.check_text(raw, direction="inbound")

        _emit({
            "backend": backend, "model": resolved_model, "kind": resolved_kind,
            "in_chars": len(send_prompt), "images": len(images) if images else 0,
            "out_chars": len(raw), "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "ok": True, "error": None, "attempt": attempt, "cached": cached,
            "in_tokens": usage.get("in_tokens"), "out_tokens": usage.get("out_tokens"),
        })

        # Parse JSON when requested; fall back to raw string on parse failure
        if json_mode:
            try:
                return cast(dict[str, Any], json.loads(raw))
            except json.JSONDecodeError:
                # Return raw string rather than crashing; caller can inspect
                osh.warning(
                    "Requested JSON mode but response was not valid JSON; returning raw text"
                )
                return raw
        return raw

    # Every engine in the chain failed.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("no engine could serve the request")


def embed(text: str) -> list[float]:
    """
    Return an embedding vector for the given text.

    Only the Ollama backend is supported for embeddings. The OpenAI-compatible
    embedding endpoint (``/v1/embeddings``) is not yet implemented because the
    retrieval use case is not yet in scope.

    Parameters
    ----------
    text : str
        Input text to embed.

    Returns
    -------
    list[float]
        Dense embedding vector from the Ollama ``/api/embeddings`` endpoint.

    Raises
    ------
    RuntimeError
        If the Ollama request fails or the response lacks an ``embedding`` field.
    NotImplementedError
        If the active backend is not ``ollama``.

    Examples
    --------
    >>> # vec = embed("hello world")  # requires Ollama running
    >>> # len(vec) > 0
    >>> True
    True
    """
    import requests

    backend = _backend()
    if backend != "ollama":
        osh.error(f"embed() unsupported on backend {backend!r} (ollama only)")
        raise NotImplementedError(
            f"embed() is only supported with the 'ollama' backend; current backend is {backend!r}."
        )

    payload = {
        "model": _text_model(),
        "prompt": text,
    }
    url = f"{_base_url()}/api/embeddings"
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        osh.error(f"Ollama embed request failed:\n\t{url}\n\t{exc}")
        raise RuntimeError(f"Ollama embed request to {url} failed: {exc}") from exc

    data = resp.json()
    if "embedding" not in data:
        osh.error(f"Ollama embed response missing 'embedding' field: {data!r}")
        raise RuntimeError(f"Ollama embed response missing 'embedding' field: {data!r}")
    return list(data["embedding"])
