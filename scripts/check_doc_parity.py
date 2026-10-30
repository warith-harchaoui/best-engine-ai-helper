"""Structural parity checker for this repository's mirrored English/French docs.

Three of the root Markdown files ship twice, once per language::

    README.md   <-> LISEZMOI.md
    EXAMPLES.md <-> EXEMPLES.md
    LANDSCAPE.md<-> PAYSAGE.md

That is roughly 7,000 lines of prose maintained as six files, and nothing
checked that the two halves still said the same thing. They twice did not.
The failure mode is not a mistranslation -- a human reading either file alone
notices nothing -- it is **structure diverging while each side stays locally
coherent**: a section that was promoted in one language and not the other, a
heading that exists only in French, a line of terminal output trimmed from the
French panel while the French paragraph underneath still promises it.

What this script compares is therefore the *skeleton*, never the wording. Six
invariants, each chosen because it holds across a translation and breaks on a
drift:

1. **Heading levels, in order.** The text differs by language; the shape does
   not. A section promoted, demoted, moved, added or dropped on one side only
   shows up here and nowhere else.
2. **Fenced blocks, per section.** Code and terminal output are mostly not
   translated, so the *number and kind* of fences under a given heading is a
   language-independent fact.
3. **Shell command skeletons.** Inside ``sh``/``bash``/``console`` fences:
   the command head plus its flags, with quoted arguments and trailing
   comments removed -- those are legitimately translated (``--task "invoice
   lines"`` / ``--task "lignes de facture"``), a renamed flag is not.
4. **Link targets.** URLs are not translated either, except for the handful
   of file and asset names that have a deliberate twin; those go through
   :data:`MIRROR` first, and ``#fragments`` are dropped because anchors are
   generated from translated headings.
5. **Fence sizes.** How many *significant* lines (blank lines and whole-line
   comments removed, because a translated comment wraps differently) each
   block holds. A row quietly dropped from a terminal panel changes no
   heading and no block count, so nothing above sees it.
6. **Tables, per section.** Same reasoning as fences: a table is a structure,
   and one side gaining or losing a row-separator line means the two files no
   longer present the same material.

Deliberately dependency-free (stdlib only), like
``scripts/check_triggers.py``, so the lightest CI lane runs it without
installing anything. ``tests/test_doc_parity.py`` calls it, which is what puts
it in the pre-push gate and in CI.

Run it directly::

    python scripts/check_doc_parity.py           # exit 0 = the pairs agree
    python scripts/check_doc_parity.py --list    # per-pair counts, always exit 0

Author
------
[Warith Harchaoui](https://www.linkedin.com/in/warith-harchaoui/)
"""

from __future__ import annotations

import argparse
import difflib
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

#: The mirrored files, English first. Adding a pair here is the only edit a new
#: translated document needs.
PAIRS: list[tuple[str, str]] = [
    ("README.md", "LISEZMOI.md"),
    ("EXAMPLES.md", "EXEMPLES.md"),
    ("LANDSCAPE.md", "PAYSAGE.md"),
]

#: Names that differ between the two languages **on purpose**, English -> French.
#: Applied to link targets before they are compared, so that a French file
#: pointing at ``EXEMPLES.md`` and ``paysage.png`` counts as agreeing with an
#: English file pointing at ``EXAMPLES.md`` and ``landscape.png``. Everything
#: NOT in this map must match literally -- that is the point: an asset that
#: gained a French twin has to be declared here, not discovered by a reader.
MIRROR: dict[str, str] = {
    "README.md": "LISEZMOI.md",
    "EXAMPLES.md": "EXEMPLES.md",
    "LANDSCAPE.md": "PAYSAGE.md",
    "how-it-works": "comment-ca-marche",
    "two-sources": "deux-sources",
    "three-families": "trois-familles",
    "measurement-loop": "boucle-de-mesure",
    "memory-budget": "budget-memoire",
    "arena-staleness": "obsolescence-arena",
    "selection-pipeline": "pipeline-de-selection",
    "streamed-forward-pass": "passe-avant-en-flux",
    "streaming-triggers": "declencheurs-du-flux",
    "where-it-runs": "ou-ca-tourne",
    "virtual-model-name": "nom-de-modele-virtuel",
    "landscape": "paysage",
}

