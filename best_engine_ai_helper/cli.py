"""
cli — the command line of best-engine-ai-helper, built with click.

One command line, one module: `best-engine-ai-helper` (registered in
pyproject.toml) is the only CLI this package ships. An argparse twin used to
mirror it command for command, which doubled every option and every test for
no behaviour anybody could observe; it was removed in 1.9.0 and click became
a core dependency rather than an opt-in extra.

Commands:
  detect          Print detected hardware as JSON.
  recommend       Print ranked model candidates for this hardware.
  resolve         Turn a usage brief into a machine-specific engine file.
  report          Recommend engine(s) for a task, as Markdown or JSON.
  usages          Browse and resolve the sev7n usage catalog.
  catalog show    Print the merged model catalog as a table.
  catalog update  Refresh the catalog cache; --arena adds Arena ratings.
  hardware show   Print the merged hardware chip table.
  hardware update Record this machine's chip and memory into the cache.
  pull            Pull the best model and run Ralph validation gates.
  storage         Plan capacity: disk, and what fits in memory together.
  providers       Which cloud providers are usable right now, and why not.
  doctor          Compare what was resolved against what the daemon serves.
  validate        Run Ralph gates on the already-configured model.
  gui             Launch the minimal browser GUI.
  env             Print the env block for ~/.zshrc or sourcing.
  activity        Summarize the local activity/cost ledger.
  airllm status   Can this machine stream layers, and should it?
  airllm plan     What a too-large model would cost here, ranked.
  airllm prepare  Download and split a checkpoint before the first call.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
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

from . import __version__
from . import catalog as _catalog
from . import cloud_catalog as _cloud_catalog
from . import detect as _detect
from . import hardware as _hardware
from . import observe as _observe
from . import offload as _offload
from . import score as _score
from . import throughput as _throughput
from .recommend import _fmt_tps
from .recommend import cloud_recommend as _cloud_recommend
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


@click.group(
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
)
# `__version__` is passed explicitly rather than read from the installed
# distribution metadata: `package_name=` alone reports whatever was last
# pip-installed, so an editable checkout answered `--version` with the previous
# release. `prog_name` likewise, or `python -m best_engine_ai_helper.cli
# --version` names the module instead of the command. `-V` is capital because
# `-v` is already `--verbose` below.
@click.version_option(
    __version__,
    "-V",
    "--version",
    package_name="best-engine-ai-helper",
    prog_name="best-engine-ai-helper",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase log verbosity: -v shows info, -vv also shows debug. "
    "Warnings and errors are always shown.",
)
def cli(verbose: int) -> None:
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


def _raw_estimate_for(tag: str) -> float | None:
    """What the uncalibrated bandwidth model predicts for `tag` on this machine.

    Stored next to a measurement so the two can be compared later. Deliberately
    uncalibrated: the ratio between them IS the calibration, so feeding an
    already-corrected estimate in would make the correction chase its own tail.

    Parameters
    ----------
    tag : str
        Model tag to look up in the merged catalog.

    Returns
    -------
    float or None
        The raw estimate, or None when the model or the bandwidth is unknown.
    """
    entry = next((e for e in _catalog.load_catalog() if e.get("id") == tag), None)
    if entry is None:
        return None
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    return _score.estimated_tokens_per_second(entry, bandwidth, calibrated=False)


def _report_measurement(meter: _throughput.Meter, tag: str) -> None:
    """Persist and announce what the gates measured, or say nothing was measurable.

    Parameters
    ----------
    meter : throughput.Meter
        The meter the gates ran through.
    tag : str
        The model tag that was validated.
    """
    measurement = meter.measurement()
    if measurement is None:
        # Nothing worth storing: the backend reported no token counts, or the
        # sample was too short to be more than first-token latency. Silence
        # here is correct -- a figure invented to fill the field would be
        # consulted later as though it had been measured.
        click.echo(f"No usable throughput sample for {tag}; speed stays an estimate.", err=True)
        return

    path = _throughput.record(tag, measurement, estimated_tps=_raw_estimate_for(tag))
    basis = "daemon decode clock" if measurement["basis"] == "eval_duration" else "wall clock"
    click.echo(
        f"Measured {measurement['tokens_per_second']} tok/s for {tag} "
        f"on {measurement['measured_on']} "
        f"({measurement['tokens']} tokens over {measurement['calls']} call(s), {basis}).\n"
        f"\t{path}"
    )


#: Columns of the streaming candidate table. Deliberately different from the
#: resident-model table: `ram_gb` there is the model, here it is one shard, and
#: "tok/s" would read as a rounding error at these rates, so the honest column
#: is seconds per token.
_STREAM_COLUMNS = ["id", "params", "shard_gb", "ckpt_gb", "s/token", "disk_gb", "runs", "notes"]


def _streaming_rows(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Format already-ranked streaming plans as a display table.

    Takes the plans rather than the catalog entries on purpose: the caller has
    already ranked them with the batch size, answer length and compression the
    user asked for, and ranking a second time here would print a table computed
    under different assumptions from the pick below it.

    Parameters
    ----------
    plans : list[dict]
        :func:`offload.plan` dicts, typically from :func:`offload.rank`.

    Returns
    -------
    list[dict[str, Any]]
        Display rows in :data:`_STREAM_COLUMNS` order, in the order given.

    Examples
    --------
    >>> rows = _streaming_rows(
    ...     _offload.rank(
    ...         [{"id": "a", "kind": "llm", "size_b": 70, "layers": 80, "hf_id": "x/a"}],
    ...         budget_gb=32.0,
    ...         disk={"read_gbs": 4.0, "free_gb": 900.0},
    ...         kind="llm",
    ...     )
    ... )
    >>> rows[0]["id"], rows[0]["runs"]
    ('a', 'yes')
    """
    rows: list[dict[str, Any]] = []
    for plan in plans:
        # A blocker is the reason a candidate is not offered, and it is more
        # useful in the notes column than the catalog's marketing line.
        note = plan["blockers"][0] if plan["blockers"] else (f"{plan['layers']} layers")
        rows.append(
            {
                "id": plan["catalog_id"],
                "params": f"{plan['size_b']:.0f}B" if plan["size_b"] else "-",
                "shard_gb": plan["resident_gb"] if plan["resident_gb"] is not None else "-",
                "ckpt_gb": plan["checkpoint_gb"] if plan["checkpoint_gb"] is not None else "-",
                "s/token": plan["seconds_per_token"] if plan["seconds_per_token"] else "-",
                "disk_gb": plan["disk"]["peak_gb"],
                "runs": "yes" if plan["usable"] else "NO",
                "notes": note[:52],
            }
        )
    return rows


