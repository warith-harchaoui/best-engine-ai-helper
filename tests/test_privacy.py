"""
Tests for best_engine_ai_helper.privacy — local-LLM surrogate pseudonymization.

The local model is mocked (no network), so the tests exercise the substitution,
consistency, collision, restore, and Presidio-augmentation-degradation logic
deterministically.
"""

from __future__ import annotations

from best_engine_ai_helper import llm, privacy

_ENGINE = {"backend": "ollama", "base_url": "http://localhost:11434", "llm": {"model": "qwen3:8b"}}


def test_pseudonymize_restore_and_presidio_degradation(monkeypatch) -> None:
    text = "Marie lives in Lyon and works at Acme. Marie loves Lyon."
    fake = {
        "entities": [
            {"text": "Marie", "type": "person", "surrogate": "Claudine"},
            {"text": "Lyon", "type": "city", "surrogate": "Paris"},
            {"text": "Acme", "type": "organisation", "surrogate": "Globex"},
        ]
    }
    monkeypatch.setattr(llm, "chat", lambda *a, **k: fake)

    scrubbed, mapping = privacy.pseudonymize(text, _ENGINE, locale="en_US")
    # Originals gone, surrogates present — every occurrence (consistency).
    for original in ("Marie", "Lyon", "Acme"):
        assert original not in scrubbed
    assert scrubbed.count("Claudine") == 2 and scrubbed.count("Paris") == 2
    assert mapping == {"Claudine": "Marie", "Paris": "Lyon", "Globex": "Acme"}
    # Restore is the exact inverse.
    assert privacy.restore(scrubbed, mapping) == text

    # A following apostrophe still restores (Claudine's -> Marie's); a
    # surrogate inside a larger word is NOT touched.
    assert privacy.restore("Claudine's book", {"Claudine": "Marie"}) == "Marie's book"
    assert privacy.restore("Parisian food", {"Paris": "Lyon"}) == "Parisian food"
    # An empty needle is a no-op, never a regex crash.
    assert privacy._replace_word("some text", "", "surrogate") == "some text"

    # Empty / identical / too-short / duplicate spans are ignored, not
    # substituted; a surrogate colliding with text already present is
    # disambiguated deterministically instead of silently overwriting.
    noisy = {
        "entities": [
            {"text": "A", "type": "x", "surrogate": "B"},  # too short
            {"text": "Bob", "type": "person", "surrogate": "Bob"},  # identical
            {"text": "", "type": "x", "surrogate": "Z"},  # empty
            {"text": "Ann", "type": "person", "surrogate": "Ann2"},  # first mapping
            {"text": "Ann", "type": "person", "surrogate": "Ann3"},  # duplicate original
            {"text": "Sam", "type": "person", "surrogate": "here"},  # collides with "here" in text
        ]
    }
    monkeypatch.setattr(llm, "chat", lambda *a, **k: noisy)
    scrubbed2, mapping2 = privacy.pseudonymize("A Bob Ann Sam here", _ENGINE)
    assert "A Bob " in scrubbed2  # too-short/identical/empty spans left untouched
    assert mapping2["Ann2"] == "Ann"  # duplicate original kept the first mapping
    assert "Ann3" not in mapping2
    # "Sam" got a disambiguated surrogate since "here" already collides with
    # existing text.
    sam_surrogate = next(k for k, v in mapping2.items() if v == "Sam")
    assert sam_surrogate != "here"

    # Presidio (the [cloud] extra) is not installed in this test environment:
    # augment_with_presidio degrades to a no-op, entities unchanged.
    entities: list[dict] = [{"text": "x"}]
    assert privacy.augment_with_presidio("some text", entities) == entities
