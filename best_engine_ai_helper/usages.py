"""
usages — the sev7n usage catalog ("description d'usage").

A *usage profile* names a concrete sev7n workload (``text2sql``, ``rag-answer``,
``embeddings``, …) and states only its **needs**: task type, whether it needs
schema-constrained output, a comfort throughput floor, a memory headroom, an
advisory quality bar and context length. A profile never names a model — that
would defeat the whole tool. best-engine reads the needs, probes the machine,
and *chooses* the concrete local model, writing that choice into a gitignored,
machine-specific engine file (the extension of the ``env.sh`` it already emits).

Each profile is, at heart, a named ``llm.brief.yaml``: its ``brief`` block holds
exactly the fields :func:`engine.resolve` already understands, so a profile is
resolved by the same four-criteria picker (structured output, memory fit, task
fit, throughput) as any hand-written brief. The catalog supplies the criteria;
the picker supplies the model.

Profiles are grouped into **families** (``F1`` constrained-generation, ``F2``
prose-generation, ``F3`` embeddings) — the usages that can share one model. A
caller can resolve a whole family in one shot (one model for the group) or a
single profile (specialised) when the hardware allows it.

The bundled catalog is ``usages.yaml`` at the package root; a user overlay at
``~/.best-engine-ai-helper/usages_cache.yaml`` overrides profiles by ``name`` and
families by ``id``.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

from . import catalog as _catalog
from . import detect as _detect
from . import engine as _engine
from .score import effective_budget as _effective_budget

# Root of the installed package; usages.yaml sits next to models.yaml.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SEED_PATH = _PACKAGE_ROOT / "usages.yaml"

# User-writable overlay, mirroring the model-catalog cache convention.
_USER_DIR = Path.home() / ".best-engine-ai-helper"
_CACHE_PATH = _USER_DIR / "usages_cache.yaml"
CACHE_PATH = _CACHE_PATH

# Embedders are pulled and served through Ollama regardless of the generative
# backend, so the embed path fixes this base URL rather than the vLLM one.
_OLLAMA_URL = "http://localhost:11434"

# Benchmark key the embeddings family ranks its candidates on (MTEB average).
_EMBED_SCORE_KEY = "mteb"


def _load_doc(path: Path) -> dict[str, Any]:
    """
    Load a usage-catalog YAML document as a mapping, or ``{}`` if absent/empty.

    Parameters
    ----------
    path : Path
        Absolute path to the YAML file.

    Returns
    -------
    dict[str, Any]
        The parsed mapping (keys ``families`` / ``profiles``), or ``{}`` when the
        file is missing, empty, or malformed — so a missing overlay is a no-op.

    Examples
    --------
    >>> _load_doc(Path("/does/not/exist.yaml"))
    {}
    """
    if not osh.file_exists(str(path)):
        osh.debug(f"Usage catalog absent, treating as empty:\n\t{path}")
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        osh.warning(f"Malformed usage catalog, ignoring:\n\t{path}\n\t{exc}")
        return {}
    return raw if isinstance(raw, dict) else {}


def _merge_by_key(
    seed: list[dict[str, Any]], overlay: list[dict[str, Any]], key: str
) -> list[dict[str, Any]]:
    """
    Overlay entries onto seed entries by ``key``; seed order first, new appended.

    Parameters
    ----------
    seed : list[dict[str, Any]]
        The bundled entries.
    overlay : list[dict[str, Any]]
        User-cache entries; one whose ``key`` matches a seed entry replaces it.
    key : str
        The identity field (``"name"`` for profiles, ``"id"`` for families).

    Returns
    -------
    list[dict[str, Any]]
        Merged entries, seed order preserved, overlay-only entries appended.

    Examples
    --------
    >>> _merge_by_key([{"name": "a", "v": 1}], [{"name": "a", "v": 2}], "name")
    [{'name': 'a', 'v': 2}]
    """
    merged = {e[key]: e for e in seed}
    for entry in overlay:
        if key in entry:
            merged[entry[key]] = entry
    result = [merged[e[key]] for e in seed]
    seen = {e[key] for e in seed}
    result.extend(e for e in overlay if e.get(key) not in seen and key in e)
    return result


def load_usages(usages_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load the bundled usage profiles merged with the user overlay.

    Parameters
    ----------
    usages_path : Path or None
        Path to the seed ``usages.yaml``. Defaults to the bundled file; pass an
        explicit path in tests.

    Returns
    -------
    list[dict[str, Any]]
        Profile dicts, each with at least ``name``, ``brief`` and ``family``.

    Examples
    --------
    >>> names = [p["name"] for p in load_usages()]
    >>> "text2sql" in names and "embeddings" in names
    True
    """
    seed_doc = _load_doc(usages_path if usages_path is not None else _SEED_PATH)
    seed = list(seed_doc.get("profiles", []))
    overlay = list(_load_doc(_CACHE_PATH).get("profiles", []))
    return _merge_by_key(seed, overlay, "name")