@cli.command("detect")
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


@cli.command("recommend")
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
@click.option(
    "--backend",
    type=click.Choice(["ollama", "vllm", "airllm"]),
    default="ollama",
    show_default=True,
    help=(
        "Size and rank for this backend. 'vllm' loads heavier FP16 weights; "
        "'airllm' streams layers off disk, so the footprint becomes one shard "
        "and the rate becomes disk-bound (seconds per token). Candidates the "
        "backend cannot serve are left out."
    ),
)
def recommend_cmd(
    kind: str,
    headroom: float,
    application: str | None,
    min_tps: float,
    live: bool,
    backend: str,
) -> None:
    """Print ranked model candidates for this hardware (dry run, no pull)."""
    hw = _detect.available_memory()
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    # The catalog is a catalog of models; a backend can only run some of them.
    # Without this the table offered Ollama a model named by a directory slug it
    # cannot pull, and offered the streaming backend a GGUF tag it cannot read —
    # `resolve` has always filtered, and this view had not.
    entries = _catalog.servable_only(_catalog.load_catalog(), backend)
    load = _detect.server_load() if live else None
    streaming = backend == "airllm"
    disk = _detect.disk_profile() if streaming else {}
    if streaming:
        # The interactive floor describes a resident model. Judging a streamed
        # one by it marks every candidate uncomfortable and says nothing.
        if min_tps == _score.COMFORT_TPS:
            min_tps = _offload.COMFORT_TPS_STREAMING
        click.echo(
            f"\nLayer streaming off {disk.get('storage')} storage at "
            f"{disk.get('read_gbs')} GB/s ({disk.get('basis')}), "
            f"{disk.get('free_gb')} GB free. Memory is one layer shard; the drive "
            f"sets the speed. Batch floor: {min_tps} tok/s."
        )

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
            bandwidth_gbs=bandwidth,
            min_tps=min_tps,
            backend=backend,
            disk_read_gbs=disk.get("read_gbs"),
        )
        header = f"\n=== {k.upper()} candidates"
        if application:
            header += f" [{application}]"
        header += f" ({backend}) ==="
        click.echo(header)
        if streaming:
            click.echo(header)
            plans = _offload.rank(
                entries,
                budget_gb=_offload.budget_gb(hw, load),
                disk=disk,
                kind=k,  # type: ignore[arg-type]
            )
            click.echo(_fmt_table(_streaming_rows(plans), _STREAM_COLUMNS))
            continue
        rows = []
        for e in ranked:
            # rank() has already decided these, and it is the only caller that
            # knows whether a measurement was available. Recomputing the
            # estimate here would quietly discard it.
            tps = e.get("_tps")
            comfy = bool(e.get("_comfy"))
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
                    # A measured figure is marked, because it carries more
                    # weight than an estimate: only a measurement can demote.
                    "tok/s": (
                        f"{tps:.0f}{'*' if e.get('_tps_basis') == 'measured' else ''}"
                        if tps
                        else "-"
                    ),
                    "comfy": "yes" if comfy else "NO",
                    "notes": (e.get("notes") or "")[:40],
                }
            )
        click.echo(_fmt_table(rows, ["id", "ram_gb", "score", "fits", "tok/s", "comfy", "notes"]))

    click.echo()


