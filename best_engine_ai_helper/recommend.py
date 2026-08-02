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

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import os_helper as osh

from .score import COMFORT_TPS, effective_budget, estimated_tokens_per_second, rank

# Keyword -> benchmark axis. The task text is scanned for these; the first axis
# whose keywords appear wins for the text model. Vision keywords additionally
# turn on the VLM recommendation. Deliberately small and legible: this is a
# heuristic to turn a vague phrase into a scoring axis, not an NLP model.
_AXIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ocr": ("ocr", "scan", "receipt", "invoice", "document", "handwrit"),
    "code": ("code", "coding", "program", "python", "sql", "javascript", "bug"),
    "math": ("math", "calculation", "arithmetic", "equation", "proof"),
    "vision": ("image", "vision", "visual", "photo", "picture", "diagram",
               "screenshot", "chart", "quality assessment", "aesthetic"),
}
_VISION_AXES = {"vision", "ocr"}


def parse_task(task: str | None) -> dict[str, Any]:
    """
    Turn a vague task phrase into the model kinds and benchmark axis it implies.

    Returns a dict with ``kinds`` (subset of ``["llm", "vlm"]`` in pull order),
    ``application`` (the benchmark axis for the text model), and ``matched``
    (the keywords that fired, for the report's justification). A task that
    mentions nothing visual still gets an LLM on the ``generalist`` axis; any
    vision keyword adds a VLM.
    """
    text = (task or "").lower()
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

    needs_vlm = any(
        w in text for a in _VISION_AXES for w in _AXIS_KEYWORDS[a]
    )
    kinds = ["llm"]
    if needs_vlm:
        kinds.append("vlm")
    # If the task is purely an OCR axis, the VLM should be scored on ocr.
    vlm_axis = "ocr" if any(w in text for w in _AXIS_KEYWORDS["ocr"]) else "vision"
    return {"kinds": kinds, "application": axis, "vlm_application": vlm_axis,
            "matched": sorted(set(matched))}


def _candidate_row(
    entry: dict[str, Any], budget: float, bandwidth_gbs: float | None, axis: str,
    min_tps: float = COMFORT_TPS,
) -> dict[str, Any]:
    """One catalog entry annotated with the four decision factors."""
    from .score import _benchmark_score  # local: internal scorer

    ram = float(entry.get("ram_gb", 0) or 0)
    kind = entry.get("kind", "llm")
    fits = ram <= budget
    tps = estimated_tokens_per_second(entry, bandwidth_gbs)
    return {
        "id": entry.get("id"),
        "kind": kind,
        "ram_gb": ram,
        "score": _benchmark_score(entry, kind, axis),
        "fits": fits,
        # False = can't honour Ollama structured JSON output, so it is never
        # auto-chosen for the helper's schema-driven tasks (see score.rank).
        "structured_output": entry.get("structured_output", True) is not False,
        "est_tokens_per_s": tps,
        # Fits in memory AND decodes fast enough to be usable interactively. When
        # bandwidth is unknown (tps is None) speed can't be estimated, so it is
        # not held against the model — memory fit alone decides.
        "comfortable": fits and (tps is None or tps >= min_tps),
        "notes": entry.get("notes", ""),
    }


