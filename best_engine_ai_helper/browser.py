"""
browser — choose a language model for a machine best-engine never sees: the visitor's browser.

Everywhere else best-engine probes the machine, then picks ONE model. In a web
page it cannot: the machine is the visitor's, and it reveals itself only at the
first question, through what the browser chooses to expose. So the browser
target works in two halves.

1. **In advance, here** — :func:`plan` reads a usage profile (``rag-answer``…)
   and the browser catalog (``data/browser_models.yaml``), and writes an ordered
   ladder of candidates, every one with its requirements: download size per
   dtype, ``shader-f16``, a device-memory floor, the exact files to fetch.
2. **At run time, in the page** — the page walks the ladder down and takes the
   first candidate the machine and the line can bear. :func:`choose` is that
   walk, in Python: the reference the JavaScript twin is tested against, and a
   way to simulate a device (``best-engine-ai-helper browser choose``).

The criteria are new to best-engine, because a page pays for things a server
never does:

- **the download**, judged against the bandwidth OBSERVED in the page (a 3 GB
  model is fine on fibre and absurd on a train), and free once cached;
- **shader-f16**, which decides between q4f16 and q4 weights;
- **deviceMemory**, a rounded figure, as a proxy for a GPU nobody can query;
- **mobile** and **data saver**, which rule a multi-gigabyte download out;
- **the storage quota** left for the browser's cache.

A signal the browser does not expose (Safari has no deviceMemory) is never held
against the machine; an unknown bandwidth is replaced by a deliberately modest
assumption, so that silence never buys a 5 GB download.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SEED_PATH = Path(__file__).resolve().parent / "data" / "browser_models.yaml"
_CACHE_PATH = Path.home() / ".best-engine-ai-helper" / "browser_cache.yaml"
HUB = "https://huggingface.co"

#: Runtime the plan is written for. The page must import this exact build: the
#: catalog's ONNX exports and chat templates are checked against it.
TRANSFORMERS_JS = "@huggingface/transformers@4.3.2"

#: Policy written into every plan, read by the page.
DEFAULT_POLICY = {
    # Longest first download offered without second thoughts, in seconds.
    "max_download_s": 180,
    # Assumed bandwidth when the page could not measure one: 20 Mbit/s.
    "unknown_bandwidth_Bps": 2_500_000,
    # Bytes fetched PER WEIGHT SHARD to measure the bandwidth: one Range
    # request per shard, all at once, timed from the first byte, the way the
    # model will load (a CDN caps each connection).
    "probe_bytes": 4_000_000,
    # Free storage needed, as a multiple of the download.
    "storage_margin": 1.1,
    # effectiveType values that rule a model download out.
    "slow_networks": ["slow-2g", "2g", "3g"],
}

#: A model measured below this on the usage stays in the catalog, with its
#: score, but leaves the ladder: downloading it would mostly buy answers the
#: page then sets aside. Unmeasured models are kept, on their prior.
DEFAULT_MIN_SCORE = 0.5


def load_browser_catalog(
    seed: Path | None = None, cache: Path | None = None
) -> list[dict[str, Any]]:
    """
    The browser catalog: the bundled seed, overlaid by the user cache by ``id``.

    Examples
    --------
    >>> cat = load_browser_catalog(cache=Path("/nonexistent"))
    >>> cat[0]["id"]
    'onnx-community/gemma-4-E4B-it-ONNX'
    >>> sorted(cat[1]["variants"])
    ['q4', 'q4f16']
    """
    entries = yaml.safe_load((seed or _SEED_PATH).read_text(encoding="utf-8")) or []
    cache = cache if cache is not None else _CACHE_PATH
    if cache.exists():
        overlay = {e["id"]: e for e in (yaml.safe_load(cache.read_text(encoding="utf-8")) or [])}
        entries = [{**e, **overlay.get(e["id"], {})} for e in entries]
    return entries


def _hub_tree(repo: str) -> list[dict[str, Any]]:
    url = f"{HUB}/api/models/{repo}/tree/main/onnx"
    with urllib.request.urlopen(url, timeout=30) as resp:
        tree: list[dict[str, Any]] = json.load(resp)
    return tree


def refresh(
    catalog: list[dict[str, Any]] | None = None,
    *,
    fetch: Callable[[str], list[dict[str, Any]]] = _hub_tree,
    cache: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Re-read each variant's files and download size from the Hugging Face Hub.

    A variant's files are the ONNX graphs and weight shards whose names end in
    its dtype (``model_q4f16.onnx``, ``embed_tokens_q4f16.onnx_data``…); vision
    and audio encoders are left out, the browser target being text-only. The
    result is written to the user cache unless ``cache`` is ``False``-y.

    Examples
    --------
    >>> tree = [{"path": "onnx/model_q4.onnx", "size": 10},
    ...         {"path": "onnx/model_q4.onnx_data", "lfs": {"size": 90}},
    ...         {"path": "onnx/vision_encoder_q4.onnx", "size": 5}]
    >>> cat = [{"id": "x/y", "variants": {"q4": {"needs_f16": False}}}]
    >>> out = refresh(cat, fetch=lambda repo: tree, cache=None)
    >>> out[0]["variants"]["q4"]["bytes"], out[0]["variants"]["q4"]["files"]
    (100, ['onnx/model_q4.onnx', 'onnx/model_q4.onnx_data'])
    """
    catalog = catalog if catalog is not None else load_browser_catalog()
    out = []
    for entry in catalog:
        tree = fetch(entry["id"])
        variants = {}
        for dtype, v in entry["variants"].items():
            files, size = [], 0
            for f in tree:
                name = f["path"].split("/")[-1]
                if "vision" in name or "audio" in name:
                    continue
                if name.split(".onnx")[0].endswith("_" + dtype):
                    files.append(f["path"])
                    size += (f.get("lfs") or {}).get("size") or f.get("size") or 0
            variants[dtype] = {**v, "bytes": size, "files": sorted(files)} if files else v
        out.append(
            {
                **entry,
                "variants": variants,
                "fetched_at": datetime.now(timezone.utc).date().isoformat(),
            }
        )
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out


