"""
detect — hardware detection for local model selection.

Probes the current machine for available memory (unified, VRAM, RAM) and
identifies the GPU or CPU vendor. All public functions return simple scalars
or dicts so callers need no knowledge of OS internals.

Probe order matters: Apple Silicon detection runs first because macOS can also
report nvidia-smi output in certain VM/eGPU setups. After Apple, NVIDIA, then
AMD, then a CPU-only fallback using half of available RAM as a conservative
estimate of what a model loader can actually use.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], **kwargs: Any) -> str:
    """
    Run a subprocess and return its stdout as a string.

    Returns an empty string on any failure so callers can treat the result
    as a simple truthiness check without try/except at every call site.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments, as passed to subprocess.run.
    **kwargs
        Forwarded to subprocess.run (e.g. timeout).

    Returns
    -------
    str
        Decoded stdout, or '' on error.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            **kwargs,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        # FileNotFoundError: binary not on PATH
        # CalledProcessError: binary exists but returned non-zero
        return ""


def _parse_memory_gb(value_str: str) -> float | None:
    """
    Parse a memory string like '96 GB' or '32768 MiB' into GB as a float.

    Parameters
    ----------
    value_str : str
        Raw string from system_profiler or similar tools.

    Returns
    -------
    float or None
        Memory in GB, or None if the string could not be parsed.
    """
    s = value_str.strip()
    try:
        if "GB" in s.upper():
            return float(s.upper().replace("GB", "").strip())
        if "GIB" in s.upper():
            return float(s.upper().replace("GIB", "").strip())
        if "MB" in s.upper():
            return float(s.upper().replace("MB", "").strip()) / 1024.0
        if "MIB" in s.upper():
            return float(s.upper().replace("MIB", "").strip()) / 1024.0
        # Bare integer assumed to be bytes (e.g., wmic output)
        return float(s) / (1024 ** 3)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def platform_name() -> str:
    """
    Return the current OS as a short lowercase string.

    Returns
    -------
    str
        One of: 'darwin', 'linux', 'windows'.

    Examples
    --------
    >>> platform_name() in ('darwin', 'linux', 'windows')
    True
    """
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    # All other POSIX systems treated as linux for our purposes
    return "linux"


# ---------------------------------------------------------------------------
# Chip vendor
# ---------------------------------------------------------------------------

def chip_vendor() -> str:
    """
    Identify the primary compute vendor for model inference.

    Checks in order: Apple Silicon, NVIDIA (nvidia-smi), AMD (rocm-smi),
    then falls back to 'cpu'.

    Returns
    -------
    str
        One of: 'apple', 'nvidia', 'amd', 'intel', 'cpu'.

    Examples
    --------
    >>> chip_vendor() in ('apple', 'nvidia', 'amd', 'intel', 'cpu')
    True
    """
    plat = platform_name()

    if plat == "darwin":
        # system_profiler reliably reports the Apple Silicon chip name
        out = _run(["system_profiler", "SPHardwareDataType"])
        if "Apple M" in out or "Apple A" in out:
            return "apple"

    # Try NVIDIA — works on Linux and Windows
    if _run(["nvidia-smi", "-L"]):
        return "nvidia"

    # AMD ROCm stack
    if _run(["rocm-smi", "--showid"]):
        return "amd"

    # Intel Arc / integrated GPU (future-proofing)
    if plat == "linux":
        lspci = _run(["lspci"])
        if "Intel" in lspci and "VGA" in lspci:
            return "intel"

    return "cpu"


# ---------------------------------------------------------------------------
# Memory detection
# ---------------------------------------------------------------------------

def _apple_unified_gb() -> float | None:
    """
    Read the unified memory size from system_profiler on macOS.

    Returns
    -------
    float or None
        Memory in GB, or None if not running on Apple Silicon.
    """
    out = _run(["system_profiler", "SPHardwareDataType"])
    for line in out.splitlines():
        # The relevant line looks like: "  Memory: 96 GB"
        if "Memory:" in line and ("GB" in line or "MB" in line):
            _, _, value = line.partition("Memory:")
            parsed = _parse_memory_gb(value)
            if parsed is not None:
                return parsed
    return None


def chip_name() -> str | None:
    """Return the Apple Silicon chip name (e.g. ``"Apple M2 Max"``), or None.

    Read from ``system_profiler`` on macOS; None on other platforms or when the
    chip line is absent.
    """
    if platform_name() != "darwin":
        return None
    out = _run(["system_profiler", "SPHardwareDataType"])
    for line in out.splitlines():
        if "Chip:" in line:
            return line.partition("Chip:")[2].strip() or None
    return None