def recommend(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    task: str | None = None,
    *,
    headroom: float = 0.85,
    compute: dict[str, Any] | None = None,
    min_tps: float = COMFORT_TPS,
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
        Memory safety margin passed to :func:`score.effective_budget`.
    compute : dict or None
        Compute profile from :func:`detect.compute_profile` (accelerator +
        bandwidth). None disables the throughput estimate.

    Returns
    -------
    dict
        A JSON-ready report: the parsed task, hardware, memory budget, and for
        each needed kind the chosen model plus the full ranked candidate table,
        with per-model fit and estimated throughput.
    """
    compute = compute or {}
    bandwidth = compute.get("bandwidth_gbs")
    budget = effective_budget(hw, headroom=headroom)
    parsed = parse_task(task)
    osh.info(
        f"Recommending for task axis '{parsed['application']}' "
        f"(kinds: {', '.join(parsed['kinds'])}); memory budget {budget:.1f} GB"
    )

    picks: dict[str, Any] = {}
    for kind in parsed["kinds"]:
        axis = parsed["vlm_application"] if kind == "vlm" else parsed["application"]
        ranked = rank(hw, catalog, kind, headroom=headroom, application=axis)
        rows = [_candidate_row(e, budget, bandwidth, axis, min_tps) for e in ranked]
        fitting = [r for r in rows if r["fits"]]
        comfortable = [r for r in fitting if r["comfortable"]]
        # Prefer the highest-scoring model that both fits memory AND decodes fast
        # enough to be usable; fall back to a fitting-but-slow model only when
        # nothing comfortable exists, and to an over-budget model as a last resort.
        chosen = (comfortable or fitting or rows or [None])[0]
        if chosen is None:
            osh.warning(f"No candidate found for kind '{kind}' on axis '{axis}'")
        else:
            osh.info(
                f"Chosen {kind} on axis '{axis}': {chosen['id']} "
                f"({chosen['ram_gb']:.1f} GB, {'fits' if chosen['fits'] else 'over budget'})"
            )
            if not chosen.get("structured_output", True):
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
                osh.warning(
                    f"Chosen {kind} '{chosen['id']}' fits memory but is estimated at "
                    f"~{chosen['est_tokens_per_s']} tok/s (< {min_tps:.0f} comfortable); "
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
                r for r in (comfortable or fitting)
                if r["score"] >= chosen["score"] - 3
                and (r["structured_output"] or not chosen["structured_output"])
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


def _fmt_tps(v: float | None) -> str:
    return f"{v:.0f}" if v else "-"


def to_markdown(report: dict[str, Any]) -> str:
    """Render a :func:`recommend` report as a Markdown document."""
    hw = report["hardware"]
    comp = hw.get("compute", {}) or {}
    task = report["task"]
    lines: list[str] = []
    lines.append("# Best local engine — recommendation")
    lines.append("")
    lines.append(f"**Task:** {task.get('input') or 'general text assistant'}  ")
    if task.get("matched"):
        lines.append(f"**Matched keywords:** {', '.join(task['matched'])}  ")
    lines.append(f"**Needs:** {', '.join(k.upper() for k in task['kinds'])}")
    lines.append("")
    lines.append("## Hardware")
    lines.append("")
    lines.append(f"- Chip / accelerator: {comp.get('chip') or '?'} "
                 f"({comp.get('accelerator', 'unknown')})")
    pool = hw.get("unified_gb") or hw.get("vram_gb") or hw.get("ram_gb")
    lines.append(f"- Memory pool: {pool} GB")
    if comp.get("bandwidth_gbs"):
        lines.append(f"- Memory bandwidth: {comp['bandwidth_gbs']:.0f} GB/s "
                     "(sets the decode-speed ceiling)")
    lines.append(f"- Usable model budget: **{report['memory_budget_gb']:.1f} GB** "
                 f"(headroom {report['headroom']})")
    if report.get("comfort_tps"):
        lines.append(f"- Comfort throughput floor: **{report['comfort_tps']:.0f} tok/s** "
                     "(a model below this fits memory but decodes too slowly to recommend)")
    lines.append("")

    for kind, block in report["recommendations"].items():
        chosen = block["chosen"]
        lines.append(f"## Best {kind.upper()} (axis: {block['axis']})")
        lines.append("")
        if chosen:
            tps = _fmt_tps(chosen["est_tokens_per_s"])
            if not chosen["fits"]:
                flag = "  ⚠️ exceeds memory budget (spills to CPU)"
            elif not chosen.get("comfortable", True):
                flag = "  ⚠️ below comfort floor (fits but decodes slowly)"
            else:
                flag = ""
            lines.append(f"**→ `{chosen['id']}`** — {chosen['ram_gb']:.1f} GB, "
                         f"score {chosen['score']:.0f}, ~{tps} tok/s" + flag)
            alt = block["lighter_alternative"]
            if alt:
                lines.append("")
                lines.append(f"Lighter alternative: `{alt['id']}` — "
                             f"{alt['ram_gb']:.1f} GB, score {alt['score']:.0f}, "
                             f"~{_fmt_tps(alt['est_tokens_per_s'])} tok/s.")
        else:
            lines.append("_No candidate found._")
        lines.append("")
        lines.append("| model | RAM GB | score | fits | ~tok/s | comfy |")
        lines.append("|---|---|---|---|---|---|")
        for r in block["candidates"]:
            lines.append(f"| `{r['id']}` | {r['ram_gb']:.1f} | {r['score']:.0f} | "
                         f"{'yes' if r['fits'] else 'no'} | {_fmt_tps(r['est_tokens_per_s'])} | "
                         f"{'yes' if r.get('comfortable') else 'no'} |")
        lines.append("")

    lines.append("## How this was decided")
    lines.append("")
    lines.append(report["method"])
    lines.append("")
    lines.append("Sources:")
    for s in report["sources"]:
        lines.append(f"- {s}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], stem: str | Path) -> tuple[Path, Path]:
    """Write both a JSON and a Markdown rendering; return (md_path, json_path)."""
    stem = Path(stem)
    md_path = stem.with_suffix(".md")
    json_path = stem.with_suffix(".json")
    osh.make_directory(str(md_path.parent))
    md_path.write_text(to_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    osh.info(f"Wrote recommendation report:\n\t{md_path}\n\t{json_path}")
    return md_path, json_path
