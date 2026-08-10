"""
llm — pluggable local-model backend for best-engine-ai-helper.

Provides two public functions, ``chat`` and ``embed``, that route requests to
the backend selected by the ``SPREZZATURE_LLM_BACKEND`` environment variable.
Callers use only these two functions; the transport details (Ollama JSON API
vs OpenAI-compatible REST vs LangChain) stay invisible to them.

Supported backends
------------------
ollama
    Default. POSTs to ``{SPREZZATURE_LLM_BASE_URL}/api/generate``.
    Works offline once the model is pulled.
openai
    Any OpenAI-compatible server: vLLM, llama.cpp, LM Studio, Text Generation
    Inference. POSTs to ``{SPREZZATURE_LLM_BASE_URL}/v1/chat/completions``.
langchain
    Thin wrapper over ``ChatOllama`` or ``ChatOpenAI`` from LangChain.
    Only useful if you need LangChain retrievers or agent abstractions.

Environment variables
---------------------
SPREZZATURE_LLM_BACKEND
    ``ollama`` | ``openai`` | ``langchain``. Defaults to ``ollama``.
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
    API key for servers that require one. Empty string by default (most local
    servers do not require authentication).

Observability
-------------
Every :func:`chat` call fans a small event dict out to any observer registered
via :func:`add_observer` (backend, model, kind, char counts, latency, success/
error). No observer is registered by default. :mod:`best_engine_ai_helper.observe`
provides a SQLite-backed sink (call ``observe.enable()``) that turns this into
a queryable local activity/cost ledger, surfaced by the ``usage`` CLI command
and the ``/api/usage`` endpoint.

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
from typing import Any

import os_helper as osh

# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------

# Backends that speak the OpenAI Chat Completions wire format, so they route
# through ``_chat_openai``: a local vLLM server, and any generic OpenAI-compatible
# server. Cloud providers (and Anthropic/Gemini's own formats) arrive on the
# 'cloud' branch.
_OPENAI_COMPATIBLE = frozenset({"vllm", "openai"})

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
    """Return the API key; empty string means no authentication required."""
    return os.environ.get("SPREZZATURE_LLM_API_KEY", "")


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
) -> str:
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
    str
        The model's text response.

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
    return str(data["response"])


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
) -> str:
    """
    Send a chat request to an OpenAI-compatible /v1/chat/completions endpoint.

    Covers vLLM, llama.cpp in server mode, LM Studio, Text Generation
    Inference, and OpenAI itself. The message structure matches the OpenAI
    Chat Completions schema exactly.

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

    Returns
    -------
    str
        The model's text response from ``choices[0].message.content``.

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
    key = _api_key()
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
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError) as exc:
        osh.error(f"Malformed completion response: {data!r}")
        raise RuntimeError(f"Malformed completion response: {data!r}") from exc


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
) -> str:
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
    str
        The model's text response.

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
    return str(result.content)


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
    engine: dict[str, Any] | str | None = None,
    kind: str | None = None,
) -> str | dict[str, Any]:
    """
    Send a prompt to the configured local model and return the response.

    The backend and model come from one of two sources. When ``engine`` is given
    (the suite's preferred path), they are read from a resolved engine descriptor
    — the gitignored ``llm.engine.yaml`` a repo gets from ``best-engine-ai-helper
    resolve``; a ``vllm`` backend is served over the OpenAI-compatible protocol.
    Otherwise the legacy env path applies: the backend is
    ``SPREZZATURE_LLM_BACKEND`` and the model resolves via env / persisted config.

    Parameters
    ----------
    prompt : str
        User-facing prompt text.
    system : str or None
        System-level instructions sent before the user prompt. Use for persona,
        output format constraints, or house style rules.
    images : list[bytes] or None
        Raw image bytes (PNG or JPEG). When provided, the vision model is used
        unless ``model`` is specified explicitly. The Ollama backend encodes
        images as base64; the OpenAI backend uses data URI content parts.
    json_schema : dict or None
        When provided, the response is constrained to this JSON Schema. The
        Ollama backend passes it as ``format`` (grammar-constrained structured
        output) and the OpenAI backend as a ``json_schema`` response format, so
        the returned JSON matches the schema's shape -- not merely valid JSON of
        some arbitrary shape.
    model : str or None
        Override the model tag/id. Wins over both the engine descriptor and the
        env default. When absent with no engine, defaults to the vision model
        when images are present, else the text model.
    temperature : float
        Sampling temperature. Lower values are more deterministic. Defaults to
        0.2 because structured extraction tasks benefit from low variance.
    engine : dict | str | None
        A resolved engine descriptor (dict from :func:`engine.resolve` /
        :func:`engine.ensure`, or a path to ``llm.engine.yaml``). When given, its
        ``backend`` / ``base_url`` and the per-kind ``model`` drive the request.
    kind : {'llm', 'vlm'} or None
        Which model to use from ``engine``. Defaults to ``vlm`` when images are
        present, else ``llm``. Ignored when ``engine`` is None.

    Returns
    -------
    str or dict
        When ``json_schema`` is provided and the model returns valid JSON, the
        result is parsed and returned as a dict. Otherwise a plain string.

    Raises
    ------
    RuntimeError
        If the HTTP request fails, the backend is unreachable, or the response
        is malformed.
    ValueError
        If ``SPREZZATURE_LLM_BACKEND`` is set to an unrecognised value.

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

    # Resolve (backend, base_url, model). Engine descriptor wins when supplied;
    # otherwise the legacy env path. `transport` is the wire protocol: a vLLM
    # backend speaks the OpenAI-compatible protocol, so it maps to `_chat_openai`.
    base_url: str | None = None
    if engine is not None:
        from . import engine as _engine

        eng = engine if isinstance(engine, dict) else _engine.load_engine(engine)
        k = kind or ("vlm" if images else "llm")
        backend, base_url, engine_model = _engine.model_for(eng, k)
        resolved_model = model or engine_model
        transport = "openai" if backend in _OPENAI_COMPATIBLE else backend
    else:
        resolved_model = _resolve_model(model, images)
        backend = _backend()
        transport = backend

    osh.info(
        f"chat via {backend}: model={resolved_model}, "
        f"images={len(images) if images else 0}, json={json_mode}"
    )
    resolved_kind = kind or ("vlm" if images else "llm")

    t0 = time.perf_counter()
    try:
        if transport == "ollama":
            raw = _chat_ollama(
                prompt,
                system=system,
                images=images,
                json_schema=json_schema,
                model=resolved_model,
                temperature=temperature,
                base_url=base_url,
            )
        elif transport == "openai":
            raw = _chat_openai(
                prompt,
                system=system,
                images=images,
                json_schema=json_schema,
                model=resolved_model,
                temperature=temperature,
                base_url=base_url,
            )
        elif transport == "langchain":
            raw = _chat_langchain(
                prompt,
                system=system,
                images=images,
                json_schema=json_schema,
                model=resolved_model,
                temperature=temperature,
            )
        else:
            osh.error(f"Unknown backend: {backend!r}")
            raise ValueError(
                f"Unknown backend: {backend!r}. Valid values: "
                "'ollama', 'vllm', 'openai', 'langchain'."
            )
    except Exception as exc:
        _emit({
            "backend": backend, "model": resolved_model, "kind": resolved_kind,
            "in_chars": len(prompt), "images": len(images) if images else 0,
            "out_chars": 0, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "ok": False, "error": repr(exc),
        })
        raise

    _emit({
        "backend": backend, "model": resolved_model, "kind": resolved_kind,
        "in_chars": len(prompt), "images": len(images) if images else 0,
        "out_chars": len(raw), "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "ok": True, "error": None,
    })

    # Parse JSON when requested; fall back to raw string on parse failure
    if json_mode:
        try:
            parsed: dict[str, Any] = json.loads(raw)
            return parsed
        except json.JSONDecodeError:
            # Return raw string rather than crashing; caller can inspect
            osh.warning("Requested JSON mode but response was not valid JSON; returning raw text")
            return raw

    return raw


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
