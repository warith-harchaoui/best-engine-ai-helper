"""
recommend — the end-to-end "which engine" algorithm.

Takes three inputs, at least one of them allowed to be vague:

1. a **hardware description** (memory pool + compute profile),
2. the **benchmark catalog** (models with public scores), and
3. a **task**, which may be a free-text phrase ("retail product descriptions
   and image-quality checks") rather than a fixed keyword,

and returns the best local engine to pull for each kind the task needs
(LLM for text, VLM for images), justified by three factors it makes explicit:

- **task fit** — the model's benchmark on the axis the task maps to,
- **memory fit** — whether it fits the accelerator's usable budget (so it runs
  on the GPU, not spilled to CPU), and
- **throughput** — an estimate of decode tokens/s from memory bandwidth.

The result is a plain dict (ready for ``json.dumps``) and, via
:func:`to_markdown`, a human-readable report. Nothing here calls a model or the
network; it is pure ranking over the catalog and the detected hardware.

:func:`cloud_recommend` is the paid counterpart: same task-to-axis mapping
(:func:`parse_task`), but ranks :mod:`best_engine_ai_helper.cloud_catalog`'s
paid-model catalog on quality vs. price instead of local hardware fit — no
hardware probe, no API key, nothing reaches the network; it only tells you
which model *would* be picked. :func:`to_markdown` renders it as an extra
section when a report carries a ``"cloud"`` key (see :func:`to_markdown_cloud`).

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal, cast

import os_helper as osh

from .score import (
    COMFORT_TPS,
    MAX_HEADROOM,
    effective_budget,
    estimated_tokens_per_second,
    rank,
)

# A candidate scoring within this many benchmark points of the strongest allowed
# model is "good enough". Among that band we pick the LEANEST/fastest model, not
# the top scorer — the core anti-greed rule (a 12B that matches a 32B to within a
# few points but runs 3x faster is the better local default).
_SUFFICIENT_MARGIN: float = 3.0

# Keyword -> benchmark axis. The task text is scanned for these; the first axis
# whose keywords appear wins for the text model. Vision keywords additionally
# turn on the VLM recommendation. Deliberately small and legible: this is a
# heuristic to turn a vague phrase into a scoring axis, not an NLP model.
_AXIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ocr": ("ocr", "scan", "receipt", "invoice", "document", "handwrit"),
    "code": ("code", "coding", "program", "python", "sql", "javascript", "bug"),
    "math": ("math", "calculation", "arithmetic", "equation", "proof"),
    "vision": (
        "image",
        "vision",
        "visual",
        "photo",
        "picture",
        "diagram",
        "screenshot",
        "chart",
        "quality assessment",
        "aesthetic",
    ),
}
_VISION_AXES = {"vision", "ocr"}


def _detect_language(text: str) -> str | None:
    """
    Best-effort ISO 639-1 language code for a task description.

    Uses ``langdetect`` (deterministic, offline, no model call — a fixed
    n-gram profile, not an LLM). Recorded as metadata for activity monitoring
    (which languages a company's users actually write task descriptions in),
    not used as a reliability gate: langdetect is a known weak performer on
    short phrases and can be confidently wrong (e.g. "write SQL queries"
    detects as French at 99.9% confidence) rather than merely uncertain, so a
    low-confidence score would not be a trustworthy "unclean text" signal.
    An outright detection failure (no usable characters: symbols, digits-only)
    is a reliable signal and is surfaced by the caller instead.

    Parameters
    ----------
    text : str
        Non-empty task description (already stripped).

    Returns
    -------
    str or None
        The top-guess language code, or None if ``langdetect`` is not
        installed or detection raised (e.g. no alphabetic content).
    """
    try:
        from langdetect import LangDetectException, detect
    except ImportError:
        return None
    try:
        return str(detect(text))
    except LangDetectException:
        return None


def parse_task(task: str | None) -> dict[str, Any]:
    """
    Turn a vague task phrase into the model kinds and benchmark axis it implies.

    Returns a dict with ``kinds`` (subset of ``["llm", "vlm"]`` in pull order),
    ``application`` (the benchmark axis for the text model), ``matched`` (the
    keywords that fired, for the report's justification), and ``language``
    (best-effort ISO 639-1 code from :func:`_detect_language`, or None). A
    task that mentions nothing visual still gets an LLM on the ``generalist``
    axis; any vision keyword adds a VLM.

    Parameters
    ----------
    task : str or None
        Free-text task description. ``None``, a blank/whitespace-only string,
        or text with no detectable language (symbols/digits only) falls back
        to a generic text-assistant profile, but logs a loud warning first: a
        recommendation with no clean task description carries no useful label
        for activity/cost monitoring or for the report's justification, so a
        caller skipping it should see that reflected back.

    Examples
    --------
    >>> parse_task("write product descriptions and check photo quality")["kinds"]
    ['llm', 'vlm']
    >>> parse_task(None)["application"]  # logs a WARNING, still resolves
    'generalist'
    """
    stripped = (task or "").strip()
    language: str | None = None
    if not stripped:
        osh.warning(
            "recommend: no task description provided; falling back to a generic "
            "text-assistant profile. Pass a clear task description — activity "
            "and cost monitoring cannot attribute this call to a job without one."
        )
    else:
        language = _detect_language(stripped)
        if language is None:
            osh.warning(
                f"recommend: task description {stripped!r} has no detectable "
                "language (symbols/digits only?) — this does not look like a "
                "clean description; activity/cost monitoring works best with "
                "clear text."
            )
    text = stripped.lower()
    matched: list[str] = []
    axis = "generalist"
    for candidate_axis, words in _AXIS_KEYWORDS.items():
        hit = [w for w in words if w in text]
        if hit:
            matched.extend(hit)
            # A non-vision axis (code/math) sets the text model's axis; vision
            # keywords are recorded but the text axis stays generalist unless a
            # text-specific axis also matched.
            if candidate_axis not in _VISION_AXES:
                axis = candidate_axis

    needs_vlm = any(w in text for a in _VISION_AXES for w in _AXIS_KEYWORDS[a])
    kinds = ["llm"]
    if needs_vlm:
        kinds.append("vlm")
    # If the task is purely an OCR axis, the VLM should be scored on ocr.
    vlm_axis = "ocr" if any(w in text for w in _AXIS_KEYWORDS["ocr"]) else "vision"
    return {
        "kinds": kinds,
        "application": axis,
        "vlm_application": vlm_axis,
        "matched": sorted(set(matched)),
        "language": language,
    }


def _candidate_row(
    entry: dict[str, Any],
    budget: float,
    bandwidth_gbs: float | None,
    axis: str,
    min_tps: float = COMFORT_TPS,
    backend: str = "ollama",
) -> dict[str, Any]:
    """One catalog entry annotated with the four decision factors.

    ``ram_gb``, ``fits`` and ``est_tokens_per_s`` are computed for ``backend``:
    an Ollama pick sizes against the Q4 ``ram_gb``, a vLLM pick against the
    heavier FP16 footprint (see :func:`score.model_footprint_gb`).
    """
    from .score import _benchmark_score, model_footprint_gb  # local: internal

    ram = model_footprint_gb(entry, backend)
    kind = entry.get("kind", "llm")
    fits = ram <= budget

    # Take the figure `rank` already resolved rather than recomputing one.
    # `rank` is the only place that knows whether a measurement exists for this
    # exact (model, machine) pair, and recomputing the estimate here discarded
    # it: a model measured at 8 tok/s against a 20 tok/s floor came back
    # `comfortable` at its estimated 43 tok/s, which put it back in the pool
    # `_pick_sufficient` chooses from -- so the measurement demoted it in the
    # ranking and then lost the decision anyway. Entries that did not come
    # through `rank` (none today, but the function does not require it) still
    # get the estimate.
    if "_tps_basis" in entry:
        tps = entry.get("_tps")
        basis = entry.get("_tps_basis")
    else:
        tps = estimated_tokens_per_second(entry, bandwidth_gbs, backend)
        basis = "estimated" if tps is not None else None

    return {
        "id": entry.get("id"),
        # HuggingFace id (vLLM) and parameter count carried through so the
        # resolver can build a vLLM engine entry without re-reading the catalog.
        "vllm_id": entry.get("vllm_id"),
        "size_b": entry.get("size_b"),
        "kind": kind,
        "ram_gb": ram,
        "score": _benchmark_score(entry, kind, axis),
        "fits": fits,
        # False = can't honour structured JSON output, so it is never auto-chosen
        # for the helper's schema-driven tasks (see score.rank).
        "structured_output": entry.get("structured_output", True) is not False,
        "est_tokens_per_s": tps,
        # Where that number came from: "measured" on this machine, "estimated"
        # from memory bandwidth, or None when neither was available. Carried
        # into the row because every display of `est_tokens_per_s` would
        # otherwise read as an estimate, including the ones that are not.
        "tps_basis": basis,
        # Fits in memory AND decodes fast enough to be usable interactively. When
        # throughput is unknown (tps is None) speed can't be judged, so it is
        # not held against the model — memory fit alone decides.
        "comfortable": fits and (tps is None or tps >= min_tps),
        # Set by score.rank when the caller supplied the daemon's tag list.
        "installed": bool(entry.get("_installed")),
        "notes": entry.get("notes", ""),
    }


def _pick_sufficient(pool: list[dict[str, Any]], require_structured: bool = True) -> dict[str, Any]:
    """Return the leanest model within :data:`_SUFFICIENT_MARGIN` points of the best.

    ``pool`` is sorted best-first (structured-capable, then benchmark score), so
    ``pool[0]`` is the strongest allowed candidate. Among every candidate scoring
    within the margin of it — and no less structured-capable — the one with the
    smallest memory footprint wins. This is the anti-greed pick: good enough on
    quality, cheapest to run, rather than the absolute top scorer.

    Footprint is compared to the nearest gigabyte, and a model already on disk
    wins inside that rounding. The two costs are not the same kind of thing: a
    gigabyte of footprint is paid on every single run, while a download is paid
    once, so leanness stays the primary key and "already here" only decides
    between models that are equally lean in any sense the user would notice.
    """
    top = pool[0]
    near = [
        r
        for r in pool
        if r["score"] >= top["score"] - _SUFFICIENT_MARGIN
        and (not require_structured or r["structured_output"] or not top["structured_output"])
    ]
    if not near:
        return top
    return min(near, key=lambda r: (round(float(r["ram_gb"])), not r.get("installed", False)))


def recommend(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    task: str | None = None,
    *,
    headroom: float = MAX_HEADROOM,
    compute: dict[str, Any] | None = None,
    min_tps: float = COMFORT_TPS,
    backend: str = "ollama",
    kinds: list[Literal["llm", "vlm"]] | None = None,
    load: dict[str, Any] | None = None,
    installed: set[str] | None = None,
    require_structured: bool = True,
) -> dict[str, Any]:
    """
    Recommend the best engine per needed kind for this hardware and task.

    Parameters
    ----------
    hw : dict
        Memory description from :func:`detect.available_memory`.
    catalog : list of dict
        Benchmark catalog from :func:`catalog.load_catalog`.
    task : str or None
        Free-text or keyword task. None means a generalist text assistant.
    headroom : float
        Memory safety margin passed to :func:`score.effective_budget` (clamped to
        :data:`score.MAX_HEADROOM`).
    compute : dict or None
        Compute profile from :func:`detect.compute_profile` (accelerator +
        bandwidth). None disables the throughput estimate.
    min_tps : float
        Comfort throughput floor; a fitting model below it is only picked when no
        comfortable one exists (and the choice is warned about).
    backend : {'ollama', 'vllm'}
        Serving backend, so memory fit and throughput reflect what actually
        loads. Threaded to :func:`score.rank` and :func:`_candidate_row`.
    require_structured : bool
        Whether the job needs schema-constrained output. True (the default)
        keeps a model that cannot honour it out of auto-selection; False lets
        such a model win on score alone, which is what a brief saying
        ``structured_output: false`` is asking for.
    installed : set of str or None
        Tags the local daemon already serves. Breaks ties between candidates of
        comparable quality and comparable footprint, so a model already on disk
        is preferred over an equivalent 20 GB download. Never overrides quality
        or leanness.
    kinds : list of str or None
        Explicit kinds to resolve (``["llm"]``, ``["vlm"]`` or both), overriding
        the kinds inferred from ``task``. The task text still selects the
        benchmark axis. Used when the caller already knows what it needs (e.g. a
        brief that declares ``kind: both``).
    load : dict or None
        Live server state from :func:`detect.server_load` (current free RAM,
        CPU/GPU/disk usage, already-running engines). Forwarded to
        :func:`score.effective_budget`/:func:`score.rank` so the recommendation
        reflects what else is happening on this machine right now, not only its
        theoretical capacity. None (the default) reproduces the load-blind
        behaviour exactly; also included as ``server_load`` in the returned
        report when given, for activity monitoring.

    Returns
    -------
    dict
        A JSON-ready report: the parsed task, hardware, memory budget, and for
        each needed kind the chosen model plus the full ranked candidate table,
        with per-model fit and estimated throughput.
    """
    compute = compute or {}
    bandwidth = compute.get("bandwidth_gbs")
    budget = effective_budget(hw, headroom=headroom, load=load)
    parsed = parse_task(task)
    needed_kinds = (
        kinds if kinds is not None else cast(list[Literal["llm", "vlm"]], parsed["kinds"])
    )
    osh.info(
        f"Recommending for task axis '{parsed['application']}' "
        f"(kinds: {', '.join(needed_kinds)}, backend: {backend}); "
        f"memory budget {budget:.1f} GB"
    )

    picks: dict[str, Any] = {}
    for kind in needed_kinds:
        axis = parsed["vlm_application"] if kind == "vlm" else parsed["application"]
        ranked = rank(
            hw,
            catalog,
            kind,
            headroom=headroom,
            application=axis,
            backend=backend,
            load=load,
            # Both of these were missing, and their absence silently switched
            # off the measured-throughput gate on this path. `rank` only
            # demotes a model it has *measured* below the floor, and it can
            # only do that when it is told the floor -- `min_tps` defaults to
            # None, which means "no floor", so every measurement was collected
            # and then ignored. `bandwidth_gbs` is the same kind of omission
            # one layer down: without it `rank` cannot estimate at all, so
            # entries with no measurement came back with `_tps = None`.
            bandwidth_gbs=bandwidth,
            min_tps=min_tps,
            installed=installed,
            require_structured=require_structured,
        )
        rows = [_candidate_row(e, budget, bandwidth, axis, min_tps, backend) for e in ranked]
        fitting = [r for r in rows if r["fits"]]
        comfortable = [r for r in fitting if r["comfortable"]]
        # Prefer models that fit memory AND decode fast enough to be usable; fall
        # back to fitting-but-slow only when nothing is comfortable, then to an
        # over-budget last resort. Within the chosen tier, _pick_sufficient takes
        # the LEANEST model within a few benchmark points of the best (anti-greed)
        # rather than the top scorer.
        pool = comfortable or fitting or rows
        chosen: dict[str, Any] | None = _pick_sufficient(pool, require_structured) if pool else None
        if chosen is None:
            osh.warning(f"No candidate found for kind '{kind}' on axis '{axis}'")
        else:
            osh.info(
                f"Chosen {kind} on axis '{axis}': {chosen['id']} "
                f"({chosen['ram_gb']:.1f} GB, {'fits' if chosen['fits'] else 'over budget'})"
            )
            if require_structured and not chosen.get("structured_output", True):
                # Only happens when no structured-capable model fits the budget
                # (e.g. a small machine, where the only VLMs that fit are the
                # Qwen3-VL family). Say so plainly so the caller can warn the user
                # rather than silently getting empty structured responses.
                osh.warning(
                    f"Chosen {kind} '{chosen['id']}' does NOT support Ollama structured "
                    "JSON output; schema-driven tasks (intent, critique) will fail on it. "
                    "Pull a structured-capable model or free up memory for one."
                )
            if chosen["fits"] and not chosen.get("comfortable", True):
                # Fits in memory but decodes below the comfort floor: the classic
                # "it loads, but it crawls" pick. Say so plainly instead of
                # silently recommending a model that makes the machine feel stuck.
                #
                # Name the basis. "Estimated at 8 tok/s" invites the reader to
                # discount the number as a model's guess; "measured at 8 tok/s"
                # does not, and when it was measured here the second sentence is
                # the true one. Reaching this line at all means nothing
                # comfortable was available, so the warning is the only place
                # the distinction still gets made.
                how = "measured at " if chosen.get("tps_basis") == "measured" else "estimated at ~"
                osh.warning(
                    f"Chosen {kind} '{chosen['id']}' fits memory but is {how}"
                    f"{chosen['est_tokens_per_s']} tok/s (< {min_tps:.0f} comfortable); "
                    "expect sluggish interactive use — a smaller model would feel faster."
                )
        # Lightest model within 3 benchmark points of the chosen one: the
        # "good enough but leaner / faster" alternative worth surfacing. It must
        # not be less structured-output-capable than the chosen model, otherwise
        # the "leaner" pick would silently fail the suite's schema-driven tasks
        # (e.g. suggesting a Qwen3-VL under a structured-capable chosen).
        lighter = None
        if chosen:
            near = [
                r
                for r in (comfortable or fitting)
                if r["score"] >= chosen["score"] - 3
                and (
                    not require_structured
                    or r["structured_output"]
                    or not chosen["structured_output"]
                )
            ]
            if near:
                lighter = min(near, key=lambda r: r["ram_gb"])
                if lighter["id"] == chosen["id"]:
                    lighter = None
        picks[kind] = {
            "axis": axis,
            "chosen": chosen,
            "lighter_alternative": lighter,
            "candidates": rows,
        }

    return {
        "task": {"input": task, **parsed},
        "hardware": {**hw, **({"compute": compute} if compute else {})},
        **({"server_load": load} if load else {}),
        "memory_budget_gb": budget,
        "headroom": headroom,
        "comfort_tps": min_tps,
        "recommendations": picks,
        "method": _METHOD_NOTE,
        "sources": _SOURCES,
    }


_METHOD_NOTE = (
    "Each model is judged on four explicit factors: structured-output capability "
    "(whether it honours Ollama JSON-schema output -- the helper routes every "
    "task through a schema, so a model that can't is never auto-chosen however "
    "high it scores), task fit (its benchmark on the task's axis), memory fit "
    "(whether its peak-inference RAM fits the accelerator's usable budget, so it "
    "runs on the GPU rather than spilling to CPU), and throughput (estimated "
    "decode tokens/s = memory bandwidth / model size x 0.65 efficiency, because "
    "generation is memory-bandwidth bound). The chosen model is the highest "
    "task-fit, structured-capable model that BOTH fits the memory budget AND "
    "clears the comfort throughput floor (estimated tokens/s >= comfort_tps): a "
    "model that merely fits memory but decodes too slowly to be usable is flagged "
    "and never auto-chosen over a comfortable one, however high it scores. A "
    "lighter alternative is offered when one is nearly as strong but smaller and faster."
)

_SOURCES = [
    "Apple Metal recommendedMaxWorkingSetSize ~66% (<=36 GB) / ~75% (>36 GB) of "
    "unified memory (apple-specs, Metal docs).",
    "Inference RAM = weights + KV cache (15-20%) + overhead (5-10%), up to ~2x "
    "weights at long context (local-LLM sizing guides).",
    "Decode is memory-bandwidth bound: tokens/s ~= bandwidth / active-model-bytes, "
    "derated to ~50-80% real-world (llama.cpp / MLX benchmarks).",
]


_CLOUD_METHOD_NOTE = (
    "Each paid model is judged on two explicit factors, min-max normalized across "
    "the candidate pool: task fit (its benchmark on the task's axis) and price "
    "(the blended $/1M-token list price -- cheaper is better). quality_vs_cost "
    "(0..1) weighs the two: 1.0 picks purely on benchmark score, 0.0 picks purely "
    "on price, 0.7 (the default) leans quality with price as a tiebreaker. "
    "Structured-output capability is checked first, exactly as in local mode: a "
    "model that cannot honour a JSON schema is never auto-chosen over one that "
    "can. This is a REFERENCE ranking, not a live call: it needs no API key and "
    "reaches no network, and the benchmark figures are hand-maintained seed "
    "values (see pricing.yaml) -- good for comparing candidates against each "
    "other, not a substitute for checking the provider's own current numbers."
)


def cloud_recommend(
    task: str | None = None,
    *,
    kinds: list[Literal["llm", "vlm"]] | None = None,
    quality_vs_cost: float | None = None,
    provider: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Recommend the best PAID model per needed kind for a task (reference only).

    The cloud counterpart of :func:`recommend`: same :func:`parse_task` mapping
    from a free-text task to the kinds needed and the benchmark axis, but ranks
    :mod:`best_engine_ai_helper.cloud_catalog`'s paid-model catalog on quality vs.
    price instead of local memory/throughput fit. No hardware probe, no API key,
    no network call — every paid model in the catalog is reachable from any
    machine, so there is nothing to detect; this only tells you which one *would*
    be picked.

    Parameters
    ----------
    task : str or None
        Free-text or keyword task, same parsing as :func:`recommend`.
    kinds : list of {'llm', 'vlm'} or None
        Explicit kinds to resolve, overriding the kinds inferred from ``task``.
    quality_vs_cost : float or None
        0..1 weight on quality vs. price (clamped into range by
        :mod:`cloud_catalog`). ``None`` uses
        :data:`cloud_catalog.DEFAULT_QUALITY_VS_COST`.
    provider : str or None
        Restrict candidates to one provider (e.g. ``"openai"``). ``None`` ranks
        across every provider in the catalog.
    catalog : list[dict[str, Any]] or None
        Injectable for tests; defaults to :func:`cloud_catalog.load_cloud_catalog`.

    Returns
    -------
    dict
        A JSON-ready report: the parsed task, the quality/price weight, and for
        each needed kind the chosen paid model plus the full ranked candidate
        table (mirrors :func:`recommend`'s shape under ``"recommendations"``).

    Examples
    --------
    >>> catalog = [{"id": "m", "provider": "p", "kind": "llm",
    ...             "structured_output": True, "benchmarks": {"general": 80},
    ...             "input_per_1m": 1.0, "output_per_1m": 2.0}]
    >>> rep = cloud_recommend("write a summary", catalog=catalog)
    >>> rep["recommendations"]["llm"]["chosen"]["id"]
    'm'
    """
    from . import cloud_catalog as _cc

    cat = catalog if catalog is not None else _cc.load_cloud_catalog()
    weight = _cc.DEFAULT_QUALITY_VS_COST if quality_vs_cost is None else quality_vs_cost
    parsed = parse_task(task)
    needed_kinds = (
        kinds if kinds is not None else cast(list[Literal["llm", "vlm"]], parsed["kinds"])
    )

    picks: dict[str, Any] = {}
    for kind in needed_kinds:
        axis = parsed["vlm_application"] if kind == "vlm" else parsed["application"]
        ranked = _cc.rank_cloud(cat, kind, axis, weight, provider=provider)
        picks[kind] = {"axis": axis, "chosen": ranked[0] if ranked else None, "candidates": ranked}

    return {
        "task": {"input": task, **parsed},
        "quality_vs_cost": _cc._clamp_weight(weight),
        "provider_filter": provider,
        "recommendations": picks,
        "method": _CLOUD_METHOD_NOTE,
    }


def _fmt_tps(v: float | None, basis: str | None = None) -> str:
    """Format tokens/s, marking a measured figure with a trailing ``*``.

    The convention is the one `candidates` already prints and the README
    already documents: ``*`` means measured on this machine, anything else is
    an estimate from memory bandwidth. Reusing it rather than inventing a
    second marker for the same distinction, since two notations for one fact
    is worse than either.

    Examples
    --------
    >>> _fmt_tps(42.4, "measured")
    '42*'
    >>> _fmt_tps(42.4)
    '~42'
    >>> _fmt_tps(None)
    '-'
    """
    # `is None`, not falsiness: a measured 0.0 tok/s is a real and alarming
    # answer, and reporting it as "-" would hide a stalled daemon behind the
    # same dash that means "nobody asked". See scripts/measure_absent_vs_zero.py
    # for why this package treats that confusion as a defect family rather
    # than a style question.
    if v is None:
        return "-"
    return f"{v:.0f}*" if basis == "measured" else f"~{v:.0f}"


def to_markdown(report: dict[str, Any]) -> str:
    """Render a :func:`recommend` report as a Markdown document."""
    hw = report["hardware"]
    comp = hw.get("compute", {}) or {}
    task = report["task"]
    lines: list[str] = []
    lines.append("# Best local engine — recommendation")
    lines.append("")
    lines.append(f"**Task:** {task.get('input') or 'general text assistant'}  ")
    if task.get("language"):
        lines.append(f"**Language:** {task['language']}  ")
    if task.get("matched"):
        lines.append(f"**Matched keywords:** {', '.join(task['matched'])}  ")
    lines.append(f"**Needs:** {', '.join(k.upper() for k in task['kinds'])}")
    lines.append("")
    lines.append("## Hardware")
    lines.append("")
    lines.append(
        f"- Chip / accelerator: {comp.get('chip') or '?'} ({comp.get('accelerator', 'unknown')})"
    )
    pool = hw.get("unified_gb") or hw.get("vram_gb") or hw.get("ram_gb")
    lines.append(f"- Memory pool: {pool} GB")
    if comp.get("bandwidth_gbs"):
        lines.append(
            f"- Memory bandwidth: {comp['bandwidth_gbs']:.0f} GB/s (sets the decode-speed ceiling)"
        )
    lines.append(
        f"- Usable model budget: **{report['memory_budget_gb']:.1f} GB** "
        f"(headroom {report['headroom']})"
    )
    if report.get("comfort_tps"):
        lines.append(
            f"- Comfort throughput floor: **{report['comfort_tps']:.0f} tok/s** "
            "(a model below this fits memory but decodes too slowly to recommend)"
        )
    lines.append("")

    load = report.get("server_load")
    if load:
        lines.append("## Server load (live, at recommendation time)")
        lines.append("")
        lines.append(f"- Available RAM: {load['available_ram_gb']:.1f} GB")
        gpu_pct = load.get("gpu_percent")
        gpu_suffix = f", GPU: {gpu_pct:.0f}%" if gpu_pct is not None else ""
        lines.append(f"- CPU: {load['cpu_percent']:.0f}%" + gpu_suffix)
        lines.append(
            f"- Disk free: {load['disk_free_gb']:.1f} GB ({load['disk_percent_used']:.0f}% used)"
        )
        lines.append(f"- Already-running engines: {load['running_engines']}")
        lines.append("")

    for kind, block in report["recommendations"].items():
        chosen = block["chosen"]
        lines.append(f"## Best {kind.upper()} (axis: {block['axis']})")
        lines.append("")
        if chosen:
            tps = _fmt_tps(chosen["est_tokens_per_s"], chosen.get("tps_basis"))
            if not chosen["fits"]:
                flag = "  ⚠️ exceeds memory budget (spills to CPU)"
            elif not chosen.get("comfortable", True):
                flag = "  ⚠️ below comfort floor (fits but decodes slowly)"
            else:
                flag = ""
            lines.append(
                f"**→ `{chosen['id']}`** — {chosen['ram_gb']:.1f} GB, "
                f"score {chosen['score']:.0f}, {tps} tok/s" + flag
            )
            alt = block["lighter_alternative"]
            if alt:
                lines.append("")
                lines.append(
                    f"Lighter alternative: `{alt['id']}` — "
                    f"{alt['ram_gb']:.1f} GB, score {alt['score']:.0f}, "
                    f"{_fmt_tps(alt['est_tokens_per_s'], alt.get('tps_basis'))} tok/s."
                )
        else:
            lines.append("_No candidate found._")
        lines.append("")
        lines.append("| model | RAM GB | score | fits | tok/s | comfy |")
        lines.append("|---|---|---|---|---|---|")
        for r in block["candidates"]:
            lines.append(
                f"| `{r['id']}` | {r['ram_gb']:.1f} | {r['score']:.0f} | "
                f"{'yes' if r['fits'] else 'no'} | "
                f"{_fmt_tps(r['est_tokens_per_s'], r.get('tps_basis'))} | "
                f"{'yes' if r.get('comfortable') else 'no'} |"
            )
        lines.append("")
        lines.append(
            "`*` marks a figure measured on this machine; "
            "`~` marks an estimate from memory bandwidth."
        )
        lines.append("")

    lines.append("## How this was decided")
    lines.append("")
    lines.append(report["method"])
    lines.append("")
    lines.append("Sources:")
    for s in report["sources"]:
        lines.append(f"- {s}")
    lines.append("")

    # A "cloud" key (see cloud_recommend) renders as an extra section, so a
    # single to_markdown(report) call covers both the local pick (this
    # function's own body) and the reference paid pick, in one document.
    if report.get("cloud"):
        lines.append(to_markdown_cloud(report["cloud"]))

    return "\n".join(lines)


def to_markdown_cloud(report: dict[str, Any]) -> str:
    """Render a :func:`cloud_recommend` report as a Markdown section.

    Parameters
    ----------
    report : dict[str, Any]
        Output of :func:`cloud_recommend`.

    Returns
    -------
    str
        A Markdown document, structurally parallel to :func:`to_markdown`'s
        per-kind sections but scored on quality-vs-price instead of memory fit.
    """
    task = report["task"]
    lines: list[str] = []
    lines.append("# Best cloud engine — recommendation (reference, no API key needed)")
    lines.append("")
    lines.append(f"**Task:** {task.get('input') or 'general text assistant'}  ")
    lines.append(f"**Needs:** {', '.join(k.upper() for k in task['kinds'])}  ")
    lines.append(
        f"**Quality vs. cost:** {report['quality_vs_cost']:.2f} "
        "(1.0 = best benchmark regardless of price, 0.0 = cheapest regardless of quality)"
    )
    if report.get("provider_filter"):
        lines.append(f"**Provider filter:** {report['provider_filter']}")
    lines.append("")

    for kind, block in report["recommendations"].items():
        chosen = block["chosen"]
        lines.append(f"## Best cloud {kind.upper()} (axis: {block['axis']})")
        lines.append("")
        if chosen:
            price = chosen["price_per_1m"]
            # None means nobody priced this entry, which is not zero. Printing
            # "$0.00" would state a fact the catalog does not contain.
            cost = f"~${price:.2f}/1M tokens (blended)" if price is not None else "price unknown"
            lines.append(
                f"**→ `{chosen['id']}`** ({chosen['provider']}) — "
                f"score {chosen['score']:.0f}, {cost}"
            )
        else:
            lines.append("_No candidate found._")
        lines.append("")
        lines.append("| model | provider | score | $/1M | structured |")
        lines.append("|---|---|---|---|---|")
        for r in block["candidates"]:
            price = r["price_per_1m"]
            lines.append(
                f"| `{r['id']}` | {r['provider']} | {r['score']:.0f} | "
                f"{f'{price:.2f}' if price is not None else '?'} | "
                f"{'yes' if r.get('structured_output', True) else 'no'} |"
            )
        lines.append("")

    lines.append("## How the cloud pick was decided")
    lines.append("")
    lines.append(report["method"])
    lines.append("")
    return "\n".join(lines)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically: no reader ever sees a partial write.

    Writes to a sibling temp file in the same directory (so the final
    ``os.replace`` is a same-filesystem rename, not a cross-filesystem copy)
    then renames it over the destination.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_report(report: dict[str, Any], stem: str | Path) -> tuple[Path, Path]:
    """Write both a JSON and a Markdown rendering; return (md_path, json_path)."""
    stem = Path(stem)
    md_path = stem.with_suffix(".md")
    json_path = stem.with_suffix(".json")
    osh.make_directory(str(md_path.parent))
    _atomic_write_text(md_path, to_markdown(report))
    _atomic_write_text(json_path, json.dumps(report, indent=2))
    osh.info(f"Wrote recommendation report:\n\t{md_path}\n\t{json_path}")
    return md_path, json_path
