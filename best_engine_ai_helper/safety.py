"""
safety — NSFW / policy scanning for cloud calls (Phase 6.5).

Scans text (an outbound prompt before it leaves the machine, or an inbound
response after it arrives) and images (outbound only — nothing arrives as
image bytes in a response today) for policy violations, and enforces a
configurable action: ``block`` (raise), ``redact`` (text only — swap in a
placeholder), or ``warn`` (log only, pass through unchanged). Every decision
is logged via ``os_helper`` regardless of action, so a warn-mode deployment
still keeps a full audit trail.

Real classifiers are optional (the ``[filtered]`` extra): Detoxify for text, a
CLIP-based NSFW image classifier for images. Absent them, text scanning falls
back to a deterministic keyword heuristic — crude, but it never silently
no-ops. Image scanning has no comparable safe heuristic (a wrong guess is
worse than an honest "I don't know"), so it degrades to ``"unavailable"``
rather than fabricate a verdict.

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
# when Detoxify is not installed. NOT a substitute for a real classifier —
# it only catches unambiguous, explicit phrases; most real violations will
# pass through undetected. Install the `[filtered]` extra for real coverage.
_FALLBACK_TERMS: tuple[str, ...] = (
    "kill yourself",
    "child sexual abuse",
    "bomb making instructions",
)

_DETOXIFY_MODEL: Any = None
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
    """Best-effort text score without Detoxify: 1.0 on an explicit hit, else 0.0."""
    lowered = text.lower()
    return 1.0 if any(term in lowered for term in _FALLBACK_TERMS) else 0.0


def _cached_detoxify() -> Any:
    """Load Detoxify once per process — model load is expensive."""
    global _DETOXIFY_MODEL
    if _DETOXIFY_MODEL is None:
        from detoxify import Detoxify

        _DETOXIFY_MODEL = Detoxify("original")
    return _DETOXIFY_MODEL


def scan_text(text: str) -> dict[str, Any]:
    """
    Score ``text`` for toxic/NSFW content.

    Uses Detoxify (the ``[filtered]`` extra) when installed; falls back to a
    crude keyword heuristic otherwise (see the module docstring for why this
    is not a substitute for the real classifier).

    Parameters
    ----------
    text : str
        Text to scan.

    Returns
    -------
    dict
        ``{"score": float in [0, 1], "label": str, "backend": "detoxify" |
        "heuristic"}``.
    """
    try:
        import detoxify  # noqa: F401
    except ImportError:
        return {"score": _fallback_text_score(text), "label": "toxicity", "backend": "heuristic"}

    model = _cached_detoxify()
    result = model.predict(text)
    label, score = max(result.items(), key=lambda kv: kv[1])
    return {"score": float(score), "label": str(label), "backend": "detoxify"}


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