def plan(
    usage: str = "rag-answer",
    *,
    languages: list[str] | None = None,
    catalog: list[dict[str, Any]] | None = None,
    policy: dict[str, Any] | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    """
    The ordered ladder of browser candidates for ``usage``, ready for a page.

    One rung per (model, dtype), best first: models by their rank for the usage
    (a measured score when the catalog carries one, the curator's prior
    otherwise), and within a model the ``shader-f16`` variant first, since it
    is both smaller and faster where it runs. A model that does not serve every
    language in ``languages`` is left out, and so is a model MEASURED on the
    usage below ``min_score``; the plan lists both under ``excluded``.

    Examples
    --------
    >>> p = plan("rag-answer", languages=["fr", "en"])
    >>> p["usage"], p["runtime"]
    ('rag-answer', 'transformers.js')
    >>> [c["model"].split("/")[1] + " " + c["dtype"] for c in p["candidates"]]
    ['gemma-4-E4B-it-ONNX q4f16', 'gemma-4-E4B-it-ONNX q4', 'gemma-4-E2B-it-ONNX q4f16', \
'gemma-4-E2B-it-ONNX q4']
    """
    from . import usages as _usages

    profile = _usages.get_usage(usage)  # KeyError on an unknown usage
    catalog = catalog if catalog is not None else load_browser_catalog()
    languages = languages or ["fr", "en"]

    def rank(e: dict[str, Any]) -> tuple[int, float, int]:
        measured = (e.get("measured") or {}).get(usage)
        prior = (e.get("tasks") or {}).get(usage, 99)
        # A measured score outranks any prior; higher score first, and the
        # prior breaks ties: on a few dozen questions, equal scores are common
        # and say nothing about which model is better.
        return (0, -measured, prior) if measured is not None else (1, 0, prior)

    pool, excluded = [], []
    for e in catalog:
        if usage not in (e.get("tasks") or {}):
            continue
        measured = (e.get("measured") or {}).get(usage)
        if not set(languages) <= set(e.get("languages", [])):
            excluded.append({"model": e["id"], "reason": "languages"})
        elif measured is not None and measured < min_score:
            excluded.append({"model": e["id"], "reason": f"measured {measured} < {min_score}"})
        else:
            pool.append(e)
    candidates = []
    for e in sorted(pool, key=rank):
        for dtype, v in sorted(e["variants"].items(), key=lambda kv: not kv[1].get("needs_f16")):
            candidates.append(
                {
                    "model": e["id"],
                    "family": e.get("family"),
                    "dtype": dtype,
                    "bytes": int(v["bytes"]),
                    "needs_f16": bool(v.get("needs_f16")),
                    "min_device_memory_gb": e.get("min_device_memory_gb"),
                    "files": [f"{HUB}/{e['id']}/resolve/main/{f}" for f in v.get("files", [])],
                    "loader": e.get("loader", "tokenizer"),
                    "chat_kwargs": e.get("chat_kwargs") or {},
                    "params_b": e.get("params_b"),
                    "license": e.get("license"),
                    "measured": (e.get("measured") or {}).get(usage),
                }
            )
    return {
        "usage": usage,
        "summary": profile.get("summary", ""),
        "runtime": "transformers.js",
        "transformers": TRANSFORMERS_JS,
        "languages": languages,
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "policy": {**DEFAULT_POLICY, **(policy or {})},
        "min_score": min_score,
        "candidates": candidates,
        "excluded": excluded,
    }


def choose(the_plan: dict[str, Any], device: dict[str, Any]) -> dict[str, Any]:
    """
    Walk the ladder for one device; the reference of the page's JavaScript.

    ``device`` holds what the page measured; every key is optional:
    ``webgpu``, ``f16``, ``mobile``, ``save_data``, ``effective_type``,
    ``device_memory_gb``, ``storage_free_bytes``, ``bandwidth_Bps`` and
    ``cached`` (the candidates, as ``"model|dtype"``, already in the cache).

    Returns ``{"candidate", "reason", "seconds"}``; ``candidate`` is None when
    nothing fits, and ``reason`` says why: ``webgpu``, ``mobile``, ``network``,
    ``device`` (no rung fits the GPU, memory or storage), ``download`` (every
    fitting rung is too long to fetch on this line). A cached rung costs no
    download, whatever its size.

    Examples
    --------
    >>> p = plan("rag-answer")
    >>> fast = {"webgpu": True, "f16": True, "bandwidth_Bps": 50e6}
    >>> c = choose(p, fast)
    >>> c["candidate"]["model"].split("/")[1], c["candidate"]["dtype"], c["reason"]
    ('gemma-4-E4B-it-ONNX', 'q4f16', 'ok')
    >>> mid = {**fast, "bandwidth_Bps": 20e6}            # 160 Mbit/s: E4B takes 4 min
    >>> choose(p, mid)["candidate"]["model"].split("/")[1]
    'gemma-4-E2B-it-ONNX'
    >>> choose(p, {**fast, "bandwidth_Bps": 5e6})["reason"]   # 40 Mbit/s: nothing in 3 min
    'download'
    >>> choose(p, {"webgpu": True, "mobile": True})["reason"]
    'mobile'
    """
    pol = the_plan["policy"]
    if not device.get("webgpu"):
        return {"candidate": None, "reason": "webgpu", "seconds": None}
    if device.get("mobile"):
        return {"candidate": None, "reason": "mobile", "seconds": None}
    if device.get("save_data") or device.get("effective_type") in pol["slow_networks"]:
        return {"candidate": None, "reason": "network", "seconds": None}
    cached = set(device.get("cached") or [])
    bandwidth = device.get("bandwidth_Bps") or pol["unknown_bandwidth_Bps"]
    fits_device = False
    for c in the_plan["candidates"]:
        if c["needs_f16"] and not device.get("f16"):
            continue
        mem = device.get("device_memory_gb")
        if mem is not None and c.get("min_device_memory_gb") and mem < c["min_device_memory_gb"]:
            continue
        if f"{c['model']}|{c['dtype']}" in cached:
            return {"candidate": c, "reason": "cached", "seconds": 0.0}
        free = device.get("storage_free_bytes")
        if free is not None and free < c["bytes"] * pol["storage_margin"]:
            continue
        fits_device = True
        seconds = c["bytes"] / bandwidth
        if seconds <= pol["max_download_s"]:
            return {"candidate": c, "reason": "ok", "seconds": round(seconds, 1)}
    return {"candidate": None, "reason": "download" if fits_device else "device", "seconds": None}
