"""
score — select the best model for the current hardware.

Given the detected memory pool and the merged catalog, this module picks the
highest-scoring model that fits within a safety headroom. The algorithm is
intentionally simple: filter, then sort by benchmark score, then take the max.

Memory priority mirrors what Ollama uses at runtime:
  unified_gb (Apple Silicon) > vram_gb (discrete GPU) > ram_gb * 0.5 (CPU)

The 0.5 factor for CPU RAM is conservative; a model loader competes with the
OS, background daemons, and the inference server itself for RAM.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import math
from typing import Any, Literal

import os_helper as osh

# Maps an application keyword to an ordered list of benchmark keys to try.
# The first non-null value found in a catalog entry is used as the score.
#
# Position in the list IS the axis's weight, which is where the Arena axes earn
# their placement. An Arena rating comes from humans comparing two anonymous
# answers and preferring one, so it measures conversational preference
# precisely and almost nothing else. For `chat` that is the best public signal
# there is, and it leads. For `code` it is a weak proxy -- a model that writes
# agreeable prose outranks one that emits a schema-valid query, because nobody
# voting was asked to run the query -- so it sits behind the code axis and the
# generalist axis, as a last resort rather than a tiebreak.
#
# `arena_code` is the Arena's own coding board: still a preference vote, but
# cast on coding prompts, so it outranks the undifferentiated `arena` for code
# while still deferring to an execution-based benchmark like HumanEval+.
_APP_BENCH_PRIORITY: dict[str, list[str]] = {
    "code": ["code", "general", "arena_code", "arena"],
    "math": ["math", "general", "arena"],
    "ocr": ["ocr", "vision", "arena_vision", "general"],
    "vision": ["vision", "arena_vision", "general"],
    "chat": ["arena", "general"],
    "generalist": ["general", "arena"],
}


# Fraction of an Apple Silicon unified-memory pool the GPU (Metal) may use
# before allocations spill to CPU and inference slows sharply. macOS sets this
# recommendedMaxWorkingSetSize at ~66% for pools of 36 GB or less and ~75%
# above that. Treating the *whole* pool as usable (the old behaviour) over-
# promises: it steers you to a model that technically loads but leaves no room
# for the OS, your own application, or KV-cache growth. Source: apple-specs /
# Metal working-set docs; see references/CODING.md.
_APPLE_GPU_FRACTION_SMALL = 0.66
_APPLE_GPU_FRACTION_LARGE = 0.75
_APPLE_SMALL_POOL_GB = 36.0

# Discrete-GPU VRAM is almost entirely usable; leave a small margin for the
# driver context. CPU-only inference is bounded by system RAM, but you never
# want to hand all of it to a model, so treat half as the working budget.
_DISCRETE_VRAM_FRACTION = 0.92
_CPU_RAM_FRACTION = 0.5

# Real-world decode throughput as a fraction of the memory-bandwidth ceiling.
# Token generation reads the active model once per token, so the ceiling is
# bandwidth / model-bytes; attention over the KV cache, kernel launches, and
# sampling pull the achieved rate down to roughly 50-80%.
#
# The achieved fraction is NOT the same across backends, even on identical
# hardware (confirmed on Ubuntu + discrete GPU: Ollama and vLLM do not decode
# at the same speed for the same model). Two per-backend figures, both
# deliberately conservative:
#
# - Ollama (llama.cpp/GGML runtime): 0.65, a mid-conservative point across
#   Apple Metal and CUDA. Source: llama.cpp / MLX community benchmarks; see
#   references/CODING.md.
# - vLLM (CUDA/ROCm only — see engine.default_backend): 0.75. PagedAttention
#   avoids the KV-cache fragmentation and per-token allocation overhead that
#   pulls llama.cpp's achieved rate down, and vLLM's CUDA-graph capture
#   removes most Python/kernel-launch overhead from the decode step, so a
#   single-stream vLLM decode tracks closer to the bandwidth ceiling. Source:
#   vLLM project benchmarks (PagedAttention paper, vLLM blog); see
#   references/CODING.md. This figure describes single-request decode, not
#   vLLM's much larger *aggregate* throughput advantage under concurrent
#   batched requests, which this single-model estimator does not model.
_DECODE_EFFICIENCY = 0.65
_VLLM_DECODE_EFFICIENCY = 0.75

_DECODE_EFFICIENCY_BY_BACKEND: dict[str, float] = {
    "ollama": _DECODE_EFFICIENCY,
    "vllm": _VLLM_DECODE_EFFICIENCY,
}

# Comfort floor: a model can fit in memory yet decode too slowly to be usable
# interactively. This is the minimum estimated decode rate (tokens/s) below which
# a model is flagged "not comfortable" and is NOT auto-recommended even though it
# fits — the missing half of "fits your hardware" (fits in memory AND runs at a
# tolerable speed). 15 tok/s is a bit faster than a brisk reader, roughly the
# point below which local chat starts to feel like waiting. On an M2 Max
# (400 GB/s) it draws the line just under the 14B class, exactly where a 32B
# model drops to ~7 tok/s. Source: MLX / llama.cpp community UX benchmarks.
COMFORT_TPS: float = 15.0

#: Benchmark axis an embedding model is judged on. Embedders are not scored on
#: the general/vision axes the other kinds use, so anything ranking them has to
#: reach for this one by name.
EMBED_SCORE_KEY = "mteb"

# Width of the "same quality, really" band on the 0-100 benchmark scale. Two
# models whose scores land inside the same band are treated as indistinguishable
# on quality, which lets a cheaper tiebreak decide between them -- in practice,
# preferring a model already on disk over a 20 GB download.
#
# Deliberately narrow. Benchmark scores are not precise to the point, but they
# are not noise either, and a wide band would quietly let "already pulled" beat
# a genuinely better model. Two points is about the width of the disagreement
# between two leaderboards scoring the same model, which is the error bar this
# is meant to absorb.
QUALITY_TIE_BAND: float = 2.0

# Live-load derating: knocked off the budget on TOP of headroom when the
# machine is demonstrably busy right now (see `detect.server_load`), so two
# machines with identical total capacity do not get identical recommendations
# when one is idle and the other is already saturated. Deliberately coarse —
# a single threshold each, not a continuous curve — because the live values
# are a snapshot, not a stable input worth over-fitting.
_CPU_BUSY_PERCENT: float = 85.0
_CPU_BUSY_DERATE: float = 0.85
_DISK_LOW_GB: float = 10.0
_DISK_LOW_DERATE: float = 0.85

# Hard ceiling on the safety headroom. Headroom is the fraction of the
# accelerator's *usable* pool a model may occupy; anything above 0.5 leaves too
# little room for the OS, the caller's own workload, and KV-cache growth as the
# context fills, and steers the picker toward models that technically load but
# feel starved in practice. Any caller-supplied headroom is clamped down to this;
# it is never exceeded. This is the primary "don't be greedy" guard.
MAX_HEADROOM: float = 0.5

# Bytes per parameter for an unquantised (FP16/BF16) weight — what vLLM loads by
# default from a HuggingFace checkpoint, in contrast to Ollama's Q4 GGUF tags.
_FP16_BYTES_PER_PARAM: float = 2.0

# Multiplier over raw FP16 weights to account for the KV cache, activations, and
# CUDA-graph/runtime buffers vLLM allocates alongside the weights. Deliberately
# conservative: a model that only *just* fits its weights will OOM once a real
# context fills the KV cache.
_VLLM_OVERHEAD: float = 1.15


def model_footprint_gb(entry: dict[str, Any], backend: str = "ollama") -> float:
    """
    Estimate a model's peak inference memory (GB) on a given serving backend.

    The catalog's ``ram_gb`` is an **Ollama Q4** estimate. vLLM instead loads the
    full FP16/BF16 HuggingFace weights (~2 bytes/param) plus KV cache and runtime
    buffers, so the same model is markedly heavier there. Sizing a vLLM pick
    against ``ram_gb`` would over-promise and pick a model that will not actually
    fit — the "unrealistic recommendation" this guards against.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; uses ``ram_gb`` (Ollama) or ``size_b`` (vLLM).
    backend : {'ollama', 'vllm'}
        Serving backend the footprint is estimated for. Unknown values are
        treated as ``'ollama'`` (the conservative catalog figure).

    Returns
    -------
    float
        Estimated peak memory in GB.
    """
    ram = float(entry.get("ram_gb", 0) or 0)
    size_b = float(entry.get("size_b", 0) or 0)

    # An entry carrying neither figure cannot be sized, and saying so is the
    # only safe answer. It used to return 0.0 -- absent read as a legitimate
    # zero, the defect family `scripts/measure_absent_vs_zero.py` exists to
    # hunt, and this very line was on its survivor list. The hand review
    # cleared it on the grounds that "the fallback equals the value it would
    # swallow"; here it does not. Zero GB does not mean "unknown", it means
    # "fits on any machine", so a catalog entry with no size at all beat every
    # real model on fit AND on leanness, and was recommended on a machine where
    # nothing real fit. `ollama_library.to_specs` already states the rule this
    # restores: an entry whose size is unknown cannot be sized.
    if ram <= 0 and size_b <= 0:
        return math.inf

    if backend != "vllm":
        return ram if ram > 0 else math.inf
    if size_b <= 0:
        # No parameter count to size FP16 weights from: fall back to the Ollama
        # figure rather than pretend it is free.
        return ram
    fp16 = size_b * _FP16_BYTES_PER_PARAM * _VLLM_OVERHEAD
    # Never report a vLLM footprint smaller than the Q4 estimate — FP16 is always
    # heavier, so the Ollama number is a hard floor.
    return round(max(fp16, ram), 3)


def is_sizeable(entry: dict[str, Any], backend: str = "ollama") -> bool:
    """
    True when `entry` carries enough information to be sized on `backend`.

    A model that cannot be sized is not a candidate: the whole job here is
    comparing a footprint against this machine's memory, and an entry that
    cannot supply one has nothing to compare. Separate from
    :func:`model_footprint_gb` so the call sites that *filter* read as filters
    rather than as float comparisons against infinity.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    backend : {'ollama', 'vllm'}
        Serving backend the footprint would be estimated for.

    Returns
    -------
    bool
        False when neither ``ram_gb`` nor ``size_b`` yields a usable footprint.
    """
    return math.isfinite(model_footprint_gb(entry, backend))


def sizeable_only(
    entries: list[dict[str, Any]], backend: str = "ollama", where: str = "selection"
) -> list[dict[str, Any]]:
    """
    Drop entries that cannot be sized, saying how many and from where.

    Announced rather than silent, by the same rule the backend gate follows: a
    pool quietly shrinking is how a caller concludes their catalog was
    considered when half of it was skipped.

    Parameters
    ----------
    entries : list of dict
        Candidate catalog entries.
    backend : {'ollama', 'vllm'}
        Serving backend the footprint would be estimated for.
    where : str
        Caller name, used in the warning so the message names the decision the
        entries were dropped from.

    Returns
    -------
    list of dict
        Only the entries that can be sized.
    """
    kept = [e for e in entries if is_sizeable(e, backend)]
    dropped = len(entries) - len(kept)
    if dropped:
        subject = "entry carries" if dropped == 1 else "entries carry"
        osh.warning(
            f"{dropped} catalog {subject} neither ram_gb nor size_b and cannot "
            f"be sized; excluded from {where}. An entry with no size would "
            "otherwise fit every machine."
        )
    return kept


def effective_budget(
    hw: dict[str, float | None],
    headroom: float = MAX_HEADROOM,
    load: dict[str, Any] | None = None,
) -> float:
    """
    Compute the memory budget (GB) a model may occupy at run time.

    The budget is the accelerator's usable memory pool, scaled by an extra
    ``headroom`` margin left for the operating system, your own application, and
    KV-cache growth as context fills. On Apple Silicon the usable pool is *not*
    the whole unified memory: Metal caps GPU allocations at about 66% of the
    pool at or below 36 GB and about 75% above it, beyond which inference spills
    to CPU. Compare a catalog entry's ``ram_gb`` (already a peak-inference
    estimate, weights plus a moderate KV cache) against this budget.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`. Expected keys:
        ``unified_gb``, ``vram_gb``, ``ram_gb``.
    headroom : float
        Extra safety fraction applied on top of the accelerator cap, reserving
        room for the OS, the caller's workload, and KV growth. Defaults to
        :data:`MAX_HEADROOM` (0.5) and is **clamped** down to it — a larger value
        is never honoured, to keep picks realistic.
    load : dict or None
        Live server state from :func:`detect.server_load` (``available_ram_gb``,
        ``cpu_percent``, ``disk_free_gb``, ...). When given, the theoretical
        accelerator budget is additionally capped at what is ACTUALLY free
        right now (another process, or an already-running engine, holds memory
        the static hardware totals in ``hw`` know nothing about), and further
        derated when the CPU is already saturated or the disk is nearly full.
        ``None`` (the default) reproduces the pre-existing, load-blind
        behaviour exactly.

    Returns
    -------
    float
        Effective memory budget in GB.

    Examples
    --------
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0})
    36.0
    >>> effective_budget({'unified_gb': None, 'vram_gb': 24.0, 'ram_gb': 64.0})
    11.04
    >>> # headroom above the 0.5 ceiling is clamped, not honoured
    >>> effective_budget({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}, headroom=0.85)
    36.0
    >>> # a busy machine gets a smaller budget than an idle one with the same hardware
    >>> hw = {'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}
    >>> effective_budget(hw, load={'available_ram_gb': 10.0})
    10.0
    """
    # Clamp to the hard ceiling: an over-generous headroom is the main source of
    # unrealistically large picks, so it is silently reduced, never exceeded.
    headroom = min(headroom, MAX_HEADROOM)
    if hw.get("unified_gb"):
        pool = float(hw["unified_gb"])  # type: ignore[arg-type]
        cap = (
            _APPLE_GPU_FRACTION_LARGE if pool > _APPLE_SMALL_POOL_GB else _APPLE_GPU_FRACTION_SMALL
        )
        available = pool * cap
    elif hw.get("vram_gb"):
        available = float(hw["vram_gb"]) * _DISCRETE_VRAM_FRACTION  # type: ignore[arg-type]
    else:
        available = float(hw.get("ram_gb") or 8.0) * _CPU_RAM_FRACTION

    budget = available * headroom

    if load:
        # Never let the theoretical accelerator cap exceed what is actually
        # free right now. Exact for Apple Silicon and the CPU-only branch
        # (their pool IS system RAM); a conservative-but-not-exact cap for a
        # discrete GPU, since VRAM and system RAM are separate pools and this
        # only catches the "system RAM itself is also exhausted" case.
        live_ram = load.get("available_ram_gb")
        if live_ram is not None:
            budget = min(budget, float(live_ram))

        # A saturated CPU or a nearly-full disk make this a bad moment to load
        # one more model regardless of memory headroom — derate further so the
        # pick reflects that, rather than only ever reacting to memory.
        cpu_percent = load.get("cpu_percent")
        if cpu_percent is not None and cpu_percent >= _CPU_BUSY_PERCENT:
            budget *= _CPU_BUSY_DERATE
        disk_free_gb = load.get("disk_free_gb")
        if disk_free_gb is not None and disk_free_gb <= _DISK_LOW_GB:
            budget *= _DISK_LOW_DERATE

    return round(budget, 3)


def estimated_tokens_per_second(
    entry: dict[str, Any],
    bandwidth_gbs: float | None,
    backend: str = "ollama",
    calibrated: bool = True,
) -> float | None:
    """
    Estimate local decode throughput (tokens/s) for a model on this machine.

    Token generation is memory-bandwidth bound: each new token requires reading
    the model's active weights from memory once, so the ceiling is
    ``bandwidth / model_bytes``. The estimate derates that ceiling by a
    backend-specific decode efficiency (see
    :data:`_DECODE_EFFICIENCY_BY_BACKEND`) to reflect KV-cache reads, kernel
    overhead, and sampling. It describes steady-state generation, not the
    compute-bound prefill of a long prompt.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; its :func:`model_footprint_gb` is the active-model size.
    bandwidth_gbs : float or None
        Memory bandwidth in GB/s from :func:`detect.compute_profile`. When None
        (unknown hardware, e.g. an unrecognised discrete-GPU model) the
        estimate is not computable and None is returned.
    backend : {'ollama', 'vllm'}
        Serving backend. Affects both the size proxy (heavier FP16 weights
        under vLLM decode more slowly than the Q4 Ollama figure) AND the
        decode efficiency (vLLM's PagedAttention + CUDA-graph decode tracks
        closer to the bandwidth ceiling than llama.cpp's — confirmed to
        differ on identical Ubuntu + discrete-GPU hardware, not just a
        cross-platform artifact).

    calibrated : bool
        Apply this machine's measured correction factor when one exists (see
        :func:`throughput.calibration_factor`). On by default: an estimate that
        has been corrected against a real measurement on this hardware is
        strictly better than one that has not. Pass False to see the raw
        bandwidth model, which is what the calibration itself is derived
        against -- leaving it True there would feed the correction back into
        its own input.

    Returns
    -------
    float or None
        Estimated tokens/s, rounded to one decimal, or None when bandwidth or
        model size is unavailable.
    """
    if not bandwidth_gbs:
        return None
    ram = model_footprint_gb(entry, backend)
    # `<= 0` no longer covers it: an entry that cannot be sized now reports an
    # infinite footprint, and dividing by that yields a confident 0.0 tok/s
    # where the honest answer is "no estimate". Same distinction as the
    # footprint itself — unknown is not a very small number.
    if ram <= 0 or not math.isfinite(ram):
        return None
    efficiency = _DECODE_EFFICIENCY_BY_BACKEND.get(backend, _DECODE_EFFICIENCY)
    raw = bandwidth_gbs / ram * efficiency

    if calibrated:
        # `_DECODE_EFFICIENCY` is an average over other people's hardware, so on
        # any one machine it carries a systematic bias. The bias belongs to the
        # machine much more than to the model, so correcting by it transfers:
        # having measured one model, every other estimate on this machine gets
        # closer to the truth, including for models that were never pulled.
        #
        # Tested rather than asserted (scripts/validate_calibration.py): on an
        # Apple M2 Max the correction helped in every direction tried, cutting
        # the error from 64-118% down to 17-25%. Closer, not close -- which is
        # why a measurement, where one exists, is preferred to this.
        from . import throughput as _throughput

        calibration = _throughput.calibration_factor()
        if calibration is not None:
            factor, samples = calibration
            osh.debug(
                f"Applying measured throughput calibration {factor} "
                f"({samples} sample(s) on this machine) to the estimate for "
                f"{entry.get('id', '?')}."
            )
            raw *= factor

    return round(raw, 1)


def _benchmark_score(
    entry: dict[str, Any],
    kind: Literal["llm", "vlm"],
    application: str | None = None,
) -> float:
    """
    Extract the relevant benchmark score for ranking.

    When *application* is given it is looked up in ``_APP_BENCH_PRIORITY`` and
    the first non-null benchmark in that priority list is used.  When absent
    (or unknown) the legacy rule applies: vision score for VLMs, general for
    LLMs.  Falls back to 0 when no matching score is found.

    Parameters
    ----------
    entry : dict[str, Any]
        A catalog entry dict.
    kind : {'llm', 'vlm'}
        The inference kind being selected.
    application : str or None
        Optional use-case keyword (e.g. ``"code"``, ``"math"``, ``"ocr"``).
        ``None`` or ``"generalist"`` use the default kind-based rule.

    Returns
    -------
    float
        Benchmark score, or 0.0 if absent.
    """
    benchmarks = entry.get("benchmarks") or {}

    if application:
        priority = _APP_BENCH_PRIORITY.get(application.lower())
        if priority:
            for key in priority:
                val = benchmarks.get(key)
                if val is not None:
                    return float(val)
            return 0.0

    # Default: vision axis for VLMs, general for LLMs. Explicit None checks
    # (not `or`) so a legitimately-recorded score of 0.0 is honoured rather
    # than silently treated as missing and replaced by a fallback axis.
    if kind == "vlm":
        vision = benchmarks.get("vision")
        score = vision if vision is not None else benchmarks.get("general")
    else:
        score = benchmarks.get("general")
    return float(score) if score is not None else 0.0


def select(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = MAX_HEADROOM,
    application: str | None = None,
    backend: str = "ollama",
    load: dict[str, Any] | None = None,
    require_structured: bool = True,
) -> dict[str, Any]:
    """
    Pick the best-scoring model that fits in available memory.

    Candidates for a 'vlm' selection include both VLMs and LLMs with vision
    capability (kind == 'vlm'). Candidates for a 'llm' selection include
    text-only LLMs and VLMs (since a VLM handles text-only prompts equally).

    Selection order:

    1. Filter: keep entries whose ``ram_gb`` fits within the effective budget.
    2. Rank: structured-output capability first (a model that cannot honour
       Ollama structured output is never chosen over one that can), then
       benchmark score (application-specific if given, else vision for VLM or
       general for LLM). This matches :func:`rank`, so ``rank(...)[0]`` and
       ``select(...)`` agree.
    3. Last resort: if nothing fits, return the smallest model in the catalog
       rather than raising; the caller decides whether to warn the user.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`.
    catalog : list[dict[str, Any]]
        Merged model entries from :func:`catalog.load_catalog`.
    kind : {'llm', 'vlm'}
        The type of model to select.
    headroom : float
        Extra safety on top of the accelerator cap. Clamped to
        :data:`MAX_HEADROOM` (0.5); default 0.5.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Selects the benchmark
        axis used for scoring.  ``None`` uses the default kind-based rule.
    backend : {'ollama', 'vllm'}
        Serving backend, so memory fit is checked against the footprint that
        actually loads (FP16 for vLLM, Q4 ``ram_gb`` for Ollama).
    load : dict or None
        Live server state from :func:`detect.server_load`, forwarded to
        :func:`effective_budget`. None reproduces the load-blind behaviour.

    Returns
    -------
    dict[str, Any]
        The selected catalog entry.

    Raises
    ------
    ValueError
        If the catalog is empty.

    Examples
    --------
    >>> hw = {'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}
    >>> catalog = [{'id': 'v', 'kind': 'vlm', 'ram_gb': 9.0,
    ...             'benchmarks': {'vision': 80}}]
    >>> select(hw, catalog, kind='vlm')['id']
    'v'
    """
    if not catalog:
        osh.error("Catalog is empty; cannot select a model.")
        raise ValueError("Catalog is empty; cannot select a model.")

    # VLMs can answer text-only queries, so they count as valid LLM candidates too
    if kind == "vlm":
        candidates = [e for e in catalog if e.get("kind") == "vlm"]
    else:
        # LLM selection accepts both pure LLMs and VLMs (VLMs subsume LLMs)
        candidates = [e for e in catalog if e.get("kind") in {"llm", "vlm"}]

    if not candidates:
        candidates = list(catalog)

    # Before anything is compared against a budget: an entry with no size is
    # not a smaller model, it is an unknown one. Left in, it won both the fit
    # test and the `smallest` fallback below.
    candidates = sizeable_only(candidates, backend, where="select()")
    if not candidates:
        osh.error("No catalog entry carries a usable size; cannot select a model.")
        raise ValueError("No catalog entry carries a usable size; cannot select a model.")

    budget = effective_budget(hw, headroom=headroom, load=load)

    # Keep only models whose backend-specific footprint fits the safety budget
    fitting = [e for e in candidates if model_footprint_gb(e, backend) <= budget]

    if fitting:
        # Structured-output capability is the primary key, exactly as in rank():
        # a model that can't honour Ollama structured output is never chosen over
        # a capable one, however high its raw score. This keeps select() and
        # rank()[0] in agreement, so the library and the CLI recommend the same
        # model. Absent field defaults to capable.
        def _sort_key(e: dict[str, Any]) -> tuple[bool, float]:
            # See rank(): only a demotion when the job actually needs schemas.
            structured_ok = not require_structured or e.get("structured_output", True) is not False
            return (structured_ok, _benchmark_score(e, kind, application))

        return max(fitting, key=_sort_key)

    # Nothing fits: return the smallest model as a last resort so the caller
    # can surface a useful warning rather than crashing entirely
    smallest = min(candidates, key=lambda e: model_footprint_gb(e, backend))
    osh.warning(
        f"No {kind} model fits the {budget:.1f} GB budget; "
        f"falling back to smallest: {smallest.get('id')}"
    )
    return smallest


def rank(
    hw: dict[str, float | None],
    catalog: list[dict[str, Any]],
    kind: Literal["llm", "vlm"],
    headroom: float = MAX_HEADROOM,
    application: str | None = None,
    backend: str = "ollama",
    load: dict[str, Any] | None = None,
    bandwidth_gbs: float | None = None,
    min_tps: float | None = None,
    installed: set[str] | None = None,
    require_structured: bool = True,
) -> list[dict[str, Any]]:
    """
    Return all candidates sorted by benchmark score, annotated with fit status.

    Each entry in the result gets a ``_fits`` key (bool) indicating whether it
    fits within the effective budget. The top entry is identical to what
    :func:`select` would return.

    Parameters
    ----------
    hw : dict[str, float | None]
        Output of :func:`detect.available_memory`.
    catalog : list[dict[str, Any]]
        Merged model entries from :func:`catalog.load_catalog`.
    kind : {'llm', 'vlm'}
        The inference kind to filter and rank by.
    headroom : float
        Extra safety on top of the accelerator cap. Clamped to
        :data:`MAX_HEADROOM` (0.5); default 0.5.
    application : str or None
        Optional use-case keyword (``"code"``, ``"math"``, ``"ocr"``,
        ``"vision"``, ``"chat"``, ``"generalist"``).  Drives which benchmark
        column is used for ranking.
    backend : {'ollama', 'vllm'}
        Serving backend, so ``_fits`` reflects the footprint that actually
        loads (FP16 for vLLM, Q4 ``ram_gb`` for Ollama).
    load : dict or None
        Live server state from :func:`detect.server_load`, forwarded to
        :func:`effective_budget`. None reproduces the load-blind behaviour.
    bandwidth_gbs : float or None
        Memory bandwidth from :func:`detect.compute_profile`, used to estimate
        throughput for candidates with no measurement. None leaves the
        throughput annotations unpopulated unless a measurement exists.
    min_tps : float or None
        Throughput floor in tokens/s. A candidate **measured** below it on this
        machine is demoted out of auto-selection, in the same way and for the
        same reason as one that does not fit memory. A candidate merely
        *estimated* below it is annotated and left in place: the estimator was
        measured here to run optimistic by a wide margin, so letting it
        disqualify anything would reject models that run perfectly well. None
        disables the check entirely.
    require_structured : bool
        Whether schema-constrained output is a requirement of the job. True
        (the default) demotes a model that cannot honour Ollama structured
        output below one that can, however well it scores. False drops that
        key entirely, for a caller whose brief says it does not need schemas.
    installed : set of str or None
        Model tags already present on the machine. Used only to break ties
        between candidates of comparable quality (within
        :data:`QUALITY_TIE_BAND`), never to promote a worse model over a better
        one: at equal quality a model already on disk beats a 20 GB download,
        and at unequal quality the better model still wins. Passed in rather
        than probed here so that ranking stays a pure function and no network
        call hides inside a sort.

    Returns
    -------
    list[dict[str, Any]]
        Candidates sorted descending by benchmark score, each annotated with
        ``_fits``, and with ``_tps`` / ``_tps_basis`` / ``_comfy`` when a
        throughput figure could be obtained.

    Examples
    --------
    >>> catalog = [{'id': 'v', 'kind': 'vlm', 'ram_gb': 9.0,
    ...             'benchmarks': {'vision': 80}}]
    >>> rank({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0}, catalog, 'vlm')[0]['_fits']
    True
    """
    from . import throughput as _throughput

    if kind == "vlm":
        candidates = [e for e in catalog if e.get("kind") == "vlm"]
    else:
        candidates = [e for e in catalog if e.get("kind") in {"llm", "vlm"}]

    if not candidates:
        candidates = list(catalog)

    # Same rule as `select`, and the reason it has to be here too: `recommend`
    # reaches `_pick_sufficient` through this function, and that pick takes the
    # LEANEST candidate within a few benchmark points -- which an unsizeable
    # entry wins outright at a reported 0.0 GB.
    candidates = sizeable_only(candidates, backend, where="ranking")

    budget = effective_budget(hw, headroom=headroom, load=load)

    annotated = []
    for entry in candidates:
        copy = dict(entry)
        copy["_fits"] = model_footprint_gb(entry, backend) <= budget

        # A measurement for this exact (model, machine) pair beats an estimate,
        # which is the whole argument of this package applied to itself. Only a
        # figure from the serving daemon's own decode clock is trusted here --
        # a wall-clock figure also contains prompt processing and queueing, so
        # it understates speed, and understating is what would wrongly demote a
        # model below.
        measured = _throughput.measured_tps(str(copy.get("id") or ""), trusted_only=True)
        if measured is not None:
            copy["_tps"] = measured
            copy["_tps_basis"] = "measured"
        else:
            estimated = estimated_tokens_per_second(entry, bandwidth_gbs, backend)
            copy["_tps"] = estimated
            copy["_tps_basis"] = "estimated" if estimated is not None else None

        if min_tps is not None and copy["_tps"] is not None:
            copy["_comfy"] = bool(copy["_fits"]) and copy["_tps"] >= min_tps
        annotated.append(copy)

    # Two primary sort keys ahead of raw benchmark score, both of the same
    # shape: a model that cannot do the job is demoted below one that can, no
    # matter how well it scores, but stays in the list so a caller who wants it
    # on purpose can still find it.
    #
    # 1. Structured output. The helper routes every task through a JSON schema,
    #    so a model that can't honour Ollama structured output (the Qwen3-VL
    #    family returns empty) is out of auto-selection. Absent field defaults
    #    to True (assume capable) for forward compatibility.
    # 2. A throughput floor that was actually MEASURED below on this machine.
    #    This is the half of "fits your hardware" that used to be advisory: a
    #    model too slow to use here is as unusable as one that does not fit in
    #    memory, and it is now treated the same. An estimate never demotes --
    #    `_measured_slow` is False unless the figure came from a measurement --
    #    so a machine that has never run `pull` ranks exactly as it did before.
    # 3. Among candidates of indistinguishable quality, prefer one already on
    #    disk. This is a tiebreak and nothing more: the banded score is compared
    #    FIRST, so a genuinely better model still wins however large its
    #    download. It only decides when the benchmark cannot, which is the case
    #    where the honest answer is "either, so take the cheap one".
    present = installed or set()

    def _sort_key(e: dict[str, Any]) -> tuple[bool, bool, float, bool, float]:
        # Only a demotion when the caller says the job needs schemas. A brief
        # declaring `structured_output: false` is saying the opposite, and
        # ignoring it cost that caller the better model for nothing.
        structured_ok = not require_structured or e.get("structured_output", True) is not False
        measured_slow = (
            min_tps is not None
            and e.get("_tps_basis") == "measured"
            and e.get("_tps") is not None
            and float(e["_tps"]) < min_tps
        )
        score = _benchmark_score(e, kind, application)
        band = (score // QUALITY_TIE_BAND) * QUALITY_TIE_BAND if QUALITY_TIE_BAND > 0 else score
        ident = str(e.get("id") or "")
        # Plain membership is both necessary and sufficient: `pull.installed_tags`
        # already adds the bare form for a `:latest` tag and only for that, so a
        # looser `name.split(":")[0]` test would call `gemma3:12b` installed when
        # the daemon holds nothing but `gemma3:latest` -- a different model.
        already_here = ident in present
        return (structured_ok, not measured_slow, band, already_here, score)

    ranked = sorted(annotated, key=_sort_key, reverse=True)
    for entry in ranked:
        ident = str(entry.get("id") or "")
        entry["_installed"] = ident in present
    return ranked
