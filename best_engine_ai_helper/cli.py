"""
cli — Click command-line interface for best-engine-ai-helper.

Entry point: `best-engine-ai-helper` (registered in pyproject.toml).

Commands:
  detect          Print detected hardware as JSON.
  recommend       Print ranked model candidates for this hardware.
  catalog show    Print the merged model catalog as a table.
  catalog update  Refresh the catalog cache from the ApXML model directory.
  hardware show   Print the merged hardware chip table.
  hardware update Record this machine's chip and memory into the cache.
  pull            Pull the best model and run Ralph validation gates.
  validate        Run Ralph gates on the already-configured model.
  env             Print the env block for ~/.zshrc or sourcing.
  activity        Summarize the local activity/cost ledger.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import functools
import json
import logging
import os
import subprocess
import sys
from typing import Any

import click
import os_helper as osh

from . import catalog as _catalog
from . import detect as _detect
from . import hardware as _hardware
from . import observe as _observe
from . import score as _score
from .recommend import recommend as _recommend_engines
from .recommend import to_markdown as _report_markdown
from .recommend import write_report as _write_report

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """
    Format a list of dicts as a plain-text table with aligned columns.

    Parameters
    ----------
    rows : list[dict]
        Data rows; missing keys are rendered as '-'.
    columns : list[str]
        Column names in display order.

    Returns
    -------
    str
        Formatted table string ready for print().
    """
    # Compute column widths from headers and data
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            cell = str(row.get(col, "-"))
            widths[col] = max(widths[col], len(cell))

    header = "  ".join(col.ljust(widths[col]) for col in columns)
    sep = "  ".join("-" * widths[col] for col in columns)
    lines = [header, sep]
    for row in rows:
        line = "  ".join(str(row.get(col, "-")).ljust(widths[col]) for col in columns)
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="best-engine-ai-helper")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase log verbosity: -v shows info, -vv also shows debug. "
    "Warnings and errors are always shown.",
)
def main(verbose: int) -> None:
    """Pick and pull the best local LLM/VLM for the current hardware."""
    # Configure the os_helper logger so library osh.info/debug calls surface on
    # demand. Logs go to stderr so command stdout (JSON, tables) stays clean and
    # pipeable. Default keeps only warnings and errors; -v adds info, -vv debug.
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)
    osh.init_logging(level=level, stdout=False)
    # Local-only activity/cost ledger (see observe.py and the `usage` command);
    # opt out with BEST_ENGINE_NO_LEDGER=1. No-op for commands that never call
    # llm.chat (detect, catalog show, ...) — nothing is written unless a model
    # is actually called.
    if not os.environ.get("BEST_ENGINE_NO_LEDGER"):
        _observe.enable()


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


@main.command("detect")
@click.option("--json", "as_json", is_flag=True, default=True, hidden=True)
def detect_cmd(as_json: bool) -> None:
    """Print detected hardware as JSON."""
    # JSON is always the output format for machine-readability
    mem = _detect.available_memory()
    info = {
        "platform": _detect.platform_name(),
        "chip_vendor": _detect.chip_vendor(),
        "memory": mem,
        # Raw CPU/GPU facts straight from os_helper — cores, model names, and
        # per-GPU VRAM, distinct from "memory" above (this repo's inference
        # budget pools) and from "compute" elsewhere (bandwidth estimate).
        "hardware": osh.hardware_info(),
    }
    click.echo(json.dumps(info, indent=2))


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------

_VALID_APPLICATIONS = ["code", "math", "ocr", "vision", "chat", "generalist"]


@main.command("recommend")
@click.option(
    "--kind",
    type=click.Choice(["llm", "vlm", "both"]),
    default="both",
    show_default=True,
    help="Model type to recommend.",
)
@click.option(
    "--headroom",
    type=float,
    default=_score.MAX_HEADROOM,
    show_default=True,
    help=(
        "Safety headroom fraction (0-1) applied to available memory. Clamped "
        f"to {_score.MAX_HEADROOM} (score.MAX_HEADROOM) -- a larger value is "
        "never honoured."
    ),
)
@click.option(
    "--application",
    type=click.Choice(_VALID_APPLICATIONS),
    default=None,
    show_default=False,
    help=(
        "Target use-case: code, math, ocr, vision, chat, generalist. "
        "Selects the benchmark axis used for ranking. "
        "Omit for the default kind-based rule (vision for VLM, general for LLM)."
    ),
)
@click.option(
    "--min-tps",
    type=float,
    default=_score.COMFORT_TPS,
    show_default=True,
    help=(
        "Comfort throughput floor in tokens/s: a model that fits memory but is "
        "estimated below this decodes too slowly to recommend (shown comfy=NO)."
    ),
)
@click.option(
    "--live",
    is_flag=True,
    default=False,
    help=(
        "Also weigh CURRENT server load (free RAM, CPU/GPU/disk usage, already-"
        "running engines), not just theoretical capacity. Off by default: it adds "
        "a live probe (~0.1-0.5s) and makes the result depend on this exact moment "
        "rather than being a deterministic function of the hardware alone."
    ),
)
def recommend_cmd(
    kind: str, headroom: float, application: str | None, min_tps: float, live: bool
) -> None:
    """Print ranked model candidates for this hardware (dry run, no pull)."""
    hw = _detect.available_memory()
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    entries = _catalog.load_catalog()
    load = _detect.server_load() if live else None

    kinds: list[str] = ["llm", "vlm"] if kind == "both" else [kind]

    for k in kinds:
        ranked = _score.rank(
            hw,
            entries,
            # `k` is `str` at the type level; the CLI framework, not mypy,
            # enforces it is actually "llm" or "vlm" (see the choices on
            # `kind` above), so `rank`'s Literal["llm", "vlm"] can't narrow
            # it statically.
            kind=k,  # type: ignore[arg-type]
            headroom=headroom,
            application=application,
            load=load,
        )
        header = f"\n=== {k.upper()} candidates"
        if application:
            header += f" [{application}]"
        header += " ==="
        click.echo(header)
        rows = []
        for e in ranked:
            tps = _score.estimated_tokens_per_second(e, bandwidth)
            comfy = bool(e.get("_fits")) and (tps is None or tps >= min_tps)
            rows.append(
                {
                    "id": e.get("id", "-"),
                    "ram_gb": e.get("ram_gb", "-"),
                    "score": (
                        e.get("benchmarks", {}).get("vision")
                        if k == "vlm"
                        else e.get("benchmarks", {}).get("general")
                    )
                    or "-",
                    "fits": "yes" if e.get("_fits") else "NO",
                    "tok/s": f"{tps:.0f}" if tps else "-",
                    "comfy": "yes" if comfy else "NO",
                    "notes": (e.get("notes") or "")[:40],
                }
            )
        click.echo(_fmt_table(rows, ["id", "ram_gb", "score", "fits", "tok/s", "comfy", "notes"]))

    click.echo()


@main.command("resolve")
@click.option(
    "--brief",
    type=str,
    required=True,
    help="Path to the committed usage brief (llm.brief.yaml).",
)
@click.option(
    "--out",
    type=str,
    default=None,
    help="Where to write the engine file. Default: llm.engine.yaml beside the brief.",
)
@click.option(
    "--backend",
    type=click.Choice(["auto", "ollama", "vllm"]),
    default="auto",
    show_default=True,
    help="Serving backend. 'auto' = vLLM on a discrete GPU (NVIDIA/AMD), else Ollama.",
)
@click.option(
    "--endpoint",
    type=str,
    default=None,
    help="Override the server base URL (e.g. a remote vLLM box).",
)
def resolve_cmd(brief: str, out: str | None, backend: str, endpoint: str | None) -> None:
    """Resolve a usage brief into a machine-specific engine file (gitignored).

    Reads the committed brief, detects this machine's hardware, picks a realistic
    backend + model per kind, and writes the engine descriptor consumers read at
    call time. The output is hardware-specific — add it to .gitignore, never
    commit it.
    """
    from pathlib import Path

    from . import engine as _engine

    brief_path = Path(brief)
    if not brief_path.is_file():
        click.echo(f"Brief not found: {brief_path}", err=True)
        sys.exit(1)

    out_path = Path(out) if out else brief_path.with_name(_engine.ENGINE_NAME)
    try:
        descriptor = _engine.resolve(brief_path, backend=backend, endpoint=endpoint)
        _engine.write_engine(descriptor, out_path)
    except Exception as exc:  # keep resolution failures readable, no traceback
        osh.error(f"resolve failed:\n\t{exc}")
        click.echo(f"resolve failed: {exc}", err=True)
        sys.exit(1)

    chosen = ", ".join(f"{k}={descriptor[k]['model']}" for k in ("llm", "vlm") if descriptor.get(k))
    click.echo(
        f"Wrote {out_path}\n"
        f"  backend: {descriptor['backend']}  ({chosen})\n"
        f"  NOTE: hardware-specific — add '{out_path.name}' to .gitignore, do not commit."
    )
    for cmd in descriptor.get("serve", []):
        click.echo(f"  bring it up:  {cmd}")


@main.command("report")
@click.option(
    "--task",
    type=str,
    default=None,
    help=(
        'Free-text task, e.g. "retail product descriptions and image-quality '
        'checks". Vision words add a VLM; code/math/ocr words pick the axis. '
        "Omit for a general text assistant."
    ),
)
@click.option(
    "--headroom",
    type=float,
    default=_score.MAX_HEADROOM,
    show_default=True,
    help=(
        "Memory safety fraction on top of the accelerator cap. Clamped to "
        f"{_score.MAX_HEADROOM} (score.MAX_HEADROOM) -- a larger value is "
        "never honoured."
    ),
)
@click.option(
    "--out",
    type=str,
    default=None,
    help="Path stem to write <stem>.md and <stem>.json. Omit to only print.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "json"]),
    default="md",
    show_default=True,
    help="What to print to stdout.",
)
@click.option(
    "--live",
    is_flag=True,
    default=False,
    help=(
        "Also weigh CURRENT server load (free RAM, CPU/GPU/disk usage, already-"
        "running engines), not just theoretical capacity. Off by default: it adds "
        "a live probe (~0.1-0.5s) and makes the result depend on this exact moment "
        "rather than being a deterministic function of the hardware alone."
    ),
)
def report_cmd(task: str | None, headroom: float, out: str | None, fmt: str, live: bool) -> None:
    """Recommend the best engine(s) for this hardware and task; emit MD + JSON."""
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    load = _detect.server_load() if live else None
    rep = _recommend_engines(hw, entries, task=task, headroom=headroom, compute=compute, load=load)

    if out:
        md_path, json_path = _write_report(rep, out)
        click.echo(f"wrote {md_path} and {json_path}", err=True)

    if fmt == "json":
        click.echo(json.dumps(rep, indent=2))
    else:
        click.echo(_report_markdown(rep))


# ---------------------------------------------------------------------------
# usages subgroup — the sev7n usage catalog (task profiles + families)
# ---------------------------------------------------------------------------


@main.group("usages")
def usages_group() -> None:
    """Browse and resolve the sev7n usage catalog (task profiles + families)."""


@usages_group.command("list")
def usages_list() -> None:
    """List every usage profile and family (names, not models)."""
    from . import usages as _usages

    click.echo("Families (usages that can share one model):")
    frows = [
        {
            "id": f["id"],
            "name": f["name"],
            "members": ", ".join(f["members"]),
            "summary": f["summary"][:48],
        }
        for f in _usages.list_families()
    ]
    click.echo(_fmt_table(frows, ["id", "name", "members", "summary"]))

    click.echo("\nProfiles:")
    prows = [
        {
            "name": p["name"],
            "family": p["family"] or "-",
            "status": p["status"],
            "summary": p["summary"][:52],
        }
        for p in _usages.list_usages()
    ]
    click.echo(_fmt_table(prows, ["name", "family", "status", "summary"]))


@usages_group.command("show")
@click.argument("name")
def usages_show(name: str) -> None:
    """Show one profile's needs (task, structured output, floors) — no model."""
    from . import usages as _usages

    try:
        prof = _usages.get_usage(name)
    except KeyError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    brief = prof.get("brief", {})
    click.echo(
        f"{prof['name']}  [{prof.get('status', 'stable')}, family {prof.get('family', '-')}]"
    )
    click.echo(f"  {prof.get('summary', '')}\n")
    click.echo(prof.get("description", "").strip() + "\n")
    click.echo("Needs (selection criteria):")
    click.echo(f"  kind             : {brief.get('kind', '-')}")
    click.echo(f"  structured_output: {brief.get('structured_output', '-')}")
    click.echo(f"  min_tps          : {brief.get('min_tps', '-')}")
    click.echo(f"  headroom         : {brief.get('headroom', '-')}")
    click.echo(f"  min_quality      : {prof.get('min_quality', '-')}")
    click.echo(f"  context_length   : {prof.get('context_length', '-')}")
    click.echo(f"  local_strict     : {prof.get('local_strict', True)}")
    click.echo(f"  task             : {' '.join(brief.get('task', '').split())}")


