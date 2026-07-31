"""
sources.apxml — open-weight model specs from the ApXML LLM directory.

ApXML (https://apxml.com/models) publishes a directory of open-weight LLMs and
VLMs with the facts this project selects on: parameter count, modality,
architecture (dense vs MoE), context length, licence, the HuggingFace weights
URL, and — most valuable here — ApXML's own peak inference VRAM estimate at
Q4/Q8/FP16. Those VRAM figures share the semantics of a catalog entry's
``ram_gb`` (weights plus a moderate KV cache), so they feed the fit decision
directly.

The pages are server-rendered React (Next.js). The model data is not exposed as
a REST endpoint; it is streamed inside ``self.__next_f.push([1, "<chunk>"])``
script calls. We reconstruct the payload from those chunks and brace-match the
model object out of it — no headless browser required.

One deliberate gap: the *numeric* benchmark scores (LiveBench, Aider, MMLU-Pro,
GPQA, …) are fetched by a client-side call and are absent from the static HTML,
so this adapter never synthesises benchmark axes. It contributes spec and
memory-fit metadata; leaderboard sources contribute the scores.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

# Open-weight-only listing; the ``modelType`` filter is honoured server-side.
DIRECTORY_URL = "https://apxml.com/models?modelType=open_weight"

# Per-model detail page; the spec object (VRAM, params, licence) lives here.
MODEL_URL = "https://apxml.com/models/{slug}"

# ApXML returns an empty table to non-browser agents, so present a browser UA.
_USER_AGENT = "Mozilla/5.0 (compatible; best-engine-ai-helper/0.2)"

# Detail-page links in the directory look like ``/models/<slug>``; the slug is
# lowercase alphanumerics and hyphens. Anchored so query strings do not leak in.
_SLUG_RE = re.compile(r"/models/([a-z0-9][a-z0-9-]*)")

# A directory-level link that is not a model (the listing's own filter view).
_NON_MODEL_SLUGS = frozenset({"compare"})

# Each RSC chunk is a JSON string literal; capture its still-escaped body.
_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')

# The spec object is the only place a real numeric parameter count is quoted as
# ``"num_of_params":"<n>"`` — the i18n label maps never carry a numeric value.
_MODEL_ANCHOR = '"num_of_params":"'


def _reconstruct_rsc_payload(html: str) -> str:
    """
    Rebuild the React Server Components payload embedded in an ApXML page.

    Next.js streams data as a sequence of ``self.__next_f.push([1, "<chunk>"])``
    calls whose chunks concatenate into one logical string. Each chunk is a JSON
    string literal, so it is unescaped by decoding it as JSON before joining.

    Parameters
    ----------
    html : str
        Raw HTML of an ApXML directory or model page.

    Returns
    -------
    str
        The concatenated, unescaped payload. Empty string when the page carries
        no RSC chunks (e.g. an error page).

    Examples
    --------
    >>> _reconstruct_rsc_payload('x self.__next_f.push([1,"ab\\\\ncd"]) y')
    'ab\\ncd'
    """
    # Decode each chunk as its own JSON string so escapes (\", \n, \uXXXX) and
    # any split multi-byte sequences resolve exactly as the browser sees them.
    chunks = [json.loads('"' + body + '"') for body in _RSC_CHUNK_RE.findall(html)]
    return "".join(chunks)


def _extract_json_object(text: str, anchor: str) -> dict[str, Any] | None:
    """
    Return the smallest JSON object containing ``anchor``, via brace matching.

    The payload is a flat string, not addressable JSON, so we locate the anchor,
    walk left to the object's opening brace, then walk right matching braces
    while respecting string literals (braces inside strings are ignored).

    Parameters
    ----------
    text : str
        Reconstructed RSC payload to search.
    anchor : str
        A substring known to sit inside the target object (here, the quoted
        ``num_of_params`` key with its numeric value).

    Returns
    -------
    dict[str, Any] or None
        The parsed object, or None when the anchor is absent or the surrounding
        braces do not parse as JSON.

    Examples
    --------
    >>> _extract_json_object('[{"a":1,"k":"v"}]', '"k":"v"')
    {'a': 1, 'k': 'v'}
    """
    at = text.find(anchor)
    if at < 0:
        return None

    # Walk backwards to the opening brace of the object that holds the anchor,
    # counting nested objects so we stop at the right depth, not the first '{'.
    depth = 0
    start = None
    i = at
    while i >= 0:
        char = text[i]
        if char == "}":
            depth += 1
        elif char == "{":
            if depth == 0:
                start = i
                break
            depth -= 1
        i -= 1
    if start is None:
        return None

    # Walk forwards to the matching close brace. `instr`/`esc` keep us from
    # miscounting braces that appear inside quoted string values.
    depth = 0
    instr = False
    esc = False
    for j in range(start, len(text)):
        char = text[j]
        if esc:
            esc = False
            continue
        if char == "\\":
            esc = True
            continue
        if char == '"':
            instr = not instr
            continue
        if instr:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                # Whole object captured; a malformed slice is treated as "no data".
                try:
                    return json.loads(text[start : j + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_directory_slugs(html: str) -> list[str]:
    """
    Extract the open-weight model slugs listed on a directory page.

    Parameters
    ----------
    html : str
        Raw HTML of the ApXML models directory.

    Returns
    -------
    list[str]
        Unique model slugs in first-seen order, minus non-model links.

    Examples
    --------
    >>> parse_directory_slugs('<a href="/models/qwen3-8b">')
    ['qwen3-8b']
    """
    seen: dict[str, None] = {}
    # dict preserves insertion order and dedupes the repeated links per row.
    for slug in _SLUG_RE.findall(html):
        if slug not in _NON_MODEL_SLUGS:
            seen.setdefault(slug, None)
    return list(seen)


def _hf_id_from_weights_url(url: str | None) -> str | None:
    """
    Derive a HuggingFace repo id (``org/model``) from a weights URL.

    Parameters
    ----------
    url : str or None
        Value of the model's ``link_weights`` field.

    Returns
    -------
    str or None
        ``org/model`` when the URL points at huggingface.co, else None.

    Examples
    --------
    >>> _hf_id_from_weights_url('https://huggingface.co/Qwen/Qwen3.5-9B')
    'Qwen/Qwen3.5-9B'
    >>> _hf_id_from_weights_url('https://example.com/x') is None
    True
    """
    if not url or "huggingface.co/" not in url:
        return None
    # Keep the first two path segments after the host; drop any /tree/... suffix.
    tail = url.split("huggingface.co/", 1)[1].strip("/")
    parts = tail.split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _to_float(value: Any) -> float | None:
    """
    Coerce ApXML's quoted numerics to float, tolerating None and bad strings.

    Parameters
    ----------
    value : Any
        Raw field value (ApXML quotes numbers, e.g. ``"9.00"``).

    Returns
    -------
    float or None
        Parsed float, or None when the value is missing or non-numeric.

    Examples
    --------
    >>> _to_float("9.00")
    9.0
    >>> _to_float(None) is None
    True
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_model_page(html: str) -> dict[str, Any] | None:
    """
    Parse one ApXML model detail page into a normalized spec dict.

    Parameters
    ----------
    html : str
        Raw HTML of an ApXML ``/models/<slug>`` page.

    Returns
    -------
    dict[str, Any] or None
        Normalized fields (see below), or None when the page holds no model
        object. ``kind`` is ``"vlm"`` for multimodal models, else ``"llm"``.
        ``ram_gb`` mirrors the Q4 VRAM estimate — the quant this project pulls
        by default — so it drops straight into the fit check.

    Examples
    --------
    >>> spec = parse_model_page(open('fixture.html').read())  # doctest: +SKIP
    >>> spec['kind'] in ('llm', 'vlm')                        # doctest: +SKIP
    True
    """
    payload = _reconstruct_rsc_payload(html)
    obj = _extract_json_object(payload, _MODEL_ANCHOR)
    if obj is None:
        return None

    # Anything not text-only is treated as vision-capable, matching the catalog's
    # llm/vlm split (a VLM is assumed to retain text ability).
    modality = obj.get("modality")
    kind = "llm" if modality == "text" else "vlm"

    weights_url = obj.get("link_weights")
    provider = obj.get("provider") or {}

    # Q4 is the project's default pull, so surface its VRAM as the headline
    # ram_gb while keeping the other quants for callers that need them.
    vram_q4 = _to_float(obj.get("inference_vram_required_q4"))

    return {
        "slug": obj.get("slug"),
        "name": obj.get("name"),
        "provider": provider.get("name"),
        "kind": kind,
        "modality": modality,
        "size_b": _to_float(obj.get("num_of_params")),
        "architecture": obj.get("architecture"),
        "num_of_experts": obj.get("num_of_experts"),
        "num_of_active_experts": obj.get("num_of_active_experts"),
        "context_length": obj.get("context_length"),
        "license": obj.get("license"),
        "open_weights": bool(obj.get("open_weights")),
        "weights_url": weights_url,
        "vllm_id": _hf_id_from_weights_url(weights_url),
        "release_date": obj.get("release_date"),
        "ram_gb": vram_q4,
        "vram_q4_gb": vram_q4,
        "vram_q8_gb": _to_float(obj.get("inference_vram_required_q8")),
        "vram_fp16_gb": _to_float(obj.get("inference_vram_required_fp16")),
        "url": MODEL_URL.format(slug=obj.get("slug")),
    }


