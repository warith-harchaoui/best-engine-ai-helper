"""
sources.litellm_prices — paid-model list prices from LiteLLM's public table.

``pricing.yaml`` is hand-maintained, and its own header says to "refresh when a
provider reprices or ships a new flagship". Nothing enforced that, and nothing
could: there was no source to refresh *from*, so the file aged silently while
`observe.py` priced every paid call against it and `cloud_catalog.rank_cloud`
ranked on the same numbers.

LiteLLM publishes one JSON covering every major provider, kept current because
their own router bills against it:

    https://github.com/BerriAI/litellm → model_prices_and_context_window.json

What it supplies, and the whole reason this adapter exists:

- ``input_cost_per_token`` / ``output_cost_per_token`` — list price, which is
  what a cost estimate needs to be worth printing.
- ``max_input_tokens`` — the context length. A separate open item on the local
  side, and free here.
- ``supports_vision`` → our ``kind`` (``vlm`` when true, ``llm`` when not);
  ``supports_response_schema`` → our ``structured_output``.

**One deliberate gap, mirroring :mod:`sources.apxml`.** The table carries no
benchmark scores, so this adapter never synthesises them. It contributes price
and capability metadata; the quality axes stay hand-maintained, and a refresh
preserves the scores already in the seed rather than blanking them.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from typing import Any

import os_helper as osh
import requests

#: The table itself. Raw rather than the API so a refresh needs no token and no
#: dependency on LiteLLM the package.
PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)

#: LiteLLM's ``litellm_provider`` values, mapped onto the provider names this
#: package routes to (``engine._CLOUD_BASE_URLS``). Anything outside this map
#: is skipped: a price for a provider no transport here can reach would be a
#: number with nowhere to go.
#:
#: **Azure is deliberately absent, and it used to be here.** It is the one
#: provider in ``llm._OPENAI_COMPATIBLE`` with no entry in
#: ``engine._CLOUD_BASE_URLS``, because it has no universal base URL to put
#: there: the endpoint is ``https://<your-resource>.openai.azure.com`` and the
#: id a request carries is a *deployment name* the tenant chose, not the model
#: name the table lists. A catalog entry is something the ranker may pick and
#: then route to from its id alone, and an Azure row is not that -- it would
#: resolve to ``base_url=""``. It also duplicated: 66 of its 94 rows repeated
#: an OpenAI id already in the table, so they inflated the triage list with
#: models that were already there under a provider that works.
#:
#: Azure remains usable, as it always was, by pointing a brief at your own
#: endpoint. What is removed is the pretence that it can be auto-picked.
_PROVIDERS: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "mistral": "mistral",
    "openrouter": "openrouter",
    "together_ai": "together",
}

#: Entry modes worth carrying. ``image_generation`` is deliberately absent: it
#: is priced per image rather than per token, which this catalog's schema has
#: no field for, and inventing one from a token price would be a fiction.
_MODES: dict[str, str] = {"chat": "chat", "embedding": "embed"}

#: Ids that name a template or a billing bucket rather than a model you can
#: call. ``ft:`` prefixes a fine-tune family; ``together-ai-<range>`` is a
#: parameter-count price band; ``container`` and the ``-preview`` tooling
#: entries are API products with no chat completion behind them.
_SKIP_PREFIXES: tuple[str, ...] = ("ft:", "together-ai-")


def _is_model_id(model: str) -> bool:
    """Whether *model* names something callable rather than a billing bucket.

    Parameters
    ----------
    model : str
        Candidate model id, already stripped of any provider prefix.

    Returns
    -------
    bool
        True when the id looks like a model a transport could send.

    Examples
    --------
    >>> _is_model_id("gpt-4o")
    True
    >>> _is_model_id("ft:gpt-3.5-turbo")
    False
    >>> _is_model_id("together-ai-21.1b-41b")
    False
    """
    if not model or model.startswith(_SKIP_PREFIXES):
        return False
    # A surviving slash means a nested routing surface (bedrock/, vertex_ai/,
    # eu./us. regional mirrors) rather than a first-party model name.
    return "/" not in model


def normalize_price_entry(key: str, spec: dict[str, Any], fetched_at: str) -> dict[str, Any] | None:
    """
    Turn one LiteLLM table row into a cloud-catalog entry, or None to skip it.

    Parameters
    ----------
    key : str
        The table key, either a bare model id or ``<provider>/<model>``.
    spec : dict[str, Any]
        The row.
    fetched_at : str
        ISO date stamp recorded on the entry.

    Returns
    -------
    dict[str, Any] or None
        An entry carrying ``id``, ``provider``, ``kind``,
        ``structured_output``, ``input_per_1m``, ``output_per_1m``,
        ``context_length``, ``source`` and ``fetched_at`` — or None when the
        row names a provider, mode or id this package cannot use.

    Examples
    --------
    >>> row = {"litellm_provider": "openai", "mode": "chat",
    ...        "input_cost_per_token": 2.5e-06, "output_cost_per_token": 1e-05,
    ...        "max_input_tokens": 128000, "supports_vision": True,
    ...        "supports_response_schema": True}
    >>> entry = normalize_price_entry("gpt-4o", row, "2026-10-28")
    >>> entry["id"], entry["kind"], entry["input_per_1m"]
    ('gpt-4o', 'vlm', 2.5)
    >>> normalize_price_entry("x", {"litellm_provider": "bedrock"}, "2026-10-28") is None
    True
    """
    if not isinstance(spec, dict):
        return None
    provider = _PROVIDERS.get(str(spec.get("litellm_provider") or ""))
    if provider is None:
        return None
    mode = _MODES.get(str(spec.get("mode") or ""))
    if mode is None:
        return None

    model = key
    if "/" in key:
        head, _, tail = key.partition("/")
        # Only a prefix naming the row's own provider is a first-party id; a
        # different one (bedrock/, vertex_ai/) is somebody else's routing.
        if head != str(spec.get("litellm_provider")):
            return None
        model = tail
    if not _is_model_id(model):
        return None

    input_cost = spec.get("input_cost_per_token")
    output_cost = spec.get("output_cost_per_token")
    if input_cost is None and output_cost is None:
        return None

    if mode == "embed":
        kind = "embed"
    else:
        kind = "vlm" if spec.get("supports_vision") else "llm"

    entry: dict[str, Any] = {
        "id": model,
        "provider": provider,
        "kind": kind,
        "input_per_1m": round(float(input_cost or 0.0) * 1_000_000, 6),
        "output_per_1m": round(float(output_cost or 0.0) * 1_000_000, 6),
        "source": "litellm",
        "fetched_at": fetched_at,
    }
    if "supports_response_schema" in spec:
        entry["structured_output"] = bool(spec["supports_response_schema"])
    context = spec.get("max_input_tokens") or spec.get("max_tokens")
    if isinstance(context, int) and context > 0:
        entry["context_length"] = context
    return entry


def fetch_cloud_prices(timeout: float = 30.0, url: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch and normalise the public price table.

    Parameters
    ----------
    timeout : float
        Seconds to wait for the HTTP response.
    url : str or None
        Override the source URL (tests point this at a fixture file served
        locally, or monkeypatch :func:`requests.get`).

    Returns
    -------
    list[dict[str, Any]]
        Normalised entries, one per usable model, sorted by provider then id.

    Raises
    ------
    requests.RequestException
        Propagated from the fetch; the CLI turns it into a readable message
        rather than a traceback.
    """
    from ..catalog import _today

    source = url or PRICES_URL
    osh.info(f"Fetching paid-model prices from:\n\t{source}")
    response = requests.get(source, timeout=timeout)
    response.raise_for_status()
    table = response.json()
    if not isinstance(table, dict):
        raise ValueError(f"{source}: expected a JSON object, got {type(table)!r}")

    stamp = _today()
    entries = [
        entry
        for key, spec in table.items()
        if (entry := normalize_price_entry(str(key), spec, stamp)) is not None
    ]
    entries.sort(key=lambda e: (str(e["provider"]), str(e["id"])))
    osh.info(f"{len(entries)} paid model(s) usable from {len(table)} table rows.")
    return entries