#: Fence info strings whose body is read as shell. A bare fence (no info
#: string) is NOT shell: this repository uses it for terminal output and for
#: pseudo-formulas, both of which translate, and reading those as commands
#: produced nothing but false alarms.
_SHELL_INFO = {"sh", "bash", "shell", "console", "zsh"}

_FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
# Every Markdown link and image, however nested, ends ``](target)``. Matching
# the bracketed text as well -- the obvious spelling -- gets the badge idiom
# ``[![alt](shield.svg)](LICENSE)`` wrong whichever way it is written: a
# non-nesting character class stops at the inner ``]`` and returns the shield
# while losing the LICENSE, and a nesting one returns the LICENSE while losing
# the shield. Anchoring on the closing bracket alone returns both.
_LINK = re.compile(r"\]\(([^)\s]+)")
_BARE_URL = re.compile(r"(?<![(<\w])(https?://[^\s)\]\"'<>]+)")


@dataclass
class Block:
    """One fenced block: where it starts, its info string, and its body."""

    line: int
    info: str
    section: int
    body: list[str] = field(default_factory=list)


@dataclass
class Doc:
    """A parsed Markdown document, reduced to the parts a translation preserves.

    Attributes
    ----------
    path : Path
        The file this came from.
    headings : list[tuple[int, str, int]]
        ``(level, text, line)`` for every ATX heading outside a fence.
    blocks : list[Block]
        Every fenced block, tagged with the index of the heading it sits under
        (``-1`` for the preamble above the first heading).
    links : list[tuple[str, int]]
        ``(target, line)`` for every link, image and bare URL outside a fence.
    tables : list[int]
        Section index of every table separator row, one entry per table.
    """

    path: Path
    headings: list[tuple[int, str, int]] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    links: list[tuple[str, int]] = field(default_factory=list)
    tables: list[int] = field(default_factory=list)

    def heading_line(self, index: int) -> int:
        """Line number of heading *index*, or 0 for the preamble.

        Examples
        --------
        >>> Doc(Path("x"), headings=[(1, "Title", 3)]).heading_line(0)
        3
        >>> Doc(Path("x")).heading_line(-1)
        0
        """
        if 0 <= index < len(self.headings):
            return self.headings[index][2]
        return 0

    def heading_text(self, index: int) -> str:
        """Text of heading *index*, or ``'(preamble)'`` for the part above the first.

        Examples
        --------
        >>> Doc(Path("x"), headings=[(2, "Install", 9)]).heading_text(0)
        'Install'
        >>> Doc(Path("x")).heading_text(-1)
        '(preamble)'
        """
        if 0 <= index < len(self.headings):
            return self.headings[index][1]
        return "(preamble)"


@dataclass
class Problem:
    """One parity breach, phrased so the message alone is actionable."""

    check: str
    message: str

    def __str__(self) -> str:
        """Render as ``check: message``.

        Examples
        --------
        >>> print(Problem("headings", "level 3 vs level 4"))
        headings: level 3 vs level 4
        """
        return f"{self.check}: {self.message}"