def load_families(usages_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load the bundled families merged with the user overlay.

    Parameters
    ----------
    usages_path : Path or None
        Path to the seed ``usages.yaml``. Defaults to the bundled file.

    Returns
    -------
    list[dict[str, Any]]
        Family dicts, each with at least ``id``, ``brief`` and ``members``.

    Examples
    --------
    >>> [f["id"] for f in load_families()]
    ['F1', 'F2', 'F3']
    """
    seed_doc = _load_doc(usages_path if usages_path is not None else _SEED_PATH)
    seed = list(seed_doc.get("families", []))
    overlay = list(_load_doc(_CACHE_PATH).get("families", []))
    return _merge_by_key(seed, overlay, "id")


def list_usages() -> list[dict[str, Any]]:
    """
    Enumerate profiles for discovery: name, family, status, summary.

    Returns
    -------
    list[dict[str, Any]]
        One compact row per profile, in catalog order.

    Examples
    --------
    >>> rows = list_usages()
    >>> {"name", "family", "status", "summary"} <= set(rows[0])
    True
    """
    return [
        {
            "name": p["name"],
            "family": p.get("family"),
            "status": p.get("status", "stable"),
            "summary": p.get("summary", ""),
        }
        for p in load_usages()
    ]


def list_families() -> list[dict[str, Any]]:
    """
    Enumerate families for discovery: id, name, members, summary.

    Returns
    -------
    list[dict[str, Any]]
        One compact row per family, in catalog order.

    Examples
    --------
    >>> [r["id"] for r in list_families()]
    ['F1', 'F2', 'F3']
    """
    return [
        {
            "id": f["id"],
            "name": f.get("name", f["id"]),
            "members": f.get("members", []),
            "summary": f.get("summary", ""),
        }
        for f in load_families()
    ]


def get_usage(name: str) -> dict[str, Any]:
    """
    Return one profile by ``name``, with a helpful error when it is unknown.

    Parameters
    ----------
    name : str
        The profile name (e.g. ``"text2sql"``).

    Returns
    -------
    dict[str, Any]
        The profile dict.

    Raises
    ------
    KeyError
        If no profile carries that name; the message suggests close matches.

    Examples
    --------
    >>> get_usage("text2sql")["family"]
    'F1'
    """
    by_name = {p["name"]: p for p in load_usages()}
    if name in by_name:
        return by_name[name]
    close = difflib.get_close_matches(name, list(by_name), n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise KeyError(f"Unknown usage profile {name!r}.{hint} Known profiles: {', '.join(by_name)}.")


def get_family(family_id: str) -> dict[str, Any]:
    """
    Return one family by ``id``, with a helpful error when it is unknown.

    Parameters
    ----------
    family_id : str
        The family id (``"F1"``, ``"F2"`` or ``"F3"``).

    Returns
    -------
    dict[str, Any]
        The family dict.

    Raises
    ------
    KeyError
        If no family carries that id.

    Examples
    --------
    >>> get_family("F3")["name"]
    'embeddings'
    """
    by_id = {f["id"]: f for f in load_families()}
    if family_id in by_id:
        return by_id[family_id]
    raise KeyError(f"Unknown family {family_id!r}. Known families: {', '.join(by_id)}.")


def _brief_of(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Extract the resolvable brief from a profile or family, forcing local mode.

    Parameters
    ----------
    spec : dict[str, Any]
        A profile or family dict carrying a ``brief`` block.

    Returns
    -------
    dict[str, Any]
        A copy of the brief with ``mode: local`` set (the catalog is local-only).

    Examples
    --------
    >>> _brief_of({"brief": {"kind": "llm", "task": "x"}})["mode"]
    'local'
    """
    brief = dict(spec.get("brief", {}))
    brief.setdefault("mode", "local")
    return brief


def usage_brief(name: str) -> dict[str, Any]:
    """
    Return the resolvable brief for a profile (ready for :func:`engine.resolve`).

    Parameters
    ----------
    name : str
        The profile name.

    Returns
    -------
    dict[str, Any]
        The brief block with ``mode: local``.

    Examples
    --------
    >>> usage_brief("classification")["kind"]
    'llm'
    """
    return _brief_of(get_usage(name))


def family_brief(family_id: str) -> dict[str, Any]:
    """
    Return the representative brief for a family (ready for :func:`engine.resolve`).

    Parameters
    ----------
    family_id : str
        The family id.

    Returns
    -------
    dict[str, Any]
        The brief block with ``mode: local``.

    Examples
    --------
    >>> family_brief("F2")["kind"]
    'llm'
    """
    return _brief_of(get_family(family_id))


def _is_embedding(spec: dict[str, Any]) -> bool:
    """
    Report whether a profile/family is an embedding job (``kind: embed``).

    Parameters
    ----------
    spec : dict[str, Any]
        A profile or family dict.

    Returns
    -------
    bool
        True when its brief kind is ``embed``.

    Examples
    --------
    >>> _is_embedding({"brief": {"kind": "embed"}})
    True
    >>> _is_embedding({"brief": {"kind": "llm"}})
    False
    """
    return str(spec.get("brief", {}).get("kind", "")).strip().lower() == "embed"


def _resolve_embedding(
    spec: dict[str, Any],
    *,
    catalog: list[dict[str, Any]] | None,
    hw: dict[str, float | None] | None,
    compute: dict[str, Any] | None,
    headroom: float,
) -> dict[str, Any]:
    """
    Resolve an embedding need by memory fit over the catalog's ``embed`` models.

    An embedder is not a generative model, so it is not ranked by the LLM/VLM
    task-fit picker. Instead, among the catalog entries with ``kind: embed`` that
    fit the memory budget, the highest retrieval score (``mteb``) wins; if none
    fit, the smallest embedder is the last resort so the caller can warn.

    Parameters
    ----------
    spec : dict[str, Any]
        The embedding profile or family.
    catalog, hw, compute : optional
        Injectable for tests; default to the live catalog and detected hardware.
    headroom : float
        Memory safety fraction passed to :func:`score.effective_budget`.

    Returns
    -------
    dict[str, Any]
        An engine descriptor with an ``embed`` section (never committed).

    Examples
    --------
    >>> cat = [{"id": "small", "kind": "embed", "ram_gb": 0.5,
    ...         "benchmarks": {"mteb": 62}},
    ...        {"id": "big", "kind": "embed", "ram_gb": 1.2,
    ...         "benchmarks": {"mteb": 66}}]
    >>> hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    >>> d = _resolve_embedding(get_family("F3"), catalog=cat, hw=hw,
    ...                        compute={"chip": "M2", "accelerator": "apple"},
    ...                        headroom=0.5)
    >>> d["embed"]["model"], d["embed"]["fits"]
    ('big', True)
    """
    catalog = catalog if catalog is not None else _catalog.load_catalog()
    hw = hw if hw is not None else _detect.available_memory()
    compute = compute if compute is not None else _detect.compute_profile()
    budget = _effective_budget(hw, headroom=headroom)

    embedders = [e for e in catalog if e.get("kind") == "embed"]
    if not embedders:
        osh.warning("No embedding model in the catalog; F3 cannot be resolved.")
        chosen: dict[str, Any] | None = None
        fits = False
    else:

        def _score(e: dict[str, Any]) -> float:
            return float((e.get("benchmarks") or {}).get(_EMBED_SCORE_KEY) or 0.0)

        fitting = [e for e in embedders if float(e.get("ram_gb", 0) or 0) <= budget]
        if fitting:
            # Best retrieval quality that fits; ties broken toward the lighter one.
            chosen = max(fitting, key=lambda e: (_score(e), -float(e.get("ram_gb", 0) or 0)))
            fits = True
        else:
            # Nothing fits: smallest embedder, flagged, so the caller can warn.
            chosen = min(embedders, key=lambda e: float(e.get("ram_gb", 0) or 0))
            fits = False
            osh.warning(
                f"No embedder fits the {budget:.1f} GB budget; "
                f"falling back to smallest: {chosen.get('id')}"
            )

    memory_gb = hw.get("unified_gb") or hw.get("vram_gb") or hw.get("ram_gb")
    descriptor: dict[str, Any] = {
        "generated_by": "best-engine-ai-helper — machine-specific, do not commit",
        "mode": "local",
        "kind": "embed",
        "resolved_for": {
            "chip": compute.get("chip") or _detect.chip_vendor(),
            "accelerator": compute.get("accelerator"),
            "memory_gb": round(float(memory_gb), 1) if memory_gb else None,
        },
        # Ollama serves the embed tags locally, whatever the generative backend.
        "backend": "ollama",
        "base_url": _OLLAMA_URL,
        "headroom": headroom,
    }
    if chosen is not None:
        descriptor["embed"] = {
            "model": chosen["id"],
            "ram_gb": chosen.get("ram_gb"),
            "mteb": (chosen.get("benchmarks") or {}).get(_EMBED_SCORE_KEY),
            "fits": fits,
        }
        descriptor["serve"] = [f"ollama pull {chosen['id']}"]
    else:
        descriptor["embed"] = None
        descriptor["serve"] = []
    return descriptor


def _annotate(
    descriptor: dict[str, Any], spec: dict[str, Any], *, label_key: str
) -> dict[str, Any]:
    """
    Attach usage metadata to an engine descriptor and flag sub-quality picks.

    Parameters
    ----------
    descriptor : dict[str, Any]
        The engine descriptor from :func:`engine.resolve` or the embed path.
    spec : dict[str, Any]
        The profile or family it was resolved from.
    label_key : {'usage', 'family'}
        Which identity field to stamp on the descriptor.

    Returns
    -------
    dict[str, Any]
        The same descriptor, enriched in place.

    Examples
    --------
    >>> d = _annotate({"llm": {"score": 60}}, {"name": "x", "min_quality": 80},
    ...               label_key="usage")
    >>> d["usage"], d["min_quality"], d["llm"]["below_min_quality"]
    ('x', 80, True)
    """
    # A profile is stamped by its name; a family by its id (F1/F2/F3).
    descriptor[label_key] = (
        (spec.get("id") if label_key == "family" else spec.get("name"))
        or spec.get("name")
        or spec.get("id")
    )
    descriptor["status"] = spec.get("status", "stable")
    descriptor["local_strict"] = spec.get("local_strict", True)
    min_quality = spec.get("min_quality")
    descriptor["min_quality"] = min_quality
    descriptor["context_length_hint"] = spec.get("context_length")

    # An advisory quality bar: flag (never block) a pick whose benchmark on the
    # task axis lands below it, so the caller can decide whether to accept it.
    if min_quality is not None:
        for kind in ("llm", "vlm"):
            section = descriptor.get(kind)
            if not isinstance(section, dict):
                continue
            score = section.get("score")
            if score is not None and score < float(min_quality):
                section["below_min_quality"] = True
                osh.warning(
                    f"{descriptor[label_key]}: chosen {kind} scores {score:.0f} on "
                    f"its axis, below the profile's advisory floor {min_quality}."
                )
    return descriptor


def resolve_usage(
    name: str,
    *,
    backend: str = "auto",
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve a usage profile into a machine-specific engine descriptor.

    This is the "give me the model for profile ``name``" entry point. It reads
    only the profile's needs, then lets best-engine choose the concrete model for
    this machine. The returned descriptor is machine-specific: persist it to a
    **gitignored** file (see :func:`engine.write_engine`), never commit it.

    Parameters
    ----------
    name : str
        The profile name (``"text2sql"``, ``"rag-answer"``, …).
    backend : {'auto', 'ollama', 'vllm'}
        Serving backend; ``auto`` picks per :func:`engine.default_backend`.
    endpoint : str or None
        Override the server base URL.
    catalog, hw, compute : optional
        Injectable for tests; default to the live catalog and detected hardware.

    Returns
    -------
    dict[str, Any]
        The engine descriptor, annotated with the profile's metadata.

    Examples
    --------
    >>> hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    >>> compute = {"accelerator": "apple", "chip": "M2", "bandwidth_gbs": None}
    >>> cat = [{"id": "coder", "kind": "llm", "size_b": 7, "ram_gb": 5.0,
    ...         "benchmarks": {"general": 66, "code": 85},
    ...         "structured_output": True, "vllm_id": "org/Coder"}]
    >>> eng = resolve_usage("text2sql", backend="ollama", catalog=cat,
    ...                     hw=hw, compute=compute)
    >>> eng["llm"]["model"], eng["usage"], eng["status"]
    ('coder', 'text2sql', 'stable')
    """
    profile = get_usage(name)
    headroom = float(profile.get("brief", {}).get("headroom", 0.5))
    if _is_embedding(profile):
        descriptor = _resolve_embedding(
            profile, catalog=catalog, hw=hw, compute=compute, headroom=headroom
        )
    else:
        descriptor = _engine.resolve(
            _brief_of(profile),
            backend=backend,
            endpoint=endpoint,
            catalog=catalog,
            hw=hw,
            compute=compute,
        )
    return _annotate(descriptor, profile, label_key="usage")


def resolve_family(
    family_id: str,
    *,
    backend: str = "auto",
    endpoint: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    hw: dict[str, float | None] | None = None,
    compute: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve a whole family into one machine-specific engine descriptor.

    Resolving a family yields a single model for the group (the shared pick),
    whereas :func:`resolve_usage` yields the possibly-specialised model for one
    profile. The result is machine-specific — persist it gitignored, never commit.

    Parameters
    ----------
    family_id : str
        The family id (``"F1"``, ``"F2"``, ``"F3"``).
    backend, endpoint, catalog, hw, compute : see :func:`resolve_usage`.

    Returns
    -------
    dict[str, Any]
        The engine descriptor, annotated with the family's metadata.

    Examples
    --------
    >>> hw = {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    >>> cat = [{"id": "emb", "kind": "embed", "ram_gb": 1.2,
    ...         "benchmarks": {"mteb": 66}}]
    >>> eng = resolve_family("F3", catalog=cat, hw=hw,
    ...                      compute={"chip": "M2", "accelerator": "apple"})
    >>> eng["embed"]["model"], eng["family"]
    ('emb', 'F3')
    """
    family = get_family(family_id)
    headroom = float(family.get("brief", {}).get("headroom", 0.5))
    if _is_embedding(family):
        descriptor = _resolve_embedding(
            family, catalog=catalog, hw=hw, compute=compute, headroom=headroom
        )
    else:
        descriptor = _engine.resolve(
            _brief_of(family),
            backend=backend,
            endpoint=endpoint,
            catalog=catalog,
            hw=hw,
            compute=compute,
        )
    return _annotate(descriptor, family, label_key="family")
