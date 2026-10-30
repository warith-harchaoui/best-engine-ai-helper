"""Arithmetic checker for the worked examples printed in this repository's docs.

``scripts/check_doc_parity.py`` compares the two languages against each other.
It cannot compare either of them against the **code**, and it is structurally
blind to the failure that matters most in a worked example: a block of output
that was correct when it was pasted and has not been re-run since. Both
languages carry the same stale numbers, so parity calls them identical and is
right to.

That is not hypothetical. The engine descriptor in ``EXAMPLES.md`` showed::

    checkpoint_gb: 8.0
    disk_peak_gb: 16.8
    disk_steady_gb: 8.8

for a model whose checkpoint is 8.0 GB. Three numbers, in five consecutive
lines, that cannot all be true at once. The 2.1x peak is a fossil of the
runtime that decomposed a checkpoint into per-layer shards beside the original
before anything ran, so the cache briefly held both; :mod:`best_engine_ai_helper.streaming`
stopped doing that, :func:`best_engine_ai_helper.offload.disk_required_gb` now
returns the checkpoint for *both* keys, and the printed example went on
promising a reader a transient their drive will never see.

So this script reads the fenced ``yaml`` and ``json`` blocks in the shipped
documents and checks the **relations between the numbers inside one block**.
It never re-runs anything and never compares against this machine: every rule
below holds on any hardware, which is the only kind of rule a documented
example can be held to.

Six invariants, each naming what guarantees it:

1. ``disk_steady_gb == checkpoint_gb`` -- ``disk_required_gb`` returns the
   checkpoint's own size, because streaming memory-maps the original
   safetensors and copies nothing.
2. ``disk_peak_gb == disk_steady_gb`` -- same two lines of that function, one
   value. A peak that could differ would be a scratch copy, and there is none.
   This is also the only form in which the open question "is the equality a
   property of the runtime or a coincidence of this model?" can be answered
   where the consumer actually reads it.
3. ``seconds_per_token == round(1 / est_tokens_per_s, 1)`` -- two spellings of
   one measurement (``offload.seconds_per_token`` is the inversion). An
   example that updates the rate and not the inverse says two different things
   about the same model.
4. ``ram_gb < checkpoint_gb`` wherever ``streaming: true`` -- not a theorem
   about the code (a small model with an enormous context could in principle
   break it), but the claim the feature is *for*: resident memory is one
   layer, not the file. An example showing otherwise demonstrates the opposite
   of what its section is about.
5. ``backend: lightweight`` implies ``base_url: ''`` -- lightweight is a
   library running in the caller's process, and a port would send a reader
   looking for a daemon that will never exist.
6. ``backend: lightweight`` implies ``structured_output: false`` -- the
   backend has no schema-constrained generation, and ``engine.py`` hardcodes
   the ``False`` rather than deriving it.

An invariant is checked only where the block supplies every key it needs, so a
partial example is never penalised for being partial.

``CHANGELOG.md`` is excluded on purpose: it is a record of what the numbers
*were*, and correcting history there would be the actual error.

Deliberately dependency-free (stdlib only), like ``check_doc_parity.py``, so
the lightest CI lane runs it without installing anything.
``tests/test_doc_examples.py`` calls it, which is what puts it in the pre-push
gate and in CI.

Run it directly::

    python scripts/check_doc_examples.py          # exit 0 = the examples agree
    python scripts/check_doc_examples.py --list   # per-file counts, always exit 0

Author
------
[Warith Harchaoui](https://www.linkedin.com/in/warith-harchaoui/)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent

#: Root documents NOT held to the invariants below. ``CHANGELOG.md`` records
#: what the numbers *were*, and correcting history there would be the actual
#: error. Everything else at the repository root is in scope, discovered rather
#: than listed: a hand-written list is one more place to forget, and the whole
#: subject of this script is a printed number nobody remembered to re-read.
EXCLUDED: set[str] = {"CHANGELOG.md"}

#: Fence info strings whose body carries structured data. Bare fences are
#: terminal output in this repository and `sh` fences are commands; neither is
#: a mapping, and reading them as one produced only noise.
_DATA_INFO = {"yaml", "yml", "json"}


def documents() -> list[Path]:
    """
    Every root Markdown file in scope, in a stable order.

    Returns
    -------
    list[Path]
        Sorted by name, with :data:`EXCLUDED` removed. A document added to the
        repository is covered the moment it lands, which is the point: nobody
        has to remember this file exists.
    """
    return [path for path in sorted(_REPO.glob("*.md")) if path.name not in EXCLUDED]


# Fences inside a numbered list carry the list's indentation, and `README.md`
# puts its engine descriptor in one. The opening indent is captured so the
# keys underneath can be measured relative to it.
_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
# One `key: value` line, in either language of the two fence kinds: YAML writes
# the key bare, JSON quotes it. Keys here are always plain identifiers, which
# is what lets one regex read both.
_KEY = re.compile(r'^(\s*)-?\s*"?([A-Za-z_][A-Za-z0-9_]*)"?\s*:\s*(.*)$')


def strip_comment(text: str) -> str:
    """
    Drop a trailing ``#`` comment without cutting a URL fragment in half.

    The rule is the one a reader uses: a comment's ``#`` has whitespace in
    front of it (or starts the line), and an anchor's does not. Quoted text is
    left alone entirely, because a ``#`` inside quotes is data.

    Parameters
    ----------
    text : str
        One raw line.

    Returns
    -------
    str
        The line with any trailing comment removed, right-stripped.

    Examples
    --------
    >>> strip_comment("base_url: ''   # a library, not a server")
    "base_url: ''"
    >>> strip_comment("url: https://example.org/page#section")
    'url: https://example.org/page#section'
    >>> strip_comment("  # whole-line comment")
    ''
    """
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
    return text.rstrip()


def parse_scalar(raw: str) -> Any:
    """
    Read one YAML/JSON scalar the way both languages happen to agree on.

    Only the forms these documents actually use: numbers, booleans, null, and
    quoted or bare strings. Anything else comes back as the bare string, which
    every invariant below then declines to compare.

    Parameters
    ----------
    raw : str
        The text after the colon, comment already removed.

    Returns
    -------
    Any
        ``float``, ``bool``, ``None`` or ``str``.

    Examples
    --------
    >>> parse_scalar("8.0"), parse_scalar("true"), parse_scalar("''")
    (8.0, True, '')
    >>> parse_scalar("gemma3:12b")
    'gemma3:12b'
    """
    text = raw.strip().rstrip(",")
    if text in {"''", '""'}:
        return ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return float(text)
    except ValueError:
        return text


@dataclass
class Scope:
    """One mapping inside one fenced block: its keys, and where each was written.

    Attributes
    ----------
    path : Path
        The document the block came from.
    line : int
        1-based line of the key that opened this mapping, or of the fence for
        the block's top level.
    name : str
        Dotted path to this mapping, ``"<root>"`` for a block's top level.
    values : dict[str, Any]
        Scalar keys defined directly in this mapping. Nested mappings are
        separate :class:`Scope` objects, so ``llm.checkpoint_gb`` never
        collides with ``vlm.checkpoint_gb``.
    lines : dict[str, int]
        Where each of those keys was written, so a complaint can name a line.
    root : dict[str, Any]
        The block's top-level scalars, for the two rules whose condition
        (``backend``) may sit above the mapping it governs.
    """

    path: Path
    line: int
    name: str
    values: dict[str, Any] = field(default_factory=dict)
    lines: dict[str, int] = field(default_factory=dict)
    root: dict[str, Any] = field(default_factory=dict)

    def backend(self) -> Any:
        """Backend governing this mapping: its own if it names one, else the block's."""
        return self.values.get("backend", self.root.get("backend"))

    def where(self, *keys: str) -> str:
        """``path:line`` of the first of ``keys`` this mapping defines."""
        for key in keys:
            if key in self.lines:
                return f"{self.path.name}:{self.lines[key]}"
        return self.path.name


