"""
best_engine_ai_helper — pick the best local large language model (LLM) or
vision-language model (VLM) for the current hardware.

Public API (importable without invoking the CLI):

  from best_engine_ai_helper.detect import platform_name, chip_vendor, available_memory
  from best_engine_ai_helper.catalog import load_catalog, estimate_ram
  from best_engine_ai_helper.hardware import load_hardware, lookup_chip
  from best_engine_ai_helper.score import select, rank, effective_budget
  from best_engine_ai_helper import airllm_decide, airllm_plan  # layer streaming
  from best_engine_ai_helper import airllm_compare  # streamed vs native, timed
  from best_engine_ai_helper import imagine_plan, imagine_generate  # text-to-image

An OpenAI-compatible HTTP surface sits on the same app as the GUI and the MCP
endpoint (``best-engine-ai-helper serve``): point any OpenAI SDK at
``/v1`` and ask for the model named ``best``. See
:mod:`best_engine_ai_helper.openai_api`.
  from best_engine_ai_helper import text_model, vision_model  # cheap tag resolvers

The CLI entry point is ``best-engine-ai-helper`` (see cli.py). Importing this
package does not trigger any CLI parsing or subprocess calls.

Downstream suite packages that just need "which model tag do I use?" should call
:func:`text_model` / :func:`vision_model` — they resolve an env override, then
the selection persisted by ``pull``, then a safe default, without ever probing
hardware, so they are cheap and deterministic (CI-safe).

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
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
    disk_profile,
    measure_disk_read_gbs,
    platform_name,
    storage_class,
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

# Text-to-image: the third kind of model this package chooses. Same shape as
# everything else here — a footprint against this machine's budget, a time
# estimate in the unit a human waits in, and a catalogue entry rather than a
# hardcoded name.
from .imagine import COMFORT_SECONDS_PER_IMAGE, seconds_per_image
from .imagine import available as imagine_available
from .imagine import footprint_gb as image_footprint_gb
from .imagine import generate as imagine_generate
from .imagine import load as imagine_load
from .imagine import pick as imagine_pick
from .imagine import plan as imagine_plan
from .imagine import rank as imagine_rank

# Layer streaming (airllm): run a model that does NOT fit in memory by reading
# one layer shard at a time off disk. Exported under `airllm_*` names because
# that is the word a caller is looking for; the module is `offload` because the
# idea is bigger than the one package implementing it.
from .offload import COMFORT_TPS_STREAMING
from .offload import available as airllm_available
from .offload import budget_gb as streaming_budget_gb
from .offload import compare as airllm_compare
from .offload import decide as airllm_decide
from .offload import disk_required_gb as airllm_disk_required_gb
from .offload import estimated_tokens_per_second as airllm_tokens_per_second
from .offload import footprint_gb as airllm_footprint_gb
from .offload import generate as airllm_generate
from .offload import generation_time as airllm_generation_time
from .offload import load as airllm_load
from .offload import pick as airllm_pick
from .offload import plan as airllm_plan
from .offload import rank as airllm_rank
from .offload import runtime as airllm_runtime
from .offload import seconds_per_pass as airllm_seconds_per_pass

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
    usable_pool_gb,
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
    "disk_profile",
    "storage_class",
    "measure_disk_read_gbs",
    "load_catalog",
    "estimate_ram",
    "load_hardware",
    "lookup_chip",
    "select",
    "rank",
    "effective_budget",
    "usable_pool_gb",
    "estimated_tokens_per_second",
    "model_footprint_gb",
    "MAX_HEADROOM",
    # layer streaming (airllm)
    "airllm_available",
    "airllm_runtime",
    "airllm_decide",
    "airllm_footprint_gb",
    "airllm_tokens_per_second",
    "airllm_seconds_per_pass",
    "airllm_generation_time",
    "airllm_compare",
    "airllm_disk_required_gb",
    "airllm_plan",
    "airllm_rank",
    "airllm_pick",
    "airllm_load",
    "airllm_generate",
    "streaming_budget_gb",
    "COMFORT_TPS_STREAMING",
    # text-to-image
    "imagine_available",
    "imagine_plan",
    "imagine_rank",
    "imagine_pick",
    "imagine_load",
    "imagine_generate",
    "image_footprint_gb",
    "seconds_per_image",
    "COMFORT_SECONDS_PER_IMAGE",
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

__version__ = "1.9.0"
__author__ = "Warith Harchaoui"
__email__ = "warithmetics@deraison.ai"