def parse(path: Path) -> Doc:
    """Read *path* and reduce it to its translation-invariant skeleton.

    A single pass, because the three pieces of state interact: headings and
    links must be ignored inside a fence (this repository's shell blocks are
    full of ``# comment`` lines that look exactly like ATX headings -- the
    first draft of this checker reported three phantom headings in each file
    for precisely that reason), and a fence must be closed by its own delimiter
    rather than by any run of backticks.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    Doc
        The parsed skeleton.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d:
    ...     p = pathlib.Path(d) / "m.md"
    ...     _ = p.write_text("# T\\n\\n```sh\\n# not a heading\\nls -l\\n```\\n")
    ...     doc = parse(p)
    >>> [(lvl, txt) for lvl, txt, _ in doc.headings]
    [(1, 'T')]
    >>> doc.blocks[0].info, doc.blocks[0].body
    ('sh', ['# not a heading', 'ls -l'])
    """
    doc = Doc(path=path)
    fence: tuple[str, int] | None = None
    current: Block | None = None
    section = -1

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _FENCE.match(raw)
        if match is not None:
            marker, info = match.group(1), match.group(2).strip()
            if fence is None:
                fence = (marker[0], len(marker))
                current = Block(line=lineno, info=info, section=section)
                continue
            # A closing delimiter is the same character, at least as long, and
            # carries no info string -- otherwise ```` ```python ```` nested in
            # an outer ```` ```` ```` block would close it.
            if marker[0] == fence[0] and len(marker) >= fence[1] and not info:
                fence = None
                if current is not None:
                    doc.blocks.append(current)
                current = None
                continue

        if fence is not None:
            if current is not None:
                current.body.append(raw)
            continue

        heading = _HEADING.match(raw)
        if heading is not None:
            doc.headings.append((len(heading.group(1)), heading.group(2).strip(), lineno))
            section = len(doc.headings) - 1
            continue

        if _TABLE_RULE.match(raw):
            doc.tables.append(section)

        for target in _LINK.findall(raw):
            doc.links.append((target, lineno))
        for url in _BARE_URL.findall(raw):
            doc.links.append((url, lineno))

    # An unterminated fence is a malformed document, not a parity question, but
    # swallowing it would hide the rest of the file from every check below.
    if current is not None:
        doc.blocks.append(current)
    return doc


def mirror(target: str) -> str:
    """Rewrite a link target into its English spelling, for comparison only.

    Parameters
    ----------
    target : str
        A link target as written, possibly with a ``#fragment``.

    Returns
    -------
    str
        The target with every :data:`MIRROR` value replaced by its key and the
        fragment removed. Anchors are generated from headings, so they are
        translated by construction and cannot be compared.

    Examples
    --------
    >>> mirror("https://example.org/blob/main/EXEMPLES.md#un-titre")
    'https://example.org/blob/main/EXAMPLES.md'
    >>> mirror("assets/diagrams/deux-sources.png")
    'assets/diagrams/two-sources.png'
    >>> mirror("https://example.org/plain")
    'https://example.org/plain'
    """
    cleaned = target.split("#", 1)[0].rstrip(".,;:")
    for english, french in MIRROR.items():
        cleaned = cleaned.replace(french, english)
    return cleaned


def command_skeleton(block: Block) -> list[str]:
    """The commands in a shell *block*, stripped of everything a translator touches.

    Keeps the command head (the executable and its subcommands) and every
    flag; drops quoted arguments, operands and trailing comments. Those are
    where the French and English examples legitimately differ -- ``--prompt "a
    red bicycle"`` against ``--prompt "un vélo rouge"`` -- while a renamed or
    dropped flag is exactly the drift worth catching.

    Parameters
    ----------
    block : Block
        A fenced block; a non-shell info string yields an empty list.

    Returns
    -------
    list[str]
        One normalised string per command line.

    Examples
    --------
    >>> b = Block(line=1, info="sh", section=0, body=[
    ...     '# a comment line',
    ...     'best-engine-ai-helper report --task "invoice lines" --out engine.env',
    ... ])
    >>> command_skeleton(b)
    ['best-engine-ai-helper report --task --out']
    >>> command_skeleton(Block(line=1, info="yaml", section=0, body=["a: 1"]))
    []
    """
    if (block.info.split()[0].lower() if block.info else "") not in _SHELL_INFO:
        return []

    out: list[str] = []
    for raw in block.body:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            # An unbalanced quote in a prose-y example line; splitting on
            # whitespace is a worse answer than skipping, but never a wrong one.
            tokens = line.split()
        kept: list[str] = []
        seen_flag = False
        for token in tokens:
            if token.startswith("-"):
                seen_flag = True
                kept.append(token)
            elif not seen_flag:
                kept.append(token)
        if kept:
            out.append(" ".join(kept))
    return out