@cli.command("resolve")
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
    type=click.Choice(["auto", "ollama", "vllm", "airllm"]),
    default="auto",
    show_default=True,
    help=(
        "Serving backend. 'auto' = vLLM on Linux with a discrete GPU (NVIDIA/AMD), "
        "else Ollama — and, when nothing fits this machine's memory, an automatic "
        "fallback to 'airllm' layer streaming for the kinds that found nothing "
        "(set BEST_ENGINE_AIRLLM=never, or `airllm: never` in the brief, to switch "
        "that off). 'airllm' here asks for streaming outright."
    ),
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


@cli.command("report")
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
@click.option(
    "--cloud/--no-cloud",
    default=True,
    show_default=True,
    help=(
        "Also show the best PAID model for this task, for comparison against "
        "the local pick. Reference only: no API key needed, no network call "
        "-- it ranks the bundled pricing.yaml catalog on quality vs. price."
    ),
)
@click.option(
    "--quality-vs-cost",
    type=float,
    default=_cloud_catalog.DEFAULT_QUALITY_VS_COST,
    show_default=True,
    help=(
        "Cloud pick only: 0..1 weight on quality vs. price. 1.0 = best "
        "benchmark regardless of price; 0.0 = cheapest regardless of quality."
    ),
)
@click.option(
    "--cloud-provider",
    type=str,
    default=None,
    help="Cloud pick only: restrict to one provider (e.g. openai, anthropic, mistral).",
)
@click.option(
    "--backend",
    type=click.Choice(["auto", "ollama", "vllm"]),
    default="auto",
    show_default=True,
    help="Serving backend. 'auto' = vLLM on Linux with a discrete GPU (NVIDIA/AMD), else Ollama.",
)
def report_cmd(
    task: str | None,
    headroom: float,
    out: str | None,
    fmt: str,
    live: bool,
    cloud: bool,
    quality_vs_cost: float,
    cloud_provider: str | None,
    backend: str,
) -> None:
    """Recommend the best engine(s) for this hardware and task; emit MD + JSON."""
    from . import engine as _engine
    from .pull import installed_tags

    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    load = _detect.server_load() if live else None

    # This command used to size every pick against Ollama Q4 regardless of what
    # the machine would actually serve with, so on the one configuration where
    # `resolve` picks vLLM -- Linux with a discrete GPU, the documented
    # production case -- the report and the engine file disagreed, and the
    # report was the optimistic one. Measured on a 48 GB GPU: the report
    # offered `qwen2.5-coder:14b` at 9.9 GB while the engine it would build
    # picked `qwen2.5-coder:7b` at 16.1 GB. "vLLM picks are sized against full
    # FP16 weights, so a vLLM pick is realistic on the real GPU" was true of
    # `resolve` and false here.
    if backend == "auto":
        backend = _engine.default_backend()

    # And the already-pulled tiebreak, which only ever fired through
    # `engine.resolve`. Same condition `storage` uses: the tag list is an
    # Ollama concept, so it is asked for only when Ollama is the backend.
    present = installed_tags() if backend == "ollama" else set()

    rep = _recommend_engines(
        hw,
        entries,
        task=task,
        headroom=headroom,
        compute=compute,
        load=load,
        backend=backend,
        installed=present,
    )
    if cloud:
        rep["cloud"] = _cloud_recommend(
            task, quality_vs_cost=quality_vs_cost, provider=cloud_provider
        )

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


@cli.group("usages")
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
            # Same notation as the `candidates` table: "*" measured here,
            # "~" estimated. The engine file now records which this was.
            #
            # Borrowed from `recommend` rather than written again: the two
            # hand-rolled copies formatted the number before testing whether
            # there was one, so a machine the bandwidth probe cannot read
            # (a CI container, for one) crashed the command on
            # `None.__format__`. One formatter cannot disagree with itself.
            extra = (
                f", {_fmt_tps(tps, section.get('tps_basis'))} tok/s"
                if isinstance(tps, (int, float))
                else ""
            )
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


