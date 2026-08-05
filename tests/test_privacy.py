"""
Tests for best_engine_ai_helper.privacy — local-LLM surrogate pseudonymization.

The local model is mocked (no network), so the tests exercise the substitution,
consistency, collision and restore logic deterministically.
"""

from __future__ import annotations

from best_engine_ai_helper import llm, privacy

_ENGINE = {"backend": "ollama", "base_url": "http://localhost:11434",
           "llm": {"model": "qwen3:8b"}}


def test_pseudonymize_and_restore_roundtrip(monkeypatch) -> None:
    text = "Marie lives in Lyon and works at Acme. Marie loves Lyon."
    fake = {"entities": [
        {"text": "Marie", "type": "person", "surrogate": "Claudine"},
        {"text": "Lyon", "type": "city", "surrogate": "Paris"},
        {"text": "Acme", "type": "organisation", "surrogate": "Globex"},
    ]}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: fake)

    scrubbed, mapping = privacy.pseudonymize(text, _ENGINE, locale="en_US")
    # Originals gone, surrogates present — every occurrence (consistency).
    for original in ("Marie", "Lyon", "Acme"):
        assert original not in scrubbed
    assert scrubbed.count("Claudine") == 2 and scrubbed.count("Paris") == 2
    assert mapping == {"Claudine": "Marie", "Paris": "Lyon", "Globex": "Acme"}
    # Restore is the exact inverse.
    assert privacy.restore(scrubbed, mapping) == text


def test_restore_handles_possessive_morphology() -> None:
    # A following apostrophe still restores (Claudine's -> Marie's).
    assert privacy.restore("Claudine's book", {"Claudine": "Marie"}) == "Marie's book"
    # A surrogate inside a larger word is NOT touched.
    assert privacy.restore("Parisian food", {"Paris": "Lyon"}) == "Parisian food"


def test_pseudonymize_skips_noise(monkeypatch) -> None:
    # Empty / identical / too-short spans are ignored, not substituted.
    fake = {"entities": [
        {"text": "A", "type": "x", "surrogate": "B"},          # too short
        {"text": "Bob", "type": "person", "surrogate": "Bob"},  # identical
        {"text": "", "type": "x", "surrogate": "Z"},            # empty
    ]}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: fake)
    scrubbed, mapping = privacy.pseudonymize("A Bob here", _ENGINE)
    assert scrubbed == "A Bob here" and mapping == {}