def _inline_pairs(body: str) -> list[tuple[str, str]]:
    """
    Split a one-line flow mapping into key/value pairs.

    ``README.md`` compresses a descriptor onto one line -- ``llm: {model:
    gemma3:12b, ram_gb: 9.2}`` -- and those numbers deserve the same checking
    as the expanded form. Splitting on the *first* colon of each comma-item is
    what keeps ``gemma3:12b`` intact.

    Examples
    --------
    >>> _inline_pairs("{model: gemma3:12b, ram_gb: 9.2}")
    [('model', 'gemma3:12b'), ('ram_gb', '9.2')]
    """
    inner = body.strip()
    if inner.startswith("{"):
        inner = inner[1:]
    if inner.endswith("}"):
        inner = inner[:-1]
    pairs: list[tuple[str, str]] = []
    for item in inner.split(","):
        if ":" not in item:
            continue
        key, _, value = item.partition(":")
        key = key.strip().strip("\"'")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            pairs.append((key, value.strip()))
    return pairs


def scopes(path: Path) -> list[Scope]:
    """
    Every mapping inside every data fence of one document.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    list[Scope]
        One entry per mapping, block top levels included. Order follows the
        file.
    """
    found: list[Scope] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    fence: str | None = None
    margin = 0
    stack: list[tuple[int, Scope]] = []
    root: dict[str, Any] = {}

    for number, raw in enumerate(lines, start=1):
        marker = _FENCE.match(raw)
        if marker and (fence is None or marker.group(2).startswith(fence)):
            if fence is None:
                info = marker.group(3).strip().lower()
                if info in _DATA_INFO:
                    fence, margin = marker.group(2), len(marker.group(1))
                    root = {}
                    top = Scope(path=path, line=number, name="<root>", root=root)
                    stack = [(-1, top)]
                    found.append(top)
                continue
            fence, margin = None, 0
            stack = []
            continue
        if fence is None or not stack:
            continue

        line = strip_comment(raw)
        entry = _KEY.match(line)
        if not entry:
            continue
        indent = len(entry.group(1)) - margin
        key, rest = entry.group(2), entry.group(3).strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if rest.startswith("{") and rest.endswith("}"):
            child = Scope(
                path=path,
                line=number,
                name=f"{parent.name}.{key}" if parent.name != "<root>" else key,
                root=root,
            )
            for inner_key, inner_value in _inline_pairs(rest):
                child.values[inner_key] = parse_scalar(inner_value)
                child.lines[inner_key] = number
            found.append(child)
            continue
        if rest in {"", "{", "[", "|", ">"}:
            child = Scope(
                path=path,
                line=number,
                name=f"{parent.name}.{key}" if parent.name != "<root>" else key,
                root=root,
            )
            found.append(child)
            stack.append((indent, child))
            continue

        value = parse_scalar(rest)
        parent.values[key] = value
        parent.lines[key] = number
        if parent.name == "<root>":
            root[key] = value

    return found