@cli.group("catalog")
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
@click.option(
    "--ollama",
    "from_ollama",
    is_flag=True,
    default=False,
    help=(
        "Widen the catalog from the official Ollama library instead of ApXML. "
        "These entries are real pull tags, so they can actually be served; "
        "they carry no benchmark scores, so they rank below any scored model "
        "until a scored source fills them in."
    ),
)
@click.option(
    "--arena",
    is_flag=True,
    default=False,
    help=(
        "Also merge LM Arena conversational ratings. These cover hosted "
        "frontier models far better than small local ones, so the axis mostly "
        "serves the cloud catalog. Arena publishes no API and every mirror is "
        "a third-party scrape: when none is fresh enough, the command says so "
        "and leaves the axis empty."
    ),
)
def catalog_update(limit: int | None, timeout: float, arena: bool, from_ollama: bool) -> None:
    """Refresh the catalog cache from the ApXML open-weight model directory.

    Fetched specs are normalized to catalog entries and merged into
    ``~/.best-engine-ai-helper/catalog_cache.yaml`` by id; the bundled seed is
    never modified. ApXML supplies specs and memory-fit figures but no numeric
    benchmarks, so refreshed entries carry null scores until a scored source
    fills them.

    ``--arena`` is one such scored source, with a caveat worth stating up
    front: it rates what its voters can chat with, so it populates the cloud
    catalog far better than the local one.
    """
    source_name = "the Ollama library" if from_ollama else "ApXML"
    click.echo(f"Fetching models from {source_name}…", err=True)
    try:
        if from_ollama:
            from .sources import ollama_library

            specs = ollama_library.fetch_pullable_models(timeout=timeout, limit=limit)
            entries = _catalog.normalize_ollama_specs(specs)
        else:
            from .sources import apxml

            specs = apxml.fetch_open_weight_models(timeout=timeout, limit=limit)
            entries = _catalog.normalize_apxml_specs(specs)
    except Exception as exc:  # network / parse failures should not traceback
        osh.error(f"catalog update failed:\n\t{exc}")
        click.echo(f"catalog update failed: {exc}", err=True)
        sys.exit(1)

    if not entries:
        click.echo(f"No usable models returned from {source_name}; cache unchanged.", err=True)
        sys.exit(1)

    if arena:
        click.echo("Fetching conversational ratings from LM Arena mirrors…", err=True)
        entries, message, merged = _catalog.merge_arena_axes(entries, timeout=timeout)
        if not merged:
            osh.warning(message)
        click.echo(message, err=True)

    path = _catalog.write_cache(entries)
    click.echo(f"Updated catalog cache with {len(entries)} model(s):\n\t{path}")


# ---------------------------------------------------------------------------
# hardware subgroup
# ---------------------------------------------------------------------------


@cli.group("hardware")
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


@cli.command("pull")
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
        # The gates are about to generate tokens either way, so timing them
        # costs no extra inference -- it is the same work with a stopwatch on
        # it. This is the one place the package stopped estimating decode speed
        # and started measuring it.
        meter = _throughput.Meter()
        metered_chat = meter.wrap(chat_for_candidate)
        click.echo(f"Running VLM gate on {tag} ...")
        vlm_ok = _validate_vlm.validate(metered_chat)
        click.echo(f"Running prose gate on {tag} ...")
        llm_ok = _validate_llm.validate(metered_chat)

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
            _report_measurement(meter, tag)
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


@cli.command("storage")
@click.option(
    "--backend",
    type=click.Choice(["ollama", "vllm"]),
    default="ollama",
    show_default=True,
    help="Serving backend, so footprints are sized the way they will load.",
)
def storage_cmd(backend: str) -> None:
    """Plan capacity: what fits on disk, and what fits in memory together.

    The second question is the one that usually matters. A working setup is a
    text model, a vision model and an embedder, and what decides the day is
    whether they can sit in memory *at the same time* rather than taking turns.
    Each may fit alone while the trio does not, and a per-model view would
    never say so.
    """
    from . import storage as _storage
    from .pull import installed_tags

    entries = _catalog.load_catalog()
    hw = _detect.available_memory()
    budget = _score.effective_budget(hw)
    present = installed_tags() if backend == "ollama" else set()

    report = _storage.report(entries, budget, installed=present, backend=backend)
    disk = report["disk"]

    click.echo(
        f"disk   : {disk['free_gb']} GB free of {disk['total_gb']} "
        f"({disk['percent_used']}% used); {disk['spendable_gb']} GB spendable"
    )
    click.echo(f"memory : {report['memory_budget_gb']} GB available to models together")

    if report["already_here"]:
        here = ", ".join(f"{r['id']} ({r['disk_gb']} GB)" for r in report["already_here"])
        click.echo(f"\nalready here: {here}")

    click.echo(f"\nCould be pulled into the space left ({len(report['pullable_now'])}):")
    for row in report["pullable_now"]:
        click.echo(f"  {row['disk_gb']:>6.1f} GB  {row['id']}  [{row['kind']}]")
    if not report["pullable_now"]:
        click.echo("  (nothing fits in the remaining space)")

    click.echo("\nCan be held in memory at the same time, best first:")
    for combo in report["resident_sets"]:
        names = " + ".join(f"{k}:{v}" for k, v in combo["models"].items())
        # Score first, because it is what the list is ordered by. Printing
        # only the memory left the reader to infer an order from a column
        # that no longer decides it.
        click.echo(
            f"  score {combo['total_score']:>6.1f}  {combo['total_ram_gb']:>6.1f} GB  "
            f"{names}   (headroom {combo['headroom_gb']} GB)"
        )
    if not report["resident_sets"]:
        click.echo("  (no one-per-kind combination fits; they must take turns)")

    for warning in report["warnings"]:
        click.echo(f"\n! {warning}", err=True)


