"""
ralph — the generic Ralph loop and its two instantiations.

The Ralph loop is the "produce, inspect, fix, repeat until a verdict" pattern
used throughout the sprezzature suite. This module implements the generic
driver and two concrete variants:

* ``eyeball_loop``: inspects a visual artifact (PNG) with a vision-language
  model; fixes the source code that generated it.
* ``prose_loop``: inspects prose with a text model enforcing a writing charter;
  fixes the text at paragraph-pair seams.

Both variants share the same generic driver so the convergence logic, iteration
budget, and no-op guard are implemented once.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import os_helper as osh

from . import i18n

# All prompt text (system + user templates for the eyeball and prose variants)
# lives in locales/i18n.yaml's `prompts:` namespace, authored in English
# (meta.model_prompt_locale) — see i18n.py and CODING.md section 21.3. This
# module only fills in the `{placeholder}` fields via str.format at call time.

# ---------------------------------------------------------------------------
# Generic driver
# ---------------------------------------------------------------------------

def ralph_loop(
    source: Any,
    *,
    render: Callable[[Any], Any],
    inspect: Callable[[Any], str],
    apply_fix: Callable[[Any, str], Any],
    verdict: Callable[[str], dict[str, Any]],
    max_iters: int = 6,
    on_iteration: Callable[[int, Any, Any, str, dict[str, Any]], None] | None = None,
) -> tuple[Any, list[tuple[int, str, dict[str, Any]]]]:
    """
    Run the produce-inspect-fix-repeat loop until convergence or budget is spent.

    The caller supplies four callbacks that define the loop's behaviour; the
    driver handles iteration, convergence detection, and history recording.

    Parameters
    ----------
    source : Any
        Initial artifact source: a file path, a code string, a prose block.
        The loop edits this value in place across iterations.
    render : callable
        ``render(source) -> artifact`` — turn the source into an inspectable
        artifact. For the eyeball loop this renders a PNG; for the prose loop
        the artifact is the text itself (identity).
    inspect : callable
        ``inspect(artifact) -> critique: str`` — examine the artifact and return
        a free-form critique string.
    apply_fix : callable
        ``apply_fix(source, critique) -> new_source`` — edit the source to
        address the critique. Must return the same type as ``source``.
    verdict : callable
        ``verdict(critique) -> dict`` — decide whether to ship. The dict must
        have at minimum a boolean ``"ship"`` key.
    max_iters : int
        Maximum number of produce-inspect-fix cycles. Default 6.
    on_iteration : callable or None
        Optional callback called at the end of each iteration with arguments
        ``(iter_index, source, artifact, critique, verdict_dict)``. Use for
        logging or writing assessment files.

    Returns
    -------
    tuple[Any, list[tuple[int, str, dict]]]
        ``(final_source, history)`` where ``history`` is a list of
        ``(iteration_index, critique, verdict_dict)`` triples.

    Examples
    --------
    >>> def mock_render(s):  return s + "_rendered"
    >>> def mock_inspect(a): return "no issues"
    >>> def mock_fix(s, c):  return s
    >>> def mock_verdict(c): return {"ship": True, "blocking": [], "score": 1.0}
    >>> src, hist = ralph_loop(
    ...     "source",
    ...     render=mock_render, inspect=mock_inspect,
    ...     apply_fix=mock_fix, verdict=mock_verdict,
    ... )
    >>> src
    'source'
    >>> hist[0][2]["ship"]
    True
    """
    history: list[tuple[int, str, dict[str, Any]]] = []

    for i in range(max_iters):
        # Step 1: render the source into an inspectable artifact
        artifact = render(source)
        # Step 2: inspect the artifact and produce a critique
        critique = inspect(artifact)
        # Step 3: decide whether the artifact is ready to ship
        vdict = verdict(critique)
        history.append((i, critique, vdict))

        if on_iteration is not None:
            on_iteration(i, source, artifact, critique, vdict)

        osh.info(f"Ralph iteration {i + 1}/{max_iters}: ship={vdict.get('ship')}")

        # Stop when the verdict says ship — the artifact is good enough
        if vdict.get("ship"):
            osh.info(f"Ralph converged (ship) after {i + 1} iteration(s)")
            return source, history

        # Step 4: apply the fix to the source
        new_source = apply_fix(source, critique)

        # Guard: if the fix is a no-op the loop would spin; stop early
        if new_source == source:
            osh.info(f"Ralph stopped early: fix was a no-op at iteration {i + 1}")
            return source, history

        source = new_source

    # Budget exhausted: return whatever we have
    osh.warning(f"Ralph budget exhausted after {max_iters} iteration(s) without shipping")
    return source, history


# ---------------------------------------------------------------------------
# Eyeball loop (visual quality)
# ---------------------------------------------------------------------------

def eyeball_loop(
    source: str,
    *,
    kind: str,
    llm_chat: Callable[..., Any],
    renderers: dict[str, Callable[[str], bytes]] | None = None,
    max_iters: int = 6,
    on_iteration: Callable[[int, str, bytes, str, dict[str, Any]], None] | None = None,
) -> tuple[str, list[tuple[int, str, dict[str, Any]]]]:
    """
    Run the eyeball loop on a visual artifact source.

    Renders the source to a PNG, critiques it with a VLM, applies a text-model
    fix to the source, and repeats. Uses the generic ``ralph_loop`` driver
    internally.

    Parameters
    ----------
    source : str
        Source text to render: a Vega-Lite JSON string, HTML, Mermaid, or TikZ.
    kind : str
        Surface kind. Controls which renderer is selected: ``"vega"``,
        ``"html"``, ``"mermaid"``, ``"tikz"``, ``"svg"``.
    llm_chat : callable
        The ``chat`` function from ``llm.py`` (or a compatible mock). Injected
        so tests can patch it without touching the module-level default.
    renderers : dict or None
        Optional dict mapping kind strings to render callables
        ``(source_str) -> bytes``. When None the function raises
        ``NotImplementedError`` pointing to the sprezzature-figures renderers.
    max_iters : int
        Maximum iteration budget. Default 6.
    on_iteration : callable or None
        Optional per-iteration callback.

    Returns
    -------
    tuple[str, list[tuple[int, str, dict]]]
        ``(final_source, history)``.

    Raises
    ------
    NotImplementedError
        If ``renderers`` is None and no built-in renderer is available for
        ``kind``. Wire in the renderers from sprezzature-figures.
    """
    # The renderers are defined in sprezzature-figures/scripts and are not a
    # dependency of this package; the caller must inject them.
    if renderers is None or kind not in renderers:
        raise NotImplementedError(
            f"No renderer for kind={kind!r}. "
            "Pass a 'renderers' dict with a callable for this surface. "
            "See sprezzature-figures/scripts/ralph_eyeball_loop.py for the "
            "existing renderer implementations."
        )

    render_fn = renderers[kind]

    def render(src: str) -> bytes:
        """Render source to a PNG byte string."""
        return render_fn(src)

    def inspect(png: bytes) -> str:
        """Critique the rendered PNG using the configured VLM."""
        # The critique prompt embeds the PNG and asks for structured feedback
        return str(llm_chat(
            i18n.prompt("eyeball_critique", "user"),
            system=i18n.prompt("eyeball_critique", "system"),
            images=[png],
        ))

    def apply_fix(src: str, critique: str) -> str:
        """Generate an edited source that addresses the critique."""
        prompt = i18n.prompt("eyeball_fix", "user").format(source=src, critique=critique)
        return str(llm_chat(prompt, system=i18n.prompt("eyeball_fix", "system")))

    def verdict(critique: str) -> dict[str, Any]:
        """Ask the VLM for a structured ship/no-ship decision."""
        prompt = i18n.prompt("eyeball_verdict", "user").format(critique=critique)
        raw = llm_chat(prompt, json_schema={"type": "object"})
        # llm.chat parses JSON when json_schema is provided; fall back gracefully
        if isinstance(raw, dict):
            return raw
        try:
            parsed: dict[str, Any] = json.loads(str(raw))
            return parsed
        except json.JSONDecodeError:
            # Malformed verdict: treat as "do not ship" so the loop continues
            osh.warning("Eyeball verdict was not valid JSON; treating as do-not-ship")
            return {"ship": False, "blocking": ["verdict parse failure"], "score": 0.0}

    return ralph_loop(
        source,
        render=render,
        inspect=inspect,
        apply_fix=apply_fix,
        verdict=verdict,
        max_iters=max_iters,
        on_iteration=on_iteration,
    )


# ---------------------------------------------------------------------------
# Prose loop (writing charter)
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs on blank lines, stripping leading/trailing space.

    Parameters
    ----------
    text : str
        Input prose block.

    Returns
    -------
    list[str]
        Non-empty paragraphs; blank-line separators discarded.
    """
    # Two or more newlines delimit paragraph boundaries
    import re
    parts = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def prose_loop(
    text: str,
    *,
    charter: str,
    llm_chat: Callable[..., Any],
    max_passes: int = 3,
) -> str:
    """
    Enforce the writing charter on a prose block via paragraph-pair seam checks.

    Implements WRITING.md §10 "Flow by Paragraph Pairs" locally. For each
    overlapping window (para n, para n+1), a text model checks the seam for
    bolted-on transitions, logic gaps, echoed words, and charter violations.
    When a seam needs fixing, a second call edits the last sentence of n and the
    opening of n+1. The loop repeats until a full pass makes no edit or the
    budget is spent.

    Parameters
    ----------
    text : str
        Prose block to refine. Paragraphs are separated by blank lines.
    charter : str
        Writing charter excerpt to embed in every seam and fix prompt. Keeps the
        model focused on the specific rules that matter for this language.
    llm_chat : callable
        The ``chat`` function from ``llm.py`` or a compatible mock.
    max_passes : int
        Maximum number of full passes over all paragraph pairs. Default 3.

    Returns
    -------
    str
        The refined prose block with the same paragraph structure.

    Examples
    --------
    >>> # With a mock llm that fixes nothing, the output equals the input
    >>> def noop_chat(p, **kw): return '{"needs_fix": false, "reasons": []}'
    >>> text = "Paragraph one.\\n\\nParagraph two."
    >>> result = prose_loop(text, charter="No dashes.", llm_chat=noop_chat)
    >>> result == text
    True
    """
    paras = _split_paragraphs(text)
    if len(paras) < 2:
        # Nothing to check at a paragraph seam when there is only one paragraph
        return text

    osh.info(f"Prose loop over {len(paras)} paragraph(s), up to {max_passes} pass(es)")
    for _pass in range(max_passes):
        changed = False
        # Slide an overlapping window over every adjacent pair
        for n in range(len(paras) - 1):
            a, b = paras[n], paras[n + 1]
            seam_prompt = i18n.prompt("prose_seam", "user").format(charter=charter, a=a, b=b)
            raw = llm_chat(
                seam_prompt,
                system=i18n.prompt("prose_seam", "system"),
                json_schema={"type": "object"},
            )
            # Parse the seam verdict; treat malformed responses as "no fix needed"
            if isinstance(raw, dict):
                seam_verdict = raw
            else:
                try:
                    seam_verdict = json.loads(str(raw))
                except json.JSONDecodeError:
                    seam_verdict = {"needs_fix": False, "reasons": []}

            if not seam_verdict.get("needs_fix", False):
                continue

            # Fix: ask the model to revise only the seam sentences
            fix_prompt = i18n.prompt("prose_fix", "user").format(
                charter=charter, a=a, b=b,
                critique=json.dumps(seam_verdict.get("reasons", [])),
            )
            fix_raw = llm_chat(
                fix_prompt,
                system=i18n.prompt("prose_fix", "system"),
                json_schema={"type": "object"},
            )
            if isinstance(fix_raw, dict):
                fix = fix_raw
            else:
                try:
                    fix = json.loads(str(fix_raw))
                except json.JSONDecodeError:
                    # Skip this pair if the fix response is unparseable
                    continue

            new_a = fix.get("a", a)
            new_b = fix.get("b", b)
            if new_a != a or new_b != b:
                paras[n] = new_a
                paras[n + 1] = new_b
                changed = True

        # A full pass with no changes means the text has converged
        if not changed:
            osh.info(f"Prose loop converged after pass {_pass + 1}")
            break

    return "\n\n".join(paras)