def _echo_resolved(descriptor: dict[str, Any], out: str | None) -> None:
    """Print a resolved usage/family descriptor and optionally write it (gitignored)."""
    label = descriptor.get("usage") or descriptor.get("family") or "?"
    chosen = []
    for kind in ("llm", "vlm", "embed"):
        section = descriptor.get(kind)
        if isinstance(section, dict) and section.get("model"):
            ram = section.get("ram_gb")
            tps = section.get("est_tokens_per_s")
            extra = f", ~{tps:.0f} tok/s" if isinstance(tps, (int, float)) else ""
            chosen.append(f"{kind}={section['model']} ({ram} GB{extra})")
    click.echo(
        f"{label}: backend {descriptor.get('backend')}  "
        + ("  ".join(chosen) if chosen else "no model resolved")
    )
    if descriptor.get("status") == "scaffold":
        click.echo("  NOTE: scaffolded profile — resolvable now, downstream wiring pending.")
    click.echo(
        "  NOTE: machine-specific — the chosen model lives only in the "
        "generated file; keep it gitignored, never commit."
    )
    if out:
        from . import engine as _engine

        path = _engine.write_engine(descriptor, out)
        click.echo(f"  wrote {path}")
        for cmd in descriptor.get("serve", []):
            click.echo(f"  bring it up:  {cmd}")


