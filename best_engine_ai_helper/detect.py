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
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import mmap
import os
import tempfile
import time
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
    return str(osh.platform_name())


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
    return str(osh.gpu_vendor())


def chip_name() -> str | None:
    """Return the Apple Silicon chip name (e.g. ``"Apple M2 Max"``), or None.

    Delegates to :func:`os_helper.apple_chip_name`; None on non-macOS
    platforms or when the chip line is absent (old Intel Macs).
    """
    chip = osh.apple_chip_name()
    return str(chip) if chip is not None else None


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
    ``gpu_utilization_percent`` — available since os-helper 2.3.0, the floor
    pinned in ``pyproject.toml`` (``os-helper>=2.3.0,<3``), so any install of
    this package already has them.

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


# ---------------------------------------------------------------------------
# Storage bandwidth — the ceiling on layer-streaming (lightweight) decode
# ---------------------------------------------------------------------------

#: Sequential-read bandwidth (GB/s) assumed per storage class, used when no
#: measurement is available. Deliberately on the low side of each class: the
#: figure bounds :func:`offload.estimated_tokens_per_second`, and an optimistic
#: disk number promises a streaming speed the machine will not deliver.
#:
#: - ``apple-internal``: Apple Silicon's soldered NVMe reads 4-7 GB/s depending
#:   on chip and capacity (M1 ~4.5, M2/M3/M4 up to ~7); 4.0 is the floor of the
#:   range, so every Mac meets or beats it.
#: - ``nvme``: a PCIe 3.0 x4 drive sustains ~3.0-3.5 GB/s and Gen4 ~5-7; 2.5
#:   holds for the oldest NVMe still shipping in a workstation.
#: - ``ssd-sata``: the SATA III link itself caps at 6 Gbit/s ≈ 0.55 GB/s.
#: - ``hdd``: 0.12 GB/s is a 7200 rpm platter's sustained outer-track rate.
#:
#: Sources: manufacturer sequential-read specifications per class; see
#: references/CODING.md.
_DISK_READ_GBS: dict[str, float] = {
    "apple-internal": 4.0,
    "nvme": 2.5,
    "ssd-sata": 0.55,
    "hdd": 0.12,
}

#: macOS ``fcntl`` command that turns the unified buffer cache off for one file
#: descriptor (``F_NOCACHE`` in ``<sys/fcntl.h>``). Not exposed by Python's
#: ``fcntl`` module, so the constant is spelled out here.
_F_NOCACHE = 48

#: Chunk size and default total for the optional read measurement. 4 MiB is a
#: multiple of every sector/page size O_DIRECT demands alignment against, and
#: 256 MiB is long enough to leave the burst/SLC window of a consumer SSD while
#: still writing in well under a second on any drive worth streaming from.
_PROBE_CHUNK_BYTES = 4 * 1024 * 1024
_PROBE_TOTAL_BYTES = 256 * 1024 * 1024


def storage_class() -> str:
    """
    Classify the drive that holds the model cache.

    Layer streaming reads the weights off this drive once per token, so its
    class — not the memory bus — is what bounds throughput. Classification is
    deliberately coarse (four classes, see :data:`_DISK_READ_GBS`): the goal is
    the right order of magnitude for an estimate, not a device database.

    Returns
    -------
    str
        One of ``'apple-internal'``, ``'nvme'``, ``'ssd-sata'``, ``'hdd'`` or
        ``'unknown'``. ``'unknown'`` is returned rather than a guess when the
        platform exposes no rotational/transport hint, so callers can say
        "not estimated" instead of inventing a speed.

    Examples
    --------
    >>> storage_class() in ('apple-internal', 'nvme', 'ssd-sata', 'hdd', 'unknown')
    True
    """
    system = platform_name()
    if system == "darwin":
        # Every Apple Silicon Mac ships soldered NVMe; an Intel Mac may not, and
        # its class is not worth probing for a product whose floor is an M-series
        # machine, so it degrades to the generic NVMe figure.
        return "apple-internal" if chip_vendor() == "apple" else "nvme"

    if system == "linux":
        return _linux_storage_class()

    # Windows: WMI would answer this (MSFT_PhysicalDisk.MediaType), but it
    # needs a subprocess and this module leaves raw probing to os_helper.
    # An NVMe assumption is right on any machine bought to run models, and
    # the basis field says it was assumed.
    return "nvme" if system == "windows" else "unknown"


