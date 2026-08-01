"""
Tests for best_engine_ai_helper.hardware.

Exercises the bundled hardware.yaml load and the chip lookup function.
Multiple entries per chip name (memory tiers) are an important case because
lookup_chip returns the first match, and callers depend on that behaviour.
"""

from __future__ import annotations

from best_engine_ai_helper import hardware

# ---------------------------------------------------------------------------
# load_hardware — bundled seed
# ---------------------------------------------------------------------------

def test_load_hardware_returns_nonempty_list() -> None:
    entries = hardware.load_hardware()
    assert len(entries) > 0, "Bundled hardware table should have at least one entry"


def test_load_hardware_entries_have_required_keys() -> None:
    required = {"chip", "vendor", "memory_gb", "ollama_usable_gb"}
    entries = hardware.load_hardware()
    for e in entries:
        missing = required - set(e.keys())
        assert not missing, f"Entry {e.get('chip')} missing keys: {missing}"


def test_load_hardware_vendors_are_known() -> None:
    entries = hardware.load_hardware()
    known = {"apple", "nvidia", "amd", "intel"}
    for e in entries:
        assert e["vendor"] in known, (
            f"Entry {e.get('chip')} has unexpected vendor: {e['vendor']!r}"
        )


def test_load_hardware_usable_le_total() -> None:
    # ollama_usable_gb must not exceed the physical memory_gb
    entries = hardware.load_hardware()
    for e in entries:
        assert float(e["ollama_usable_gb"]) <= float(e["memory_gb"]), (
            f"{e['chip']}: ollama_usable_gb ({e['ollama_usable_gb']}) "
            f"> memory_gb ({e['memory_gb']})"
        )


def test_load_hardware_has_apple_and_nvidia() -> None:
    entries = hardware.load_hardware()
    vendors = {e["vendor"] for e in entries}
    assert "apple" in vendors, "Bundled table should include Apple Silicon entries"
    assert "nvidia" in vendors, "Bundled table should include NVIDIA entries"


# ---------------------------------------------------------------------------
# lookup_chip
# ---------------------------------------------------------------------------

def test_lookup_chip_finds_apple_m2_max() -> None:
    hw = hardware.load_hardware()
    entry = hardware.lookup_chip("Apple M2 Max", hw)
    assert entry is not None, "Apple M2 Max should be in the bundled table"
    assert entry["vendor"] == "apple"


def test_lookup_chip_returns_first_match_for_multi_tier_chip() -> None:
    # Apple M2 Max has entries at 32, 64, and 96 GB. The function documents
    # that it returns the first match — callers must know this behaviour.
    hw = hardware.load_hardware()
    entry = hardware.lookup_chip("Apple M2 Max", hw)
    assert entry is not None
    # The seed lists 32 GB as the first M2 Max entry; verify that
    assert float(entry["memory_gb"]) == 32.0, (
        "lookup_chip should return the FIRST match in list order (32 GB for M2 Max)"
    )


def test_lookup_chip_case_insensitive() -> None:
    hw = hardware.load_hardware()
    lower = hardware.lookup_chip("apple m2 max", hw)
    upper = hardware.lookup_chip("APPLE M2 MAX", hw)
    assert lower is not None
    assert upper is not None
    assert lower["chip"] == upper["chip"]


def test_lookup_chip_substring_match() -> None:
    hw = hardware.load_hardware()
    # 'M4 Ultra' should match 'Apple M4 Ultra' entries
    entry = hardware.lookup_chip("M4 Ultra", hw)
    assert entry is not None
    assert "M4 Ultra" in entry["chip"]


def test_lookup_chip_returns_none_for_unknown_chip() -> None:
    hw = hardware.load_hardware()
    result = hardware.lookup_chip("NonExistent GPU 9000", hw)
    assert result is None


def test_lookup_chip_finds_nvidia_rtx_4090() -> None:
    hw = hardware.load_hardware()
    entry = hardware.lookup_chip("RTX 4090", hw)
    assert entry is not None
    assert entry["vendor"] == "nvidia"
    assert float(entry["memory_gb"]) == 24.0


# ---------------------------------------------------------------------------
# detect_local_entry / write_cache — `hardware update` refresh path
# ---------------------------------------------------------------------------

def test_detect_local_entry_apple(monkeypatch) -> None:
    from best_engine_ai_helper import detect

    monkeypatch.setattr(detect, "chip_vendor", lambda: "apple")
    monkeypatch.setattr(
        detect, "compute_profile",
        lambda: {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400},
    )
    monkeypatch.setattr(
        detect, "available_memory",
        lambda: {"unified_gb": 32.0, "vram_gb": None, "ram_gb": 32.0},
    )
    entry = hardware.detect_local_entry(fetched_at="2026-08-01")
    assert entry is not None
    assert entry["chip"] == "Apple M2 Max"
    assert entry["vendor"] == "apple"
    assert entry["memory_gb"] == 32.0
    # 12.5% OS reservation: 32 * 0.875 = 28.
    assert entry["ollama_usable_gb"] == 28.0
    assert entry["source"] == "detected"


def test_detect_local_entry_gpu_without_name(monkeypatch) -> None:
    from best_engine_ai_helper import detect

    monkeypatch.setattr(detect, "chip_vendor", lambda: "nvidia")
    monkeypatch.setattr(
        detect, "compute_profile",
        lambda: {"accelerator": "gpu-cuda", "chip": None, "bandwidth_gbs": None},
    )
    monkeypatch.setattr(
        detect, "available_memory",
        lambda: {"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0},
    )
    entry = hardware.detect_local_entry(fetched_at="2026-08-01")
    assert entry is not None
    # No chip name exposed -> a vendor/accelerator label, and VRAM is the budget.
    assert "NVIDIA" in entry["chip"]
    assert entry["memory_gb"] == 24.0


def test_detect_local_entry_no_memory_returns_none(monkeypatch) -> None:
    from best_engine_ai_helper import detect

    monkeypatch.setattr(detect, "chip_vendor", lambda: "cpu")
    monkeypatch.setattr(
        detect, "compute_profile",
        lambda: {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None},
    )
    monkeypatch.setattr(
        detect, "available_memory",
        lambda: {"unified_gb": None, "vram_gb": None, "ram_gb": 0.0},
    )
    assert hardware.detect_local_entry(fetched_at="2026-08-01") is None


def test_hardware_write_cache_merges_by_chip_and_tier(tmp_path) -> None:
    from pathlib import Path

    import yaml

    cache = Path(tmp_path) / "hardware_cache.yaml"
    a = {
        "chip": "Apple M2 Max", "vendor": "apple", "memory_gb": 32.0,
        "ollama_usable_gb": 28.0, "source": "detected", "fetched_at": "2026-08-01",
    }
    hardware.write_cache([a], cache_path=cache)

    # Same chip + tier overwrites; a different tier appends.
    a2 = dict(a, ollama_usable_gb=29.0, fetched_at="2026-08-02")
    b = dict(a, memory_gb=96.0, ollama_usable_gb=84.0)
    hardware.write_cache([a2, b], cache_path=cache)

    data = yaml.safe_load(cache.read_text(encoding="utf-8"))
    tiers = {(e["chip"], e["memory_gb"]): e for e in data}
    assert set(tiers) == {("Apple M2 Max", 32.0), ("Apple M2 Max", 96.0)}
    assert tiers[("Apple M2 Max", 32.0)]["ollama_usable_gb"] == 29.0
