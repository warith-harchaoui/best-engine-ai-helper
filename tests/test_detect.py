"""
Tests for best_engine_ai_helper.detect.

Raw hardware probing (subprocess calls to nvidia-smi / rocm-smi /
system_profiler / lspci, CPU/RAM introspection) lives in
``os_helper.hardware_utils`` and is tested there. This module only tests the
AI-throughput layer built on top: the bandwidth lookup tables (Apple, NVIDIA,
AMD), ``compute_profile()``, and ``available_memory()``. Tests patch the
local wrapper functions (``detect.chip_vendor`` / ``detect.chip_name``) or the
``os_helper`` calls directly, so every vendor branch runs deterministically
without needing the tools that back it installed.
"""

from __future__ import annotations

import pytest

from best_engine_ai_helper import detect


def test_platform_name_matches_os_helper() -> None:
    import os_helper as osh

    assert detect.platform_name() == osh.platform_name()
    assert detect.platform_name() in ("darwin", "linux", "windows")


def test_chip_vendor_and_chip_name_delegate_to_os_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    monkeypatch.setattr(osh, "gpu_vendor", lambda: "nvidia")
    assert detect.chip_vendor() == "nvidia"
    monkeypatch.setattr(osh, "apple_chip_name", lambda: "Apple M2 Max")
    assert detect.chip_name() == "Apple M2 Max"


def test_bandwidth_from_table_prefers_most_specific_label() -> None:
    table = {"RTX 4070": 504.2, "RTX 4070 Ti": 999.0}
    # The longer label ('RTX 4070 Ti') must win over the shorter substring
    # ('RTX 4070') when both match the detected name.
    assert detect._bandwidth_from_table("NVIDIA GeForce RTX 4070 Ti", table) == 999.0
    assert detect._bandwidth_from_table("NVIDIA GeForce RTX 4070", table) == 504.2
    assert detect._bandwidth_from_table("Some Unknown GPU", table) is None
    assert detect._bandwidth_from_table(None, table) is None


def test_apple_bandwidth_known_and_unknown_chips() -> None:
    # The most specific label wins: 'M2 Max' resolves to 400, not the base 'M2'.
    assert detect._apple_bandwidth_gbs("Apple M2 Max") == 400.0
    assert detect._apple_bandwidth_gbs("Apple M1 Ultra") == 800.0
    assert detect._apple_bandwidth_gbs(None) is None
    assert detect._apple_bandwidth_gbs("Some Unknown Chip") is None


def test_nvidia_and_amd_bandwidth_tables_have_entries() -> None:
    assert detect._bandwidth_from_table(
        "NVIDIA GeForce RTX 4090", detect._NVIDIA_BANDWIDTH_GBS
    ) == 1008.0
    assert detect._bandwidth_from_table(
        "AMD Radeon RX 7900 XTX", detect._AMD_BANDWIDTH_GBS
    ) == 960.0


def test_compute_profile_apple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(detect, "chip_name", lambda: "Apple M2 Max")
    assert detect.compute_profile() == {
        "accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0,
    }


def test_compute_profile_nvidia_and_amd_populate_bandwidth(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression guard: before the NVIDIA/AMD bandwidth tables existed,
    # compute_profile() always returned bandwidth_gbs=None off Apple Silicon,
    # so estimated_tokens_per_second() could never produce a number on a
    # discrete GPU. A known GPU name must now resolve a real figure.
    import os_helper as osh

    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        osh, "gpus",
        lambda: [{"vendor": "nvidia", "name": "NVIDIA GeForce RTX 4090", "vram_gb": 24.0}],
    )
    prof = detect.compute_profile()
    assert prof == {
        "accelerator": "gpu-cuda", "chip": "NVIDIA GeForce RTX 4090", "bandwidth_gbs": 1008.0,
    }

    monkeypatch.setattr(detect, "chip_vendor", lambda: "amd")
    monkeypatch.setattr(
        osh, "gpus",
        lambda: [{"vendor": "amd", "name": "Radeon RX 7900 XTX", "vram_gb": 24.0}],
    )
    prof = detect.compute_profile()
    assert prof == {
        "accelerator": "gpu-rocm", "chip": "Radeon RX 7900 XTX", "bandwidth_gbs": 960.0,
    }


def test_compute_profile_unrecognised_gpu_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os_helper as osh

    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    # A brand-new SKU not yet in the table: chip is still reported, bandwidth
    # (and therefore the downstream tokens/s estimate) is honestly None.
    monkeypatch.setattr(
        osh, "gpus",
        lambda: [{"vendor": "nvidia", "name": "NVIDIA RTX 9999", "vram_gb": 48.0}],
    )
    prof = detect.compute_profile()
    assert prof == {"accelerator": "gpu-cuda", "chip": "NVIDIA RTX 9999", "bandwidth_gbs": None}

    # No GPU name at all (nvidia-smi returned nothing usable).
    monkeypatch.setattr(osh, "gpus", lambda: [])
    prof = detect.compute_profile()
    assert prof == {"accelerator": "gpu-cuda", "chip": None, "bandwidth_gbs": None}


def test_compute_profile_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    assert detect.compute_profile() == {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None}
    monkeypatch.setattr(detect, "chip_vendor", lambda: "intel")
    prof = detect.compute_profile()
    assert prof["accelerator"] == "cpu" and prof["chip"] is None


def test_available_memory_selects_pool_by_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    monkeypatch.setattr(osh, "ram_gb", lambda: 64.0)

    # Apple Silicon: unified pool populated, discrete VRAM left None.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(osh, "apple_unified_memory_gb", lambda: 96.0)
    mem = detect.available_memory()
    assert (mem["unified_gb"], mem["vram_gb"], mem["ram_gb"]) == (96.0, None, 64.0)

    # Discrete GPU: VRAM populated by summing every visible card, unified None.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        osh, "gpus",
        lambda: [
            {"vendor": "nvidia", "name": "RTX 4090", "vram_gb": 24.0},
            {"vendor": "nvidia", "name": "RTX 4090", "vram_gb": 24.0},
        ],
    )
    mem = detect.available_memory()
    assert (mem["unified_gb"], mem["vram_gb"]) == (None, 48.0)

    # CPU-only: neither pool populated, RAM always is.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    mem = detect.available_memory()
    assert (mem["unified_gb"], mem["vram_gb"], mem["ram_gb"]) == (None, None, 64.0)


def test_available_memory_public_contract_on_this_machine() -> None:
    mem = detect.available_memory()
    assert set(mem) == {"unified_gb", "vram_gb", "ram_gb"}
    assert isinstance(mem["ram_gb"], float) and mem["ram_gb"] > 0
    for key in ("unified_gb", "vram_gb"):
        assert mem[key] is None or (isinstance(mem[key], float) and mem[key] > 0)