def _fetch(url: str, session: requests.Session | None, timeout: float) -> str:
    """
    GET a URL with the browser User-Agent ApXML requires and return the body.

    Parameters
    ----------
    url : str
        Absolute URL to fetch.
    session : requests.Session or None
        Reused session for connection pooling; a throwaway one is made if None.
    timeout : float
        Per-request timeout in seconds.

    Returns
    -------
    str
        Response body text.

    Raises
    ------
    requests.HTTPError
        If the response status is 4xx or 5xx.
    """
    client = session or requests
    # A non-browser UA yields an empty table, so the header is mandatory here.
    resp = client.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_open_weight_models(
    session: requests.Session | None = None,
    timeout: float = 30.0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch and normalize every open-weight model in the ApXML directory.

    Network-bound: one request for the directory plus one per model. Pages that
    fail to fetch or parse are skipped rather than aborting the whole refresh, so
    a single dead link never empties the feed.

    Parameters
    ----------
    session : requests.Session or None
        Optional shared session for connection reuse.
    timeout : float
        Per-request timeout in seconds.
    limit : int or None
        Stop after this many models (useful for smoke tests); None fetches all.

    Returns
    -------
    list[dict[str, Any]]
        Normalized spec dicts as returned by :func:`parse_model_page`.

    Examples
    --------
    >>> models = fetch_open_weight_models(limit=1)  # doctest: +SKIP
    >>> models[0]['kind'] in ('llm', 'vlm')         # doctest: +SKIP
    True
    """
    sess = session or requests.Session()

    slugs = parse_directory_slugs(_fetch(DIRECTORY_URL, sess, timeout))
    if limit is not None:
        slugs = slugs[:limit]

    models: list[dict[str, Any]] = []
    for slug in slugs:
        # Best-effort per model: a broken page must not sink the whole feed.
        try:
            spec = parse_model_page(_fetch(MODEL_URL.format(slug=slug), sess, timeout))
        except requests.RequestException:
            spec = None
        if spec is not None:
            models.append(spec)
    return models
