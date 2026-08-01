"""
Tests for best_engine_ai_helper.hardware.

Covers the bundled hardware.yaml load and its invariants, the substring chip
lookup (including the multi-tier "return the first match" contract callers
depend on), and the `hardware update` refresh path (detection -> cache).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from best_engine_ai_helper import detect, hardware


def test_load_hardware_seed_invariants() -> None:
    entries = hardware.load_hardware()
    assert len(entries) > 0
    vendors = {e["vendor"] for e in entries}
    assert {"apple", "nvidia"} <= vendors  # the seed spans Apple Silicon and NVIDIA
    for e in entries:
        assert {"chip", "vendor", "memory_gb", "ollama_usable_gb"} <= e.keys()
        assert e["vendor"] in {"apple", "nvidia", "amd", "intel"}
        # Usable memory is the physical pool minus OS/driver overhead, never more.
        assert float(e["ollama_usable_gb"]) <= float(e["memory_gb"])


def test_lookup_chip_matching_rules() -> None:
    hw = hardware.load_hardware()
    # Case-insensitive substring match; 'M2 Max' finds 'Apple M2 Max'.
    assert hardware.lookup_chip("apple m2 max", hw)["chip"] == \
        hardware.lookup_chip("APPLE M2 MAX", hw)["chip"]
    # Multi-tier chips (M2 Max at 32/64/96 GB) return the FIRST list match (32 GB).
    assert float(hardware.lookup_chip("Apple M2 Max", hw)["memory_gb"]) == 32.0
    # A known discrete GPU resolves with its VRAM.
    rtx = hardware.lookup_chip("RTX 4090", hw)
    assert rtx["vendor"] == "nvidia" and float(rtx["memory_gb"]) == 24.0
    # An unknown chip is a miss, not an error.
    assert hardware.lookup_chip("NonExistent GPU 9000", hw) is None


def test_detect_local_entry_from_detection(monkeypatch) -> None:
    # Apple Silicon: unified pool is the budget; chip name carries through and
    # ollama_usable_gb applies the 12.5% OS reservation (32 * 0.875 = 28).
    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(detect, "compute_profile", lambda: {
        "accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400})
    monkeypatch.setattr(detect, "available_memory",
                        lambda: {"unified_gb": 32.0, "vram_gb": None, "ram_gb": 32.0})
    entry = hardware.detect_local_entry(fetched_at="2026-08-01")
    assert entry["chip"] == "Apple M2 Max" and entry["memory_gb"] == 32.0
    assert entry["ollama_usable_gb"] == 28.0 and entry["source"] == "detected"

    # Discrete GPU without a chip name -> a vendor/accelerator label, VRAM budget.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(detect, "compute_profile",
                        lambda: {"accelerator": "gpu-cuda", "chip": None, "bandwidth_gbs": None})
    monkeypatch.setattr(detect, "available_memory",
                        lambda: {"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0})
    gpu = hardware.detect_local_entry(fetched_at="2026-08-01")
    assert "NVIDIA" in gpu["chip"] and gpu["memory_gb"] == 24.0

    # Nothing usable detected -> nothing worth recording.
    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    monkeypatch.setattr(detect, "compute_profile",
                        lambda: {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None})
    monkeypatch.setattr(detect, "available_memory",
                        lambda: {"unified_gb": None, "vram_gb": None, "ram_gb": 0.0})
    assert hardware.detect_local_entry(fetched_at="2026-08-01") is None


def test_write_cache_upserts_by_chip_and_tier(tmp_path: Path) -> None:
    cache = tmp_path / "hardware_cache.yaml"
    base = {"chip": "Apple M2 Max", "vendor": "apple", "memory_gb": 32.0,
            "ollama_usable_gb": 28.0, "source": "detected", "fetched_at": "2026-08-01"}
    hardware.write_cache([base], cache_path=cache)
    # Same chip + tier overwrites; a different tier appends.
    hardware.write_cache(
        [dict(base, ollama_usable_gb=29.0, fetched_at="2026-08-02"),
         dict(base, memory_gb=96.0, ollama_usable_gb=84.0)],
        cache_path=cache,
    )
    tiers = {(e["chip"], e["memory_gb"]): e for e in yaml.safe_load(cache.read_text())}
    assert set(tiers) == {("Apple M2 Max", 32.0), ("Apple M2 Max", 96.0)}
    assert tiers[("Apple M2 Max", 32.0)]["ollama_usable_gb"] == 29.0
