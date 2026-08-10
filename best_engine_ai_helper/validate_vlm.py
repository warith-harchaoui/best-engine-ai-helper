"""
validate_vlm — Ralph Eyeball Loop gate for VLM validation.

Validates that the selected vision-language model (VLM) can correctly identify
concrete visual defects in a reference fixture. The test is intentionally
simple and fast: a small PNG with an obvious problem is enough to distinguish
a working VLM from one that is broken, quantized below threshold, or not yet
warmed up.

The fixture contains two seeded defects:
1. A bar with near-zero contrast against the background (accessibility fail).
2. A truncated x-axis label (layout fail).

A VLM that misses both defects fails the gate. A VLM that identifies at least
one is considered functional for the sprezzature visual-critique workflow.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import os_helper as osh

from . import i18n

# ---------------------------------------------------------------------------
# Reference fixture
# ---------------------------------------------------------------------------


def _make_fixture_png() -> bytes:
    """
    Render the reference fixture PNG in memory using Pillow.

    The fixture is a 200x150 white canvas with:
    - A tall red bar (obvious, high-contrast) labelled "A".
    - A near-white bar on white background (accessibility fail — low contrast).
    - A long x-axis label clipped by the canvas edge (layout fail).

    Returns
    -------
    bytes
        PNG bytes of the fixture image.

    Raises
    ------
    ImportError
        If Pillow is not installed. Install with ``pip install Pillow``.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ImportError("Pillow is required for validate_vlm. Run: pip install Pillow") from exc

    width, height = 200, 150
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw axes
    draw.line([(20, 120), (180, 120)], fill=(0, 0, 0), width=2)  # x-axis
    draw.line([(20, 20), (20, 120)], fill=(0, 0, 0), width=2)  # y-axis

    # Defect 1: near-white bar — very low contrast, accessibility fail
    draw.rectangle([(30, 80), (60, 120)], fill=(240, 240, 240))
    # Defect 2: obvious red bar for reference (this one should be seen easily)
    draw.rectangle([(70, 40), (100, 120)], fill=(200, 50, 50))
    # Defect 3: partially clipped label extending past the canvas right edge
    draw.text((150, 125), "Very long label text clipped", fill=(0, 0, 0))

    # Bar labels
    draw.text((38, 65), "A", fill=(180, 180, 180))  # low-contrast label on pale bar
    draw.text((78, 28), "B", fill=(255, 255, 255))  # white on red

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Validation entry point
# ---------------------------------------------------------------------------
# Critique and verdict prompts live in locales/i18n.yaml under
# prompts.vlm_gate_critique / prompts.vlm_gate_verdict (see i18n.py).


def validate(llm_chat: Callable[..., Any]) -> bool:
    """
    Run the VLM gate against the reference fixture.

    Uses the fixture from :func:`_make_fixture_png`. Sends the PNG to the VLM
    with the critique prompt, then asks a text call to produce a pass/fail
    verdict. The VLM passes if the verdict dict has ``"pass": true``.

    Parameters
    ----------
    llm_chat : callable
        The ``chat`` function from ``llm.py``, or a compatible mock. This is
        injected so tests can patch it without touching global state.

    Returns
    -------
    bool
        True if the VLM identified at least one seeded defect; False otherwise.

    Examples
    --------
    >>> def mock_chat(p, **kw):
    ...     if kw.get("images"):
    ...         return "I see a low-contrast bar and a clipped label."
    ...     return {"pass": True, "reason": "Critique mentions contrast issue."}
    >>> validate(mock_chat)
    True
    """
    osh.info("Running VLM eyeball gate against the reference fixture")
    png = _make_fixture_png()

    # Step 1: ask the VLM to critique the fixture
    critique = llm_chat(
        i18n.prompt("vlm_gate_critique", "user"),
        system=i18n.prompt("vlm_gate_critique", "system"),
        images=[png],
    )
    if not isinstance(critique, str):
        critique = str(critique)

    # Step 2: ask a text call to produce a structured pass/fail verdict
    verdict_prompt = i18n.prompt("vlm_gate_verdict", "user").format(critique=critique)
    raw = llm_chat(
        verdict_prompt,
        system=i18n.prompt("vlm_gate_verdict", "system"),
        json_schema={"type": "object"},
    )

    # Parse the verdict; treat malformed JSON as a failure
    if isinstance(raw, dict):
        verdict = raw
    else:
        import json

        try:
            verdict = json.loads(str(raw))
        except Exception:
            osh.warning("VLM gate FAILED: verdict was not valid JSON")
            return False

    passed = bool(verdict.get("pass", False))
    if passed:
        osh.info(f"VLM gate PASSED: {verdict.get('reason', '')}")
    else:
        osh.warning(f"VLM gate FAILED: {verdict.get('reason', 'no defect identified')}")
    return passed