@usages_group.command("resolve")
@click.argument("name", required=False)
@click.option(
    "--family",
    "family_id",
    type=str,
    default=None,
    help="Resolve a whole family (F1/F2/F3) to one model instead of a profile.",
)
@click.option(
    "--backend",
    type=click.Choice(["auto", "ollama", "vllm"]),
    default="auto",
    show_default=True,
    help="Serving backend; 'auto' picks per hardware.",
)
@click.option("--endpoint", type=str, default=None, help="Override the server base URL.")
@click.option(
    "--out",
    type=str,
    default=None,
    help="Write the generated engine file here (gitignored, machine-specific).",
)
def usages_resolve(
    name: str | None, family_id: str | None, backend: str, endpoint: str | None, out: str | None
) -> None:
    """Resolve a profile (or --family) into this machine's model — best-engine decides.

    Reads only the usage's needs, probes the hardware, and picks the concrete
    local model. The result is machine-specific: it lives in the generated engine
    file (gitignored), never in a committed literal.
    """
    from . import usages as _usages

    if not name and not family_id:
        click.echo("Give a profile NAME or --family F1/F2/F3.", err=True)
        sys.exit(1)
    try:
        if family_id:
            descriptor = _usages.resolve_family(family_id, backend=backend, endpoint=endpoint)
        else:
            descriptor = _usages.resolve_usage(name, backend=backend, endpoint=endpoint)  # type: ignore[arg-type]
    except (KeyError, ValueError) as exc:
        click.echo(f"resolve failed: {exc}", err=True)
        sys.exit(1)
    _echo_resolved(descriptor, out)


