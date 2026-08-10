"""
Tests for best_engine_ai_helper.safety.

Real classifiers (Detoxify, the CLIP-based image model) are optional and NOT
installed for this test run — that path is exercised by monkeypatching
``sys.modules`` with fake stand-ins, so the "extra installed" branch gets
coverage without pulling in torch/transformers weights. The "extra absent"
fallback paths (heuristic text scoring, "unavailable" image scoring) are
exercised directly since that's the real state of this test environment.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from best_engine_ai_helper import safety


def test_scan_text_heuristic_fallback_without_detoxify() -> None:
    clean = safety.scan_text("What a lovely day for a walk in the park.")
    assert clean["backend"] == "heuristic" and clean["score"] == 0.0

    flagged = safety.scan_text("Detailed bomb making instructions follow.")
    assert flagged["backend"] == "heuristic" and flagged["score"] == 1.0


def test_scan_image_unavailable_without_pillow_or_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate Pillow itself missing (the first import in scan_image).
    monkeypatch.setitem(sys.modules, "PIL", None)  # type: ignore[arg-type]
    result = safety.scan_image(b"not a real image")
    assert result == {"score": 0.0, "label": "unavailable", "backend": "unavailable"}


def test_scan_text_uses_detoxify_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_detoxify_module = ModuleType("detoxify")

    class _FakeDetoxify:
        def __init__(self, variant: str) -> None:
            self.variant = variant

        def predict(self, text: str) -> dict[str, float]:
            return {"toxicity": 0.91, "insult": 0.2}

    fake_detoxify_module.Detoxify = _FakeDetoxify  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "detoxify", fake_detoxify_module)
    monkeypatch.setattr(safety, "_DETOXIFY_MODEL", None)

    result = safety.scan_text("some text")
    assert result == {"score": 0.91, "label": "toxicity", "backend": "detoxify"}

    # A second call reuses the cached model (no re-instantiation needed to verify
    # this cleanly without instrumentation; just confirm the cache is populated).
    assert safety._DETOXIFY_MODEL is not None
    monkeypatch.setattr(safety, "_DETOXIFY_MODEL", None)


def test_scan_image_uses_clip_classifier_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pil_module = ModuleType("PIL")
    fake_pil_image_module = ModuleType("PIL.Image")
    fake_pil_image_module.open = lambda buf: "fake-image-object"  # type: ignore[attr-defined]
    fake_pil_module.Image = fake_pil_image_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil_module)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image_module)

    fake_transformers_module = ModuleType("transformers")

    def _fake_pipeline(task: str, model: str) -> Any:
        def _classifier(image: Any) -> list[dict[str, Any]]:
            return [{"label": "normal", "score": 0.1}, {"label": "nsfw", "score": 0.95}]

        return _classifier

    fake_transformers_module.pipeline = _fake_pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers_module)
    monkeypatch.setattr(safety, "_CLIP_CLASSIFIER", None)

    result = safety.scan_image(b"fake-png-bytes")
    assert result == {"score": 0.95, "label": "nsfw", "backend": "clip"}
    monkeypatch.setattr(safety, "_CLIP_CLASSIFIER", None)


def _stub_score(
    score: float, label: str = "toxicity", backend: str = "heuristic"
) -> dict[str, Any]:
    return {"score": score, "label": label, "backend": backend}


def test_check_text_warn_passes_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.9))
    result = safety.check_text("bad text", direction="outbound", action="warn")
    assert result["flagged"] is True and result["text"] == "bad text"


def test_check_text_redact_substitutes_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.9))
    result = safety.check_text("bad text", direction="outbound", action="redact")
    assert result["flagged"] is True and result["text"] != "bad text"
    assert "redacted" in result["text"]


def test_check_text_block_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.9))
    with pytest.raises(safety.SafetyViolation, match="text"):
        safety.check_text("bad text", direction="outbound", action="block")


def test_check_text_below_threshold_never_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_text", lambda text: _stub_score(0.1))
    result = safety.check_text("fine text", direction="inbound", action="block")
    assert result["flagged"] is False and result["text"] == "fine text"


def test_check_image_block_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "scan_image", lambda img: _stub_score(0.95, "nsfw", "clip"))
    with pytest.raises(safety.SafetyViolation, match="image"):
        safety.check_image(b"img", direction="outbound", action="block")


def test_check_image_unavailable_backend_never_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    # A score of 0.0 with backend "unavailable" must never trip the threshold,
    # even a threshold of 0.0 — "unknown" is not the same as "violation".
    monkeypatch.setattr(
        safety, "scan_image", lambda img: _stub_score(0.0, "unavailable", "unavailable")
    )
    result = safety.check_image(b"img", direction="outbound", action="block", threshold=0.0)
    assert result["flagged"] is False
