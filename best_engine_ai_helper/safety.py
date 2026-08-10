"""
safety — NSFW / policy scanning for cloud calls (Phase 6.5).

Scans text (an outbound prompt before it leaves the machine, or an inbound
response after it arrives) and images (outbound only — nothing arrives as
image bytes in a response today) for policy violations, and enforces a
configurable action: ``block`` (raise), ``redact`` (text only — swap in a
placeholder), or ``warn`` (log only, pass through unchanged). Every decision
is logged via ``os_helper`` regardless of action, so a warn-mode deployment
still keeps a full audit trail.

Real classifiers are optional (the ``[filtered]`` extra, both via
``transformers``): a DistilBERT model fine-tuned specifically for NSFW/sexual
text for text, a ViT NSFW/normal classifier for images. Absent them, text
scanning falls back to a deterministic keyword heuristic — crude, but it
never silently no-ops. Image scanning has no comparable safe heuristic (a
wrong guess is worse than an honest "I don't know"), so it degrades to
``"unavailable"`` rather than fabricate a verdict.

Model choices, and why (see ``.private/keep-track.md`` for the full
evaluation this repo ran before picking them):

- **Text**: ``eliasalbouzidi/distilbert-nsfw-text-classifier``, not
  Detoxify. Detoxify scores general TOXICITY (hate/insult/threat/obscenity);
  on a hand-built probe set, sexual-but-not-abusive text scored 0.01-0.40 on
  Detoxify (below this module's own 0.8 default threshold — Detoxify would
  have MISSED it) but 0.99+ on the NSFW-specific model. For a module whose
  job is NSFW filtering, a classifier trained for NSFW/sexual content beats
  one trained for something adjacent but different.
- **Image**: ``Falconsai/nsfw_image_detection`` (kept, not swapped to
  LAION's ``CLIP-based-NSFW-Detector``, despite LAION's detector being the
  more widely-cited one — it's what filtered LAION-5B, the dataset behind
  Stable Diffusion). Real, independently-run evaluation on LAION's own
  public, manually-annotated test set (``nsfw_testset.zip``, ViT-L/14
  embeddings, this module's 0.8 threshold): 96.16% accuracy, 94.56% recall,
  97.58% precision, 2.29% false-positive rate — solid, and verifiable by
  anyone. But LAION's *documented* loading path needs a SECOND deep-learning
  framework (TensorFlow) plus the unmaintained ``autokeras`` and OpenAI
  ``clip`` packages, downloads an un-versioned zip from a GitHub raw URL at
  runtime, and — found while running this exact evaluation — its packaged
  TensorFlow SavedModel no longer loads through Keras 3's own
  ``load_model()``; only a manual, undocumented ``tf.saved_model.load(...)
  .signatures["serving_default"]`` workaround gets it working today. That's
  too fragile to ship. Falconsai self-reports 98.04% accuracy (not
  independently verified here — no raw NSFW imagery was fetched to test
  it; unlike CLIP embeddings, raw image bytes of that content are not
  something this evaluation will download or store) but needs only
  ``transformers``, the same single framework already used for text above,
  with no legacy-package or un-versioned-download risk.

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
from typing import Any, Literal

import os_helper as osh

Action = Literal["block", "redact", "warn"]

DEFAULT_ACTION: Action = "warn"
DEFAULT_THRESHOLD: float = 0.8

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
_CLIP_CLASSIFIER: Any = None


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


def _cached_clip_classifier() -> Any:
    """Load the CLIP-based NSFW image classifier once per process."""
    global _CLIP_CLASSIFIER
    if _CLIP_CLASSIFIER is None:
        from transformers import pipeline

        _CLIP_CLASSIFIER = pipeline("image-classification", model="Falconsai/nsfw_image_detection")
    return _CLIP_CLASSIFIER


def scan_image(image_bytes: bytes) -> dict[str, Any]:
    """
    Score an image for NSFW content.

    Uses a CLIP-based NSFW detector (the ``[filtered]`` extra, pulls in
    ``transformers`` + ``Pillow`` + a torch backend) when installed. No
    heuristic fallback exists for images — a wrong guess is worse than an
    honest "unavailable" — so this degrades to that instead of fabricating a
    score.

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
        classifier = _cached_clip_classifier()
    except ImportError:
        return {"score": 0.0, "label": "unavailable", "backend": "unavailable"}

    image = Image.open(io.BytesIO(image_bytes))
    result = classifier(image)
    nsfw = next((r for r in result if str(r["label"]).lower() == "nsfw"), None)
    score = float(nsfw["score"]) if nsfw else 0.0
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
