"""Link checker for this repository's documents: every target has to exist.

The third external standard, after `check_doc_parity.py` (the two languages
against each other) and `check_doc_examples.py` (the numbers inside one block
against each other). A link is a claim that something is *there*, and nothing
re-read those claims after the things moved.

Two were already wrong. `CONTRIBUTING.md` and `GUI.md` both link
``[`locales/i18n.yaml`](locales/i18n.yaml)``, and there is no `locales/`
directory at the repository root: the catalogue lives inside the package, at
`best_engine_ai_helper/locales/i18n.yaml`, and `CHANGELOG.md` records the move
that put it there. Both links have returned a 404 on GitHub ever since, in two
documents whose subject is where that file is. A test in this same repository
asserts the catalogue "sits inside the package" while two documents point
outside it, and nothing compared the two.

What is checked, and nothing else:

* a relative path resolves to a file that exists;
* a `#fragment` matches a heading in the document that carries it;
* a `path#fragment` does both, the fragment against the *target* document.

`http(s)` and `mailto:` are left alone on purpose. Reaching the network would
make this checker's verdict depend on somebody else's uptime, and a gate that
goes red because a third party is down is a gate people learn to skip.

Three traps, each of which made an earlier draft of this script lie. They are
written down because every one of them produced a confident list of breaches
that were not there:

1. **GitHub keeps accented letters in an anchor.** Normalising through NFKD
   and dropping combining marks turns `#7-trop-gros-pour-tenir` into something
   no French heading ever generates, and reports every anchor in the French
   documents as broken. Nineteen false alarms.
2. **Each space becomes its own hyphen.** French puts a space *before* a
   colon, so `quand même : le flux` loses the colon and keeps both spaces
   around it, and the anchor really does contain `--`. Collapsing whitespace
   with `\\s+` reports the two correct links that rely on this as broken. A
   comma, which carries no space before it, leaves only one hyphen -- so the
   rule has to be per-space, not per-run-of-space.
3. **`](#)` is a badge that is deliberately not a link.** The shields row in
   both READMEs uses it for the Python-version badge, which is decoration
   rather than navigation. Reading it as an empty anchor reports two more.

A checker that cannot tell a convention from a defect is worse than no
checker, because its noise is indistinguishable from its signal.

Deliberately dependency-free (stdlib only), like its two siblings.
`tests/test_doc_links.py` calls it, which is what puts it in the gate.

Run it directly::

    python scripts/check_doc_links.py           # exit 0 = every target exists
    python scripts/check_doc_links.py --list    # per-document counts, exit 0

Author
------
[Warith Harchaoui](https://www.linkedin.com/in/warith-harchaoui/)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

#: Documents NOT checked. `CHANGELOG.md` names files as they were at the time
#: of each release, so a path that has since moved is history rather than a
#: breach, exactly as in ``check_doc_examples.py``.
EXCLUDED: set[str] = {"CHANGELOG.md"}

#: Link targets that are a convention rather than a destination. The shields
#: row in both READMEs writes `](#)` for a badge that is decoration.
_NOT_A_TARGET: set[str] = {"#"}

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# Every Markdown link and image ends `](target)`, however the text nests.
_LINK = re.compile(r"\]\(([^)\s]+)\)")


def anchor_of(heading: str) -> str:
    """
    GitHub's anchor for one heading's text.

    Inline markup is unwrapped first (a heading may carry code spans, emphasis
    or even a link), then everything that is not a word character, a space or
    a hyphen is dropped, and each remaining space becomes a hyphen.

    Parameters
    ----------
    heading : str
        The heading text, without its leading ``#`` marks.

    Returns
    -------
    str
        The fragment a link has to use to reach it.

    Examples
    --------
    >>> anchor_of("Setup")
    'setup'
    >>> anchor_of("1. What this machine can run")
    '1-what-this-machine-can-run'
    >>> # Accents survive, and French spacing before a colon leaves TWO spaces
    >>> # once the colon is dropped, so the anchor really does carry `--`.
    >>> anchor_of("Trop gros : exécutable")
    'trop-gros--exécutable'
    >>> anchor_of("Trop gros, exécutable")   # a comma leaves only one
    'trop-gros-exécutable'
    """
    text = re.sub(r"`([^`]*)`", r"\1", heading.strip())
    text = re.sub(r"\*\*?([^*]*)\*\*?", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    return text.replace(" ", "-").strip("-")


def anchors(path: Path) -> set[str]:
    """
    Every fragment one document offers, from its headings.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    set[str]
        Fragments, without the leading ``#``. Empty if the file is unreadable,
        which the caller reports as a missing file rather than as no anchors.
    """
    if not path.is_file():
        return set()
    found: set[str] = set()
    fence: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        marker = _FENCE.match(raw)
        if marker and (fence is None or marker.group(2).startswith(fence)):
            fence = None if fence else marker.group(2)
            continue
        if fence:
            continue
        heading = _HEADING.match(raw)
        if heading:
            found.add(anchor_of(heading.group(2)))
    return found


def links(path: Path) -> list[tuple[int, str]]:
    """
    Every link target in one document, with the line it sits on.

    Fenced blocks are skipped: a URL inside example output is not a link, and
    reading it as one is how a checker starts reporting someone else's server.
    """
    out: list[tuple[int, str]] = []
    fence: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        marker = _FENCE.match(raw)
        if marker and (fence is None or marker.group(2).startswith(fence)):
            fence = None if fence else marker.group(2)
            continue
        if fence:
            continue
        out += [(number, target) for target in _LINK.findall(raw)]
    return out


def check(path: Path) -> list[str]:
    """
    Every link in one document whose target does not exist.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    list[str]
        Empty when every relative target resolves.
    """
    problems: list[str] = []
    own = anchors(path)
    for number, target in links(path):
        if target in _NOT_A_TARGET or target.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, fragment = target.partition("#")
        if not file_part:
            if fragment not in own:
                problems.append(f"{path.name}:{number} no heading makes the anchor #{fragment}")
            continue
        destination = (_REPO / file_part).resolve()
        if not destination.exists():
            problems.append(f"{path.name}:{number} links {file_part}, which does not exist")
            continue
        if fragment and destination.suffix == ".md":
            if fragment not in anchors(destination):
                problems.append(
                    f"{path.name}:{number} links {file_part}#{fragment}, "
                    f"and {destination.name} has no such heading"
                )
    return problems


def documents() -> list[Path]:
    """Root Markdown files in scope, sorted, with :data:`EXCLUDED` removed."""
    return [path for path in sorted(_REPO.glob("*.md")) if path.name not in EXCLUDED]


def main(argv: list[str] | None = None) -> int:
    """
    Command-line entry point.

    Returns
    -------
    int
        0 when every relative target resolves, 1 otherwise.

    Examples
    --------
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
        if args.list:
            targets = [t for _, t in links(path)]
            local = [t for t in targets if not t.startswith(("http", "mailto:"))]
            print(
                f"{path.name:<16} {len(targets):>4} links "
                f"{len(local):>3} local {len(anchors(path)):>3} anchors"
            )
            continue
        problems = check(path)
        print(f"{path.name}: {'ok' if not problems else f'{len(problems)} problem(s)'}")
        for problem in problems:
            print(f"  {problem}")
        total += len(problems)

    if args.list:
        return 0
    if total:
        print(f"\n{total} broken link(s) across {len(scanned)} document(s)")
        return 1
    print(f"\nevery documented link resolves ({len(scanned)} documents)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