def _linux_storage_class() -> str:
    """
    Classify the Linux block device backing the home directory.

    Reads ``/sys/block/<dev>/queue/rotational`` — the kernel's own answer to
    "is this a platter?" — and keys an SSD's transport off the device name
    (``nvme*`` versus ``sd*``). Pure sysfs reads, no subprocess.

    Returns
    -------
    str
        One of ``'nvme'``, ``'ssd-sata'``, ``'hdd'`` or ``'unknown'``.

    Examples
    --------
    >>> _linux_storage_class() in ('nvme', 'ssd-sata', 'hdd', 'unknown')
    True
    """
    import re
    from pathlib import Path

    try:
        dev = os.stat(Path.home()).st_dev
        major, minor = os.major(dev), os.minor(dev)
        link = Path(f"/sys/dev/block/{major}:{minor}")
        # The home directory usually sits on a partition (`nvme0n1p2`), and only
        # the whole device carries the `queue/` attributes, so walk up to it.
        name = link.resolve().name
        whole = re.sub(r"(p?\d+)$", "", name) if not name.startswith("dm-") else name
        rotational = Path(f"/sys/block/{whole}/queue/rotational")
        if not rotational.is_file():
            return "unknown"
        if rotational.read_text().strip() == "1":
            return "hdd"
        return "nvme" if whole.startswith("nvme") else "ssd-sata"
    except OSError as exc:
        osh.debug(f"Linux storage classification failed: {exc}")
        return "unknown"


def _bypass_flag() -> int:
    """
    Return the ``open`` flag that bypasses the page cache on this platform.

    Returns
    -------
    int
        ``os.O_DIRECT`` on Linux, 0 elsewhere (macOS has no such flag and uses
        :func:`_bypass_cache` after opening instead).

    Examples
    --------
    >>> _bypass_flag() >= 0
    True
    """
    return getattr(os, "O_DIRECT", 0) if platform_name() == "linux" else 0


def _bypass_cache(fd: int) -> None:
    """
    Turn the buffer cache off for an already-open descriptor (macOS only).

    Parameters
    ----------
    fd : int
        Open file descriptor.

    Examples
    --------
    >>> import os, tempfile
    >>> handle, name = tempfile.mkstemp()
    >>> _bypass_cache(handle) is None
    True
    >>> os.close(handle); os.unlink(name)
    """
    if platform_name() != "darwin":
        return
    import fcntl

    try:
        fcntl.fcntl(fd, _F_NOCACHE, 1)
    except OSError as exc:  # a filesystem may refuse it; the caller still reads
        osh.debug(f"F_NOCACHE refused on fd {fd}: {exc}")