# ---------------------------------------------------------------------------
# catalog subgroup
# ---------------------------------------------------------------------------


@main.group("catalog")
def catalog_group() -> None:
    """Manage the model catalog."""


@catalog_group.command("show")
def catalog_show() -> None:
    """Print the merged model catalog as a table."""
    entries = _catalog.load_catalog()
    rows = []
    for e in entries:
        bench = e.get("benchmarks") or {}
        rows.append(
            {
                "id": e.get("id", "-"),
                "kind": e.get("kind", "-"),
                "size_b": e.get("size_b", "-"),
                "quant": e.get("quant", "-"),
                "disk_gb": e.get("disk_gb", "-"),
                "ram_gb": e.get("ram_gb", "-"),
                "general": bench.get("general") or "-",
                "vision": bench.get("vision") or "-",
            }
        )
    cols = ["id", "kind", "size_b", "quant", "disk_gb", "ram_gb", "general", "vision"]
    click.echo(_fmt_table(rows, cols))


@catalog_group.command("update")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Fetch at most N models (handy for a quick refresh or a smoke test).",
)
@click.option(
    "--timeout",
    type=float,
    default=30.0,
    show_default=True,
    help="Per-request network timeout, in seconds.",
)
def catalog_update(limit: int | None, timeout: float) -> None:
    """Refresh the catalog cache from the ApXML open-weight model directory.

    Fetched specs are normalized to catalog entries and merged into
    ``~/.best-engine-ai-helper/catalog_cache.yaml`` by id; the bundled seed is
    never modified. ApXML supplies specs and memory-fit figures but no numeric
    benchmarks, so refreshed entries carry null scores until a scored source
    fills them.
    """
    from .sources import apxml

    click.echo("Fetching open-weight models from ApXML…", err=True)
    try:
        specs = apxml.fetch_open_weight_models(timeout=timeout, limit=limit)
    except Exception as exc:  # network / parse failures should not traceback
        osh.error(f"catalog update failed:\n\t{exc}")
        click.echo(f"catalog update failed: {exc}", err=True)
        sys.exit(1)

    entries = _catalog.normalize_apxml_specs(specs)
    if not entries:
        click.echo("No usable models returned from ApXML; cache unchanged.", err=True)
        sys.exit(1)

    path = _catalog.write_cache(entries)
    click.echo(f"Updated catalog cache with {len(entries)} model(s):\n\t{path}")