@dataclass(frozen=True)
class Invariant:
    """One relation a documented example must satisfy, on any machine.

    Attributes
    ----------
    name : str
        Short handle, printed when it fires.
    needs : tuple[str, ...]
        Keys the mapping must define for the rule to apply at all.
    holds : Callable[[Scope], bool]
        True when the example is coherent.
    explain : Callable[[Scope], str]
        What to say when it is not, in the terms of the block that broke it.
    applies : Callable[[Scope], bool]
        Extra condition beyond ``needs`` -- the backend, or ``streaming``.
    """

    name: str
    needs: tuple[str, ...]
    holds: Callable[[Scope], bool]
    explain: Callable[[Scope], str]
    applies: Callable[[Scope], bool] = lambda scope: True


def _numbers(scope: Scope, *keys: str) -> list[float] | None:
    """The named keys as floats, or None if any is missing or not a number."""
    out: list[float] = []
    for key in keys:
        value = scope.values.get(key)
        if not isinstance(value, float) or isinstance(value, bool):
            return None
        out.append(value)
    return out


def _steady_is_the_checkpoint(scope: Scope) -> bool:
    pair = _numbers(scope, "disk_steady_gb", "checkpoint_gb")
    return pair is None or round(pair[0], 1) == round(pair[1], 1)


def _peak_is_steady(scope: Scope) -> bool:
    pair = _numbers(scope, "disk_peak_gb", "disk_steady_gb")
    return pair is None or round(pair[0], 1) == round(pair[1], 1)


def _rate_inverts(scope: Scope) -> bool:
    pair = _numbers(scope, "seconds_per_token", "est_tokens_per_s")
    if pair is None or pair[1] <= 0:
        return True
    return round(pair[0], 1) == round(1.0 / pair[1], 1)


def _resident_below_checkpoint(scope: Scope) -> bool:
    pair = _numbers(scope, "ram_gb", "checkpoint_gb")
    return pair is None or pair[0] < pair[1]


