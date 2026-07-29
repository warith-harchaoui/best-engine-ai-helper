"""
validate_llm — Ralph prose-loop gate for LLM text quality.

Validates that the selected text model can detect and fix charter violations
in reference fixture texts. Two fixtures are tested:

1. ``DASH_EN`` — an English sentence with an em dash used as a punctuation
   aside (WRITING.md §5: no punctuation dashes).
2. ``SEAM_FR`` — two French paragraphs joined by "Par ailleurs" over a logic
   gap (ECRITURE.md: banned machine-tic transition).

The model passes the gate if both fixtures are cleaned within two passes of the
prose Ralph loop (i.e., neither the em dash pattern nor "Par ailleurs" survives
in the fixed output).

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Reference fixtures with deliberate charter violations
# ---------------------------------------------------------------------------

# Em dash used as a punctuation aside — violates WRITING.md §5.
# A charter-compliant rewrite would use a comma or parentheses.
DASH_EN = (
    "The model selected by the algorithm — which scored highest on vision benchmarks "
    "— is pulled first and validated against both Ralph gates before any other candidate "
    "is considered."
)

# Two French paragraphs joined by "Par ailleurs" over a logic gap.
# "Par ailleurs" is listed in ECRITURE.md as a banned machine-tic transition.
# The second paragraph does not follow logically from the first.
SEAM_FR = (
    "Le catalogue de modèles est mis à jour automatiquement depuis quatre sources "
    "externes. Chaque source est consultée dans un ordre de priorité défini, "
    "et les entrées les plus récentes écrasent les entrées correspondantes du cache.\n\n"
    "Par ailleurs, la mémoire unifiée des puces Apple Silicon permet à Ollama "
    "d'utiliser la totalité du pool disponible sans partage avec un GPU discret."
)

# Minimal charter excerpt embedded in the prompts so the model knows exactly
# which rules to apply. A full charter would be loaded from references/.
_WRITING_CHARTER_EXCERPT = """\
Rule 5 (English): No punctuation dashes. No em dash and no en dash used as an
aside; rewrite with commas, colons, semicolons, parentheses, or short sentences.
Hyphens in compound words stay.

Rule (French): Banned transitions: "Par ailleurs", "De plus", "Autrement dit",
"En outre". Rewrite with a sentence that shows the logical connection explicitly.
No em dash or en dash as a punctuation aside.\
"""


# ---------------------------------------------------------------------------
# Validation entry point
# ---------------------------------------------------------------------------

def validate(llm_chat: Callable[..., Any]) -> bool:
    """
    Run the prose-loop gate on both text fixtures.

    Uses the prose Ralph loop from ``ralph.prose_loop`` to refine each
    fixture. The result is checked for the specific charter violations that
    were seeded in the fixture. Both fixtures must pass for the gate to return
    True.

    Parameters
    ----------
    llm_chat : callable
        The ``chat`` function from ``llm.py``, or a compatible mock.

    Returns
    -------
    bool
        True if both fixtures are free of their seeded violations after at most
        two prose-loop passes; False otherwise.

    Examples
    --------
    >>> def mock_chat(p, **kw):
    ...     # Simulate a model that replaces em dashes and Par ailleurs
    ...     return '{"needs_fix": false, "reasons": []}'
    >>> validate(mock_chat)
    True
    """
    from . import ralph

    # Test 1: em dash in English fixture
    fixed_en = ralph.prose_loop(
        DASH_EN,
        charter=_WRITING_CHARTER_EXCERPT,
        llm_chat=llm_chat,
        max_passes=2,
    )
    # The em dash character should not survive after fixing
    if "—" in fixed_en:
        return False

    # Test 2: "Par ailleurs" seam in French fixture
    fixed_fr = ralph.prose_loop(
        SEAM_FR,
        charter=_WRITING_CHARTER_EXCERPT,
        llm_chat=llm_chat,
        max_passes=2,
    )
    # The banned transition must not survive in either paragraph
    if "par ailleurs" in fixed_fr.lower():
        return False

    return True