# Apple Silicon unified-memory bandwidth in GB/s, by chip, from Apple's
# published specifications. Bandwidth is the dominant factor in local decode
# speed (token generation is memory-bandwidth bound: see references/CODING.md),
# so it, not raw core count, is what the throughput estimate keys on. Values
# are the per-chip figures Apple lists; higher-binned variants of the same
# name share the ceiling closely enough for planning. Source: apple-specs.
_APPLE_BANDWIDTH_GBS: dict[str, float] = {
    "M1 Ultra": 800.0, "M1 Max": 400.0, "M1 Pro": 200.0, "M1": 68.0,
    "M2 Ultra": 800.0, "M2 Max": 400.0, "M2 Pro": 200.0, "M2": 100.0,
    "M3 Ultra": 800.0, "M3 Max": 300.0, "M3 Pro": 150.0, "M3": 100.0,
    "M4 Max": 546.0, "M4 Pro": 273.0, "M4": 120.0,
}


def _apple_bandwidth_gbs(chip: str | None) -> float | None:
    """Look up unified-memory bandwidth for an Apple chip name.

    Matches the most specific chip label first (``M2 Max`` before ``M2``) so a
    Pro/Max/Ultra variant is not mistaken for the base chip.
    """
    if not chip:
        return None
    for label in sorted(_APPLE_BANDWIDTH_GBS, key=len, reverse=True):
        if label in chip:
            return _APPLE_BANDWIDTH_GBS[label]
    return None


def compute_profile() -> dict[str, Any]:
    """Describe the machine's inference accelerator and memory bandwidth.

    Returns a dict with:

    - ``accelerator``: ``"gpu-metal"`` (Apple Silicon), ``"gpu-cuda"`` (NVIDIA),
      ``"gpu-rocm"`` (AMD), or ``"cpu"`` (no discrete accelerator detected).
    - ``chip``: the chip / GPU name when known, else None.
    - ``bandwidth_gbs``: memory bandwidth in GB/s when known, else None. This is
      the ceiling on decode throughput; token generation reads the whole active
      model from memory once per token, so tokens/s scales with it.

    Bandwidth is only tabulated for Apple Silicon here (published specs);
    discrete-GPU bandwidth is left None because VRAM size, not bandwidth, is the
    binding constraint the catalog already models, and the figure varies by
    exact board. Callers treat a None bandwidth as "throughput not estimated".
    """
    vendor = chip_vendor()
    if vendor == "apple":
        chip = chip_name()
        return {
            "accelerator": "gpu-metal",
            "chip": chip,
            "bandwidth_gbs": _apple_bandwidth_gbs(chip),
        }
    if vendor == "nvidia":
        return {"accelerator": "gpu-cuda", "chip": None, "bandwidth_gbs": None}
    if vendor == "amd":
        return {"accelerator": "gpu-rocm", "chip": None, "bandwidth_gbs": None}
    return {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None}


def _nvidia_vram_gb() -> float | None:
    """
    Sum VRAM across all visible NVIDIA GPUs using nvidia-smi.

    Returns
    -------
    float or None
        Total VRAM in GB, or None if nvidia-smi is unavailable.
    """
    out = _run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]
    )
    if not out.strip():
        return None
    total_mib = 0.0
    for line in out.strip().splitlines():
        try:
            total_mib += float(line.strip())
        except ValueError:
            continue
    return total_mib / 1024.0 if total_mib > 0 else None


def _amd_vram_gb() -> float | None:
    """
    Read VRAM from ROCm's rocm-smi on AMD Linux systems.

    Returns
    -------
    float or None
        VRAM in GB, or None if rocm-smi is unavailable or reports nothing.
    """
    out = _run(["rocm-smi", "--showmeminfo", "vram"])
    for line in out.splitlines():
        # Typical line: "GPU[0]         : VRAM Total Memory (B): 17163091968"
        if "VRAM Total Memory" in line and "B)" in line:
            _, _, val = line.partition(":")
            try:
                return float(val.strip()) / (1024 ** 3)
            except ValueError:
                continue
    return None


def _ram_gb_psutil() -> float:
    """
    Return total system RAM in GB using psutil.

    psutil is a mandatory runtime dependency so this never raises ImportError.

    Returns
    -------
    float
        Total RAM in GB.
    """
    import psutil  # always available as a declared dependency

    return psutil.virtual_memory().total / (1024 ** 3)


def available_memory() -> dict[str, float | None]:
    """
    Detect available memory for model inference.

    Probes in priority order:
    1. Apple Silicon unified memory (macOS with Apple chip)
    2. NVIDIA VRAM via nvidia-smi
    3. AMD VRAM via rocm-smi
    4. System RAM via psutil (always populated)

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
    plat = platform_name()

    unified_gb: float | None = None
    vram_gb: float | None = None
    ram_gb: float = _ram_gb_psutil()

    if plat == "darwin":
        # On Apple Silicon, the unified pool is the inference budget
        unified_gb = _apple_unified_gb()
    else:
        # Prefer NVIDIA over AMD when both are present (unusual but possible)
        vram_gb = _nvidia_vram_gb()
        if vram_gb is None:
            vram_gb = _amd_vram_gb()

    return {
        "unified_gb": unified_gb,
        "vram_gb": vram_gb,
        "ram_gb": ram_gb,
    }