INVARIANTS: list[Invariant] = [
    Invariant(
        name="steady-is-the-checkpoint",
        needs=("disk_steady_gb", "checkpoint_gb"),
        holds=_steady_is_the_checkpoint,
        explain=lambda s: (
            f"disk_steady_gb {s.values['disk_steady_gb']} is not the "
            f"checkpoint_gb {s.values['checkpoint_gb']} printed beside it; "
            "`offload.disk_required_gb` returns the checkpoint's own size, "
            "because streaming memory-maps the original and copies nothing"
        ),
    ),
    Invariant(
        name="peak-is-steady",
        needs=("disk_peak_gb", "disk_steady_gb"),
        holds=_peak_is_steady,
        explain=lambda s: (
            f"disk_peak_gb {s.values['disk_peak_gb']} differs from "
            f"disk_steady_gb {s.values['disk_steady_gb']}; a peak above the "
            "steady figure is a scratch copy, and this runtime makes none"
        ),
    ),
    Invariant(
        name="rate-inverts",
        needs=("seconds_per_token", "est_tokens_per_s"),
        holds=_rate_inverts,
        explain=lambda s: (
            f"seconds_per_token {s.values['seconds_per_token']} is not "
            f"1 / est_tokens_per_s {s.values['est_tokens_per_s']} "
            f"(= {round(1.0 / s.values['est_tokens_per_s'], 1)}); the two are "
            "one measurement written twice"
        ),
    ),
    Invariant(
        name="resident-below-checkpoint",
        needs=("ram_gb", "checkpoint_gb"),
        applies=lambda s: s.values.get("streaming") is True,
        holds=_resident_below_checkpoint,
        explain=lambda s: (
            f"ram_gb {s.values['ram_gb']} is not below checkpoint_gb "
            f"{s.values['checkpoint_gb']} in an example that claims "
            "streaming: true, which is the one thing streaming is for"
        ),
    ),
    Invariant(
        name="lightweight-has-no-port",
        needs=("base_url",),
        applies=lambda s: s.backend() == "lightweight",
        holds=lambda s: s.values.get("base_url") == "",
        explain=lambda s: (
            f"backend lightweight publishes base_url {s.values['base_url']!r}; "
            "it is a library running in the caller's process, and a port sends "
            "a reader looking for a daemon that will never exist"
        ),
    ),
    Invariant(
        name="lightweight-has-no-schema",
        needs=("structured_output",),
        applies=lambda s: s.backend() == "lightweight",
        holds=lambda s: s.values.get("structured_output") is False,
        explain=lambda s: (
            "backend lightweight claims structured_output "
            f"{s.values['structured_output']!r}; the backend has no "
            "schema-constrained generation and `engine.py` writes False"
        ),
    ),
]


def check(path: Path) -> list[str]:
    """
    Every invariant breach in one document, as sentences naming a line.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    list[str]
        Empty when every fenced example is coherent.
    """
    problems: list[str] = []
    for scope in scopes(path):
        for rule in INVARIANTS:
            if not all(key in scope.values for key in rule.needs):
                continue
            if not rule.applies(scope):
                continue
            if not rule.holds(scope):
                problems.append(
                    f"{scope.where(*rule.needs)} [{rule.name}] in `{scope.name}`: "
                    f"{rule.explain(scope)}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    """
    Command-line entry point.

    Parameters
    ----------
    argv : list[str] or None
        Arguments, defaulting to ``sys.argv[1:]``.

    Returns
    -------
    int
        0 when every documented example is coherent, 1 otherwise.

    Examples
    --------
    ``--list`` describes what was read and never judges it, so a doctest can
    call it without the repository's current state deciding the outcome:

    >>> import contextlib, io
    >>> out = io.StringIO()
    >>> with contextlib.redirect_stdout(out):
    ...     status = main(["--list"])
    >>> status
    0
    >>> "README.md" in out.getvalue()
    True
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list",
        action="store_true",
        help="print what each document contains and exit 0, without judging it",
    )
    args = parser.parse_args(argv)

    total = 0
    scanned = documents()
    for path in scanned:
        name = path.name
        if args.list:
            found = scopes(path)
            checked = sum(
                1
                for scope in found
                for rule in INVARIANTS
                if all(key in scope.values for key in rule.needs) and rule.applies(scope)
            )
            print(f"{name:<16} {len(found):>3} mappings {checked:>3} invariant(s) applied")
            continue
        problems = check(path)
        print(f"{name}: {'ok' if not problems else f'{len(problems)} problem(s)'}")
        for problem in problems:
            print(f"  {problem}")
        total += len(problems)

    if args.list:
        return 0
    if total:
        print(f"\n{total} incoherent example(s) across {len(scanned)} document(s)")
        return 1
    print(f"\nevery documented example is coherent ({len(scanned)} documents)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
