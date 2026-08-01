"""
Tests for best_engine_ai_helper.detect.

The hardware probes shell out to system_profiler / nvidia-smi / rocm-smi /
lspci. Rather than depend on which tools a CI box happens to have, these tests
patch ``detect._run`` to feed canned tool output, so every vendor and memory
branch runs deterministically. One test keeps the real machine's public
contract (``available_memory`` shape) honest.
"""

from __future__ import annotations

import sys

import pytest

from best_engine_ai_helper import detect

# A representative macOS ``system_profiler SPHardwareDataType`` excerpt.
_MAC_HW = (
    "Hardware:\n"
    "    Hardware Overview:\n"
    "      Model Name: MacBook Pro\n"
    "      Chip: Apple M2 Max\n"
    "      Memory: 96 GB\n"
)


def _fake_run(mapping: dict[str, str]):
    """Return a ``_run`` replacement yielding ``mapping[cmd[0]]`` (default '')."""
    def run(cmd: list[str], **kw: object) -> str:
        return mapping.get(cmd[0], "")
    return run


def test_chip_vendor_detects_each_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each vendor is selected by the first probe that returns non-empty output.
    cases = [
        ("darwin", {"system_profiler": _MAC_HW}, "apple"),
        ("linux", {"nvidia-smi": "GPU 0: NVIDIA RTX 4090 (UUID: ...)"}, "nvidia"),
        ("linux", {"rocm-smi": "GPU[0]: 1002"}, "amd"),
        ("linux", {"lspci": "01:00.0 VGA compatible controller: Intel Arc"}, "intel"),
        ("linux", {}, "cpu"),
    ]
    for plat, mapping, expected in cases:
        monkeypatch.setattr(detect, "platform_name", lambda p=plat: p)
        monkeypatch.setattr(detect, "_run", _fake_run(mapping))
        assert detect.chip_vendor() == expected, f"{plat} / {mapping}"


def test_platform_name_matches_sys_platform() -> None:
    result = detect.platform_name()
    assert result in ("darwin", "linux", "windows")
    if sys.platform.startswith("darwin"):
        assert result == "darwin"
    elif sys.platform.startswith("win"):
        assert result == "windows"
    else:
        assert result == "linux"


def test_parse_memory_gb_units_and_garbage() -> None:
    assert detect._parse_memory_gb("96 GB") == 96.0
    assert detect._parse_memory_gb("  8 GB ") == 8.0
    assert detect._parse_memory_gb("32768 MiB") == pytest.approx(32.0)
    assert detect._parse_memory_gb(str(16 * 1024**3)) == pytest.approx(16.0)  # bare bytes
    assert detect._parse_memory_gb("not a number") is None


def test_apple_memory_chip_and_bandwidth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "platform_name", lambda: "darwin")
    monkeypatch.setattr(detect, "_run", _fake_run({"system_profiler": _MAC_HW}))
    assert detect._apple_unified_gb() == 96.0
    assert detect.chip_name() == "Apple M2 Max"
    # The most specific label wins: 'M2 Max' resolves to 400, not the base 'M2'.
    assert detect._apple_bandwidth_gbs("Apple M2 Max") == 400.0
    assert detect._apple_bandwidth_gbs(None) is None
    assert detect._apple_bandwidth_gbs("Some Unknown Chip") is None


def test_compute_profile_per_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "chip_name", lambda: "Apple M2 Max")
    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    assert detect.compute_profile() == {
        "accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0,
    }
    for vendor, accel in [("nvidia", "gpu-cuda"), ("amd", "gpu-rocm"), ("cpu", "cpu")]:
        monkeypatch.setattr(detect, "chip_vendor", lambda v=vendor: v)
        prof = detect.compute_profile()
        assert prof["accelerator"] == accel and prof["chip"] is None


def test_discrete_gpu_vram_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    # nvidia-smi lists one line of MiB per GPU; the sum is converted to GB.
    monkeypatch.setattr(detect, "_run", _fake_run({"nvidia-smi": "24564\n24564\n"}))
    assert detect._nvidia_vram_gb() == pytest.approx(2 * 24564 / 1024, rel=1e-3)
    monkeypatch.setattr(detect, "_run", _fake_run({}))
    assert detect._nvidia_vram_gb() is None
    # rocm-smi reports total VRAM in bytes; the number must follow the first
    # colon on the line (partition(":") keys on that), then convert to GB.
    monkeypatch.setattr(detect, "_run", _fake_run(
        {"rocm-smi": "VRAM Total Memory (B): 17163091968"}))
    assert detect._amd_vram_gb() == pytest.approx(17163091968 / 1024**3, rel=1e-3)


def test_available_memory_selects_pool_by_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "_ram_gb_psutil", lambda: 64.0)
    # Apple Silicon: unified pool populated, discrete VRAM left None.
    monkeypatch.setattr(detect, "platform_name", lambda: "darwin")
    monkeypatch.setattr(detect, "_apple_unified_gb", lambda: 96.0)
    mem = detect.available_memory()
    assert (mem["unified_gb"], mem["vram_gb"], mem["ram_gb"]) == (96.0, None, 64.0)
    # Discrete GPU on Linux: VRAM populated (NVIDIA preferred over AMD), unified None.
    monkeypatch.setattr(detect, "platform_name", lambda: "linux")
    monkeypatch.setattr(detect, "_nvidia_vram_gb", lambda: 24.0)
    monkeypatch.setattr(detect, "_amd_vram_gb", lambda: None)
    mem = detect.available_memory()
    assert (mem["unified_gb"], mem["vram_gb"]) == (None, 24.0)


def test_run_returns_empty_on_missing_binary() -> None:
    # A binary that isn't on PATH must yield '' so probes are simple truthiness
    # checks with no try/except at every call site.
    assert detect._run(["definitely-not-a-real-binary-zzz"]) == ""


def test_available_memory_public_contract_on_this_machine() -> None:
    mem = detect.available_memory()
    assert set(mem) == {"unified_gb", "vram_gb", "ram_gb"}
    assert isinstance(mem["ram_gb"], float) and mem["ram_gb"] > 0
    for key in ("unified_gb", "vram_gb"):
        assert mem[key] is None or (isinstance(mem[key], float) and mem[key] > 0)
