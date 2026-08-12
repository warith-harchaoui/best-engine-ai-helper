"""
Tests for best_engine_ai_helper.ralph — the generic produce/inspect/fix loop
and its prose and eyeball instantiations. Callbacks are plain Python stubs and
the eyeball renderer is faked, so nothing renders or calls a model.
"""

from __future__ import annotations

from typing import Any

import pytest

from best_engine_ai_helper import ralph


def test_ralph_loop_converges_caps_and_stops_on_noop() -> None:
    # Converges the iteration after the fix, when the verdict finally ships.
    calls = {"n": 0}

    def verdict(_c: str) -> dict[str, Any]:
        calls["n"] += 1
        return {"ship": calls["n"] >= 2, "blocking": [], "score": 0.9}

    src, hist = ralph.ralph_loop(
        "s",
        render=lambda s: s,
        inspect=lambda a: "issue",
        apply_fix=lambda s, c: s + "+",
        verdict=verdict,
    )
    assert len(hist) == 2 and hist[-1][2]["ship"] is True and src == "s+"

    # Never exceeds max_iters when the verdict never ships.
    _, capped = ralph.ralph_loop(
        "x",
        render=lambda s: s,
        inspect=lambda a: "bad",
        apply_fix=lambda s, c: s + "+",
        verdict=lambda c: {"ship": False},
        max_iters=3,
    )
    assert len(capped) == 3

    # A no-op fix exits after one iteration; on_iteration fires once.
    seen: list[int] = []
    _, once = ralph.ralph_loop(
        "same",
        render=lambda s: s,
        inspect=lambda a: "x",
        apply_fix=lambda s, c: s,
        verdict=lambda c: {"ship": False},
        max_iters=6,
        on_iteration=lambda i, *a: seen.append(i),
    )
    assert len(once) == 1 and seen == [0]


def test_prose_and_eyeball_loops() -> None:
    # A model that reports no seam issue returns the text unchanged; a
    # single-paragraph text has no seam to check.
    def clean(_p: str, **kw: Any) -> Any:
        return {"needs_fix": False, "reasons": []} if kw.get("json_schema") else ""

    text = "Paragraph one.\n\nParagraph two."
    assert ralph.prose_loop(text, charter="No dashes.", llm_chat=clean) == text
    solo = "Only one paragraph."
    assert ralph.prose_loop(solo, charter="c", llm_chat=clean) == solo

    # When the seam check flags a problem, the fix is applied and the text changes.
    def fixer(_p: str, **kw: Any) -> Any:
        schema = kw.get("json_schema")
        if not schema:
            return ""
        system = kw.get("system", "").lower()
        if "seam" in system or "needs_fix" in system:
            return {"needs_fix": True, "reasons": ["bolted-on-transition"]}
        return {"a": "Revised A.", "b": "Revised B."}

    assert ralph.prose_loop(text, charter="No machine tics.", llm_chat=fixer) != text

    # A malformed (non-JSON) seam verdict degrades to "no fix needed" rather
    # than crashing -- a model returning garbage is a real failure mode, not
    # just a hypothetical.
    def garbled_seam(_p: str, **kw: Any) -> Any:
        return "not json at all" if kw.get("json_schema") else ""

    assert ralph.prose_loop(text, charter="c", llm_chat=garbled_seam) == text

    # A malformed fix response skips that pair (leaves it unchanged) rather
    # than crashing, even though the seam itself was correctly flagged.
    def garbled_fix(_p: str, **kw: Any) -> Any:
        schema = kw.get("json_schema")
        if not schema:
            return ""
        system = kw.get("system", "").lower()
        if "seam" in system or "needs_fix" in system:
            return '{"needs_fix": true, "reasons": ["x"]}'
        return "not json at all"

    assert ralph.prose_loop(text, charter="c", llm_chat=garbled_fix) == text

    # No renderer for the requested kind -- a clear NotImplementedError, not
    # a crash deep inside rendering.
    with pytest.raises(NotImplementedError, match="renderer"):
        ralph.eyeball_loop(
            '{"mark": "bar"}', kind="vega", llm_chat=lambda p, **k: "", renderers=None
        )
    with pytest.raises(NotImplementedError, match="renderer"):
        ralph.eyeball_loop('{"mark": "bar"}', kind="vega", llm_chat=lambda p, **k: "", renderers={})

    # A malformed (non-JSON) verdict degrades to "do not ship" rather than
    # crashing.
    def garbled_verdict(prompt: str, **kw: Any) -> Any:
        if kw.get("images"):
            return "some critique"
        if kw.get("json_schema"):
            return "not json at all"
        return prompt

    _src3, garbled_hist = ralph.eyeball_loop(
        '{"mark": "bar"}',
        kind="vega",
        llm_chat=garbled_verdict,
        renderers={"vega": lambda s: b"PNG"},
        max_iters=1,
    )
    assert len(garbled_hist) == 1 and garbled_hist[0][2]["ship"] is False
    assert garbled_hist[0][2]["blocking"] == ["verdict parse failure"]

    # A faked renderer avoids real rendering; the VLM critique + verdict ship on
    # the first pass, so the loop records exactly one iteration.
    def fake_chat(prompt: str, **kw: Any) -> Any:
        if kw.get("images"):
            return "Low contrast bar and a clipped label."
        if kw.get("json_schema"):
            return {"ship": True, "blocking": [], "score": 0.9}
        return prompt  # fix path, not reached once the verdict ships

    _src, ship_hist = ralph.eyeball_loop(
        '{"mark": "bar"}',
        kind="vega",
        llm_chat=fake_chat,
        renderers={"vega": lambda s: b"\x89PNG-fake"},
    )
    assert len(ship_hist) == 1 and ship_hist[0][2]["ship"] is True

    # The verdict never ships, so the fix path runs each iteration; the
    # verdict arrives as a JSON *string* (not a dict), exercising the parse
    # branch.
    fixes = {"n": 0}

    def chat(prompt: str, **kw: Any) -> Any:
        if kw.get("images"):
            return "still has a clipped label"
        if kw.get("json_schema"):
            return '{"ship": false, "blocking": ["clip"], "score": 0.3}'
        fixes["n"] += 1
        return f"{prompt}_fix{fixes['n']}"  # a fresh source each pass

    _src2, no_ship_hist = ralph.eyeball_loop(
        '{"mark": "bar"}',
        kind="vega",
        llm_chat=chat,
        renderers={"vega": lambda s: b"PNG"},
        max_iters=2,
    )
    assert len(no_ship_hist) == 2 and all(h[2]["ship"] is False for h in no_ship_hist)
    assert fixes["n"] >= 1  # the fix path ran
