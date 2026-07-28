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
