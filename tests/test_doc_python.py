"""Every Python recipe in the documents still names code that exists.

Iteration 12 put the shell half of `CODING.md`'s promise under a gate: every
`best-engine-ai-helper ...` line in these documents is resolved against the
real Click tree. It left the other half open, and the asymmetry is the whole
reason this file exists. `EXAMPLES.md` ships sixteen `python` fences and
`EXEMPLES.md` the same sixteen; nothing read them. A public function renamed
tomorrow stales all thirty-two silently, in the half of the documentation a
library user actually copies.

**This check finds nothing today.** All sixteen parse, every name they import
exists, every attribute they reach resolves, and every call they make fits the
signature it targets. That is said plainly rather than hidden behind a green
tick: it is here because its sibling found two defects in the shell half on the
day it was written, and because "nobody has renamed anything yet" is a property
of this week rather than of the code.

What it does NOT do is execute them. Running these recipes needs a daemon, a
network, a GPU and in one case a paid API key, so execution would make the gate
depend on all four. It checks the shape instead: the names, the attributes and
the call signatures, which is exactly the part a rename breaks.

One trap, which four drafts of various probes fell into on the way here: a
submodule is not an attribute of its package until something imports it.
`from best_engine_ai_helper import llm` is valid and `getattr(beah, "llm")` is
None, so a naive check reports the one import every streaming recipe opens
with. The fix is to ask the import system rather than the namespace.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parent.parent

#: The package whose names these recipes are checked against. Anything else a
#: recipe imports (`openai`, `pathlib`) is somebody else's contract.
_PACKAGE = "best_engine_ai_helper"

#: Documents carrying Python recipes. Both languages, because the code inside a
#: fence is not translated: the same sixteen blocks ship twice, and a rename
#: stales both.
DOCS = ["EXAMPLES.md", "EXEMPLES.md"]

_FENCE = re.compile(r"^```python\n(.*?)^```", re.S | re.M)


def recipes(path: Path) -> list[str]:
    """Every ``python`` fence in one document, in order."""
    return _FENCE.findall(path.read_text(encoding="utf-8"))


def _resolve(dotted: str) -> Any:
    """
    Resolve a dotted name under the package, importing submodules as needed.

    Parameters
    ----------
    dotted : str
        A name such as ``best_engine_ai_helper.llm`` or
        ``best_engine_ai_helper.chat``.

    Returns
    -------
    Any
        The object, or None when nothing of that name exists.

    Notes
    -----
    Asking the import system first is what separates a missing name from an
    unimported submodule. `getattr` alone answers None for both.
    """
    try:
        return importlib.import_module(dotted)
    except ImportError:
        pass
    module_name, _, attribute = dotted.rpartition(".")
    if not module_name:
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    return getattr(module, attribute, None)


def _bindings(tree: ast.AST) -> tuple[dict[str, Any], list[str]]:
    """Local names a recipe binds from this package, plus imports that fail."""
    bound: dict[str, Any] = {}
    missing: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != _PACKAGE:
                    continue
                target = _resolve(alias.name)
                if target is None:
                    missing.append(f"`import {alias.name}` names nothing")
                else:
                    bound[alias.asname or alias.name] = target
        elif isinstance(node, ast.ImportFrom):
            if not node.module or node.module.split(".")[0] != _PACKAGE:
                continue
            for alias in node.names:
                target = _resolve(f"{node.module}.{alias.name}")
                if target is None:
                    missing.append(f"`from {node.module} import {alias.name}` names nothing")
                else:
                    bound[alias.asname or alias.name] = target
    return bound, missing


def _callee(node: ast.Call, bound: dict[str, Any]) -> tuple[str, Any] | None:
    """The object a call targets, when it is rooted in one of ``bound``."""
    parts: list[str] = []
    current: ast.expr = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name) or current.id not in bound:
        return None
    target = bound[current.id]
    label = current.id
    for part in reversed(parts):
        label = f"{label}.{part}"
        target = getattr(target, part, None)
        if target is None:
            return label, None
    return label, target


def _call_problems(label: str, target: Any, node: ast.Call) -> list[str]:
    """Keyword and arity mismatches between a documented call and its signature."""
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):  # a builtin or C callable: no introspection
        return []
    parameters = signature.parameters
    problems: list[str] = []
    keywords = {kw.arg for kw in node.keywords if kw.arg}
    if not any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        problems += [
            f"`{label}(...)` has no parameter `{name}`"
            for name in sorted(keywords - set(parameters))
        ]
    required = [
        name
        for name, parameter in parameters.items()
        if parameter.default is parameter.empty
        and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not any(p.kind is p.VAR_POSITIONAL for p in parameters.values()):
        supplied = len(node.args) + len(keywords & set(required))
        if supplied < len(required):
            problems.append(
                f"`{label}(...)` needs {len(required)} required argument(s), {supplied} given"
            )
    return problems


def check(path: Path) -> list[str]:
    """
    Every Python recipe in one document that no longer matches the library.

    Returns
    -------
    list[str]
        Empty when all of them parse and name live code.
    """
    problems: list[str] = []
    for index, source in enumerate(recipes(path)):
        where = f"{path.name} python block {index + 1}"
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            problems.append(f"{where}: does not parse ({exc.msg} at line {exc.lineno})")
            continue
        bound, missing = _bindings(tree)
        problems += [f"{where}: {problem}" for problem in missing]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            found = _callee(node, bound)
            if found is None:
                continue
            label, target = found
            if target is None:
                problems.append(f"{where}: `{label}` does not exist")
            elif callable(target):
                problems += [
                    f"{where}: {problem}" for problem in _call_problems(label, target, node)
                ]
    return problems


@pytest.mark.parametrize("doc", DOCS)
def test_every_python_recipe_still_names_live_code(doc: str) -> None:
    """The gate itself, in both languages, since the code inside a fence is shared."""
    problems = check(_REPO / doc)
    assert not problems, "stale Python recipe(s):\n" + "\n".join(problems)


@pytest.mark.parametrize("doc", DOCS)
def test_the_gate_actually_reaches_the_recipes(doc: str) -> None:
    """A gate that silently matched nothing would pass forever.

    Both documents carry sixteen blocks and the blocks are not translated, so
    a count that drifts apart means one language gained or lost an example.
    """
    found = recipes(_REPO / doc)
    assert len(found) >= 15, f"{doc}: only {len(found)} python blocks found"
    assert len(found) == len(recipes(_REPO / DOCS[0])), (
        f"{doc} has {len(found)} python blocks against {len(recipes(_REPO / DOCS[0]))} in "
        f"{DOCS[0]}; the code in a fence is not translated, so they must agree"
    )


def test_a_renamed_function_is_caught(tmp_path: Path) -> None:
    """A checker that cannot fail is not a check.

    This is the failure the file exists for: a public name that went away,
    leaving a recipe that reads perfectly and imports nothing.
    """
    doc = tmp_path / "D.md"
    doc.write_text(
        "# T\n\n```python\nfrom best_engine_ai_helper import recommend_engines_obsolete\n```\n",
        encoding="utf-8",
    )
    assert any("names nothing" in problem for problem in check(doc))


def test_a_vanished_keyword_argument_is_caught(tmp_path: Path) -> None:
    """The quieter half: the function survives, the parameter does not."""
    doc = tmp_path / "D.md"
    doc.write_text(
        "# T\n\n```python\nfrom best_engine_ai_helper import offload\n"
        "offload.disk_required_gb({}, compression='4bit')\n```\n",
        encoding="utf-8",
    )
    assert any("has no parameter `compression`" in problem for problem in check(doc))


def test_a_submodule_import_is_not_a_breach(tmp_path: Path) -> None:
    """`from best_engine_ai_helper import llm` is valid, and `getattr` says None.

    A submodule becomes an attribute of its package only once something has
    imported it, so a check built on the namespace alone condemns the import
    every streaming recipe opens with. Four drafts of this fell for it.
    """
    doc = tmp_path / "D.md"
    doc.write_text(
        "# T\n\n```python\nfrom best_engine_ai_helper import llm\n```\n", encoding="utf-8"
    )
    assert check(doc) == []


def test_a_third_party_call_is_left_alone(tmp_path: Path) -> None:
    """`OpenAI(base_url=...)` is somebody else's contract, not ours to police."""
    doc = tmp_path / "D.md"
    doc.write_text(
        "# T\n\n```python\nfrom openai import OpenAI\n"
        "client = OpenAI(base_url='http://127.0.0.1:8000/v1', api_key='x')\n```\n",
        encoding="utf-8",
    )
    assert check(doc) == []
