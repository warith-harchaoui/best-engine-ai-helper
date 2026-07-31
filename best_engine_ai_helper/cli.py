"""
cli — Click command-line interface for best-engine-ai-helper.

Entry point: `best-engine-ai-helper` (registered in pyproject.toml).

Phase 0a commands (fully implemented):
  detect          Print detected hardware as JSON.
  recommend       Print ranked model candidates for this hardware.
  catalog show    Print the merged model catalog as a table.
  hardware show   Print the merged hardware chip table.

Phase 0b stubs (print a notice; implemented in the next phase):
  pull            Pull the best model and run Ralph validation gates.
  validate        Run Ralph gates on the already-configured model.
  env             Print the env block for ~/.zshrc or sourcing.
  catalog update  Refresh the catalog cache from external leaderboard sources.
  hardware update Refresh the hardware cache from TechPowerUp and Ollama.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import json
import logging
import os
import sys

import click
import os_helper as osh

from . import catalog as _catalog
from . import detect as _detect
from . import hardware as _hardware
from . import score as _score
from .recommend import recommend as _recommend_engines
from .recommend import to_markdown as _report_markdown
from .recommend import write_report as _write_report

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_table(rows: list[dict], columns: list[str]) -> str:
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
    default=0.85,
    show_default=True,
    help="Safety headroom fraction (0-1) applied to available memory.",
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
def recommend_cmd(kind: str, headroom: float, application: str | None) -> None:
    """Print ranked model candidates for this hardware (dry run, no pull)."""
    hw = _detect.available_memory()
    entries = _catalog.load_catalog()

    kinds: list[str] = ["llm", "vlm"] if kind == "both" else [kind]

    for k in kinds:
        ranked = _score.rank(hw, entries, kind=k, headroom=headroom, application=application)  # type: ignore[arg-type]
        header = f"\n=== {k.upper()} candidates"
        if application:
            header += f" [{application}]"
        header += " ==="
        click.echo(header)
        rows = []
        for e in ranked:
            rows.append({
                "id": e.get("id", "-"),
                "ram_gb": e.get("ram_gb", "-"),
                "score": (
                    e.get("benchmarks", {}).get("vision")
                    if k == "vlm"
                    else e.get("benchmarks", {}).get("general")
                ) or "-",
                "fits": "yes" if e.get("_fits") else "NO",
                "notes": (e.get("notes") or "")[:40],
            })
        click.echo(_fmt_table(rows, ["id", "ram_gb", "score", "fits", "notes"]))

    click.echo()


@main.command("report")
@click.option(
    "--task",
    type=str,
    default=None,
    help=(
        "Free-text task, e.g. \"retail product descriptions and image-quality "
        "checks\". Vision words add a VLM; code/math/ocr words pick the axis. "
        "Omit for a general text assistant."
    ),
)
@click.option(
    "--headroom",
    type=float,
    default=0.85,
    show_default=True,
    help="Memory safety fraction on top of the accelerator cap.",
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
def report_cmd(task: str | None, headroom: float, out: str | None, fmt: str) -> None:
    """Recommend the best engine(s) for this hardware and task; emit MD + JSON."""
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    rep = _recommend_engines(hw, entries, task=task, headroom=headroom, compute=compute)

    if out:
        md_path, json_path = _write_report(rep, out)
        click.echo(f"wrote {md_path} and {json_path}", err=True)

    if fmt == "json":
        click.echo(json.dumps(rep, indent=2))
    else:
        click.echo(_report_markdown(rep))


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
        rows.append({
            "id": e.get("id", "-"),
            "kind": e.get("kind", "-"),
            "size_b": e.get("size_b", "-"),
            "quant": e.get("quant", "-"),
            "disk_gb": e.get("disk_gb", "-"),
            "ram_gb": e.get("ram_gb", "-"),
            "general": bench.get("general") or "-",
            "vision": bench.get("vision") or "-",
        })
    cols = ["id", "kind", "size_b", "quant", "disk_gb", "ram_gb", "general", "vision"]
    click.echo(_fmt_table(rows, cols))


@catalog_group.command("update")
def catalog_update() -> None:
    """[Phase 0b] Refresh the catalog cache from external leaderboard sources."""
    click.echo("catalog update: not yet implemented (Phase 0b).", err=True)
    sys.exit(1)


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
        rows.append({
            "chip": e.get("chip", "-"),
            "vendor": e.get("vendor", "-"),
            "memory_gb": e.get("memory_gb", "-"),
            "ollama_usable_gb": e.get("ollama_usable_gb", "-"),
            "source": e.get("source", "-"),
        })
    click.echo(_fmt_table(rows, ["chip", "vendor", "memory_gb", "ollama_usable_gb", "source"]))


@hardware_group.command("update")
def hardware_update() -> None:
    """[Phase 0b] Refresh the hardware cache from TechPowerUp and Ollama pages."""
    click.echo("hardware update: not yet implemented (Phase 0b).", err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Phase 0b — pull, validate, env (fully implemented)
# ---------------------------------------------------------------------------

@main.command("pull")
@click.option("--keep-failed", is_flag=True, default=False,
              help="Do not remove failed models after a gate failure.")
@click.option("--vllm", is_flag=True, default=False,
              help="Print the vLLM serve command for the HuggingFace model instead of pulling.")
@click.option(
    "--application",
    type=click.Choice(_VALID_APPLICATIONS),
    default=None,
    show_default=False,
    help="Target use-case (code, math, ocr, vision, chat, generalist). Biases model selection.",
)
def pull_cmd(keep_failed: bool, vllm: bool, application: str | None) -> None:
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
    entries = _catalog.load_catalog()

    # Rank VLM candidates; the best VLM also covers text tasks
    ranked = _score.rank(hw, entries, kind="vlm", application=application)
    fitting = [e for e in ranked if e.get("_fits")]
    if not fitting:
        click.echo("No model fits in available memory. Trying the smallest anyway.", err=True)
        fitting = ranked[:1]

    for candidate in fitting:
        tag = candidate["id"]
        hf_id = candidate.get("vllm_id")

        if vllm:
            # Print the vLLM serve command for the user to run manually
            click.echo(f"vllm serve {hf_id or tag} --port 8000")
            sys.exit(0)

        click.echo(f"Pulling {tag} ...")
        ok = _pull.ollama_pull(tag)
        if not ok:
            click.echo(f"ollama pull {tag} failed. Skipping.", err=True)
            continue

        click.echo(f"Running VLM gate on {tag} ...")
        vlm_ok = _validate_vlm.validate(_llm.chat)
        click.echo(f"Running prose gate on {tag} ...")
        llm_ok = _validate_llm.validate(_llm.chat)

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
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "The GUI requires the [api] extra. Install with: "
            "pip install 'best-engine-ai-helper[api]'",
            err=True,
        )
        sys.exit(1)

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
