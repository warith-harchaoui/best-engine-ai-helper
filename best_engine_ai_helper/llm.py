"""
llm — pluggable local-model backend for best-engine-ai-helper.

Provides two public functions, ``chat`` and ``embed``, that route requests to
the backend selected by the ``SPREZZATURE_LLM_BACKEND`` environment variable.
All skill scripts call only these two functions; the transport details (Ollama
JSON API vs OpenAI-compatible REST vs LangChain) are invisible to callers.

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
    the ``qwen3-vl:8b`` default. Resolved by :func:`config.text_model`.
BEST_LLM_VISION (legacy alias: SPREZZATURE_LLM_VISION)
    Model tag for prompts that include images. Same precedence as the text
    model; resolved by :func:`config.vision_model`.
SPREZZATURE_LLM_API_KEY
    API key for servers that require one. Empty string by default (most local
    servers do not require authentication).

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import os_helper as osh

# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------

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
# Ollama backend
# ---------------------------------------------------------------------------

def _chat_ollama(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_mode: bool,
    model: str,
    temperature: float,
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
    json_mode : bool
        When True, instructs Ollama to return valid JSON via ``format: "json"``.
    model : str
        Ollama model tag, e.g. ``"qwen3-vl:8b"``.
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
    if json_mode:
        # Constrain output to JSON; Ollama validates the response before returning
        payload["format"] = "json"

    url = f"{_base_url()}/api/generate"
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
    return data["response"]


# ---------------------------------------------------------------------------
# OpenAI-compatible backend
# ---------------------------------------------------------------------------

def _chat_openai(
    prompt: str,
    *,
    system: str | None,
    images: list[bytes] | None,
    json_mode: bool,
    model: str,
    temperature: float,
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
    json_mode : bool
        When True, sets ``response_format`` to ``{"type": "json_object"}``.
    model : str
        Model ID, e.g. ``"qwen3-vl:8b"`` or a HuggingFace model path.
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
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = f"{_base_url()}/v1/chat/completions"
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
        return data["choices"][0]["message"]["content"]
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
    json_mode: bool,
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
            from langchain_ollama import ChatOllama  # type: ignore[import-untyped]
            llm = ChatOllama(model=model, temperature=temperature, base_url=base)
        except ImportError as exc:
            raise ImportError(
                "langchain_ollama is not installed. "
                "Run: pip install langchain-ollama"
            ) from exc
    else:
        try:
            from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                base_url=f"{base}/v1",
                api_key=_api_key() or "none",
            )
        except ImportError as exc:
            raise ImportError(
                "langchain_openai is not installed. "
                "Run: pip install langchain-openai"
            ) from exc

    from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import-untyped]

    msgs = []
    if system:
        msgs.append(SystemMessage(content=system))

    # LangChain multi-modal message support varies; raise clearly when unsupported
    if images:
        raise RuntimeError(
            "Images are not uniformly supported across LangChain backends. "
            "Use the 'ollama' or 'openai' backend for vision prompts."
        )

    if json_mode:
        # Append a JSON instruction to the system prompt as a portable fallback
        hint = "Respond ONLY with valid JSON. No prose, no markdown fences."
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
) -> str | dict[str, Any]:
    """
    Send a prompt to the configured local model and return the response.

    The backend is selected by ``SPREZZATURE_LLM_BACKEND``. All three backends
    (ollama, openai, langchain) accept the same arguments so callers are
    backend-agnostic.

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
        When provided, the model is instructed to return valid JSON. The schema
        is not yet enforced structurally (both Ollama and the OpenAI-compat
        spec use best-effort JSON mode); use it as a strong hint.
    model : str or None
        Override the model tag. Defaults to ``SPREZZATURE_LLM_VISION`` when
        images are present, or ``SPREZZATURE_LLM_TEXT`` otherwise.
    temperature : float
        Sampling temperature. Lower values are more deterministic. Defaults to
        0.2 because structured extraction tasks benefit from low variance.

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
    resolved_model = _resolve_model(model, images)
    # json_schema presence is the signal to request JSON output
    json_mode = json_schema is not None
    backend = _backend()
    osh.info(
        f"chat via {backend}: model={resolved_model}, "
        f"images={len(images) if images else 0}, json={json_mode}"
    )

    if backend == "ollama":
        raw = _chat_ollama(
            prompt,
            system=system,
            images=images,
            json_mode=json_mode,
            model=resolved_model,
            temperature=temperature,
        )
    elif backend == "openai":
        raw = _chat_openai(
            prompt,
            system=system,
            images=images,
            json_mode=json_mode,
            model=resolved_model,
            temperature=temperature,
        )
    elif backend == "langchain":
        raw = _chat_langchain(
            prompt,
            system=system,
            images=images,
            json_mode=json_mode,
            model=resolved_model,
            temperature=temperature,
        )
    else:
        osh.error(f"Unknown SPREZZATURE_LLM_BACKEND: {backend!r}")
        raise ValueError(
            f"Unknown SPREZZATURE_LLM_BACKEND: {backend!r}. "
            "Valid values: 'ollama', 'openai', 'langchain'."
        )

    # Parse JSON when requested; fall back to raw string on parse failure
    if json_mode:
        try:
            return json.loads(raw)
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
            f"embed() is only supported with the 'ollama' backend; "
            f"current backend is {backend!r}."
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
