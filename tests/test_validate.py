"""
Tests for the Ralph validation gates (validate_llm, validate_vlm).

The gates are pure functions of an injected ``llm_chat`` callable, so both the
model and (for the prose gate) the underlying prose loop are stubbed. The VLM
gate renders its reference PNG with Pillow, so the module is skipped without it.
"""

from __future__ import annotations

from typing import Any

import pytest

from best_engine_ai_helper import ralph, validate_llm, validate_vlm

pytest.importorskip("PIL")  # validate_vlm renders its fixture with Pillow


def test_validate_llm_gate_passes_only_when_violations_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_chat = lambda *a, **k: ""  # noqa: E731 - the gate ignores it once prose_loop is stubbed

    # Both fixtures cleaned (em dash and "Par ailleurs" gone) -> gate passes.
    monkeypatch.setattr(
        ralph,
        "prose_loop",
        lambda text, **kw: text.replace("—", ",").replace("Par ailleurs", "Donc"),
    )
    assert validate_llm.validate(stub_chat) is True

    # The English em dash survives -> gate fails at the English check.
    monkeypatch.setattr(ralph, "prose_loop", lambda text, **kw: text)
    assert validate_llm.validate(stub_chat) is False

    # English cleaned but the French "Par ailleurs" seam survives -> fails at
    # the French check instead (the second fixture's failure path).
    monkeypatch.setattr(ralph, "prose_loop", lambda text, **kw: text.replace("—", ","))
    assert validate_llm.validate(stub_chat) is False


def test_validate_vlm_gate_reads_the_verdict() -> None:
    def _chat(passes: bool) -> Any:
        def chat(_prompt: str, **kw: Any) -> Any:
            if kw.get("images"):
                return "low-contrast bar and a clipped label" if passes else "looks fine"
            return {"pass": passes, "reason": "..."}

        return chat

    assert validate_vlm.validate(_chat(True)) is True
    assert validate_vlm.validate(_chat(False)) is False

    # A verdict that isn't valid JSON is treated as a failure, not a crash.
    def malformed(_prompt: str, **kw: Any) -> Any:
        return "reviewer says it's fine" if kw.get("images") else "not json at all"

    assert validate_vlm.validate(malformed) is False
