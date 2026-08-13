"""
Tests for best_engine_ai_helper.safety.

Real classifiers (a DistilBERT NSFW text model via ``transformers``; LAION's
CLIP-based NSFW image detector via ``transformers`` + the bundled ONNX
classifier head) are optional and NOT installed for this test run — that
path is exercised by monkeypatching ``sys.modules`` with fake stand-ins, so
the "extra installed" branch gets coverage without pulling in real model
weights or a real ONNX runtime. The "extra absent" fallback paths (heuristic
text scoring, "unavailable" image scoring) are exercised directly since
that's the real state of this test environment.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from best_engine_ai_helper import safety


def test_scan_text_and_image_degradation_and_real_classifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate transformers itself missing so the heuristic-fallback
    # assertions below are deterministic regardless of what's importable in
    # the ambient environment — this suite's shared dev env may already have
    # transformers installed as another sibling package's transitive
    # dependency, which would otherwise make scan_text silently take the
    # real-classifier path here instead of the one under test.
    monkeypatch.setitem(sys.modules, "transformers", None)  # type: ignore[arg-type]
    clean = safety.scan_text("What a lovely day for a walk in the park.")
    assert clean["backend"] == "heuristic" and clean["score"] == 0.0
    flagged = safety.scan_text("Detailed bomb making instructions follow.")
    assert flagged["backend"] == "heuristic" and flagged["score"] == 1.0
    monkeypatch.undo()

    # Simulate Pillow itself missing (the first import in scan_image).
    monkeypatch.setitem(sys.modules, "PIL", None)  # type: ignore[arg-type]
    unavailable = safety.scan_image(b"not a real image")
    assert unavailable == {"score": 0.0, "label": "unavailable", "backend": "unavailable"}
    monkeypatch.undo()

    class _FakeImage:
        def convert(self, mode: str) -> _FakeImage:
            return self

    fake_pil_module = ModuleType("PIL")
    fake_pil_image_module = ModuleType("PIL.Image")
    fake_pil_image_module.open = lambda buf: _FakeImage()  # type: ignore[attr-defined]
    fake_pil_module.Image = fake_pil_image_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil_module)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image_module)

    # Text loads through `transformers.pipeline`; the fake module dispatches
    # on `task` the same way the real one dispatches on which architecture
    # it loads.
    fake_transformers_module = ModuleType("transformers")

    def _fake_pipeline(task: str, model: str, **kw: Any) -> Any:
        def _text_classifier(text: str) -> list[list[dict[str, Any]]]:
            return [[{"label": "safe", "score": 0.05}, {"label": "nsfw", "score": 0.95}]]

        return _text_classifier

    fake_transformers_module.pipeline = _fake_pipeline  # type: ignore[attr-defined]

    # Image embedding loads through `transformers.CLIPModel`/`CLIPProcessor`,
    # calling the low-level `vision_model` + `visual_projection` submodules
    # directly (see safety.py's module docstring for why: the high-level
    # `get_image_features()` convenience method's return shape changed
    # across transformers versions).
    class _FakeTensor:
        def __init__(self, arr: Any) -> None:
            self._arr = arr

        def detach(self) -> _FakeTensor:
            return self

        def numpy(self) -> Any:
            return self._arr

    class _FakeVisionOutput:
        def __init__(self, pooler_output: Any) -> None:
            self.pooler_output = pooler_output

    class _FakeClipModel:
        def vision_model(self, pixel_values: Any) -> _FakeVisionOutput:
            return _FakeVisionOutput(pooler_output="fake-pooled")

        def visual_projection(self, pooler_output: Any) -> _FakeTensor:
            return _FakeTensor(np.full((1, 768), 2.0))

    class _FakeClipProcessor:
        def __call__(self, images: Any, return_tensors: str) -> dict[str, Any]:
            return {"pixel_values": "fake-pixel-values"}

    fake_transformers_module.CLIPModel = type(  # type: ignore[attr-defined]
        "CLIPModel", (), {"from_pretrained": staticmethod(lambda name: _FakeClipModel())}
    )
    fake_transformers_module.CLIPProcessor = type(  # type: ignore[attr-defined]
        "CLIPProcessor", (), {"from_pretrained": staticmethod(lambda name: _FakeClipProcessor())}
    )
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers_module)

    # The bundled ONNX classifier head loads through `onnxruntime`.
    class _FakeOnnxInput:
        name = "input_1"

    class _FakeOnnxSession:
        def __init__(self, path: str, providers: list[str]) -> None:
            pass

        def get_inputs(self) -> list[_FakeOnnxInput]:
            return [_FakeOnnxInput()]

        def run(self, output_names: Any, input_feed: dict[str, Any]) -> list[Any]:
            return [np.array([[0.95]])]

    fake_onnxruntime_module = ModuleType("onnxruntime")
    fake_onnxruntime_module.InferenceSession = _FakeOnnxSession  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_onnxruntime_module)

    monkeypatch.setattr(safety, "_TEXT_CLASSIFIER", None)
    text_result = safety.scan_text("some text")
    assert text_result == {"score": 0.95, "label": "nsfw", "backend": "nsfw-distilbert"}
    assert safety._TEXT_CLASSIFIER is not None  # cached for reuse
    monkeypatch.setattr(safety, "_TEXT_CLASSIFIER", None)

    monkeypatch.setattr(safety, "_CLIP_MODEL", None)
    monkeypatch.setattr(safety, "_CLIP_PROCESSOR", None)
    monkeypatch.setattr(safety, "_ONNX_SESSION", None)
    image_result = safety.scan_image(b"fake-png-bytes")
    assert image_result == {"score": 0.95, "label": "nsfw", "backend": "clip"}
    assert safety._CLIP_MODEL is not None and safety._ONNX_SESSION is not None  # cached
    monkeypatch.setattr(safety, "_CLIP_MODEL", None)
    monkeypatch.setattr(safety, "_CLIP_PROCESSOR", None)
    monkeypatch.setattr(safety, "_ONNX_SESSION", None)

    # With onnxruntime/transformers "installed" (still faked above) but the
    # REAL Pillow decoding genuinely malformed bytes: a decode failure must
    # degrade to "unavailable" too, not crash with an uncaught PIL error.
    monkeypatch.delitem(sys.modules, "PIL", raising=False)
    monkeypatch.delitem(sys.modules, "PIL.Image", raising=False)
    malformed = safety.scan_image(b"not a real image")
    assert malformed == {"score": 0.0, "label": "unavailable", "backend": "unavailable"}
    monkeypatch.setattr(safety, "_ONNX_SESSION", None)


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
