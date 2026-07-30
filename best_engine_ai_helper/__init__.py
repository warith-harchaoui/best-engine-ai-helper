"""
best_engine_ai_helper — pick the best local LLM/VLM for the current hardware.

Public API (importable without invoking the CLI):

  from best_engine_ai_helper.detect import platform_name, chip_vendor, available_memory
  from best_engine_ai_helper.catalog import load_catalog, estimate_ram
  from best_engine_ai_helper.hardware import load_hardware, lookup_chip
  from best_engine_ai_helper.score import select, rank, effective_budget

The CLI entry point is ``best-engine-ai-helper`` (see cli.py). Importing this
package does not trigger any CLI parsing or subprocess calls.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

from .catalog import estimate_ram, load_catalog
from .detect import (
    available_memory,
    chip_name,
    chip_vendor,
    compute_profile,
    platform_name,
)
from .hardware import load_hardware, lookup_chip

# Export the engine-recommendation function under a distinct name so it does
# not shadow the ``recommend`` submodule on attribute access.
from .recommend import parse_task, to_markdown, write_report
from .recommend import recommend as recommend_engines
from .score import effective_budget, estimated_tokens_per_second, rank, select

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
    "recommend_engines",
    "parse_task",
    "to_markdown",
    "write_report",
]

__version__ = "0.2.0"
__author__ = "Warith Harchaoui"
__email__ = "warith.harchaoui@gmail.com"
