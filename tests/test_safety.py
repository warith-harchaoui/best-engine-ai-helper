"""
Tests for best_engine_ai_helper.safety.

Real classifiers (a DistilBERT NSFW text model, a ViT NSFW image model — both
via ``transformers``) are optional and NOT installed for this test run — that
path is exercised by monkeypatching ``sys.modules`` with a fake stand-in, so
the "extra installed" branch gets coverage without pulling in real model
weights. The "extra absent" fallback paths (heuristic text scoring,
"unavailable" image scoring) are exercised directly since that's the real
state of this test environment.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from best_engine_ai_helper import safety


def test_scan_text_and_image_degradation_and_real_classifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = safety.scan_text("What a lovely day for a walk in the park.")
    assert clean["backend"] == "heuristic" and clean["score"] == 0.0
    flagged = safety.scan_text("Detailed bomb making instructions follow.")
    assert flagged["backend"] == "heuristic" and flagged["score"] == 1.0

    # Simulate Pillow itself missing (the first import in scan_image).
    monkeypatch.setitem(sys.modules, "PIL", None)  # type: ignore[arg-type]
    unavailable = safety.scan_image(b"not a real image")
    assert unavailable == {"score": 0.0, "label": "unavailable", "backend": "unavailable"}
    monkeypatch.undo()

    fake_pil_module = ModuleType("PIL")
    fake_pil_image_module = ModuleType("PIL.Image")
    fake_pil_image_module.open = lambda buf: "fake-image-object"  # type: ignore[attr-defined]
    fake_pil_module.Image = fake_pil_image_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil_module)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image_module)

    # Text and image both load through `transformers.pipeline` now; the fake
    # module dispatches on `task` the same way the real one dispatches on
    # which model architecture it loads.
    fake_transformers_module = ModuleType("transformers")

    def _fake_pipeline(task: str, model: str, **kw: Any) -> Any:
        if task == "text-classification":

            def _text_classifier(text: str) -> list[list[dict[str, Any]]]:
                return [[{"label": "safe", "score": 0.05}, {"label": "nsfw", "score": 0.95}]]

            return _text_classifier

        def _image_classifier(image: Any) -> list[dict[str, Any]]:
            return [{"label": "normal", "score": 0.1}, {"label": "nsfw", "score": 0.95}]

        return _image_classifier

    fake_transformers_module.pipeline = _fake_pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers_module)

    monkeypatch.setattr(safety, "_TEXT_CLASSIFIER", None)
    text_result = safety.scan_text("some text")
    assert text_result == {"score": 0.95, "label": "nsfw", "backend": "nsfw-distilbert"}
    assert safety._TEXT_CLASSIFIER is not None  # cached for reuse
    monkeypatch.setattr(safety, "_TEXT_CLASSIFIER", None)

    monkeypatch.setattr(safety, "_CLIP_CLASSIFIER", None)
    image_result = safety.scan_image(b"fake-png-bytes")
    assert image_result == {"score": 0.95, "label": "nsfw", "backend": "clip"}
    monkeypatch.setattr(safety, "_CLIP_CLASSIFIER", None)


def _stub_score(score: float, label: str = "nsfw", backend: str = "heuristic") -> dict[str, Any]:
    return {"score": score, "label": label, "backend": backend}


def test_check_text_and_image_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.9))
    warn = safety.check_text("bad text", direction="outbound", action="warn")
    assert warn["flagged"] is True and warn["text"] == "bad text"

    redact = safety.check_text("bad text", direction="outbound", action="redact")
    assert redact["flagged"] is True and redact["text"] != "bad text"
    assert "redacted" in redact["text"]

    with pytest.raises(safety.SafetyViolation, match="text"):
        safety.check_text("bad text", direction="outbound", action="block")

    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.1))
    below_threshold = safety.check_text("fine text", direction="inbound", action="block")
    assert below_threshold["flagged"] is False and below_threshold["text"] == "fine text"

    monkeypatch.setattr(safety, "scan_image", lambda img: _stub_score(0.95, "nsfw", "clip"))
    with pytest.raises(safety.SafetyViolation, match="image"):
        safety.check_image(b"img", direction="outbound", action="block")

    # A score of 0.0 with backend "unavailable" must never trip the threshold,
    # even a threshold of 0.0 — "unknown" is not the same as "violation".
    monkeypatch.setattr(
        safety, "scan_image", lambda img: _stub_score(0.0, "unavailable", "unavailable")
    )
    unavailable = safety.check_image(b"img", direction="outbound", action="block", threshold=0.0)
    assert unavailable["flagged"] is False
