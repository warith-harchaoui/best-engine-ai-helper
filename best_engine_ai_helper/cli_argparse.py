"""
cli_argparse — argparse-based command-line interface for best-engine-ai-helper.

Entry point: `best-engine-ai-helper-argparse` (registered in pyproject.toml).

The suite convention (see os-helper's README, "Three surfaces, one codebase")
is: the argparse CLI is the zero-extra-runtime-dependency primary name, and a
click twin ships as `<pkg>-click`. best-engine-ai-helper's history inverts
this — `best-engine-ai-helper` (the published, stable entry point) is already
click-based, and click is a CORE dependency here, not an opt-in `[cli]` extra
like elsewhere in the suite. Per CODING.md rule 20.1 ("do not migrate a
stable existing CLI solely to change parser"), that entry point is left
untouched. This module instead adds the missing SECOND surface as
`best-engine-ai-helper-argparse`, mirroring every command 1:1 so both parsers
expose the identical contract (same flags, same defaults, same output). Every
handler delegates to the same library functions `cli.py`'s click commands
call — no business logic is duplicated between the two CLIs.

Commands (identical to `cli.py`):
  detect          Print detected hardware as JSON.
  recommend       Print ranked model candidates for this hardware.
  resolve         Resolve a usage brief into a machine-specific engine file.
  report          Recommend the best engine(s) for a task; emit MD + JSON.
  usages list/show/resolve   Browse and resolve the sev7n usage catalog.
  catalog show/update        Manage the model catalog.
  hardware show/update       Manage the hardware chip table.
  pull            Pull the best model and run Ralph validation gates.
  validate        Run Ralph gates on the already-configured model.
  gui             Launch the minimal browser GUI.
  env             Print the env block for ~/.zshrc or sourcing.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from typing import Any, cast

import os_helper as osh

from . import catalog as _catalog
from . import detect as _detect
from . import hardware as _hardware
from . import observe as _observe
from . import score as _score
from .cli import _VALID_APPLICATIONS, _fmt_table
from .recommend import recommend as _recommend_engines
from .recommend import to_markdown as _report_markdown
from .recommend import write_report as _write_report

# ---------------------------------------------------------------------------
# Output helpers — mirrors cli.py's click.echo split (stdout = data, stderr =
# diagnostics), see CODING.md rule 20.2.
# ---------------------------------------------------------------------------


def _emit(text: object = "") -> None:
    """
    Write one result line to stdout (the CLI's data channel).

    Parameters
    ----------
    text : object
        Value to print; stringified then followed by a single newline.
    """
    sys.stdout.write(f"{text}\n")


def _emit_err(text: object) -> None:
    """
    Write one diagnostic line to stderr.

    Parameters
    ----------
    text : object
        Value to print to stderr; stringified then followed by a newline.
    """
    sys.stderr.write(f"{text}\n")


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


def _handle_detect(_ns: argparse.Namespace) -> int:
    """
    Print detected hardware as JSON. Same payload as `cli.py`'s `detect`.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (always 0).
    """
    mem = _detect.available_memory()
    info = {
        "platform": _detect.platform_name(),
        "chip_vendor": _detect.chip_vendor(),
        "memory": mem,
        "hardware": osh.hardware_info(),
    }
    _emit(json.dumps(info, indent=2))
    return 0


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------


def _handle_recommend(ns: argparse.Namespace) -> int:
    """
    Print ranked model candidates for this hardware (dry run, no pull).

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `kind`, `headroom`, `application`, `min_tps`, `live`.

    Returns
    -------
    int
        Process exit code (always 0).
    """
    hw = _detect.available_memory()
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    entries = _catalog.load_catalog()
    load = _detect.server_load() if ns.live else None

    kinds: list[str] = ["llm", "vlm"] if ns.kind == "both" else [ns.kind]

    for k in kinds:
        ranked = _score.rank(
            hw, entries, kind=k, headroom=ns.headroom,  # type: ignore[arg-type]
            application=ns.application, load=load,
        )
        header = f"\n=== {k.upper()} candidates"
        if ns.application:
            header += f" [{ns.application}]"
        header += " ==="
        _emit(header)
        rows = []
        for e in ranked:
            tps = _score.estimated_tokens_per_second(e, bandwidth)
            comfy = bool(e.get("_fits")) and (tps is None or tps >= ns.min_tps)
            rows.append({
                "id": e.get("id", "-"),
                "ram_gb": e.get("ram_gb", "-"),
                "score": (
                    e.get("benchmarks", {}).get("vision")
                    if k == "vlm"
                    else e.get("benchmarks", {}).get("general")
                ) or "-",
                "fits": "yes" if e.get("_fits") else "NO",
                "tok/s": f"{tps:.0f}" if tps else "-",
                "comfy": "yes" if comfy else "NO",
                "notes": (e.get("notes") or "")[:40],
            })
        _emit(_fmt_table(
            rows, ["id", "ram_gb", "score", "fits", "tok/s", "comfy", "notes"]))

    _emit()
    return 0


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


def _handle_resolve(ns: argparse.Namespace) -> int:
    """
    Resolve a usage brief into a machine-specific engine file (gitignored).

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `brief`, `out`, `backend`, `endpoint`.

    Returns
    -------
    int
        Process exit code (0 on success, 1 if the brief is missing or
        resolution fails).
    """
    from pathlib import Path

    from . import engine as _engine

    brief_path = Path(ns.brief)
    if not brief_path.is_file():
        _emit_err(f"Brief not found: {brief_path}")
        return 1

    out_path = Path(ns.out) if ns.out else brief_path.with_name(_engine.ENGINE_NAME)
    try:
        descriptor = _engine.resolve(brief_path, backend=ns.backend, endpoint=ns.endpoint)
        _engine.write_engine(descriptor, out_path)
    except Exception as exc:  # keep resolution failures readable, no traceback
        osh.error(f"resolve failed:\n\t{exc}")
        _emit_err(f"resolve failed: {exc}")
        return 1

    chosen = ", ".join(
        f"{k}={descriptor[k]['model']}"
        for k in ("llm", "vlm")
        if descriptor.get(k)
    )
    _emit(
        f"Wrote {out_path}\n"
        f"  backend: {descriptor['backend']}  ({chosen})\n"
        f"  NOTE: hardware-specific — add '{out_path.name}' to .gitignore, do not commit."
    )
    for cmd in descriptor.get("serve", []):
        _emit(f"  bring it up:  {cmd}")
    return 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _handle_report(ns: argparse.Namespace) -> int:
    """
    Recommend the best engine(s) for this hardware and task; emit MD + JSON.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `task`, `headroom`, `out`, `format`, `live`.

    Returns
    -------
    int
        Process exit code (always 0).
    """
    hw = _detect.available_memory()
    compute = _detect.compute_profile()
    entries = _catalog.load_catalog()
    load = _detect.server_load() if ns.live else None
    rep = _recommend_engines(
        hw, entries, task=ns.task, headroom=ns.headroom, compute=compute, load=load
    )

    if ns.out:
        md_path, json_path = _write_report(rep, ns.out)
        _emit_err(f"wrote {md_path} and {json_path}")

    if ns.format == "json":
        _emit(json.dumps(rep, indent=2))
    else:
        _emit(_report_markdown(rep))
    return 0


# ---------------------------------------------------------------------------
# usages
# ---------------------------------------------------------------------------


def _handle_usages_list(_ns: argparse.Namespace) -> int:
    """
    List every usage profile and family (names, not models).

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (always 0).
    """
    from . import usages as _usages

    _emit("Families (usages that can share one model):")
    frows = [
        {"id": f["id"], "name": f["name"],
         "members": ", ".join(f["members"]), "summary": f["summary"][:48]}
        for f in _usages.list_families()
    ]
    _emit(_fmt_table(frows, ["id", "name", "members", "summary"]))

    _emit("\nProfiles:")
    prows = [
        {"name": p["name"], "family": p["family"] or "-",
         "status": p["status"], "summary": p["summary"][:52]}
        for p in _usages.list_usages()
    ]
    _emit(_fmt_table(prows, ["name", "family", "status", "summary"]))
    return 0


def _handle_usages_show(ns: argparse.Namespace) -> int:
    """
    Show one profile's needs (task, structured output, floors) — no model.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `name` (the usage profile name).

    Returns
    -------
    int
        Process exit code (0 on success, 1 if the profile name is unknown).
    """
    from . import usages as _usages

    try:
        prof = _usages.get_usage(ns.name)
    except KeyError as exc:
        _emit_err(str(exc))
        return 1

    brief = prof.get("brief", {})
    _emit(f"{prof['name']}  [{prof.get('status', 'stable')}, family "
          f"{prof.get('family', '-')}]")
    _emit(f"  {prof.get('summary', '')}\n")
    _emit(prof.get("description", "").strip() + "\n")
    _emit("Needs (selection criteria):")
    _emit(f"  kind             : {brief.get('kind', '-')}")
    _emit(f"  structured_output: {brief.get('structured_output', '-')}")
    _emit(f"  min_tps          : {brief.get('min_tps', '-')}")
    _emit(f"  headroom         : {brief.get('headroom', '-')}")
    _emit(f"  min_quality      : {prof.get('min_quality', '-')}")
    _emit(f"  context_length   : {prof.get('context_length', '-')}")
    _emit(f"  local_strict     : {prof.get('local_strict', True)}")
    _emit(f"  task             : {' '.join(brief.get('task', '').split())}")
    return 0


def _echo_resolved(descriptor: dict[str, Any], out: str | None) -> None:
    """
    Print a resolved usage/family descriptor and optionally write it (gitignored).

    Parameters
    ----------
    descriptor : dict[str, Any]
        Resolved engine descriptor from `usages.resolve_usage`/`resolve_family`.
    out : str or None
        Path to write the descriptor to, or None to only print it.
    """
    label = descriptor.get("usage") or descriptor.get("family") or "?"
    chosen = []
    for kind in ("llm", "vlm", "embed"):
        section = descriptor.get(kind)
        if isinstance(section, dict) and section.get("model"):
            ram = section.get("ram_gb")
            tps = section.get("est_tokens_per_s")
            extra = f", ~{tps:.0f} tok/s" if isinstance(tps, (int, float)) else ""
            chosen.append(f"{kind}={section['model']} ({ram} GB{extra})")
    _emit(f"{label}: backend {descriptor.get('backend')}  "
          + ("  ".join(chosen) if chosen else "no model resolved"))
    if descriptor.get("status") == "scaffold":
        _emit("  NOTE: scaffolded profile — resolvable now, downstream wiring pending.")
    _emit("  NOTE: machine-specific — the chosen model lives only in the "
          "generated file; keep it gitignored, never commit.")
    if out:
        from . import engine as _engine

        path = _engine.write_engine(descriptor, out)
        _emit(f"  wrote {path}")
        for cmd in descriptor.get("serve", []):
            _emit(f"  bring it up:  {cmd}")


def _handle_usages_resolve(ns: argparse.Namespace) -> int:
    """
    Resolve a profile (or --family) into this machine's model.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `name`, `family`, `backend`, `endpoint`, `out`.

    Returns
    -------
    int
        Process exit code (0 on success, 1 if neither `name` nor `family`
        is given, or resolution fails).
    """
    from . import usages as _usages

    if not ns.name and not ns.family:
        _emit_err("Give a profile NAME or --family F1/F2/F3.")
        return 1
    try:
        if ns.family:
            descriptor = _usages.resolve_family(ns.family, backend=ns.backend, endpoint=ns.endpoint)
        else:
            descriptor = _usages.resolve_usage(ns.name, backend=ns.backend, endpoint=ns.endpoint)
    except (KeyError, ValueError) as exc:
        _emit_err(f"resolve failed: {exc}")
        return 1
    _echo_resolved(descriptor, ns.out)
    return 0


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


def _handle_catalog_show(_ns: argparse.Namespace) -> int:
    """
    Print the merged model catalog as a table.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (always 0).
    """
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
    _emit(_fmt_table(rows, cols))
    return 0


def _handle_catalog_update(ns: argparse.Namespace) -> int:
    """
    Refresh the catalog cache from the ApXML open-weight model directory.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `limit`, `timeout`.

    Returns
    -------
    int
        Process exit code (0 on success, 1 on a network/parse failure or an
        empty feed).
    """
    from .sources import apxml

    _emit_err("Fetching open-weight models from ApXML…")
    try:
        specs = apxml.fetch_open_weight_models(timeout=ns.timeout, limit=ns.limit)
    except Exception as exc:  # network / parse failures should not traceback
        osh.error(f"catalog update failed:\n\t{exc}")
        _emit_err(f"catalog update failed: {exc}")
        return 1

    entries = _catalog.normalize_apxml_specs(specs)
    if not entries:
        _emit_err("No usable models returned from ApXML; cache unchanged.")
        return 1

    path = _catalog.write_cache(entries)
    _emit(f"Updated catalog cache with {len(entries)} model(s):\n\t{path}")
    return 0


# ---------------------------------------------------------------------------
# hardware
# ---------------------------------------------------------------------------


def _handle_hardware_show(_ns: argparse.Namespace) -> int:
    """
    Print the merged hardware chip table.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (always 0).
    """
    entries = _hardware.load_hardware()
    rows = [
        {
            "chip": e.get("chip", "-"),
            "vendor": e.get("vendor", "-"),
            "memory_gb": e.get("memory_gb", "-"),
            "ollama_usable_gb": e.get("ollama_usable_gb", "-"),
            "source": e.get("source", "-"),
        }
        for e in entries
    ]
    _emit(_fmt_table(rows, ["chip", "vendor", "memory_gb", "ollama_usable_gb", "source"]))
    return 0


def _handle_hardware_update(_ns: argparse.Namespace) -> int:
    """
    Record this machine's chip and memory into the hardware cache.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (0 on success, 1 if no usable memory is detected).
    """
    entry = _hardware.detect_local_entry()
    if entry is None:
        _emit_err("Could not detect usable memory; hardware cache unchanged.")
        return 1

    path = _hardware.write_cache([entry])
    _emit(
        f"Recorded this machine into the hardware cache:\n"
        f"\t{entry['chip']} — {entry['memory_gb']} GB "
        f"({entry['ollama_usable_gb']} GB usable)\n\t{path}"
    )
    return 0


# ---------------------------------------------------------------------------
# pull / validate / gui / env
# ---------------------------------------------------------------------------


def _handle_pull(ns: argparse.Namespace) -> int:
    """
    Pull the best model and run Ralph validation gates.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `keep_failed`, `vllm`, `application`, `min_tps`.

    Returns
    -------
    int
        Process exit code (0 when a candidate passes both gates or `--vllm`
        printed a serve command, 1 if none pass).
    """
    from . import llm as _llm
    from . import pull as _pull
    from . import validate_llm as _validate_llm
    from . import validate_vlm as _validate_vlm

    hw = _detect.available_memory()
    bandwidth = _detect.compute_profile().get("bandwidth_gbs")
    entries = _catalog.load_catalog()

    ranked = _score.rank(hw, entries, kind="vlm", application=ns.application)
    fitting = [e for e in ranked if e.get("_fits")]
    if not fitting:
        _emit_err("No model fits in available memory. Trying the smallest anyway.")
        fitting = ranked[:1]

    def _too_slow(entry: dict[str, Any]) -> bool:
        """
        Report whether a candidate's estimated throughput misses the comfort floor.

        Parameters
        ----------
        entry : dict[str, Any]
            Catalog entry to evaluate.

        Returns
        -------
        bool
            True when the estimated tokens/s is below `ns.min_tps`.
        """
        tps = _score.estimated_tokens_per_second(entry, bandwidth)
        return tps is not None and tps < ns.min_tps

    fitting.sort(key=_too_slow)

    for candidate in fitting:
        tag = candidate["id"]
        hf_id = candidate.get("vllm_id")

        if ns.vllm:
            _emit(f"vllm serve {hf_id or tag} --port 8000")
            return 0

        _emit(f"Pulling {tag} ...")
        ok = _pull.ollama_pull(tag)
        if not ok:
            _emit_err(f"ollama pull {tag} failed. Skipping.")
            continue

        _emit(f"Running VLM gate on {tag} ...")
        vlm_ok = _validate_vlm.validate(_llm.chat)
        _emit(f"Running prose gate on {tag} ...")
        llm_ok = _validate_llm.validate(_llm.chat)

        if vlm_ok and llm_ok:
            env_path = _pull.write_env(
                text_model=tag,
                vision_model=tag,
                backend=os.environ.get("SPREZZATURE_LLM_BACKEND", "ollama"),
                base_url=os.environ.get("SPREZZATURE_LLM_BASE_URL", "http://localhost:11434"),
            )
            _emit(f"Both gates passed. Config written to {env_path}")
            _emit(f"Source it: source {env_path}")
            return 0
        else:
            _emit_err(
                f"{tag} failed: VLM={'pass' if vlm_ok else 'FAIL'}, "
                f"prose={'pass' if llm_ok else 'FAIL'}"
            )
            if not ns.keep_failed:
                _emit_err(f"Removing {tag} ...")
                _pull.ollama_rm(tag)

    _emit_err("No candidate passed both gates.")
    return 1


def _handle_validate(_ns: argparse.Namespace) -> int:
    """
    Run Ralph gates on the already-configured model.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (0 if both gates pass, 1 otherwise or if no model
        is configured).
    """
    from . import llm as _llm
    from . import validate_llm as _validate_llm
    from . import validate_vlm as _validate_vlm

    text_model = os.environ.get("BEST_LLM_TEXT", os.environ.get("SPREZZATURE_LLM_TEXT", ""))
    if not text_model:
        _emit_err("BEST_LLM_TEXT is not set. Run `pull` first or source env.sh.")
        return 1

    _emit(f"Validating {text_model} ...")
    vlm_ok = _validate_vlm.validate(_llm.chat)
    llm_ok = _validate_llm.validate(_llm.chat)

    _emit(f"VLM gate: {'pass' if vlm_ok else 'FAIL'}")
    _emit(f"Prose gate: {'pass' if llm_ok else 'FAIL'}")

    return 0 if (vlm_ok and llm_ok) else 1


def _handle_gui(ns: argparse.Namespace) -> int:
    """
    Launch the minimal browser GUI (hardware + task -> best engine).

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `host`, `port`.

    Returns
    -------
    int
        Process exit code (0 on a clean shutdown, 1 if the `[api]` extra is
        missing).
    """
    try:
        import uvicorn
    except ImportError:
        _emit_err(
            "The GUI requires the [api] extra. Install with: "
            "pip install 'best-engine-ai-helper[api]'"
        )
        return 1

    _emit(f"Serving GUI at http://{ns.host}:{ns.port}/gui")
    uvicorn.run("best_engine_ai_helper.api:app", host=ns.host, port=ns.port)
    return 0


def _handle_env(_ns: argparse.Namespace) -> int:
    """
    Print the env block ready for ~/.zshrc or sourcing.

    Parameters
    ----------
    _ns : argparse.Namespace
        Parsed CLI arguments for this subcommand (none expected).

    Returns
    -------
    int
        Process exit code (0 on success, 1 if `env.sh` does not exist yet).
    """
    from pathlib import Path

    env_path = Path.home() / ".best-engine-ai-helper" / "env.sh"
    if not env_path.exists():
        _emit_err("env.sh not found. Run `best-engine-ai-helper pull` first.")
        return 1

    _emit(env_path.read_text(encoding="utf-8"))
    return 0


def _handle_activity(ns: argparse.Namespace) -> int:
    """
    Summarize the local activity/cost ledger (calls, cost, by user/model, errors).

    Named "activity", not "usage": this repo already has a plural `usages`
    command group (named task profiles like text2sql) -- "usage" would be a
    one-letter, easily-mistyped collision with a completely different concept.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed CLI arguments: `format`.

    Returns
    -------
    int
        Process exit code (always 0).
    """
    ledger = _observe.active_ledger() or _observe.Ledger()
    summary = ledger.summary()

    if ns.format == "json":
        _emit(json.dumps(summary, indent=2))
        return 0

    if summary["total_calls"] == 0:
        _emit("No calls recorded yet.")
        return 0

    cost = summary["total_cost_usd"]
    cost_str = f"${cost:.4f}" if cost is not None else "unknown (unpriced model in the mix)"
    _emit(f"Total calls: {summary['total_calls']}   "
          f"Total cost: {cost_str}   "
          f"Error rate: {summary['error_rate']:.1%}")
    _emit("")
    _emit("By user:")
    _emit(_fmt_table(summary["by_user"], ["user", "calls", "cost_usd"]))
    _emit("")
    _emit("By model:")
    _emit(_fmt_table(summary["by_model"], ["model", "calls", "cost_usd"]))
    if summary["recent_errors"]:
        _emit("")
        _emit("Recent errors:")
        _emit(_fmt_table(summary["recent_errors"], ["ts", "user", "model", "error"]))
    return 0


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """
    Assemble the top-level `best-engine-ai-helper-argparse` parser.

    Returns
    -------
    argparse.ArgumentParser
        Fully wired parser with every subcommand attached, mirroring `cli.py`.
    """
    parser = argparse.ArgumentParser(
        prog="best-engine-ai-helper-argparse",
        description="Pick and pull the best local LLM/VLM for the current hardware.",
    )
    try:
        from importlib.metadata import version as _pkg_version

        parser.add_argument(
            "--version", action="version",
            version=f"%(prog)s {_pkg_version('best-engine-ai-helper')}",
        )
    except Exception:  # pragma: no cover — never fatal
        pass
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase log verbosity: -v shows info, -vv also shows debug.",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("detect", help="Print detected hardware as JSON.").set_defaults(
        func=_handle_detect
    )

    p = sub.add_parser("recommend", help="Print ranked model candidates for this hardware.")
    p.add_argument("--kind", choices=["llm", "vlm", "both"], default="both",
                    help="Model type to recommend (default: both).")
    p.add_argument("--headroom", type=float, default=0.85,
                    help="Safety headroom fraction (0-1) applied to available memory "
                         "(default: 0.85).")
    p.add_argument("--application", choices=_VALID_APPLICATIONS, default=None,
                    help="Target use-case; selects the benchmark axis. Omit for the "
                         "default kind-based rule.")
    p.add_argument("--min-tps", type=float, default=_score.COMFORT_TPS,
                    help=f"Comfort throughput floor in tokens/s (default: {_score.COMFORT_TPS}).")
    p.add_argument("--live", action="store_true",
                    help="Also weigh CURRENT server load (free RAM, CPU/GPU/disk usage, "
                         "already-running engines), not just theoretical capacity. Off by "
                         "default: adds a live probe (~0.1-0.5s) and makes the result depend "
                         "on this exact moment rather than the hardware alone.")
    p.set_defaults(func=_handle_recommend)

    p = sub.add_parser("resolve", help="Resolve a usage brief into a machine-specific engine file.")
    p.add_argument("--brief", required=True, help="Path to the committed usage brief.")
    p.add_argument("--out", default=None,
                    help="Where to write the engine file "
                         "(default: llm.engine.yaml beside the brief).")
    p.add_argument("--backend", choices=["auto", "ollama", "vllm"], default="auto",
                    help="Serving backend (default: auto).")
    p.add_argument("--endpoint", default=None, help="Override the server base URL.")
    p.set_defaults(func=_handle_resolve)

    p = sub.add_parser("report", help="Recommend the best engine(s) for a task; emit MD + JSON.")
    p.add_argument("--task", default=None, help="Free-text task description.")
    p.add_argument("--headroom", type=float, default=0.85,
                    help="Memory safety fraction on top of the accelerator cap (default: 0.85).")
    p.add_argument("--out", default=None, help="Path stem to write <stem>.md and <stem>.json.")
    p.add_argument("--format", dest="format", choices=["md", "json"], default="md",
                    help="What to print to stdout (default: md).")
    p.add_argument("--live", action="store_true",
                    help="Also weigh CURRENT server load (free RAM, CPU/GPU/disk usage, "
                         "already-running engines), not just theoretical capacity. Off by "
                         "default: adds a live probe (~0.1-0.5s) and makes the result depend "
                         "on this exact moment rather than the hardware alone.")
    p.set_defaults(func=_handle_report)

    _add_usages_group(sub)
    _add_catalog_group(sub)
    _add_hardware_group(sub)

    p = sub.add_parser("pull", help="Pull the best model and run Ralph validation gates.")
    p.add_argument("--keep-failed", action="store_true",
                    help="Do not remove failed models after a gate failure.")
    p.add_argument("--vllm", action="store_true",
                    help="Print the vLLM serve command instead of pulling.")
    p.add_argument("--application", choices=_VALID_APPLICATIONS, default=None,
                    help="Target use-case; biases model selection.")
    p.add_argument("--min-tps", type=float, default=_score.COMFORT_TPS,
                    help=f"Comfort throughput floor in tokens/s (default: {_score.COMFORT_TPS}).")
    p.set_defaults(func=_handle_pull)

    sub.add_parser(
        "validate", help="Run Ralph gates on the already-configured model."
    ).set_defaults(func=_handle_validate)

    p = sub.add_parser("gui", help="Launch the minimal browser GUI.")
    p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    p.set_defaults(func=_handle_gui)

    sub.add_parser("env", help="Print the env block for ~/.zshrc or sourcing.").set_defaults(
        func=_handle_env
    )

    p = sub.add_parser(
        "activity", help="Summarize the local activity/cost ledger."
    )
    p.add_argument("--format", dest="format", choices=["table", "json"], default="table",
                    help="What to print to stdout (default: table).")
    p.set_defaults(func=_handle_activity)

    return parser


def _add_usages_group(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Attach the `usages` subcommand group (list / show / resolve).

    Parameters
    ----------
    sub : argparse._SubParsersAction[argparse.ArgumentParser]
        The top-level subparser action to register this group on.
    """
    g = sub.add_parser("usages", help="Browse and resolve the sev7n usage catalog.")
    s = g.add_subparsers(dest="action", metavar="ACTION")
    s.required = True

    s.add_parser("list", help="List every usage profile and family.").set_defaults(
        func=_handle_usages_list
    )

    p = s.add_parser("show", help="Show one profile's needs — no model.")
    p.add_argument("name", help="Usage profile name.")
    p.set_defaults(func=_handle_usages_show)

    p = s.add_parser("resolve", help="Resolve a profile (or --family) into this machine's model.")
    p.add_argument("name", nargs="?", default=None, help="Usage profile name.")
    p.add_argument("--family", dest="family", default=None,
                    help="Resolve a whole family (F1/F2/F3) instead of a profile.")
    p.add_argument("--backend", choices=["auto", "ollama", "vllm"], default="auto",
                    help="Serving backend (default: auto).")
    p.add_argument("--endpoint", default=None, help="Override the server base URL.")
    p.add_argument("--out", default=None, help="Write the generated engine file here.")
    p.set_defaults(func=_handle_usages_resolve)


def _add_catalog_group(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Attach the `catalog` subcommand group (show / update).

    Parameters
    ----------
    sub : argparse._SubParsersAction[argparse.ArgumentParser]
        The top-level subparser action to register this group on.
    """
    g = sub.add_parser("catalog", help="Manage the model catalog.")
    s = g.add_subparsers(dest="action", metavar="ACTION")
    s.required = True

    s.add_parser("show", help="Print the merged model catalog as a table.").set_defaults(
        func=_handle_catalog_show
    )

    p = s.add_parser("update", help="Refresh the catalog cache from the ApXML directory.")
    p.add_argument("--limit", type=int, default=None, help="Fetch at most N models.")
    p.add_argument("--timeout", type=float, default=30.0,
                    help="Per-request network timeout in seconds (default: 30.0).")
    p.set_defaults(func=_handle_catalog_update)


def _add_hardware_group(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Attach the `hardware` subcommand group (show / update).

    Parameters
    ----------
    sub : argparse._SubParsersAction[argparse.ArgumentParser]
        The top-level subparser action to register this group on.
    """
    g = sub.add_parser("hardware", help="Manage the hardware chip table.")
    s = g.add_subparsers(dest="action", metavar="ACTION")
    s.required = True

    s.add_parser("show", help="Print the merged hardware chip table.").set_defaults(
        func=_handle_hardware_show
    )
    s.add_parser(
        "update", help="Record this machine's chip and memory into the cache."
    ).set_defaults(func=_handle_hardware_update)


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point invoked by `best-engine-ai-helper-argparse`.

    Parameters
    ----------
    argv : sequence of str, optional
        Arguments to parse; defaults to `sys.argv[1:]`.

    Returns
    -------
    int
        Process exit code.
    """
    parser = build_parser()
    ns = parser.parse_args(argv)

    # Configure logging identically to cli.py's click group: -v/-vv raise the
    # level, logs go to stderr so stdout (JSON, tables) stays clean/pipeable.
    level = {0: logging.WARNING, 1: logging.INFO}.get(ns.verbose, logging.DEBUG)
    osh.init_logging(level=level, stdout=False)
    # Local-only activity/cost ledger (see observe.py and the `usage` command);
    # opt out with BEST_ENGINE_NO_LEDGER=1.
    if not os.environ.get("BEST_ENGINE_NO_LEDGER"):
        _observe.enable()

    return cast(int, ns.func(ns))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