@cli.command("providers")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit the rows as JSON.")
def providers_cmd(as_json: bool) -> None:
    """Which cloud providers are usable right now, and for the others, why not.

    This package claims to route on the keys you actually hold, and that claim
    is only worth something if you can see it being applied. The answer existed
    -- `cloud_catalog.provider_status`, served at `/api/providers` -- but only
    through the GUI, so the surface most people use could not ask the question.

    Never prints a key value: only whether one resolved, and the NAME of the
    variable it would come from.
    """
    from . import cloud_catalog as _cc

    rows = _cc.provider_status()
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return

    click.echo(
        _fmt_table(
            [
                {
                    "provider": r["provider"],
                    "key_env": r["key_env"],
                    "usable": "yes" if r["available"] else "NO",
                    "models": len(r["models"]),
                    "why not": r["reason"][:60],
                }
                for r in rows
            ],
            ["provider", "key_env", "usable", "models", "why not"],
        )
    )
    usable = sum(1 for r in rows if r["available"])
    click.echo(f"\n{usable} of {len(rows)} provider(s) usable.")
    if usable < len(rows):
        click.echo("Set a key in settings.yaml, a .env file, the environment, or the keychain.")


@cli.command("doctor")
@click.option(
    "--directory",
    default=".",
    show_default=True,
    help="Repo directory holding the engine file.",
)
@click.option(
    "--timeout",
    type=float,
    default=1.5,
    show_default=True,
    help="Seconds to wait for the local daemon.",
)
def doctor_cmd(directory: str, timeout: float) -> None:
    """Compare what the engine file resolved against what the daemon serves.

    "Resolved" and "runnable" are two different claims, and they drift apart
    quietly: an engine file is written once, while the daemon it names is
    mutable and ``ollama rm`` leaves no trace in the descriptor. Without this,
    the gap surfaces at the first inference call -- usually mid-job, which is
    the worst moment to learn a model was never pullable.

    Diagnoses only. Re-resolving here would hide the drift this exists to show.
    Exits non-zero when anything the file names cannot be served right now.
    """
    from . import engine as _engine

    report = _engine.diagnose(directory, timeout=timeout)

    click.echo(f"engine file : {report['engine_path']}")
    click.echo(f"backend     : {report['backend'] or '-'}")
    click.echo(f"daemon      : {'reachable' if report['daemon_reachable'] else 'NOT reachable'}")
    if report["served"]:
        click.echo(f"serves      : {', '.join(report['served'])}")

    if report["ok"]:
        click.echo("\nEverything the engine file names can be served right now.")
        return

    click.echo("")
    for finding in report["findings"]:
        click.echo(f"  - {finding['message']}", err=True)
    sys.exit(1)


@cli.command("validate")
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
    meter = _throughput.Meter()
    metered_chat = meter.wrap(_llm.chat)
    vlm_ok = _validate_vlm.validate(metered_chat)
    llm_ok = _validate_llm.validate(metered_chat)
    # Re-measuring here is the point of running `validate` again after an OS
    # update changed GPU availability: the gates re-run anyway, so the figure
    # refreshes for free.
    _report_measurement(meter, text_model)

    click.echo(f"VLM gate: {'pass' if vlm_ok else 'FAIL'}")
    click.echo(f"Prose gate: {'pass' if llm_ok else 'FAIL'}")

    if not (vlm_ok and llm_ok):
        sys.exit(1)


