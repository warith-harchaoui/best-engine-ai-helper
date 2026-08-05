"""
best_engine_ai_helper — pick the best local LLM/VLM for the current hardware.

Public API (importable without invoking the CLI):

  from best_engine_ai_helper.detect import platform_name, chip_vendor, available_memory
  from best_engine_ai_helper.catalog import load_catalog, estimate_ram
  from best_engine_ai_helper.hardware import load_hardware, lookup_chip
  from best_engine_ai_helper.score import select, rank, effective_budget
  from best_engine_ai_helper import text_model, vision_model  # cheap tag resolvers

The CLI entry point is ``best-engine-ai-helper`` (see cli.py). Importing this
package does not trigger any CLI parsing or subprocess calls.

Downstream suite packages that just need "which model tag do I use?" should call
:func:`text_model` / :func:`vision_model` — they resolve an env override, then
the selection persisted by ``pull``, then a safe default, without ever probing
hardware, so they are cheap and deterministic (CI-safe).

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from .catalog import estimate_ram, load_catalog

# Cheap, deterministic model-tag resolution (env -> persisted config -> default);
# the entry point downstream packages call to answer "which model do I use?".
from .config import (
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    load_config,
    resolved_models,
    text_model,
    vision_model,
)
from .detect import (
    available_memory,
    chip_name,
    chip_vendor,
    compute_profile,
    platform_name,
)

# The brief -> engine resolution flow: turn a repo's committed usage brief into a
# gitignored, machine-specific engine descriptor (backend + model per kind), and
# read it back. ``default_backend`` encodes the Ollama-vs-vLLM rule.
from .engine import (
    BRIEF_NAME,
    ENGINE_NAME,
    default_backend,
    ensure,
    load_engine,
    model_for,
    resolve,
    write_engine,
)
from .hardware import load_hardware, lookup_chip

# Export the engine-recommendation function under a distinct name so it does
# not shadow the ``recommend`` submodule on attribute access.
from .recommend import parse_task, to_markdown, write_report
from .recommend import recommend as recommend_engines
from .score import (
    MAX_HEADROOM,
    effective_budget,
    estimated_tokens_per_second,
    model_footprint_gb,
    rank,
    select,
)

# The usage catalog: named sev7n workloads (text2sql, rag-answer, embeddings, …)
# grouped into families, each stating only its NEEDS. resolve_usage / resolve_family
# let a caller request "the model for profile X" — best-engine chooses it.
from .usages import (
    family_brief,
    get_family,
    get_usage,
    list_families,
    list_usages,
    load_families,
    load_usages,
    resolve_family,
    resolve_usage,
    usage_brief,
)

__all__ = [
    "platform_name",
    "chip_vendor",
    "chip_name",
    "available_memory",
    "compute_profile",
    "load_catalog",
    "estimate_ram",
    "load_hardware",
    "lookup_chip",
    "select",
    "rank",
    "effective_budget",
    "estimated_tokens_per_second",
    "model_footprint_gb",
    "MAX_HEADROOM",
    "recommend_engines",
    "parse_task",
    "to_markdown",
    "write_report",
    # brief -> engine resolution
    "resolve",
    "ensure",
    "write_engine",
    "load_engine",
    "model_for",
    "default_backend",
    "BRIEF_NAME",
    "ENGINE_NAME",
    "text_model",
    "vision_model",
    "resolved_models",
    "load_config",
    "DEFAULT_TEXT_MODEL",
    "DEFAULT_VISION_MODEL",
    # usage catalog (task profiles + families)
    "list_usages",
    "list_families",
    "get_usage",
    "get_family",
    "load_usages",
    "load_families",
    "usage_brief",
    "family_brief",
    "resolve_usage",
    "resolve_family",
]

__version__ = "1.0.0"
__author__ = "Warith Harchaoui"
__email__ = "warith.harchaoui@deraison.ai"