def measure_disk_read_gbs(
    total_bytes: int = _PROBE_TOTAL_BYTES, directory: str | None = None
) -> float | None:
    """
    Measure sequential read bandwidth (GB/s), defeating the page cache.

    Writes a scratch file, flushes it to the device, then reads it back with
    caching disabled for that descriptor (``F_NOCACHE`` on macOS, ``O_DIRECT``
    on Linux). Without that step the read is served from RAM and reports the
    memory bus, not the drive — a number three times too high, which would make
    layer streaming look comfortable when it is not.

    Returns None rather than a cached-read figure on any platform that offers no
    way to bypass the cache (Windows), so an unmeasurable machine falls back to
    the declared class figure instead of to a flattering one.

    Parameters
    ----------
    total_bytes : int
        Bytes to write and read back. Rounded down to a multiple of 4 MiB, the
        alignment ``O_DIRECT`` requires. Defaults to 256 MiB.
    directory : str or None
        Where to put the scratch file. None uses the system temp directory.
        Point it at the volume holding the model cache when that differs.

    Returns
    -------
    float or None
        Measured GB/s (rounded to two decimals), or None when the measurement
        is unavailable or the platform cannot bypass its cache.

    Examples
    --------
    >>> v = measure_disk_read_gbs(total_bytes=4 * 1024 * 1024)
    >>> v is None or v > 0
    True
    """
    system = platform_name()
    if system not in ("darwin", "linux"):
        osh.debug(f"No cache-bypassing read on {system}; disk bandwidth not measured.")
        return None

    chunks = max(1, total_bytes // _PROBE_CHUNK_BYTES)
    size = chunks * _PROBE_CHUNK_BYTES
    path: str | None = None
    try:
        fd, path = tempfile.mkstemp(prefix="beah-disk-", dir=directory)
        os.close(fd)
        # mmap hands back a page-aligned buffer, which is half of what O_DIRECT
        # demands (aligned address, offset AND length). A single repeated page
        # would let a compressing filesystem (APFS, ZFS, btrfs) store almost
        # nothing and "read" it back at memory speed, so the payload is
        # incompressible.
        buffer = mmap.mmap(-1, _PROBE_CHUNK_BYTES)
        buffer.write(os.urandom(_PROBE_CHUNK_BYTES))
        view = memoryview(buffer)

        # The cache is bypassed on the WRITE too, not just the read. Pages the
        # write path leaves in the cache are still served from RAM afterwards,
        # however emphatically the reader asks for uncached I/O — which is how
        # this probe first reported 13 GB/s on a drive whose own specification
        # tops out near 7.
        write_fd = os.open(path, os.O_WRONLY | _bypass_flag())
        try:
            _bypass_cache(write_fd)
            for index in range(chunks):
                os.pwritev(write_fd, [view], index * _PROBE_CHUNK_BYTES)
            os.fsync(write_fd)
        finally:
            os.close(write_fd)

        read_fd = os.open(path, os.O_RDONLY | _bypass_flag())
        try:
            _bypass_cache(read_fd)
            start = time.perf_counter()
            read = 0
            while read < size:
                got = os.preadv(read_fd, [view], read)
                if not got:
                    break
                read += got
            elapsed = time.perf_counter() - start
        finally:
            os.close(read_fd)

        if elapsed <= 0 or read <= 0:
            return None
        gbs = (read / 1e9) / elapsed
        osh.info(f"Measured sequential disk read: {gbs:.2f} GB/s over {read / 1e6:.0f} MB.")
        return round(gbs, 2)
    except (OSError, ValueError) as exc:
        # O_DIRECT is refused by tmpfs, overlayfs and most network mounts, and
        # the alignment rules are strict -- a failure here means "cannot
        # measure", never "slow disk".
        osh.debug(f"Disk read measurement unavailable: {exc}")
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def disk_profile(measure: bool = False, directory: str | None = None) -> dict[str, Any]:
    """
    Describe the storage this machine would stream model layers from.

    The counterpart of :func:`compute_profile` for a disk-bound backend. Where
    memory bandwidth bounds an in-memory decode, *disk* bandwidth bounds a
    layer-streaming one (``offload``/lightweight), which reads every layer back per
    token.

    Parameters
    ----------
    measure : bool
        Run :func:`measure_disk_read_gbs` instead of reading the class table.
        Off by default: it writes a few hundred MB and takes a second or two, and
        a recommendation should stay a deterministic function of the hardware
        unless the caller asks for a measurement.
    directory : str or None
        Volume to measure, when ``measure`` is True. None uses the temp
        directory.

    Returns
    -------
    dict[str, Any]
        ``storage`` : str
            Class from :func:`storage_class`.
        ``read_gbs`` : float or None
            Sequential read bandwidth in GB/s; None when the class is unknown
            and no measurement succeeded.
        ``basis`` : {'measured', 'declared', 'unknown'}
            Where ``read_gbs`` came from — the same honesty rule the throughput
            estimates follow: a measured number is never presented as a table
            lookup, nor the reverse.
        ``free_gb`` : float or None
            Free space on the volume holding the home directory, where both the
            HuggingFace cache lands.

    Examples
    --------
    >>> p = disk_profile()
    >>> p['basis'] in ('measured', 'declared', 'unknown')
    True
    >>> p['read_gbs'] is None or p['read_gbs'] > 0
    True
    """
    storage = storage_class()
    read_gbs = _DISK_READ_GBS.get(storage)
    basis = "declared" if read_gbs is not None else "unknown"

    if measure:
        measured = measure_disk_read_gbs(directory=directory)
        if measured is not None:
            read_gbs, basis = measured, "measured"

    free_gb: float | None = None
    try:
        free_gb = float(osh.hardware_info()["disk"]["free_gb"])
    except (KeyError, TypeError, ValueError) as exc:
        osh.debug(f"Free-space probe failed: {exc}")

    return {"storage": storage, "read_gbs": read_gbs, "basis": basis, "free_gb": free_gb}
