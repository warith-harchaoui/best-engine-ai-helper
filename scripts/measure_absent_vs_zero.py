"""Count how often a legitimate value could be mistaken for an absent one.

There is a defect family this package has already been bitten by twice: a value
that is *legitimately* zero, empty, or simply shaped differently gets treated as
missing or interchangeable, and the result is wrong without anything raising.
The catalog fix in 1.4.4 was one instance (a directory slug taken for a pull
tag); `or` applied to a numeric is another shape of the same thing, because
``0`` and ``0.0`` are falsy while being perfectly real answers.

The temptation is to turn that into a lint rule immediately. This script exists
because that temptation should be *measured* first. A rule that flags hundreds
of lines is not a gate, it is noise that teaches everyone to ignore it, and the
only way to know which side a rule falls on is to count before committing to it.

Three candidate rules were counted against this package. The outcome, as of
2026-10-19:

=========================  =======  ================================================
Rule                       Flagged  Verdict
=========================  =======  ================================================
``or`` on a numeric            14   Reviewable by hand. Worth keeping as a report.
``.get(k)`` with no default   266   Abandoned. It cannot tell a dict lookup from a
                                    route decorator, and most hits are correct code.
``if <name>:`` on a number     66   Abandoned. Nearly every hit is a flag or a
                                    string, where truthiness is exactly right.
=========================  =======  ================================================

One rule in three survived contact with the data, which matches what the same
exercise produced on a sibling project. Reviewing the 14 survivors by hand found
**one** real latent defect — an unpriced cloud model scoring as though it were
free — and thirteen lines where the fallback equals the value it would swallow,
and so is harmless.

That is the honest shape of the result: the family is real, it is worth hunting
periodically, and it is **not** dense enough here to justify a blocking gate.
This stays a script you run and read, not a hook that fails a push.

Run it from the repository root::

    python scripts/measure_absent_vs_zero.py

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

#: Package to scan, relative to the repository root.
_PACKAGE = Path(__file__).resolve().parent.parent / "best_engine_ai_helper"


class _Counter(ast.NodeVisitor):
    """Collect one line per candidate-rule hit, with its source for review."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.or_on_numeric: list[tuple[str, int, str]] = []
        self.get_no_default: list[tuple[str, int, str]] = []
        self.truthy_on_name: list[tuple[str, int, str]] = []

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """`a or 0` — the fallback is numeric, so a real 0 on the left is lost."""
        if isinstance(node.op, ast.Or):
            for value in node.values:
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, (int, float))
                    and not isinstance(value.value, bool)
                ):
                    self.or_on_numeric.append((self.path, node.lineno, ast.unparse(node)[:90]))
                    break
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """`d.get(k)` with no sentinel — absent and present-but-None look alike."""
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 1
            and not node.keywords
        ):
            self.get_no_default.append((self.path, node.lineno, ast.unparse(node)[:90]))
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        """`if x:` — fine for a flag, wrong when x is a count that may be 0."""
        if isinstance(node.test, ast.Name):
            self.truthy_on_name.append((self.path, node.lineno, ast.unparse(node.test)[:90]))
        self.generic_visit(node)


def main() -> int:
    """Print the three counts and the hits worth reading. Returns an exit code."""
    totals: dict[str, list[tuple[str, int, str]]] = {
        "or on a numeric": [],
        ".get(k) with no default": [],
        "if <name>: on a possible number": [],
    }

    for path in sorted(_PACKAGE.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken file is not this tool's job
            print(f"skipped (syntax error): {path}", file=sys.stderr)
            continue
        counter = _Counter(str(path.relative_to(_PACKAGE.parent)))
        counter.visit(tree)
        totals["or on a numeric"].extend(counter.or_on_numeric)
        totals[".get(k) with no default"].extend(counter.get_no_default)
        totals["if <name>: on a possible number"].extend(counter.truthy_on_name)

    for rule, hits in totals.items():
        verdict = "reviewable" if len(hits) <= 30 else "TOO NOISY to gate on"
        print(f"\n=== {rule}: {len(hits)} line(s) — {verdict} ===")
        if len(hits) > 30:
            print("  (not listed; a rule this dense would be ignored, not obeyed)")
            continue
        for file, line, src in hits:
            print(f"  {file}:{line}  {src}")

    print(
        "\nThis reports; it does not gate. Read the survivors and judge each one:"
        "\na fallback that equals the value it would swallow is harmless, and most are."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
