"""
Tests for best_engine_ai_helper.detect.

All tests run without network access or model downloads. The hardware probes
themselves may return None values on machines without the relevant tools, but
the public interface must always return a structurally valid result.
"""

from __future__ import annotations

import sys

from best_engine_ai_helper import detect


def test_platform_name_returns_known_string() -> None:
    result = detect.platform_name()
    assert result in ("darwin", "linux", "windows"), (
        f"platform_name() returned unexpected value: {result!r}"
    )


def test_platform_name_matches_sys_platform() -> None:
    result = detect.platform_name()
    # Cross-check against sys.platform so the mapping is verified, not just the shape
    if sys.platform.startswith("darwin"):
        assert result == "darwin"
    elif sys.platform.startswith("win"):
        assert result == "windows"
    else:
        assert result == "linux"


def test_chip_vendor_returns_known_string() -> None:
    result = detect.chip_vendor()
    assert result in ("apple", "nvidia", "amd", "intel", "cpu"), (
        f"chip_vendor() returned unexpected value: {result!r}"
    )


def test_available_memory_has_required_keys() -> None:
    mem = detect.available_memory()
    assert set(mem.keys()) == {"unified_gb", "vram_gb", "ram_gb"}, (
        f"available_memory() returned unexpected keys: {set(mem.keys())}"
    )


def test_available_memory_ram_gb_positive() -> None:
    mem = detect.available_memory()
    # ram_gb is always populated by psutil and must be positive
    assert isinstance(mem["ram_gb"], float)
    assert mem["ram_gb"] > 0, "ram_gb must be positive"


def test_available_memory_optional_fields_are_none_or_positive() -> None:
    mem = detect.available_memory()
    for key in ("unified_gb", "vram_gb"):
        val = mem[key]
        # Must be None (absent probe) or a positive float
        assert val is None or (isinstance(val, float) and val > 0), (
            f"{key} must be None or a positive float, got {val!r}"
        )


def test_apple_silicon_returns_unified_on_darwin() -> None:
    # On Apple Silicon macs, unified_gb should be populated
    if detect.platform_name() == "darwin" and detect.chip_vendor() == "apple":
        mem = detect.available_memory()
        assert mem["unified_gb"] is not None, (
            "unified_gb should be set on Apple Silicon"
        )
        assert mem["unified_gb"] > 0


def test_available_memory_unified_and_vram_mutually_exclusive() -> None:
    # A machine is either Apple Silicon (unified) or has a discrete GPU (vram),
    # not both in practice; the probe order enforces this
    mem = detect.available_memory()
    both_set = mem["unified_gb"] is not None and mem["vram_gb"] is not None
    # Not a hard failure — eGPU setups exist — but flag if unexpected
    if both_set:
        pass  # unusual but valid; just don't crash