# ---------------------------------------------------------------------------
# hardware subgroup
# ---------------------------------------------------------------------------


@main.group("hardware")
def hardware_group() -> None:
    """Manage the hardware chip table."""


@hardware_group.command("show")
def hardware_show() -> None:
    """Print the merged hardware chip table."""
    entries = _hardware.load_hardware()
    rows = []
    for e in entries:
        rows.append(
            {
                "chip": e.get("chip", "-"),
                "vendor": e.get("vendor", "-"),
                "memory_gb": e.get("memory_gb", "-"),
                "ollama_usable_gb": e.get("ollama_usable_gb", "-"),
                "source": e.get("source", "-"),
            }
        )
    click.echo(_fmt_table(rows, ["chip", "vendor", "memory_gb", "ollama_usable_gb", "source"]))


@hardware_group.command("update")
def hardware_update() -> None:
    """Record this machine's chip and memory into the hardware cache.

    There is no public specs API covering every GPU and Apple Silicon chip, so a
    refresh captures ground truth for the machine it runs on: the detected chip,
    its memory pool, and the Ollama-usable share after the OS reservation. The
    row is upserted into ``~/.best-engine-ai-helper/hardware_cache.yaml`` (keyed
    on chip + memory tier); the bundled seed is never modified.
    """
    entry = _hardware.detect_local_entry()
    if entry is None:
        click.echo("Could not detect usable memory; hardware cache unchanged.", err=True)
        sys.exit(1)

    path = _hardware.write_cache([entry])
    click.echo(
        f"Recorded this machine into the hardware cache:\n"
        f"\t{entry['chip']} — {entry['memory_gb']} GB "
        f"({entry['ollama_usable_gb']} GB usable)\n\t{path}"
    )


# ---------------------------------------------------------------------------
# Phase 0b — pull, validate, env (fully implemented)
# ---------------------------------------------------------------------------


