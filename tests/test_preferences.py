"""
Tests for preference persistence.

Two things matter here beyond the round-trip. Preferences are stored apart from
`settings.yaml`, because that file holds API keys and a browser form must never
be in a position to rewrite it. And a form posts strings, so a value has to be
coerced on the way in or it compares wrongly against a float forever after.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from best_engine_ai_helper import config


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "preferences.yaml"
    monkeypatch.setattr(config, "_PREFERENCES_YAML", path)
    return path


def test_no_file_yet_means_defaults_not_an_error(store: Path) -> None:
    prefs = config.load_preferences()

    assert prefs["quality_vs_cost"] == 0.7
    assert prefs["local_only"] is False
    assert not store.exists()


def test_a_saved_value_survives_a_reload(store: Path) -> None:
    config.save_preferences({"quality_vs_cost": 0.2})

    assert config.load_preferences()["quality_vs_cost"] == 0.2


def test_saving_one_value_leaves_the_others_alone(store: Path) -> None:
    config.save_preferences({"quality_vs_cost": 0.2})
    config.save_preferences({"headroom": 0.3})

    prefs = config.load_preferences()
    assert prefs["quality_vs_cost"] == 0.2
    assert prefs["headroom"] == 0.3


def test_a_form_posting_strings_still_stores_numbers(store: Path) -> None:
    """A headroom left as "0.4" would compare wrongly against a float forever."""
    config.save_preferences({"headroom": "0.4", "min_tps": "20"})

    prefs = config.load_preferences()
    assert prefs["headroom"] == 0.4
    assert isinstance(prefs["headroom"], float)
    assert prefs["min_tps"] == 20.0


def test_an_unknown_key_is_not_stored(store: Path) -> None:
    """A file that accumulates whatever anyone posted stops being readable."""
    saved = config.save_preferences({"quality_vs_cost": 0.5, "nonsense": "x"})

    assert "nonsense" not in saved
    assert "nonsense" not in store.read_text(encoding="utf-8")


def test_a_value_that_cannot_be_read_is_skipped_not_stored_broken(store: Path) -> None:
    saved = config.save_preferences({"headroom": "not-a-number"})

    assert saved["headroom"] == 0.5  # the default, untouched


def test_a_corrupt_file_falls_back_to_defaults(store: Path) -> None:
    store.write_text("this: [is not: valid", encoding="utf-8")

    assert config.load_preferences()["quality_vs_cost"] == 0.7


def test_preferences_never_live_in_the_file_that_holds_keys() -> None:
    """settings.yaml is secret-bearing; a web form must not be able to rewrite it."""
    assert config._PREFERENCES_YAML.name == "preferences.yaml"
    assert "settings" not in str(config._PREFERENCES_YAML)


def test_a_mutated_result_cannot_corrupt_the_next_read(store: Path) -> None:
    prefs = config.load_preferences()
    prefs["quality_vs_cost"] = 999

    assert config.load_preferences()["quality_vs_cost"] == 0.7
