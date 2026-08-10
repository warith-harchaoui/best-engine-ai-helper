"""
Tests for best_engine_ai_helper.detect.

Raw hardware probing (subprocess calls to nvidia-smi / rocm-smi /
system_profiler / lspci, CPU/RAM introspection) lives in
``os_helper.hardware_utils`` and is tested there. This module only tests the
AI-throughput layer built on top: the bandwidth lookup tables (Apple, NVIDIA,
AMD), ``compute_profile()``, ``available_memory()``, and the live-load probe.
Tests patch the local wrapper functions (``detect.chip_vendor`` /
``detect.chip_name``) or the ``os_helper`` calls directly, so every vendor
branch runs deterministically without needing the tools that back it installed.
"""

from __future__ import annotations

import pytest

from best_engine_ai_helper import detect


def test_platform_chip_and_bandwidth_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    assert detect.platform_name() == osh.platform_name()
    assert detect.platform_name() in ("darwin", "linux", "windows")

    monkeypatch.setattr(osh, "gpu_vendor", lambda: "nvidia")
    assert detect.chip_vendor() == "nvidia"
    monkeypatch.setattr(osh, "apple_chip_name", lambda: "Apple M2 Max")
    assert detect.chip_name() == "Apple M2 Max"

    table = {"RTX 4070": 504.2, "RTX 4070 Ti": 999.0}
    # The longer label ('RTX 4070 Ti') must win over the shorter substring
    # ('RTX 4070') when both match the detected name.
    assert detect._bandwidth_from_table("NVIDIA GeForce RTX 4070 Ti", table) == 999.0
    assert detect._bandwidth_from_table("NVIDIA GeForce RTX 4070", table) == 504.2
    assert detect._bandwidth_from_table("Some Unknown GPU", table) is None
    assert detect._bandwidth_from_table(None, table) is None

    # The most specific label wins: 'M2 Max' resolves to 400, not the base 'M2'.
    assert detect._apple_bandwidth_gbs("Apple M2 Max") == 400.0
    assert detect._apple_bandwidth_gbs("Apple M1 Ultra") == 800.0
    assert detect._apple_bandwidth_gbs(None) is None
    assert detect._apple_bandwidth_gbs("Some Unknown Chip") is None

    assert (
        detect._bandwidth_from_table("NVIDIA GeForce RTX 4090", detect._NVIDIA_BANDWIDTH_GBS)
        == 1008.0
    )
    assert (
        detect._bandwidth_from_table("AMD Radeon RX 7900 XTX", detect._AMD_BANDWIDTH_GBS) == 960.0
    )


def test_compute_profile_all_vendors(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(detect, "chip_name", lambda: "Apple M2 Max")
    assert detect.compute_profile() == {
        "accelerator": "gpu-metal",
        "chip": "Apple M2 Max",
        "bandwidth_gbs": 400.0,
    }

    # Regression guard: before the NVIDIA/AMD bandwidth tables existed,
    # compute_profile() always returned bandwidth_gbs=None off Apple Silicon,
    # so estimated_tokens_per_second() could never produce a number on a
    # discrete GPU. A known GPU name must now resolve a real figure.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        osh,
        "gpus",
        lambda: [{"vendor": "nvidia", "name": "NVIDIA GeForce RTX 4090", "vram_gb": 24.0}],
    )
    nvidia_prof = detect.compute_profile()
    assert nvidia_prof == {
        "accelerator": "gpu-cuda",
        "chip": "NVIDIA GeForce RTX 4090",
        "bandwidth_gbs": 1008.0,
    }

    monkeypatch.setattr(detect, "chip_vendor", lambda: "amd")
    monkeypatch.setattr(
        osh,
        "gpus",
        lambda: [{"vendor": "amd", "name": "Radeon RX 7900 XTX", "vram_gb": 24.0}],
    )
    amd_prof = detect.compute_profile()
    assert amd_prof == {
        "accelerator": "gpu-rocm",
        "chip": "Radeon RX 7900 XTX",
        "bandwidth_gbs": 960.0,
    }

    # A brand-new SKU not yet in the table: chip is still reported, bandwidth
    # (and therefore the downstream tokens/s estimate) is honestly None.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        osh,
        "gpus",
        lambda: [{"vendor": "nvidia", "name": "NVIDIA RTX 9999", "vram_gb": 48.0}],
    )
    unknown_prof = detect.compute_profile()
    assert unknown_prof == {
        "accelerator": "gpu-cuda",
        "chip": "NVIDIA RTX 9999",
        "bandwidth_gbs": None,
    }

    # No GPU name at all (nvidia-smi returned nothing usable).
    monkeypatch.setattr(osh, "gpus", lambda: [])
    no_gpu_prof = detect.compute_profile()
    assert no_gpu_prof == {"accelerator": "gpu-cuda", "chip": None, "bandwidth_gbs": None}

    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    assert detect.compute_profile() == {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None}
    monkeypatch.setattr(detect, "chip_vendor", lambda: "intel")
    intel_prof = detect.compute_profile()
    assert intel_prof["accelerator"] == "cpu" and intel_prof["chip"] is None