@main.command("pull")
@click.option(
    "--keep-failed",
    is_flag=True,
    default=False,
    help="Do not remove failed models after a gate failure.",
)
@click.option(
    "--vllm",
    is_flag=True,
    default=False,
    help="Print the vLLM serve command for the HuggingFace model instead of pulling.",
)
@click.option(
    "--application",
    type=click.Choice(_VALID_APPLICATIONS),
    default=None,
    show_default=False,
    help="Target use-case (code, math, ocr, vision, chat, generalist). Biases model selection.",
)
@click.option(
    "--min-tps",
    type=float,
    default=_score.COMFORT_TPS,
    show_default=True,
    help=(
        "Comfort throughput floor in tokens/s. A model that fits memory but is "
        "estimated below this is tried only after comfortable ones."
    ),
)
def pull_cmd(keep_failed: bool, vllm: bool, application: str | None, min_tps: float) -> None:
    """Pull the best model and run Ralph validation gates.

    Detects hardware, ranks candidates, pulls the top model, runs both the
    VLM gate (validate_vlm) and the prose gate (validate_llm). If both pass,
    writes ~/.best-engine-ai-helper/env.sh and exits. If either fails, removes
    the model (unless --keep-failed) and tries the next candidate.
    """
    from . import llm as _llm
    from . import pull as _pull
    from . import validate_llm as _validate_llm
    from . import validate_vlm as _validate_vlm

    hw = _detect.available_memory()
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    entries = _catalog.load_catalog()

    # Rank VLM candidates; the best VLM also covers text tasks
    ranked = _score.rank(hw, entries, kind="vlm", application=application)
    fitting = [e for e in ranked if e.get("_fits")]
    if not fitting:
        click.echo("No model fits in available memory. Trying the smallest anyway.", err=True)
        fitting = ranked[:1]

    # Comfort floor: a model that fits memory but decodes too slowly (a 32B on a
    # 400 GB/s laptop crawls at ~7 tok/s) should not be pulled ahead of a slightly
    # lower-scoring model that actually runs at a usable speed. Try comfortable
    # candidates first, each group still in benchmark order; slow-but-fitting
    # models stay as a fallback. The sort is stable, so rank is preserved within
    # each group.
    def _too_slow(entry: dict[str, Any]) -> bool:
        tps = _score.estimated_tokens_per_second(entry, bandwidth)
        return tps is not None and tps < min_tps

    fitting.sort(key=_too_slow)

    for candidate in fitting:
        tag = candidate["id"]
        hf_id = candidate.get("vllm_id")

        if vllm:
            # Print the vLLM serve command for the user to run manually
            click.echo(f"vllm serve {hf_id or tag} --port 8000")
            sys.exit(0)

        click.echo(f"Pulling {tag} ...")
        try:
            ok = _pull.ollama_pull(tag)
        except FileNotFoundError:
            # No candidate can ever pull without the ollama binary -- fail
            # the whole command now instead of repeating the same crash for
            # every remaining candidate.
            click.echo("Error: ollama binary not found. Install from https://ollama.com", err=True)
            sys.exit(1)
        except subprocess.TimeoutExpired:
            # This candidate stalled (network stall, hung server); treat it
            # like a failed pull and move on, same as ok=False below.
            click.echo(f"ollama pull {tag} timed out. Skipping.", err=True)
            continue
        if not ok:
            click.echo(f"ollama pull {tag} failed. Skipping.", err=True)
            continue

        # Bind the just-pulled candidate as the model under test -- without
        # this, `_llm.chat`'s no-model-given resolution falls back to
        # BEST_LLM_TEXT/VISION (env or persisted config.json), which is
        # whatever was configured BEFORE this pull, not `tag`. That would
        # validate a stale model while promoting an untested one on success.
        chat_for_candidate = functools.partial(_llm.chat, model=tag)
        click.echo(f"Running VLM gate on {tag} ...")
        vlm_ok = _validate_vlm.validate(chat_for_candidate)
        click.echo(f"Running prose gate on {tag} ...")
        llm_ok = _validate_llm.validate(chat_for_candidate)

        if vlm_ok and llm_ok:
            # Both gates passed: write env.sh and exit successfully
            env_path = _pull.write_env(
                text_model=tag,
                vision_model=tag,
                backend=os.environ.get("SPREZZATURE_LLM_BACKEND", "ollama"),
                base_url=os.environ.get("SPREZZATURE_LLM_BASE_URL", "http://localhost:11434"),
            )
            click.echo(f"Both gates passed. Config written to {env_path}")
            click.echo(f"Source it: source {env_path}")
            sys.exit(0)
        else:
            click.echo(
                f"{tag} failed: VLM={'pass' if vlm_ok else 'FAIL'}, "
                f"prose={'pass' if llm_ok else 'FAIL'}",
                err=True,
            )
            if not keep_failed:
                click.echo(f"Removing {tag} ...", err=True)
                _pull.ollama_rm(tag)

    click.echo("No candidate passed both gates.", err=True)
    sys.exit(1)