@cli.group("airllm")
def airllm_group() -> None:
    """Layer streaming: run a model that does NOT fit in this machine's memory.

    A transformer never needs every layer resident at once. Keep one layer
    shard in memory, stream the rest off disk, and the memory a model needs
    stops scaling with its parameter count — a 70B model runs in about 4 GB
    instead of 141. The runtime is airllm (github.com/lyogavin/airllm,
    Apache-2.0), an optional extra of this package; the arithmetic deciding
    whether it is worth it is here.

    The cost is time: every token re-reads the whole checkpoint from storage, so
    the unit is seconds per token. These are batch jobs — an overnight
    evaluation, one hard question, a quality reference for a smaller local
    model. Not a chat window.
    """


@airllm_group.command("status")
@click.option(
    "--measure",
    is_flag=True,
    default=False,
    help=(
        "Measure this machine's sequential disk read instead of reading the "
        "storage-class table. Writes and reads back ~256 MB with the page cache "
        "bypassed; takes a second or two and is worth it, since the drive sets "
        "the whole speed of this backend."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the decision as JSON.",
)
@click.option(
    "--request",
    type=click.Choice(["auto", "always", "never"]),
    default=None,
    help=(
        "Ask the policy as if the brief said this. Default: whatever "
        f"{_offload.ENV_VAR} says, else 'auto'."
    ),
)
def airllm_status(measure: bool, as_json: bool, request: str | None) -> None:
    """Can this machine stream layers, and would it be asked to?"""
    compute = _detect.compute_profile()
    disk = _detect.disk_profile(measure=measure)
    decision = _offload.decide(request=request, compute=compute, disk=disk)
    hw = _detect.available_memory()
    budget = _offload.budget_gb(hw)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "decision": decision,
                    "compute": compute,
                    "disk": disk,
                    "memory_budget_gb": budget,
                    "install": _offload.INSTALL_HINT,
                },
                indent=2,
                default=str,
            )
        )
        return

    click.echo("\n=== Layer streaming (airllm) ===")
    click.echo(f"  runtime here    : {decision['runtime'] or 'none'}")
    click.echo(f"  package         : {'installed' if decision['installed'] else 'NOT installed'}")
    click.echo(f"  storage         : {disk['storage']} ({disk['basis']})")
    click.echo(f"  read bandwidth  : {disk['read_gbs']} GB/s")
    click.echo(f"  free disk       : {disk['free_gb']} GB")
    click.echo(f"  shard budget    : {budget} GB of resident memory")
    click.echo(f"  request         : {decision['request']}")
    click.echo(f"  would activate  : {'YES' if decision['activate'] else 'no'}")
    click.echo(f"  trigger         : {decision['trigger']}")
    click.echo(f"\n  {decision['reason']}")
    for blocker in decision["blockers"]:
        click.echo(f"  - {blocker}")
    if not decision["installed"]:
        click.echo(f"\n  Install the runtime:  {_offload.INSTALL_HINT}")
    click.echo()