def test_available_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    monkeypatch.setattr(osh, "ram_gb", lambda: 64.0)

    # Apple Silicon: unified pool populated, discrete VRAM left None.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(osh, "apple_unified_memory_gb", lambda: 96.0)
    apple_mem = detect.available_memory()
    assert (apple_mem["unified_gb"], apple_mem["vram_gb"], apple_mem["ram_gb"]) == (
        96.0,
        None,
        64.0,
    )

    # Discrete GPU: VRAM populated by summing every visible card, unified None.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        osh,
        "gpus",
        lambda: [
            {"vendor": "nvidia", "name": "RTX 4090", "vram_gb": 24.0},
            {"vendor": "nvidia", "name": "RTX 4090", "vram_gb": 24.0},
        ],
    )
    gpu_mem = detect.available_memory()
    assert (gpu_mem["unified_gb"], gpu_mem["vram_gb"]) == (None, 48.0)

    # CPU-only: neither pool populated, RAM always is.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    cpu_mem = detect.available_memory()
    assert (cpu_mem["unified_gb"], cpu_mem["vram_gb"], cpu_mem["ram_gb"]) == (None, None, 64.0)

    # Public contract on the REAL machine running this test, no mocking.
    monkeypatch.undo()
    real_mem = detect.available_memory()
    assert set(real_mem) == {"unified_gb", "vram_gb", "ram_gb"}
    assert isinstance(real_mem["ram_gb"], float) and real_mem["ram_gb"] > 0
    for key in ("unified_gb", "vram_gb"):
        assert real_mem[key] is None or (isinstance(real_mem[key], float) and real_mem[key] > 0)


def test_server_load_and_running_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    import os_helper as osh

    monkeypatch.setattr(
        osh,
        "hardware_info",
        lambda: {
            "cpu": {"percent": 42.0},
            "available_ram_gb": 12.3,
            "disk": {"free_gb": 55.0, "percent_used": 80.0},
            "gpu_utilization_percent": 7.0,
        },
    )
    monkeypatch.setattr(detect, "_running_engines", lambda: 2)
    load = detect.server_load()
    assert load == {
        "available_ram_gb": 12.3,
        "cpu_percent": 42.0,
        "gpu_percent": 7.0,
        "disk_free_gb": 55.0,
        "disk_percent_used": 80.0,
        "running_engines": 2,
    }
    monkeypatch.undo()  # restore the REAL _running_engines for the checks below

    class _FakeResponse:
        ok = True

        def json(self) -> dict:
            return {"models": [{"name": "qwen3:8b"}, {"name": "gemma3:12b"}]}

    class _FakeProc:
        def __init__(self, cmdline: list[str]) -> None:
            self.info = {"cmdline": cmdline}

    import psutil

    monkeypatch.setattr("requests.get", lambda url, timeout: _FakeResponse())
    monkeypatch.setattr(
        psutil,
        "process_iter",
        lambda fields: iter(
            [
                _FakeProc(["python", "-m", "vllm.entrypoints.openai.api_server"]),
                _FakeProc(["some-other-process"]),
            ]
        ),
    )
    # 2 Ollama-loaded models + 1 matching vLLM process.
    assert detect._running_engines() == 3

    def _raise(*args: object, **kwargs: object) -> None:
        raise ConnectionError("no daemon")

    monkeypatch.setattr("requests.get", _raise)
    monkeypatch.setattr(psutil, "process_iter", lambda fields: iter([]))
    assert detect._running_engines() == 0
