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
  catalog update  Refresh the catalog cache from four external sources.
  hardware update Refresh the hardware cache from TechPowerUp and Ollama.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import json
import sys

import click

from . import catalog as _catalog
from . import detect as _detect
from . import hardware as _hardware
from . import score as _score

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
def main() -> None:
    """Pick and pull the best local LLM/VLM for the current hardware."""


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
    default=0.80,
    show_default=True,
    help="Safety headroom fraction (0-1) applied to available memory.",
)
def recommend_cmd(kind: str, headroom: float) -> None:
    """Print ranked model candidates for this hardware (dry run, no pull)."""
    hw = _detect.available_memory()
    entries = _catalog.load_catalog()

    kinds: list[str] = ["llm", "vlm"] if kind == "both" else [kind]

    for k in kinds:
        ranked = _score.rank(hw, entries, kind=k, headroom=headroom)  # type: ignore[arg-type]
        click.echo(f"\n=== {k.upper()} candidates ===")
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
    """[Phase 0b] Refresh the catalog cache from four external sources."""
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
# Phase 0b stubs
# ---------------------------------------------------------------------------

@main.command("pull")
@click.option("--keep-failed", is_flag=True, default=False, help="Do not remove failed models.")
@click.option("--vllm", is_flag=True, default=False, help="Print vLLM serve command instead.")
def pull_cmd(keep_failed: bool, vllm: bool) -> None:
    """[Phase 0b] Pull the best model and run Ralph validation gates."""
    click.echo("pull: not yet implemented (Phase 0b).", err=True)
    sys.exit(1)


@main.command("validate")
def validate_cmd() -> None:
    """[Phase 0b] Run Ralph gates on the already-configured model."""
    click.echo("validate: not yet implemented (Phase 0b).", err=True)
    sys.exit(1)


@main.command("env")
def env_cmd() -> None:
    """[Phase 0b] Print the env block ready for ~/.zshrc or sourcing."""
    click.echo("env: not yet implemented (Phase 0b).", err=True)
    sys.exit(1)
