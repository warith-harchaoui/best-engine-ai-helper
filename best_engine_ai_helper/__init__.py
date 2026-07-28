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
from .detect import available_memory, chip_vendor, platform_name
from .hardware import load_hardware, lookup_chip
from .score import effective_budget, rank, select

__all__ = [
    "platform_name",
    "chip_vendor",
    "available_memory",
    "load_catalog",
    "estimate_ram",
    "load_hardware",
    "lookup_chip",
    "select",
    "rank",
    "effective_budget",
]

__version__ = "0.1.0"
__author__ = "Warith Harchaoui"
__email__ = "warith.harchaoui@gmail.com"
