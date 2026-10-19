"""
ollama_library — widen the catalog with tags Ollama can actually pull.

The bundled seed holds twenty models, hand-maintained and fully scored. The
ApXML adapter can add hundreds more, but it keys them by the *paper's* slug
(``qwen36-35b-a3b``), which is a HuggingFace repo name and not something
``ollama pull`` resolves — so those entries are vLLM-only and the
Ollama-servable pool stays at twenty. That is the real reason this catalog is
small, and it is not a scoring problem.

This source closes that gap. ``ollama.com/library`` publishes the official
library: family name, capabilities, and the parameter sizes each family ships.
A family plus a size is a pull tag — ``qwen3`` plus ``8b`` is ``qwen3:8b``,
exactly the spelling the seed already uses — so every entry produced here
passes :func:`catalog.servable` and can be served today.

What it deliberately does not do
--------------------------------
It invents no benchmark scores. Ollama's library page carries descriptions and
sizes, not leaderboard results, so every entry lands with null benchmarks and
therefore ranks **below** any scored model. That is the honest outcome and the
same contract the ApXML adapter already follows: an entry with no provenance is
worth less than no entry, so widening must not be bought by making scores up.

The practical effect is that this widens *reach* — the set of models the tool
knows how to size and pull — without touching *ranking*, until a scored source
fills the benchmarks in.

One request
-----------
The index alone carries everything needed, because it lists each family's sizes
inline. Walking the 256 per-family tag pages would be 256 requests for a
slightly more precise disk figure, which is not a trade worth making in a
command someone runs interactively.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import re
from typing import Any

import os_helper as osh
import requests

#: The official library index. No API is published, so this reads the page.
LIBRARY_URL = "https://ollama.com/library"

_USER_AGENT = "Mozilla/5.0 (compatible; best-engine-ai-helper/0.3)"

#: Capability pills the page renders next to a family name. Only the two that
#: change which *kind* a model is are consumed; `tools` and `thinking` describe
#: behaviour within a kind, not the kind itself.
_KIND_BY_CAPABILITY = {"embedding": "embed", "vision": "vlm"}

#: Size labels as the page spells them: `8b`, `0.6b`, `235b`, sometimes `7x8b`
#: for a mixture-of-experts. Captured with the multiplier so a MoE's total
#: parameter count is not silently read as one expert's.
_SIZE_RE = re.compile(r"^(?:(\d+)x)?(\d+(?:\.\d+)?)b$")

#: Gigabytes on disk per billion parameters, at the Q4 quantisation Ollama
#: serves by default. Not guessed: measured against the fourteen Q4 entries of
#: the hand-maintained seed, whose disk figures are known-good.
#:
#:   llm  n=8  median 0.646  (0.611 - 0.679)
#:   vlm  n=6  median 0.714  (0.667 - 0.800)
#:
#: The split is real rather than noise — a vision model carries an image tower
#: on top of its language weights, so it is consistently heavier per parameter.
#: Using one blended constant would under-size every VLM, and under-sizing is
#: the direction that gets a model recommended and then fails to load.
#:
#: Checked against the seed tags this source also produces: the derived figure
#: lands within about 5% either way (qwen3:8b -0.6%, gemma3:12b +2.0%,
#: qwen3:14b -4.8%). To re-derive after the seed changes materially, take the
#: median of `disk_gb / size_b` over its Q4 entries, grouped by kind.
_GB_PER_BILLION_PARAMS = {"llm": 0.646, "vlm": 0.714, "embed": 0.669}
_DEFAULT_GB_PER_BILLION = 0.669

#: Quantisation label recorded on entries from this source, matching what
#: `ollama pull <family>:<size>` actually fetches for the default tag.
REFRESH_QUANT = "Q4_K_M"


def _parse_size_b(label: str) -> float | None:
    """
    Turn a page size label into a parameter count in billions.

    Parameters
    ----------
    label : str
        A label as rendered, e.g. ``"8b"``, ``"0.6b"``, ``"8x7b"``.

    Returns
    -------
    float or None
        Billions of parameters, or None when the label is not a size.

    Examples
    --------
    >>> _parse_size_b("8b")
    8.0
    >>> _parse_size_b("0.6b")
    0.6
    >>> _parse_size_b("8x7b")
    56.0
    >>> _parse_size_b("latest") is None
    True
    """
    found = _SIZE_RE.match(label.strip().lower())
    if not found:
        return None
    multiplier, size = found.groups()
    total = float(size) * (int(multiplier) if multiplier else 1)
    return round(total, 2)


def parse_library(html: str) -> list[dict[str, Any]]:
    """
    Extract one record per model family from the library index page.

    Parameters
    ----------
    html : str
        The fetched page.

    Returns
    -------
    list of dict
        ``[{"name", "capabilities", "sizes", "description"}]`` in page order,
        which is the site's own popularity ordering.
    """
    families: list[dict[str, Any]] = []
    seen: set[str] = set()

    # The page renders one <li> per family. Splitting on it keeps each family's
    # capability pills and size labels with the family they belong to, which a
    # document-wide regex would not.
    for block in re.split(r"<li\b", html)[1:]:
        match = re.search(r'href="/library/([a-z0-9._-]+)"', block)
        if not match:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)

        text = re.sub(r"<[^>]+>", " ", block)
        capabilities = sorted(set(re.findall(r">(vision|embedding|tools|thinking)<", block)))
        sizes = [
            label
            for label in re.findall(r"\b(\d+(?:\.\d+)?b|\d+x\d+(?:\.\d+)?b)\b", text.lower())
            if _parse_size_b(label) is not None
        ]
        families.append(
            {
                "name": name,
                "capabilities": capabilities,
                "sizes": sorted(set(sizes), key=lambda s: _parse_size_b(s) or 0.0),
                "description": " ".join(text.split())[:300],
            }
        )
    return families


def fetch_library(
    session: requests.Session | None = None,
    timeout: float = 30.0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch and parse the official Ollama library index.

    Parameters
    ----------
    session : requests.Session or None
        Optional shared session.
    timeout : float
        Request timeout in seconds. Always bounded: a hung index read would
        stall a command someone is sitting in front of.
    limit : int or None
        Keep at most this many families, in the page's own ordering (most
        popular first), so a partial refresh takes the models people use.

    Returns
    -------
    list of dict
        As :func:`parse_library`.

    Examples
    --------
    >>> families = fetch_library(limit=5)       # doctest: +SKIP
    >>> families[0]["name"]                     # doctest: +SKIP
    'llama3.1'
    """
    client = session or requests
    response = client.get(LIBRARY_URL, timeout=timeout, headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    families = parse_library(response.text)
    osh.info(f"Ollama library: {len(families)} families at {LIBRARY_URL}")
    return families[:limit] if limit else families


def to_specs(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Expand families into one spec per concrete pull tag.

    A family on its own is not pullable at a chosen size, and the catalog is
    keyed by what you would actually run. ``qwen3`` with sizes ``8b`` and
    ``14b`` therefore becomes ``qwen3:8b`` and ``qwen3:14b``.

    A family listing no sizes is skipped rather than emitted as a bare name.
    The bare name usually does resolve, to whichever size the publisher made
    default, but the catalog's whole job is sizing a model against this
    machine's memory — and an entry whose size is unknown cannot be sized.

    Parameters
    ----------
    families : list of dict
        As returned by :func:`parse_library`.

    Returns
    -------
    list of dict
        Specs ready for :func:`catalog.normalize_ollama_spec`.
    """
    specs: list[dict[str, Any]] = []
    for family in families:
        kinds = [_KIND_BY_CAPABILITY[c] for c in family["capabilities"] if c in _KIND_BY_CAPABILITY]
        # A family is one kind. "vision" wins over "embedding" only in the
        # impossible case of both; in practice exactly one or neither applies,
        # and neither means a text model.
        kind = "vlm" if "vlm" in kinds else ("embed" if "embed" in kinds else "llm")

        for label in family["sizes"]:
            size_b = _parse_size_b(label)
            if size_b is None:
                continue
            specs.append(
                {
                    "id": f"{family['name']}:{label}",
                    "kind": kind,
                    "size_b": size_b,
                    "disk_gb": round(
                        size_b * _GB_PER_BILLION_PARAMS.get(kind, _DEFAULT_GB_PER_BILLION), 2
                    ),
                    "capabilities": family["capabilities"],
                    "url": f"{LIBRARY_URL}/{family['name']}",
                }
            )
    return specs


def fetch_pullable_models(
    session: requests.Session | None = None,
    timeout: float = 30.0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Every size of every family in the library, as concrete pull tags.

    Parameters
    ----------
    session : requests.Session or None
        Optional shared session.
    timeout : float
        Request timeout in seconds.
    limit : int or None
        Maximum number of *families* to expand, not tags: a family yields
        several tags, and cutting mid-family would hide sizes of a model the
        caller was told about.

    Returns
    -------
    list of dict
        Specs, one per pull tag.
    """
    return to_specs(fetch_library(session=session, timeout=timeout, limit=limit))