def _sequence_problems(
    check: str,
    en: Doc,
    fr: Doc,
    en_items: list[str],
    fr_items: list[str],
    en_lines: list[int],
    fr_lines: list[int],
    en_display: list[str] | None = None,
    fr_display: list[str] | None = None,
) -> list[Problem]:
    """Diff two parallel sequences and phrase each opcode as a Problem.

    A sequence diff rather than a zip: one inserted heading shifts everything
    after it, and reporting fifty breaches for one edit teaches people to
    ignore the check.

    Parameters
    ----------
    check : str
        Name of the invariant, used as the problem's prefix.
    en, fr : Doc
        The two documents, for their paths.
    en_items, fr_items : list[str]
        The two sequences being compared. These are what the diff is computed
        on, so they must hold nothing a translation may change.
    en_lines, fr_lines : list[int]
        Line numbers, parallel to the sequences.
    en_display, fr_display : list[str] or None
        What to *print* for each item, when the compared key is too terse to
        locate (a bare ``h3``). ``None`` prints the compared key itself.

    Returns
    -------
    list[Problem]
        One entry per differing opcode.

    Examples
    --------
    >>> a, b = Doc(Path("a.md")), Doc(Path("b.md"))
    >>> probs = _sequence_problems("x", a, b, ["p", "q"], ["p"], [1, 2], [1])
    >>> print(probs[0])
    x: b.md is missing 'q' (a.md:2)
    """
    shown_en = en_display if en_display is not None else en_items
    shown_fr = fr_display if fr_display is not None else fr_items
    problems: list[Problem] = []
    matcher = difflib.SequenceMatcher(None, en_items, fr_items, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            problems += [
                Problem(
                    check,
                    f"{fr.path.name} is missing {shown_en[k]!r} ({en.path.name}:{en_lines[k]})",
                )
                for k in range(i1, i2)
            ]
        elif tag == "insert":
            problems += [
                Problem(
                    check,
                    f"{en.path.name} is missing {shown_fr[k]!r} ({fr.path.name}:{fr_lines[k]})",
                )
                for k in range(j1, j2)
            ]
        else:
            left = ", ".join(repr(shown_en[k]) for k in range(i1, i2))
            right = ", ".join(repr(shown_fr[k]) for k in range(j1, j2))
            problems.append(
                Problem(
                    check,
                    f"{en.path.name}:{en_lines[i1]} has {left} "
                    f"where {fr.path.name}:{fr_lines[j1]} has {right}",
                )
            )
    return problems


def check_headings(en: Doc, fr: Doc) -> list[Problem]:
    """Compare the two heading skeletons: level and order, never text.

    The compared key is the level alone -- the text is in another language, so
    it cannot be an invariant. The ancestry (``h3 Install > Linux``) rides
    along for the *message* only: "h3 under Install" locates a breach far
    faster than "h3", and a reader who has to count headings to find the
    offending one will not run the check twice.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        Empty when the two outlines have the same shape.

    Examples
    --------
    >>> a = Doc(Path("a.md"), headings=[(1, "T", 1), (2, "S", 5)])
    >>> b = Doc(Path("b.md"), headings=[(1, "T", 1), (3, "S", 6)])
    >>> print(check_headings(a, b)[0])
    headings: a.md:5 has 'h2 T > S' where b.md:6 has 'h3 T > ? > S'
    """

    def trails(doc: Doc) -> list[str]:
        """Each heading as ``hN ancestor > ... > self``."""
        trail: list[str] = []
        out: list[str] = []
        for level, text, _ in doc.headings:
            del trail[level - 1 :]
            while len(trail) < level - 1:
                trail.append("?")
            trail.append(text)
            out.append(f"h{level} " + " > ".join(trail))
        return out

    return _sequence_problems(
        "headings",
        en,
        fr,
        [f"h{lvl}" for lvl, _, _ in en.headings],
        [f"h{lvl}" for lvl, _, _ in fr.headings],
        [line for _, _, line in en.headings],
        [line for _, _, line in fr.headings],
        en_display=trails(en),
        fr_display=trails(fr),
    )


def check_fences(en: Doc, fr: Doc) -> list[Problem]:
    """Compare fenced blocks, keyed by the section they live under.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        Empty when both files carry the same fences in the same sections.

    Examples
    --------
    >>> a = Doc(Path("a.md"), headings=[(2, "Run", 1)],
    ...         blocks=[Block(line=3, info="sh", section=0)])
    >>> b = Doc(Path("b.md"), headings=[(2, "Exécuter", 1)], blocks=[])
    >>> print(check_fences(a, b)[0])
    fences: b.md is missing '[Run] sh' (a.md:3)
    """
    if len(en.headings) != len(fr.headings):
        # The heading check already reported this, and section indices are not
        # comparable until it is fixed; a second wave of noise helps nobody.
        return []

    def keys(doc: Doc) -> tuple[list[str], list[int]]:
        items = [f"[{doc.heading_text(b.section)}] {b.info or '(bare)'}" for b in doc.blocks]
        return items, [b.line for b in doc.blocks]

    en_items, en_lines = keys(en)
    fr_items, fr_lines = keys(fr)
    # The French section titles are translated, so compare on the position of
    # the section rather than on its name; the name rides along for the message.
    en_cmp = [f"{b.section}:{b.info or '(bare)'}" for b in en.blocks]
    fr_cmp = [f"{b.section}:{b.info or '(bare)'}" for b in fr.blocks]
    if en_cmp == fr_cmp:
        return []
    return _sequence_problems("fences", en, fr, en_items, fr_items, en_lines, fr_lines)


def check_commands(en: Doc, fr: Doc) -> list[Problem]:
    """Compare the shell command skeletons, in document order.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        Empty when both files run the same commands with the same flags.

    Examples
    --------
    >>> a = Doc(Path("a.md"), blocks=[Block(1, "sh", 0, ["tool run --fast"])])
    >>> b = Doc(Path("b.md"), blocks=[Block(1, "sh", 0, ["tool run"])])
    >>> print(check_commands(a, b)[0])
    commands: a.md:1 has 'tool run --fast' where b.md:1 has 'tool run'
    """
    en_items: list[str] = []
    en_lines: list[int] = []
    for block in en.blocks:
        for command in command_skeleton(block):
            en_items.append(command)
            en_lines.append(block.line)
    fr_items: list[str] = []
    fr_lines: list[int] = []
    for block in fr.blocks:
        for command in command_skeleton(block):
            fr_items.append(command)
            fr_lines.append(block.line)
    return _sequence_problems("commands", en, fr, en_items, fr_items, en_lines, fr_lines)


def significant(block: Block) -> list[str]:
    """The lines of *block* a translation does not get to change the number of.

    Blank lines and whole-line ``#`` comments are dropped, and only those:
    French prose is ~15% longer than English, so a translated comment wraps
    onto one more line and a raw line count reports a breach for every
    commented shell block in the repository. What is left is the *material* --
    commands, configuration keys, the rows of a terminal panel -- and that
    count is a fact about the example rather than about the language.

    Measured over the 125 fenced blocks in the three pairs, this rule fired
    once, on a real defect: a French terminal panel that had lost the repair
    command its own surrounding paragraph promised.

    Parameters
    ----------
    block : Block
        A fenced block.

    Returns
    -------
    list[str]
        The surviving lines, stripped.

    Examples
    --------
    >>> significant(Block(1, "sh", 0, ["# why", "", "ls -l"]))
    ['ls -l']
    """
    return [
        line.strip() for line in block.body if line.strip() and not line.strip().startswith("#")
    ]


def check_fence_sizes(en: Doc, fr: Doc) -> list[Problem]:
    """Compare how much material each fenced block holds.

    :func:`check_fences` asks whether the two files have the same blocks in the
    same places; this asks whether each block still holds the same amount.
    A line quietly dropped from one side -- the breach this check was written
    for -- changes neither the block count nor any heading, so nothing else
    sees it.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        One entry per block whose significant-line counts differ.

    Examples
    --------
    >>> a = Doc(Path("a.md"), blocks=[Block(3, "", 0, ["ok", "repair: pip install x"])])
    >>> b = Doc(Path("b.md"), blocks=[Block(3, "", 0, ["ok"])])
    >>> print(check_fence_sizes(a, b)[0])
    sizes: the '(bare)' block at a.md:3 holds 2 line(s), its twin at b.md:3 holds 1
    """
    if len(en.blocks) != len(fr.blocks):
        # check_fences already named the structural difference, and the blocks
        # no longer line up positionally, so every pair after the first would
        # be compared against the wrong twin.
        return []
    problems: list[Problem] = []
    for en_block, fr_block in zip(en.blocks, fr.blocks, strict=True):
        left, right = len(significant(en_block)), len(significant(fr_block))
        if left == right:
            continue
        problems.append(
            Problem(
                "sizes",
                f"the {en_block.info or '(bare)'!r} block at "
                f"{en.path.name}:{en_block.line} holds {left} line(s), "
                f"its twin at {fr.path.name}:{fr_block.line} holds {right}",
            )
        )
    return problems


def check_links(en: Doc, fr: Doc) -> list[Problem]:
    """Compare link targets as multisets, after :func:`mirror`.

    Order is not compared here -- a translated paragraph may legitimately move
    a reference a line or two -- but the *count* is: a cross-reference that
    exists twice in one language and once in the other is a reader of one
    language being sent somewhere a reader of the other is not.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        One entry per target whose two counts differ.

    Examples
    --------
    >>> a = Doc(Path("a.md"), links=[("https://x.test/a", 4), ("#here", 9)])
    >>> b = Doc(Path("b.md"), links=[])
    >>> for p in check_links(a, b): print(p)
    links: '(in-page anchor)' appears 1x in a.md (first at :9) and 0x in b.md
    links: 'https://x.test/a' appears 1x in a.md (first at :4) and 0x in b.md
    """
    from collections import Counter

    def key(target: str) -> str:
        # A link that is only a fragment points at a heading, and headings are
        # translated, so its target cannot be compared across the pair. Its
        # *presence* still can: a "see below" the French reader gets and the
        # English one does not is a real difference, so they are pooled under
        # one label and counted rather than dropped.
        return mirror(target) or "(in-page anchor)"

    en_counts = Counter(key(t) for t, _ in en.links)
    fr_counts = Counter(key(t) for t, _ in fr.links)
    en_first: dict[str, int] = {}
    for target, line in en.links:
        en_first.setdefault(key(target), line)
    fr_first: dict[str, int] = {}
    for target, line in fr.links:
        fr_first.setdefault(key(target), line)

    problems: list[Problem] = []
    for target in sorted(set(en_counts) | set(fr_counts)):
        left, right = en_counts[target], fr_counts[target]
        if left == right:
            continue
        where = (
            f"first at :{en_first[target]}"
            if target in en_first
            else f"first at :{fr_first[target]}"
        )
        problems.append(
            Problem(
                "links",
                f"{target!r} appears {left}x in {en.path.name} ({where}) "
                f"and {right}x in {fr.path.name}",
            )
        )
    return problems


def check_tables(en: Doc, fr: Doc) -> list[Problem]:
    """Compare the number of tables under each section.

    Parameters
    ----------
    en, fr : Doc
        The English and French halves of a pair.

    Returns
    -------
    list[Problem]
        One entry per section whose table counts differ.

    Examples
    --------
    >>> a = Doc(Path("a.md"), headings=[(2, "Costs", 7)], tables=[0])
    >>> b = Doc(Path("b.md"), headings=[(2, "Coûts", 7)], tables=[])
    >>> print(check_tables(a, b)[0])
    tables: section 'Costs' (a.md:7) has 1 table(s), its French twin has 0
    """
    if len(en.headings) != len(fr.headings):
        return []
    from collections import Counter

    en_counts, fr_counts = Counter(en.tables), Counter(fr.tables)
    problems: list[Problem] = []
    for section in sorted(set(en_counts) | set(fr_counts)):
        if en_counts[section] == fr_counts[section]:
            continue
        problems.append(
            Problem(
                "tables",
                f"section {en.heading_text(section)!r} "
                f"({en.path.name}:{en.heading_line(section)}) has "
                f"{en_counts[section]} table(s), its French twin has {fr_counts[section]}",
            )
        )
    return problems


CHECKS = (
    check_headings,
    check_fences,
    check_fence_sizes,
    check_commands,
    check_links,
    check_tables,
)


def check_pair(english: Path, french: Path) -> list[Problem]:
    """Run every invariant over one pair.

    Parameters
    ----------
    english, french : Path
        The two files.

    Returns
    -------
    list[Problem]
        Every breach found, in check order.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d:
    ...     a = pathlib.Path(d) / "a.md"; b = pathlib.Path(d) / "b.md"
    ...     _ = a.write_text("# T\\n\\n## S\\n"); _ = b.write_text("# T\\n")
    ...     found = check_pair(a, b)
    >>> print(found[0])
    headings: b.md is missing 'h2 T > S' (a.md:3)
    """
    en, fr = parse(english), parse(french)
    return [problem for check in CHECKS for problem in check(en, fr)]


def main(argv: list[str] | None = None) -> int:
    """Check every pair in :data:`PAIRS` and report.

    Parameters
    ----------
    argv : list[str] or None
        Command-line arguments; ``None`` reads :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` when every pair agrees (always, under ``--list``), ``1``
        otherwise.

    Examples
    --------
    ``--list`` describes the pairs and never judges them, so it is the one
    entry point a doctest can call without the repository's current state
    deciding whether the test passes:

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
        help="print what each pair contains and exit 0, without judging it",
    )
    args = parser.parse_args(argv)

    total = 0
    for english_name, french_name in PAIRS:
        english, french = _REPO / english_name, _REPO / french_name
        if not english.exists() or not french.exists():
            print(f"missing pair: {english_name} / {french_name}")
            total += 1
            continue
        if args.list:
            en, fr = parse(english), parse(french)
            print(
                f"{english_name:<14} {len(en.headings):>3} headings "
                f"{len(en.blocks):>3} fences {len(en.links):>3} links "
                f"{len(en.tables):>2} tables"
            )
            print(
                f"{french_name:<14} {len(fr.headings):>3} headings "
                f"{len(fr.blocks):>3} fences {len(fr.links):>3} links "
                f"{len(fr.tables):>2} tables"
            )
            continue
        problems = check_pair(english, french)
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{english_name} <-> {french_name}: {status}")
        for problem in problems:
            print(f"  {problem}")
        total += len(problems)

    if args.list:
        return 0
    if total:
        print(f"\n{total} parity problem(s) across {len(PAIRS)} pair(s)")
        return 1
    print(f"\nevery pair agrees ({len(PAIRS)} pairs)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
