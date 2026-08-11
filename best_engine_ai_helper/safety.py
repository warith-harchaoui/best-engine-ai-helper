"""
safety — NSFW / policy scanning for cloud calls (Phase 6.5).

Scans text (an outbound prompt before it leaves the machine, or an inbound
response after it arrives) and images (outbound only — nothing arrives as
image bytes in a response today) for policy violations, and enforces a
configurable action: ``block`` (raise), ``redact`` (text only — swap in a
placeholder), or ``warn`` (log only, pass through unchanged). Every decision
is logged via ``os_helper`` regardless of action, so a warn-mode deployment
still keeps a full audit trail.

Real classifiers are optional (the ``[filtered]`` extra): a DistilBERT model
fine-tuned specifically for NSFW/sexual text for text, LAION's CLIP-based
NSFW image classifier for images. Absent them, text scanning falls back to
a deterministic keyword heuristic — crude, but it never silently no-ops.
Image scanning has no comparable safe heuristic (a wrong guess is worse
than an honest "I don't know"), so it degrades to ``"unavailable"`` rather
than fabricate a verdict.

Model choices, and why (see ``.private/keep-track.md`` for the full
evaluation this repo ran before picking them):

- **Text**: ``eliasalbouzidi/distilbert-nsfw-text-classifier`` (via
  ``transformers``), not Detoxify. Detoxify scores general TOXICITY
  (hate/insult/threat/obscenity); on a hand-built probe set, sexual-but-not-
  abusive text scored 0.01-0.40 on Detoxify (below this module's own 0.8
  default threshold — Detoxify would have MISSED it) but 0.99+ on the
  NSFW-specific model. For a module whose job is NSFW filtering, a
  classifier trained for NSFW/sexual content beats one trained for
  something adjacent but different.
- **Image**: LAION's ``CLIP-based-NSFW-Detector`` (ViT-L/14 embeddings via
  ``transformers``'s ``openai/clip-vit-large-patch14`` -> a small MLP head),
  not ``Falconsai/nsfw_image_detection`` (the earlier choice). Real,
  independently-run evaluation on LAION's own public, manually-annotated
  test set (``nsfw_testset.zip``, this module's 0.8 threshold): 96.16%
  accuracy, 94.56% recall, 97.58% precision, 2.29% false-positive rate —
  solid, and verifiable by anyone; Falconsai's 98.04% is self-reported on an
  undisclosed proprietary dataset, not independently checked here (no raw
  NSFW imagery was fetched to test it; unlike CLIP embeddings, raw image
  bytes of that content are not something this evaluation will download or
  store). LAION's classifier head is genuinely CLIP-based (the same
  embedding this module already needs no matter which head it uses is a
  shared-embedding-space, zero-shot-friendly representation, not an
  independent ViT fine-tune with its own idiosyncratic decision boundary),
  and it's what LAION itself used to filter LAION-5B, the dataset behind
  Stable Diffusion.

  LAION's *documented* loading path (``autokeras`` + TensorFlow + OpenAI's
  unmaintained ``clip`` package, downloading an un-versioned zip from a
  GitHub raw URL at runtime) was too fragile to ship as-is — confirmed by
  running it: its packaged TensorFlow SavedModel no longer loads through
  Keras 3's own ``load_model()`` (only an undocumented
  ``tf.saved_model.load(...).signatures["serving_default"]`` workaround got
  it running for the evaluation above). So the classifier head was
  converted once, offline, from that TensorFlow SavedModel to ONNX (via
  ``tf2onnx``) and is bundled directly in this package
  (``models/clip_nsfw_vit_l14.onnx``, ~1.9 MB, see ``models/NOTICE.md`` for
  the MIT-licensed original and the conversion note) — no TensorFlow,
  ``autokeras``, or runtime download needed, just ``onnxruntime`` (a single,
  actively maintained, lightweight package) plus the ``transformers``
  CLIP encoder already needed for the embedding. The conversion was
  verified against the original TensorFlow model on the same public test
  set: only 6 of 3199 samples (0.19%) flip their classification decision at
  the 0.8 threshold, well within normal graph-conversion floating-point
  noise (per-sample score differences concentrate in the 0.3-0.7 range,
  where a sigmoid-shaped output is most sensitive to tiny numeric
  differences; far from that range the two agree closely).

  One correctness pitfall found and fixed while wiring this up: LAION's
  classifier expects L2-*normalized* CLIP embeddings (confirmed by checking
  the test set's own embedding norms, all ≈1.0) — feeding it a raw,
  unnormalized embedding would silently produce nonsense scores. Another:
  ``CLIPModel.get_image_features()``'s return shape has changed across
  ``transformers`` major versions (a plain tensor historically; a wrapped
  ``BaseModelOutputWithPooling`` object in the ``transformers`` version this
  was verified against) — since this project's own ``pyproject.toml`` pins
  ``transformers>=4.30`` with no upper bound, :func:`_clip_image_embedding`
  calls the lower-level, architecturally-stable ``model.vision_model`` +
  ``model.visual_projection`` directly instead of that convenience method,
  to stay correct across that whole version range rather than betting on
  one version's wrapper shape.

Wired into :func:`best_engine_ai_helper.llm.chat` via its ``safety=`` keyword
(defaults to True for every engine, local or cloud): called on the
outbound prompt/images and the inbound response.

Default policy is deliberately ``warn``, not ``block``: this is a new
feature with no track record on real traffic yet, and a false positive that
silently blocks a legitimate cloud call is a worse failure mode than a
logged warning. Raise the bar (``DEFAULT_ACTION = "block"``) once you trust
it on your traffic.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Literal

import os_helper as osh

Action = Literal["block", "redact", "warn"]

DEFAULT_ACTION: Action = "warn"
DEFAULT_THRESHOLD: float = 0.8

# Bundled ONNX conversion of LAION's CLIP-based-NSFW-Detector classifier head
# (see the module docstring and models/NOTICE.md for provenance/license).
_CLIP_NSFW_MODEL_NAME = "openai/clip-vit-large-patch14"
_ONNX_MODEL_PATH = Path(__file__).resolve().parent / "models" / "clip_nsfw_vit_l14.onnx"

# A crude, zero-dependency fallback so text scanning never silently no-ops
# when the real classifier is not installed. NOT a substitute for a real
# classifier — it only catches unambiguous, explicit phrases; most real
# violations will pass through undetected. Install the `[filtered]` extra
# for real coverage.
_FALLBACK_TERMS: tuple[str, ...] = (
    "kill yourself",
    "child sexual abuse",
    "bomb making instructions",
)

_TEXT_CLASSIFIER: Any = None
_CLIP_MODEL: Any = None
_CLIP_PROCESSOR: Any = None
_ONNX_SESSION: Any = None


class SafetyViolation(RuntimeError):
    """Raised when ``action="block"`` and a scan meets the threshold."""

    def __init__(self, direction: str, kind: str, score: float, label: str) -> None:
        self.direction = direction
        self.kind = kind
        self.score = score
        self.label = label
        super().__init__(f"safety block ({direction}, {kind}): label={label!r} score={score:.2f}")


def _fallback_text_score(text: str) -> float:
    """Best-effort text score without the real classifier: 1.0 on an explicit
    hit, else 0.0."""
    lowered = text.lower()
    return 1.0 if any(term in lowered for term in _FALLBACK_TERMS) else 0.0


def _cached_nsfw_text_classifier() -> Any:
    """Load the NSFW text classifier once per process — model load is expensive."""
    global _TEXT_CLASSIFIER
    if _TEXT_CLASSIFIER is None:
        from transformers import pipeline

        _TEXT_CLASSIFIER = pipeline(
            "text-classification",
            model="eliasalbouzidi/distilbert-nsfw-text-classifier",
            top_k=None,
        )
    return _TEXT_CLASSIFIER


def scan_text(text: str) -> dict[str, Any]:
    """
    Score ``text`` for NSFW/sexual content.

    Uses a DistilBERT model fine-tuned specifically for NSFW text (the
    ``[filtered]`` extra) when installed; falls back to a crude keyword
    heuristic otherwise (see the module docstring for why this is not a
    substitute for the real classifier — and why this classifier, not a
    general toxicity one, was chosen for this module's job).

    Parameters
    ----------
    text : str
        Text to scan.

    Returns
    -------
    dict
        ``{"score": float in [0, 1], "label": str, "backend": "nsfw-distilbert"
        | "heuristic"}``.
    """
    try:
        import transformers  # noqa: F401
    except ImportError:
        return {"score": _fallback_text_score(text), "label": "nsfw", "backend": "heuristic"}

    classifier = _cached_nsfw_text_classifier()
    result = classifier(text)[0]
    nsfw_entry = next(r for r in result if r["label"] == "nsfw")
    return {"score": float(nsfw_entry["score"]), "label": "nsfw", "backend": "nsfw-distilbert"}


def _cached_clip_model_and_processor() -> tuple[Any, Any]:
    """Load the CLIP ViT-L/14 encoder + processor once per process."""
    global _CLIP_MODEL, _CLIP_PROCESSOR
    if _CLIP_MODEL is None:
        from transformers import CLIPModel, CLIPProcessor

        _CLIP_MODEL = CLIPModel.from_pretrained(_CLIP_NSFW_MODEL_NAME)
        _CLIP_PROCESSOR = CLIPProcessor.from_pretrained(_CLIP_NSFW_MODEL_NAME)
    return _CLIP_MODEL, _CLIP_PROCESSOR


def _cached_onnx_session() -> Any:
    """Load the bundled LAION NSFW classifier head (ONNX) once per process."""
    global _ONNX_SESSION
    if _ONNX_SESSION is None:
        import onnxruntime

        _ONNX_SESSION = onnxruntime.InferenceSession(
            str(_ONNX_MODEL_PATH), providers=["CPUExecutionProvider"]
        )
    return _ONNX_SESSION


def _clip_image_embedding(image: Any) -> Any:
    """L2-normalized CLIP ViT-L/14 image embedding, shape ``(1, 768)``.

    Calls the architecturally-stable ``vision_model`` + ``visual_projection``
    submodules directly rather than the ``get_image_features()`` convenience
    method, whose return shape has changed across ``transformers`` major
    versions (see the module docstring) — this project's ``transformers``
    pin spans that range.
    """
    import numpy as np

    model, processor = _cached_clip_model_and_processor()
    inputs = processor(images=image, return_tensors="pt")
    vision_out = model.vision_model(pixel_values=inputs["pixel_values"])
    projected = model.visual_projection(vision_out.pooler_output)
    embedding = projected.detach().numpy().astype("float64")
    return embedding / np.linalg.norm(embedding, axis=1, keepdims=True)


def scan_image(image_bytes: bytes) -> dict[str, Any]:
    """
    Score an image for NSFW content.

    Uses LAION's CLIP-based NSFW detector (the ``[filtered]`` extra, pulls in
    ``transformers`` for the CLIP encoder, ``onnxruntime`` for the bundled
    classifier head, and ``Pillow``) when installed. No heuristic fallback
    exists for images — a wrong guess is worse than an honest "unavailable"
    — so this degrades to that instead of fabricating a score.

    Parameters
    ----------
    image_bytes : bytes
        Raw image bytes (PNG/JPEG).

    Returns
    -------
    dict
        ``{"score": float in [0, 1], "label": str, "backend": "clip" |
        "unavailable"}``.
    """
    try:
        from PIL import Image
    except ImportError:
        return {"score": 0.0, "label": "unavailable", "backend": "unavailable"}

    try:
        session = _cached_onnx_session()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        embedding = _clip_image_embedding(image)
    except ImportError:
        return {"score": 0.0, "label": "unavailable", "backend": "unavailable"}

    input_name = session.get_inputs()[0].name
    score = float(session.run(None, {input_name: embedding})[0].reshape(-1)[0])
    return {"score": score, "label": "nsfw", "backend": "clip"}


def check_text(
    text: str,
    *,
    direction: str,
    action: Action = DEFAULT_ACTION,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """
    Scan text and enforce ``action`` when the score meets ``threshold``.

    Every call is logged (info on a clean pass, warning on a flagged score)
    regardless of ``action``, so a warn-mode deployment keeps a full audit
    trail even when nothing is blocked.

    Parameters
    ----------
    text : str
        Text to scan (an outbound prompt or an inbound response).
    direction : str
        ``"outbound"`` or ``"inbound"`` — logged for the audit trail only.
    action : {'block', 'redact', 'warn'}
        What to do when flagged. ``block`` raises :class:`SafetyViolation`.
        ``redact`` returns a placeholder in the result's ``text`` field
        instead of the original — the caller must use that field, not the
        input, when this is set. ``warn`` logs only and passes the original
        text through unchanged.
    threshold : float
        Score at or above which the text is flagged, in [0, 1].

    Returns
    -------
    dict
        ``{"flagged": bool, "score": float, "label": str, "backend": str,
        "text": str}`` — ``text`` is the original, unless ``action="redact"``
        and the text was flagged.

    Raises
    ------
    SafetyViolation
        If ``action == "block"`` and the score meets ``threshold``.
    """
    result = scan_text(text)
    flagged = result["score"] >= threshold
    out_text = text
    if flagged:
        osh.warning(
            f"safety: {direction} text flagged (label={result['label']}, "
            f"score={result['score']:.2f}, backend={result['backend']})"
        )
        if action == "block":
            raise SafetyViolation(direction, "text", result["score"], result["label"])
        if action == "redact":
            out_text = "[redacted by best-engine-ai-helper safety policy]"
    else:
        osh.info(f"safety: {direction} text OK (backend={result['backend']})")
    return {**result, "flagged": flagged, "text": out_text}


def check_image(
    image_bytes: bytes,
    *,
    direction: str,
    action: Action = DEFAULT_ACTION,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """
    Scan an image and enforce ``action`` when the score meets ``threshold``.

    Same contract as :func:`check_text`. ``redact`` has no sensible
    image-level equivalent (there is nothing to substitute an image with),
    so it behaves like ``warn`` here. An ``"unavailable"`` backend (no
    ``[filtered]`` extra installed) never flags — an unknown verdict is not a
    violation.

    Parameters
    ----------
    image_bytes : bytes
        Raw image bytes.
    direction : str
        ``"outbound"`` or ``"inbound"``.
    action : {'block', 'redact', 'warn'}
        See :func:`check_text`.
    threshold : float
        Score at or above which the image is flagged, in [0, 1].

    Returns
    -------
    dict
        ``{"flagged": bool, "score": float, "label": str, "backend": str}``.

    Raises
    ------
    SafetyViolation
        If ``action == "block"`` and the score meets ``threshold``.
    """
    result = scan_image(image_bytes)
    flagged = result["score"] >= threshold and result["backend"] != "unavailable"
    if flagged:
        osh.warning(
            f"safety: {direction} image flagged (score={result['score']:.2f}, "
            f"backend={result['backend']})"
        )
        if action == "block":
            raise SafetyViolation(direction, "image", result["score"], result["label"])
    else:
        osh.info(f"safety: {direction} image OK (backend={result['backend']})")
    return {**result, "flagged": flagged}