@main.command("validate")
def validate_cmd() -> None:
    """Run Ralph gates on the already-configured model.

    Reads BEST_LLM_TEXT / BEST_LLM_VISION from the environment (sourced from
    env.sh) and validates both gates. Useful after a manual ollama pull or
    after an OS update changes GPU availability.
    """
    from . import llm as _llm
    from . import validate_llm as _validate_llm
    from . import validate_vlm as _validate_vlm

    text_model = os.environ.get("BEST_LLM_TEXT", os.environ.get("SPREZZATURE_LLM_TEXT", ""))
    if not text_model:
        click.echo(
            "BEST_LLM_TEXT is not set. Run `pull` first or source env.sh.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Validating {text_model} ...")
    vlm_ok = _validate_vlm.validate(_llm.chat)
    llm_ok = _validate_llm.validate(_llm.chat)

    click.echo(f"VLM gate: {'pass' if vlm_ok else 'FAIL'}")
    click.echo(f"Prose gate: {'pass' if llm_ok else 'FAIL'}")

    if not (vlm_ok and llm_ok):
        sys.exit(1)


@main.command("gui")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
def gui_cmd(host: str, port: int) -> None:
    """Launch the minimal browser GUI (hardware + task -> best engine)."""
    import uvicorn

    click.echo(f"Serving GUI at http://{host}:{port}/gui")
    uvicorn.run("best_engine_ai_helper.api:app", host=host, port=port)


@main.command("env")
def env_cmd() -> None:
    """Print the env block ready for ~/.zshrc or sourcing.

    Reads the written env.sh from ~/.best-engine-ai-helper/env.sh and prints
    it to stdout. If the file does not exist, suggests running pull first.
    """
    from pathlib import Path

    env_path = Path.home() / ".best-engine-ai-helper" / "env.sh"
    if not env_path.exists():
        click.echo(
            "env.sh not found. Run `best-engine-ai-helper pull` first.",
            err=True,
        )
        sys.exit(1)

    # Print the env block for the user to inspect or pipe to a shell
    click.echo(env_path.read_text(encoding="utf-8"), nl=False)


# ---------------------------------------------------------------------------
# activity
# ---------------------------------------------------------------------------
# Named "activity", not "usage": this repo already has a plural `usages`
# command group (named task profiles like text2sql) -- "usage" would be a
# one-letter, easily-mistyped collision with a completely different concept.


@main.command("activity")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
    help="What to print to stdout.",
)
def activity_cmd(fmt: str) -> None:
    """Summarize the local activity/cost ledger (calls, cost, by user/model, errors).

    Reads ~/.best-engine-ai-helper/usage.db, populated by other commands in
    this session (or a prior one) that called a model — nothing to show until
    then. Disable recording with BEST_ENGINE_NO_LEDGER=1.
    """
    ledger = _observe.active_ledger() or _observe.Ledger()
    summary = ledger.summary()

    if fmt == "json":
        click.echo(json.dumps(summary, indent=2))
        return

    if summary["total_calls"] == 0:
        click.echo("No calls recorded yet.")
        return

    cost = summary["total_cost_usd"]
    cost_str = f"${cost:.4f}" if cost is not None else "unknown (unpriced model in the mix)"
    click.echo(
        f"Total calls: {summary['total_calls']}   "
        f"Total cost: {cost_str}   "
        f"Error rate: {summary['error_rate']:.1%}"
    )
    click.echo()
    click.echo("By user:")
    click.echo(_fmt_table(summary["by_user"], ["user", "calls", "cost_usd"]))
    click.echo()
    click.echo("By model:")
    click.echo(_fmt_table(summary["by_model"], ["model", "calls", "cost_usd"]))
    if summary["recent_errors"]:
        click.echo()
        click.echo("Recent errors:")
        click.echo(_fmt_table(summary["recent_errors"], ["ts", "user", "model", "error"]))


def console_entry() -> None:
    """Console entry point (`best-engine-ai-helper`, registered in pyproject.toml).

    Click's own `main()` only special-cases `ClickException`/`Abort` (and a
    broken pipe); a plain library exception (a connection failure, a missing
    `ollama` binary, ...) would otherwise propagate as a raw Python traceback
    instead of a clean CLI error. This wraps the whole invocation and
    translates that last case into a one-line stderr message + exit 1 --
    click's own control flow (usage errors, `--help`, an explicit
    `sys.exit(1)` in a subcommand) already raises `SystemExit`, a
    `BaseException` this does not catch, so it passes through untouched.
    """
    try:
        main()
    except Exception as err:  # noqa: BLE001 — last resort: see docstring
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    console_entry()
