"""
detect — turn raw hardware facts into AI-inference throughput estimates.

Raw probing (subprocess calls to ``nvidia-smi`` / ``rocm-smi`` /
``system_profiler`` / ``lspci``, CPU/RAM introspection) is NOT done here: it
lives in ``os_helper.hardware_utils``, a generic cross-platform hardware probe
shared by every repo in the AI Helpers suite. This module is the thin,
AI-domain layer on top of it — it takes the vendor + chip/GPU name + memory
size that ``os_helper`` reports and turns them into what a local model picker
actually needs: an accelerator kind, a memory-bandwidth estimate, and the
memory pool available for inference.

Memory bandwidth is the ceiling on decode throughput (token generation reads
the whole active model from memory once per token), so it — not raw core
count — is what :func:`compute_profile` reports and what
``score.estimated_tokens_per_second`` keys its tokens/s estimate on. Apple
Silicon publishes per-chip bandwidth; NVIDIA/AMD publish it per GPU model.
Both are tabulated below by substring match on the chip/GPU name ``os_helper``
reports; an unrecognised model degrades gracefully to "throughput not
estimated" rather than a wrong number.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

from typing import Any

import os_helper as osh

# ---------------------------------------------------------------------------
# Re-exported raw facts (thin wrappers) — kept as functions in THIS module
# so the rest of the package (and its tests) can keep importing
# `detect.platform_name` / `detect.chip_vendor` / `detect.chip_name` without
# caring that the actual probing lives in os_helper.hardware_utils.
# ---------------------------------------------------------------------------


def platform_name() -> str:
    """
    Return the current OS as a short lowercase string.

    Returns
    -------
    str
        One of: 'darwin', 'linux', 'windows'. Delegates to
        :func:`os_helper.platform_name`.

    Examples
    --------
    >>> platform_name() in ('darwin', 'linux', 'windows')
    True
    """
    return osh.platform_name()


def chip_vendor() -> str:
    """
    Identify the primary compute vendor for model inference.

    Returns
    -------
    str
        One of: 'apple', 'nvidia', 'amd', 'intel', 'cpu'. Delegates to
        :func:`os_helper.gpu_vendor`.

    Examples
    --------
    >>> chip_vendor() in ('apple', 'nvidia', 'amd', 'intel', 'cpu')
    True
    """
    return osh.gpu_vendor()


def chip_name() -> str | None:
    """Return the Apple Silicon chip name (e.g. ``"Apple M2 Max"``), or None.

    Delegates to :func:`os_helper.apple_chip_name`; None on non-macOS
    platforms or when the chip line is absent (old Intel Macs).
    """
    return osh.apple_chip_name()


# ---------------------------------------------------------------------------
# AI-throughput domain data: memory-bandwidth-per-chip lookup tables
# ---------------------------------------------------------------------------

# Apple Silicon unified-memory bandwidth in GB/s, by chip, from Apple's
# published specifications. Bandwidth is the dominant factor in local decode
# speed (token generation is memory-bandwidth bound: see references/CODING.md),
# so it, not raw core count, is what the throughput estimate keys on. Values
# are the per-chip figures Apple lists; higher-binned variants of the same
# name share the ceiling closely enough for planning. Source: apple-specs.
_APPLE_BANDWIDTH_GBS: dict[str, float] = {
    "M1 Ultra": 800.0,
    "M1 Max": 400.0,
    "M1 Pro": 200.0,
    "M1": 68.0,
    "M2 Ultra": 800.0,
    "M2 Max": 400.0,
    "M2 Pro": 200.0,
    "M2": 100.0,
    "M3 Ultra": 800.0,
    "M3 Max": 300.0,
    "M3 Pro": 150.0,
    "M3": 100.0,
    "M4 Max": 546.0,
    "M4 Pro": 273.0,
    "M4": 120.0,
}

# NVIDIA discrete-GPU memory bandwidth in GB/s, by board name, from NVIDIA's
# published specifications. Matched by substring against the name
# `os_helper.nvidia_gpus()` reads from `nvidia-smi`. Datacenter cards first
# (highest bandwidth, so a "H100 NVL" query does not fall through to a shorter
# "H100" match at the wrong figure — see the length-sorted lookup below),
# then the consumer RTX line most likely to sit under a local vLLM/Ollama
# server. Source: NVIDIA spec sheets / TechPowerUp GPU database.
_NVIDIA_BANDWIDTH_GBS: dict[str, float] = {
    # Datacenter / workstation.
    "H100 SXM": 3350.0,
    "H100 NVL": 3938.0,
    "H100 PCIe": 2000.0,
    "H200": 4800.0,
    "A100 80GB": 2039.0,
    "A100 40GB": 1555.0,
    "L40S": 864.0,
    "L40": 864.0,
    "L4": 300.0,
    "A40": 696.0,
    "A30": 933.0,
    "A10": 600.0,
    "T4": 320.0,
    "RTX 6000 Ada": 960.0,
    "RTX 5000 Ada": 576.0,
    "RTX 4000 Ada": 360.0,
    # Consumer RTX 40 series.
    "RTX 4090": 1008.0,
    "RTX 4080 SUPER": 736.0,
    "RTX 4080": 716.8,
    "RTX 4070 Ti SUPER": 672.0,
    "RTX 4070 Ti": 504.2,
    "RTX 4070 SUPER": 504.2,
    "RTX 4070": 504.2,
    "RTX 4060 Ti": 288.0,
    "RTX 4060": 272.0,
    # Consumer RTX 30 series.
    "RTX 3090 Ti": 1008.0,
    "RTX 3090": 936.2,
    "RTX 3080 Ti": 912.4,
    "RTX 3080": 760.3,
    "RTX 3070 Ti": 608.3,
    "RTX 3070": 448.0,
    "RTX 3060 Ti": 448.0,
    "RTX 3060": 360.0,
}

# AMD discrete-GPU memory bandwidth in GB/s, by board name, from AMD's
# published specifications. Matched by substring against the name
# `os_helper.amd_gpus()` reads from `rocm-smi`. Source: AMD spec sheets /
# TechPowerUp GPU database.
_AMD_BANDWIDTH_GBS: dict[str, float] = {
    "MI300X": 5300.0,
    "MI300A": 5300.0,
    "MI250X": 3277.0,
    "MI250": 3277.0,
    "MI210": 1638.0,
    "MI100": 1229.0,
    "RX 7900 XTX": 960.0,
    "RX 7900 XT": 800.0,
    "RX 7900 GRE": 576.0,
    "RX 7800 XT": 624.1,
    "RX 7700 XT": 432.0,
    "RX 6950 XT": 576.0,
    "RX 6900 XT": 512.0,
    "RX 6800 XT": 512.0,
    "RX 6800": 512.0,
    "RX 6700 XT": 384.0,
}


def _bandwidth_from_table(name: str | None, table: dict[str, float]) -> float | None:
    """Look up a chip/GPU's memory bandwidth by substring match.

    Matches the most specific (longest) label first so a Pro/Max/Ultra/Ti/
    SUPER variant is never mistaken for its shorter base-model name (e.g.
    ``'RTX 4070 Ti'`` must win over the bare ``'RTX 4070'`` when both are
    substrings of the detected name).

    Parameters
    ----------
    name : str or None
        The chip or GPU name as reported by ``os_helper`` (e.g.
        ``'Apple M2 Max'`` or ``'NVIDIA GeForce RTX 4090'``).
    table : dict[str, float]
        One of :data:`_APPLE_BANDWIDTH_GBS`, :data:`_NVIDIA_BANDWIDTH_GBS`,
        :data:`_AMD_BANDWIDTH_GBS`.

    Returns
    -------
    float or None
        Bandwidth in GB/s, or None when ``name`` is falsy or matches no
        entry — throughput simply cannot be estimated for that model.
    """
    if not name:
        return None
    for label in sorted(table, key=len, reverse=True):
        if label in name:
            return table[label]
    return None


def _apple_bandwidth_gbs(chip: str | None) -> float | None:
    """Look up unified-memory bandwidth for an Apple chip name."""
    return _bandwidth_from_table(chip, _APPLE_BANDWIDTH_GBS)


# ---------------------------------------------------------------------------
# Compute profile — accelerator + bandwidth, the AI-throughput view
# ---------------------------------------------------------------------------


def compute_profile() -> dict[str, Any]:
    """Describe the machine's inference accelerator and memory bandwidth.

    Returns a dict with:

    - ``accelerator``: ``"gpu-metal"`` (Apple Silicon), ``"gpu-cuda"`` (NVIDIA),
      ``"gpu-rocm"`` (AMD), or ``"cpu"`` (no discrete accelerator detected).
    - ``chip``: the chip / GPU name when known, else None.
    - ``bandwidth_gbs``: memory bandwidth in GB/s when the chip/GPU matches a
      known model in :data:`_APPLE_BANDWIDTH_GBS` / :data:`_NVIDIA_BANDWIDTH_GBS`
      / :data:`_AMD_BANDWIDTH_GBS`, else None. This is the ceiling on decode
      throughput; token generation reads the whole active model from memory
      once per token, so tokens/s scales with it.

    Bandwidth is tabulated for Apple Silicon (per-chip) and for discrete
    NVIDIA/AMD GPUs (per-board, matched on the model name ``os_helper``
    reports). An unrecognised GPU model — a new SKU not yet in the table, or a
    multi-GPU box where the name string is ambiguous — degrades to
    ``bandwidth_gbs: None`` rather than a fabricated number; callers treat
    that as "throughput not estimated", never as zero.
    """
    # Route through the local wrappers (not osh.* directly) so this stays on
    # the same seam callers/tests already patch (`detect.chip_vendor`,
    # `detect.chip_name`), keeping compute_profile consistent with the rest
    # of the package no matter which layer a caller mocks.
    vendor = chip_vendor()

    if vendor == "apple":
        chip = chip_name()
        return {
            "accelerator": "gpu-metal",
            "chip": chip,
            "bandwidth_gbs": _apple_bandwidth_gbs(chip),
        }

    if vendor in ("nvidia", "amd"):
        table = _NVIDIA_BANDWIDTH_GBS if vendor == "nvidia" else _AMD_BANDWIDTH_GBS
        cards = osh.gpus()
        # A multi-GPU box still reports one chip name (the first card) for
        # display; the bandwidth estimate assumes a single-GPU serve, which
        # matches how the picker sizes a model against one accelerator's pool.
        name = cards[0]["name"] if cards else None
        if not name:
            osh.debug(f"{vendor} detected but no GPU name available; throughput unestimated.")
        return {
            "accelerator": "gpu-cuda" if vendor == "nvidia" else "gpu-rocm",
            "chip": name,
            "bandwidth_gbs": _bandwidth_from_table(name, table),
        }

    return {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None}


# ---------------------------------------------------------------------------
# Available memory — the inference budget pools
# ---------------------------------------------------------------------------


def available_memory() -> dict[str, float | None]:
    """
    Detect available memory for model inference.

    Reads three pools from ``os_helper``'s hardware facts:

    1. Apple Silicon unified memory (macOS with Apple chip)
    2. NVIDIA/AMD VRAM (summed across all visible GPUs)
    3. System RAM (always populated)

    Returns
    -------
    dict[str, float | None]
        A dict with the following keys:

        unified_gb : float or None
            Apple Silicon unified memory pool, in GB.
        vram_gb : float or None
            Discrete GPU VRAM (sum of all visible GPUs), in GB.
        ram_gb : float
            Total system RAM in GB. Always a positive float.

    Examples
    --------
    >>> mem = available_memory()
    >>> set(mem.keys()) == {'unified_gb', 'vram_gb', 'ram_gb'}
    True
    >>> mem['ram_gb'] > 0
    True
    """
    # Same seam as compute_profile(): route through the local chip_vendor()
    # wrapper so both functions honour a `detect.chip_vendor` patch identically.
    vendor = chip_vendor()
    ram_gb: float = osh.ram_gb()

    unified_gb: float | None = None
    vram_gb: float | None = None

    if vendor == "apple":
        unified_gb = osh.apple_unified_memory_gb()
    elif vendor in ("nvidia", "amd"):
        # Sum VRAM across every visible GPU — the picker treats a multi-GPU
        # box as one pool, matching how Ollama/vLLM report available memory.
        cards = osh.gpus()
        total = sum(c["vram_gb"] for c in cards if c.get("vram_gb"))
        vram_gb = round(total, 1) if total > 0 else None

    osh.info(
        f"Memory detected — unified: {unified_gb} GB, vram: {vram_gb} GB, ram: {ram_gb:.1f} GB"
    )
    return {
        "unified_gb": unified_gb,
        "vram_gb": vram_gb,
        "ram_gb": ram_gb,
    }


# ---------------------------------------------------------------------------
# Live server load — current, not total, capacity
# ---------------------------------------------------------------------------
# `available_memory` and `compute_profile` describe the machine's STATIC
# capacity: total memory pools, accelerator identity. Two machines with
# identical capacity behave very differently if one is idle and the other is
# already serving three models or mid-compile — the realistic budget for
# "one more model" depends on what else is happening RIGHT NOW. The live
# metrics themselves (CPU%, free RAM, disk usage, GPU utilization) are generic
# cross-platform facts and live in `os_helper.hardware_utils`, same as every
# other raw probe this module wraps; only the Ollama/vLLM-specific
# "how many engines are already serving" count is AI-domain-specific enough
# to stay here.

# Ollama's REST base URL, same default/env-var as llm.py's `_base_url()` (not
# imported from there to avoid a cross-module private-name dependency for one
# constant).
_OLLAMA_BASE_URL_ENV = "SPREZZATURE_LLM_BASE_URL"
_OLLAMA_BASE_URL_DEFAULT = "http://localhost:11434"


def _running_engines() -> int:
    """Best-effort count of already-serving local inference engines.

    Sums Ollama's currently loaded models (queried via its ``/api/ps``
    endpoint — the source of truth, since one ``ollama serve`` daemon can
    hold several models resident at once, so a process count would
    undercount) and running vLLM server processes (each normally serves
    exactly one model, so a process count is accurate there). Both probes
    fail soft to 0 — neither engine running is the common case, not an error.

    Returns
    -------
    int
        Number of currently loaded/serving models across both engines.
    """
    count = 0

    try:
        import os

        import requests

        base_url = os.environ.get(_OLLAMA_BASE_URL_ENV, _OLLAMA_BASE_URL_DEFAULT).rstrip("/")
        resp = requests.get(f"{base_url}/api/ps", timeout=1.0)
        if resp.ok:
            count += len(resp.json().get("models", []))
    except Exception as exc:  # noqa: BLE001 — Ollama not running is the common case
        osh.debug(f"Ollama /api/ps unreachable (probably not running): {exc}")

    try:
        import psutil

        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if "vllm" in cmdline and ("serve" in cmdline or "api_server" in cmdline):
                count += 1
    except Exception as exc:  # noqa: BLE001 — process enumeration must not break detection
        osh.debug(f"vLLM process scan failed: {exc}")

    return count


def server_load() -> dict[str, Any]:
    """
    Snapshot the machine's CURRENT load — as opposed to its static capacity.

    Requires an os-helper release whose ``hardware_info()`` includes the live
    fields ``cpu.percent`` / ``available_ram_gb`` / ``disk`` /
    ``gpu_utilization_percent`` (added alongside this function; not yet in a
    published os-helper release as of this writing — bump the ``os-helper``
    pin in ``pyproject.toml`` once one ships, or this raises ``KeyError`` on
    a fresh install).

    Feeds :func:`score.effective_budget`'s optional ``load`` parameter, so a
    recommendation reflects what else is happening on this machine right now:
    another process (or an already-running engine) can hold memory the static
    hardware totals from :func:`available_memory` know nothing about.

    Returns
    -------
    dict[str, Any]
        ``available_ram_gb`` : float
            Free system RAM right now.
        ``cpu_percent`` : float
            Instantaneous CPU utilization, 0-100.
        ``gpu_percent`` : float or None
            Live discrete-GPU utilization, 0-100; None on Apple Silicon,
            CPU-only machines, or when the vendor CLI is unavailable.
        ``disk_free_gb`` : float
            Free space on the disk holding the home directory (where model
            caches live).
        ``disk_percent_used`` : float
            0-100.
        ``running_engines`` : int
            Best-effort count of already-loaded Ollama models plus running
            vLLM server processes.

    Examples
    --------
    >>> load = server_load()
    >>> load["available_ram_gb"] >= 0
    True
    >>> 0 <= load["cpu_percent"] <= 100
    True
    >>> load["running_engines"] >= 0
    True
    """
    # One aggregate call: `hardware_info()` already samples every live figure
    # this needs (plus static facts this function doesn't use), so calling it
    # once avoids redundant vendor-detection/subprocess probes that four
    # separate osh.* calls would each repeat.
    info = osh.hardware_info()
    load = {
        "available_ram_gb": info["available_ram_gb"],
        "cpu_percent": info["cpu"]["percent"],
        "gpu_percent": info["gpu_utilization_percent"],
        "disk_free_gb": info["disk"]["free_gb"],
        "disk_percent_used": info["disk"]["percent_used"],
        "running_engines": _running_engines(),
    }
    osh.info(
        f"Server load — RAM free: {load['available_ram_gb']} GB, "
        f"CPU: {load['cpu_percent']}%, GPU: {load['gpu_percent']}%, "
        f"disk free: {load['disk_free_gb']} GB, "
        f"running engines: {load['running_engines']}"
    )
    return load
