"""
privacy — local pseudonymization for cloud calls (Phase 6.4).

Replace personal data with **realistic same-type surrogates** *before* text
leaves the machine for a cloud provider, and restore the originals on the way
back. ``Marie -> Claudine``, ``Lyon -> Paris``: the prose stays natural (no
``PERSON_1`` tokens), so the cloud model reasons over coherent text and quality
is intact. The reverse map stays **local**.

Detection + surrogate proposal are done by a **local LLM** (via a resolved engine
— Ollama/vLLM), asked for schema-constrained JSON. Being local, it never ships
the raw text anywhere, and being an LLM it is context-aware: it catches
quasi-identifiers (role + city + employer) and special-category facts (health,
beliefs, …) that a pure PII regex misses. An optional deterministic layer
(Microsoft Presidio + Faker + spaCy, the ``privacy`` extra) can augment it; see
:func:`augment_with_presidio`.

Honesty (GDPR Recital 26): pseudonymized data is still *personal data*. This is
risk-reduction, not anonymization, and does not take cloud processing out of
GDPR scope. Label outputs "pseudonymized", never "anonymous".

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import re
from typing import Any

import os_helper as osh

# Schema the local LLM must fill: each detected span, its type, and a realistic
# same-type / same-locale surrogate to stand in for it.
_ENTITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string"},
                    "surrogate": {"type": "string"},
                },
                "required": ["text", "type", "surrogate"],
            },
        }
    },
    "required": ["entities"],
}

_SYSTEM = (
    "You are a privacy pre-processor. You find personal data in text and propose "
    "a realistic REPLACEMENT of the SAME type for each item, so the text can be "
    "sent to a third party without revealing real identities."
)


def _build_prompt(text: str, locale: str | None) -> str:
    """Build the detection+surrogate instruction for the local model."""
    loc = f" The text is in locale '{locale}'." if locale else ""
    return (
        "Find every piece of personal data in the TEXT below and, for each, give a "
        "realistic surrogate of the SAME type and SAME language/locale so the text "
        "stays natural — e.g. a French first name -> another French first name "
        "(Marie -> Claudine), a city -> another city (Lyon -> Paris), keeping "
        "gender and register. Cover: names, places, organisations, emails, phone "
        "numbers, IDs/account numbers, precise dates of birth, and any "
        "special-category facts (health, religion, politics, sexual orientation) "
        "or quasi-identifiers that could re-identify someone. Do NOT touch "
        "non-personal words. Use the EXACT substring from the text as `text`. Be "
        "consistent: the same person always maps to the same surrogate."
        f"{loc}\n\nTEXT:\n{text}"
    )


def _replace_word(text: str, needle: str, replacement: str) -> str:
    """Replace ``needle`` with ``replacement`` on non-word boundaries.

    Boundaries (``(?<!\\w)`` / ``(?!\\w)``) keep a surrogate from matching inside
    a larger word, while still allowing a following apostrophe so morphology like
    ``Claudine's`` restores to ``Marie's``.
    """
    if not needle:
        return text
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.sub(pattern, replacement.replace("\\", r"\\"), text)


def pseudonymize(
    text: str,
    engine: dict[str, Any] | str,
    *,
    locale: str | None = None,
    min_len: int = 2,
) -> tuple[str, dict[str, str]]:
    """
    Replace personal data in ``text`` with same-type surrogates using a local LLM.

    Parameters
    ----------
    text : str
        The text to scrub before it leaves the machine.
    engine : dict | str
        A resolved engine descriptor (or path). Use a LOCAL engine — for a cloud
        brief pass ``engine["fallback"]`` so scrubbing never touches the cloud.
    locale : str or None
        Optional locale hint (e.g. ``"fr_FR"``) so surrogates match the language.
    min_len : int
        Ignore detected spans shorter than this (avoids mangling stray letters).

    Returns
    -------
    (scrubbed_text, mapping)
        ``mapping`` is ``{surrogate: original}`` — keep it LOCAL and feed it to
        :func:`restore` on the response.
    """
    from . import llm

    result = llm.chat(
        _build_prompt(text, locale),
        engine=engine,
        kind="llm",
        json_schema=_ENTITY_SCHEMA,
        system=_SYSTEM,
        temperature=0.0,
    )
    entities = result.get("entities", []) if isinstance(result, dict) else []

    scrubbed = text
    mapping: dict[str, str] = {}  # surrogate -> original
    chosen: dict[str, str] = {}  # original -> surrogate (consistency)
    used: set[str] = set()

    # Longest spans first, so a full name is replaced before any part of it.
    for ent in sorted(entities, key=lambda e: len(str(e.get("text", ""))), reverse=True):
        original = str(ent.get("text", "")).strip()
        surrogate = str(ent.get("surrogate", "")).strip()
        if len(original) < min_len or not surrogate or original == surrogate:
            continue
        if original in chosen:
            continue  # already mapped consistently
        # Avoid a surrogate that collides with a real term still in the text or a
        # surrogate already in use — disambiguate deterministically.
        base, n = surrogate, 1
        while surrogate in used or _replace_word(text, surrogate, "\0") != text:
            n += 1
            surrogate = f"{base} {n}"
        chosen[original] = surrogate
        used.add(surrogate)
        mapping[surrogate] = original
        scrubbed = _replace_word(scrubbed, original, surrogate)

    osh.info(f"pseudonymize: {len(mapping)} entities substituted")
    return scrubbed, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    """Swap surrogates back to their originals (inverse of :func:`pseudonymize`).

    Longest surrogate first so a multi-word surrogate is restored before any of
    its parts.
    """
    out = text
    for surrogate in sorted(mapping, key=len, reverse=True):
        out = _replace_word(out, surrogate, mapping[surrogate])
    return out


def augment_with_presidio(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic backstop (optional ``cloud`` extra): add Presidio+Faker hits.

    Presidio (PII detection) + Faker (same-type surrogates) catch structured
    identifiers (emails, phones, card/IBAN, IPs) the LLM may miss, and add them to
    the entity list. Requires ``presidio-analyzer``, ``presidio-anonymizer`` and
    ``Faker`` (the ``cloud`` extra) plus spaCy models; a no-op with a warning
    when they are absent. Full wiring lands in a later 6.4 step.
    """
    try:
        from presidio_analyzer import AnalyzerEngine  # noqa: F401
    except ImportError:
        osh.warning(
            "augment_with_presidio needs the 'cloud' extra "
            "(pip install 'best-engine-ai-helper[cloud]'); returning entities unchanged."
        )
        return entities
    # Deterministic Presidio+Faker augmentation is implemented in the next 6.4 step.
    return entities