@airllm_group.command("plan")
@click.option(
    "--kind",
    type=click.Choice(["llm", "vlm", "both"]),
    default="llm",
    show_default=True,
    help="Model type to plan for.",
)
@click.option(
    "--compression",
    type=click.Choice(["4bit", "8bit"]),
    default=None,
    help=(
        "airllm's block-wise weight compression. Divides the bytes read per "
        "token, so it is the single biggest lever on speed (~3x at 4-bit) and "
        "shrinks the shards too. Needs bitsandbytes, which the extra installs."
    ),
)
@click.option(
    "--context",
    "context_k",
    type=float,
    default=4.0,
    show_default=True,
    help=(
        "Context length in thousands of tokens. Unlike the weights, the KV cache "
        "is NOT streamed: every layer's slice stays resident, so a long context "
        "costs real memory here."
    ),
)
@click.option(
    "--batch",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Independent prompts answered together. One layer pass is shared by the "
        "whole batch, so B answers arrive in the time of one — the biggest speed "
        "lever here, bigger than compression. Costs one KV cache per sequence, "
        "which the shard figure charges for."
    ),
)
@click.option(
    "--tokens",
    "new_tokens",
    type=int,
    default=300,
    show_default=True,
    help="Answer length the wait is computed for.",
)
@click.option(
    "--measure",
    is_flag=True,
    default=False,
    help="Measure disk read bandwidth rather than assuming the storage class.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
def airllm_plan(
    kind: str,
    compression: str | None,
    context_k: float,
    batch: int,
    new_tokens: int,
    measure: bool,
    as_json: bool,
) -> None:
    """Rank what this machine could stream, biggest runnable model first."""
    hw = _detect.available_memory()
    disk = _detect.disk_profile(measure=measure)
    entries = _catalog.servable_only(_catalog.load_catalog(), "airllm")
    budget = _offload.budget_gb(hw)
    kinds = ["llm", "vlm"] if kind == "both" else [kind]

    payload: dict[str, Any] = {"memory_budget_gb": budget, "disk": disk, "kinds": {}}
    for k in kinds:
        plans = _offload.rank(
            entries,
            budget_gb=budget,
            disk=disk,
            compression=compression,
            kind=k,  # type: ignore[arg-type]
            batch=batch,
            new_tokens=new_tokens,
        )
        chosen = _offload.pick(plans)
        payload["kinds"][k] = {"plans": plans, "chosen": chosen}
        if as_json:
            continue
        click.echo(
            f"\n=== {k.upper()}: streamable off {disk['storage']} at "
            f"{disk['read_gbs']} GB/s, {budget} GB shard budget ==="
        )
        click.echo(_fmt_table(_streaming_rows(plans), _STREAM_COLUMNS))
        if chosen:
            click.echo(
                f"\n  Pick: {chosen['model']} — {chosen['size_b']:.0f}B in "
                f"{chosen['resident_gb']} GB resident, {chosen['seconds_per_token']} s/token, "
                f"{chosen['disk']['peak_gb']:.0f} GB free disk to split "
                f"({chosen['disk']['steady_gb']:.0f} GB after)."
            )
            click.echo(
                f"  A {new_tokens}-token answer: {chosen['answer_human']}"
                + (
                    f" for all {batch} prompts, since they share each layer pass."
                    if batch > 1
                    else "."
                )
            )
            if not chosen["prefetching"]:
                click.echo(
                    "  Prefetching off for this pick: it does not fit with two shards "
                    "resident, and one does. Slower, but it runs."
                )
        else:
            click.echo(
                "\n  Nothing streamable: no candidate fits both one resident shard and "
                "the free disk the layer split needs."
            )

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        click.echo()


@airllm_group.command("prepare")
@click.option(
    "--model",
    type=str,
    required=True,
    help=(
        "HuggingFace repository id to download and split (e.g. meta-llama/Llama-3.3-70B-Instruct)."
    ),
)
@click.option(
    "--compression",
    type=click.Choice(["4bit", "8bit"]),
    default=None,
    help="Compress the shards as they are written.",
)
@click.option(
    "--shards-path",
    type=str,
    default=None,
    help=(
        "Where to write the per-layer shards. Default: beside the HuggingFace "
        "cache. Point this at your fastest volume — the shard read IS the decode "
        "speed."
    ),
)
@click.option(
    "--delete-original",
    is_flag=True,
    default=False,
    help=(
        "Remove the downloaded checkpoint once the shards exist, halving the disk "
        "requirement. The shards are then the only copy: losing them means "
        "downloading again."
    ),
)
def airllm_prepare(
    model: str, compression: str | None, shards_path: str | None, delete_original: bool
) -> None:
    """Download and split a checkpoint now, rather than inside the first call.

    The first streaming call pays for the download and the layer split, which
    for a large model is tens of minutes of disk. A caller who meets that inside
    a job will reasonably conclude it has hung. This pays it deliberately.
    """
    try:
        _offload.load(
            model,
            compression=compression,
            layer_shards_saving_path=shards_path,
            delete_original=delete_original,
        )
    except ImportError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    except Exception as exc:  # the download/split surface is wide; stay readable
        osh.error(f"airllm prepare failed:\n\t{exc}")
        click.echo(f"airllm prepare failed: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"Prepared {model}: layer shards are on disk and the first call will not "
        "have to split them."
    )


@airllm_group.command("compare")
@click.option(
    "--kind",
    type=click.Choice(["llm", "vlm"]),
    default="llm",
    show_default=True,
    help="Model type to compare.",
)
@click.option(
    "--application",
    type=click.Choice(_VALID_APPLICATIONS),
    default=None,
    help="Benchmark axis, so both sides are scored on the task that matters.",
)
@click.option(
    "--tokens",
    "new_tokens",
    type=int,
    default=300,
    show_default=True,
    help=("Answer length both sides are timed for. 300 tokens is about a long paragraph."),
)
@click.option(
    "--prompt-tokens",
    type=int,
    default=0,
    show_default=True,
    help=(
        "Prompt length. Free on the streamed side — one pass reads the whole "
        "checkpoint whatever rides through it — which is the one axis where "
        "streaming beats a resident model."
    ),
)
@click.option(
    "--batch",
    type=int,
    default=1,
    show_default=True,
    help=(
        "Independent prompts answered together. On the streamed side this is "
        "nearly free in time and costs one KV cache per sequence, so it is the "
        "biggest speed lever the backend has."
    ),
)
@click.option(
    "--compression",
    type=click.Choice(["4bit", "8bit"]),
    default=None,
    help="airllm weight compression for the streamed side (~3x at 4-bit).",
)
@click.option(
    "--native-backend",
    type=click.Choice(["ollama", "vllm"]),
    default=None,
    help="Backend to compare against. Default: what `resolve` would pick here.",
)
@click.option("--measure", is_flag=True, default=False, help="Measure disk read bandwidth.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
def airllm_compare(
    kind: str,
    application: str | None,
    new_tokens: int,
    prompt_tokens: int,
    batch: int,
    compression: str | None,
    native_backend: str | None,
    measure: bool,
    as_json: bool,
) -> None:
    """Native model or streamed model: the same machine, the same answer, both prices.

    The decision streaming actually forces. A machine that runs a 14B model
    comfortably can also stream a 70B one; the two differ by a few benchmark
    points in one direction and three orders of magnitude of latency in the
    other. This prints both, priced in seconds for one answer of the same
    length, so the trade can be made rather than guessed at.
    """
    from . import engine as _engine

    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    disk = _detect.disk_profile(measure=measure)
    report = _offload.compare(
        _catalog.load_catalog(),
        hw=hw,
        disk=disk,
        bandwidth_gbs=compute.get("bandwidth_gbs"),
        kind="vlm" if kind == "vlm" else "llm",
        application=application,
        native_backend=native_backend or _engine.default_backend(),
        new_tokens=new_tokens,
        prompt_tokens=prompt_tokens,
        batch=batch,
        compression=compression,
    )

    if as_json:
        click.echo(json.dumps(report, indent=2, default=str))
        return

    native = report["native"]
    streamed = report["streamed"]
    click.echo(
        f"\n=== {kind.upper()}: {native['backend']} vs airllm, for a {new_tokens}-token answer ==="
    )
    click.echo(
        f"  budgets: {native['budget_gb']} GB resident ({native['backend']}) · "
        f"{streamed['budget_gb']} GB per shard (airllm) · "
        f"disk {disk['read_gbs']} GB/s ({disk['basis']})"
    )
    if batch > 1:
        click.echo(f"  batch of {batch}: counted on the streamed side, where a pass is shared")

    rows = []
    for row in native["rows"][:6]:
        rows.append(
            {
                "model": row["catalog_id"],
                "backend": row["backend"],
                "score": f"{row['score']:.0f}" if row["score"] else "-",
                "resident": f"{row['resident_gb']:.1f}" if row["resident_gb"] else "-",
                "tok/s": f"{row['tokens_per_s']:.1f}" if row["tokens_per_s"] else "-",
                "answer": row["answer_human"],
                "runs": "yes" if row["usable"] else "NO",
            }
        )
    for row in streamed["rows"][:6]:
        rows.append(
            {
                "model": (row["model"] or "")[:40],
                "backend": "airllm",
                "score": f"{row['score']:.0f}" if row.get("score") else "-",
                "resident": f"{row['resident_gb']:.1f}" if row["resident_gb"] else "-",
                "tok/s": f"{row['effective_tps']:.3f}" if row.get("effective_tps") else "-",
                "answer": row["answer_human"],
                "runs": "yes" if row["usable"] else "NO",
            }
        )
    click.echo(
        _fmt_table(rows, ["model", "backend", "score", "resident", "tok/s", "answer", "runs"])
    )
    click.echo(f"\n  {report['verdict']}")
    if prompt_tokens:
        click.echo(
            f"  Note: the {prompt_tokens}-token prompt is counted on neither side — it is "
            "free under streaming (one pass) and unpriced here under "
            f"{native['backend']}, which flatters {native['backend']}."
        )
    click.echo()


@cli.command("gui")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
def gui_cmd(host: str, port: int) -> None:
    """Launch the minimal browser GUI (hardware + task -> best engine)."""
    import uvicorn

    click.echo(f"Serving GUI at http://{host}:{port}/gui")
    uvicorn.run("best_engine_ai_helper.api:app", host=host, port=port)


@cli.command("env")
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


@cli.command("activity")
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


def main() -> None:
    """Console entry point (`best-engine-ai-helper`, registered in pyproject.toml).

    Click's own invocation only special-cases `ClickException`/`Abort` (and a
    broken pipe); a plain library exception (a connection failure, a missing
    `ollama` binary, ...) would otherwise propagate as a raw Python traceback
    instead of a clean CLI error. This wraps the whole invocation and
    translates that last case into a one-line stderr message + exit 1 --
    click's own control flow (usage errors, `--help`, an explicit
    `sys.exit(1)` in a subcommand) already raises `SystemExit`, a
    `BaseException` this does not catch, so it passes through untouched.
    """
    try:
        cli()
    except Exception as err:  # noqa: BLE001 — last resort: see docstring
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
