"""Every `best-engine-ai-helper …` line in the docs resolves against the real CLI.

Three gates now judge the documents, and each sees something the others cannot.
`check_doc_parity.py` compares the two languages; `check_doc_examples.py`
compares the numbers inside one block against each other. Neither can compare a
documented *command* against the program it invokes, and that is where the
sharpest kind of documentation defect lives: not a number that is wrong, but a
line that does not run.

It was there. Both `README.md` and `LISEZMOI.md` printed::

    best-engine-ai-helper lightweight plan --kind llm --compression 4bit --batch 8

and `lightweight plan` has no `--compression`. Click answers "No such option"
and does nothing else, so a reader copying the line gets a usage error rather
than a plan. Forty-four lines further down, the same README explains at length
that the flag does not exist: "There is no `--compression` knob, because there
is nothing here that could honour one. (An earlier version accepted such a flag
and quoted a 3x speed-up the runtime never delivered.)" The document states the
removal and demonstrates the fossil, in both languages identically -- so the
parity gate, which does compare shell flags, called the two blocks equal and
was right to.

The same removed capability left the other fossil this repository fixed the
day before: a `disk_peak_gb` twice the checkpoint, from the runtime that
copied shards to scratch. One vanished feature, two surfaces, two prints.

A second promise lives one line below in `CODING.md`: "`EXAMPLES.md` with one
runnable recipe per public command, tested in CI". Nothing read `EXAMPLES.md`,
so the promise held by the goodwill of whoever last added a command. Two had
slipped: `catalog update`, documented only in a README table and a paragraph
of prose, and `hardware update`, which had no copy-pasteable invocation in any
root document at all. Both are checked here now, in both languages.

Why this is a test rather than a stdlib script like its two siblings: a check
of the command line has to import the command line. The dependency-free
constraint those scripts keep exists so the lightest CI lane can run them
without installing anything, and it cannot be met by a check whose whole
subject is the installed program.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import click
import pytest

from best_engine_ai_helper.cli import cli as ROOT

_REPO = Path(__file__).resolve().parent.parent

#: Documents whose command lines are resolved. `CHANGELOG.md` is excluded for
#: the same reason it is excluded from the example checker: it records what the
#: command line *was*, and a release note naming a since-removed flag is
#: history rather than a defect.
_EXCLUDED = {"CHANGELOG.md"}

#: The console script this checks. The other entry point in `pyproject.toml`,
#: `best-engine-ai-helper-mcp`, takes no subcommands and is left alone.
_PROGRAM = "best-engine-ai-helper"

# A shell pipeline or redirection ends the part that belongs to our program.
_TAIL = re.compile(r"\s[|>]\s|\s2>&1")


def _invocations(path: Path) -> list[tuple[int, list[str]]]:
    """
    Every `best-engine-ai-helper …` command in one document, as argument lists.

    Backslash continuations are joined, a leading shell prompt is dropped, and
    a trailing `#` comment is cut: all three appear in these documents and none
    is part of the command.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    list[tuple[int, list[str]]]
        Line number and the tokens after the program name.
    """
    joined: list[tuple[int, str]] = []
    pending, start = "", 0
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if line.startswith("$ "):
            line = line[2:].strip()
        if pending:
            line = f"{pending} {line}"
        else:
            start = number
        if line.endswith("\\"):
            pending = line[:-1].strip()
            continue
        pending = ""
        if line.startswith(f"{_PROGRAM} ") or line == _PROGRAM:
            joined.append((start, line))

    out: list[tuple[int, list[str]]] = []
    for number, line in joined:
        line = _TAIL.split(line)[0]
        # Only a comment that follows whitespace: a `#` glued to a token is
        # part of a URL fragment or a quoted string.
        line = re.split(r"\s+#", line)[0].strip()
        try:
            tokens = shlex.split(line)
        except ValueError:  # an unbalanced quote across a wrapped example
            continue
        out.append((number, tokens[1:]))
    return out


def _resolve(tokens: list[str]) -> tuple[click.Command, list[str], list[str]]:
    """
    Walk the subcommand chain and return the command, its path, and complaints.

    Parameters
    ----------
    tokens : list[str]
        Arguments after the program name.

    Returns
    -------
    tuple[click.Command, list[str], list[str]]
        The deepest command reached, the subcommand names consumed, and any
        complaints raised on the way.
    """
    command: click.Command = ROOT
    path: list[str] = []
    problems: list[str] = []
    rest = list(tokens)
    while rest and not rest[0].startswith("-"):
        if not isinstance(command, click.Group):
            break
        found = command.get_command(click.Context(command), rest[0])
        if found is None:
            problems.append(f"no subcommand {' '.join([*path, rest[0]])!r}")
            break
        path.append(rest.pop(0))
        command = found
    return command, path, problems


def _flag_problems(command: click.Command, path: list[str], tokens: list[str]) -> list[str]:
    """Every long option in ``tokens`` that ``command`` does not define."""
    known: set[str] = set()
    for parameter in command.params:
        known |= set(parameter.opts) | set(parameter.secondary_opts)
    known |= {"--help"}
    where = " ".join(path) or "(root)"
    return [
        f"`{where}` has no option {token.split('=')[0]}"
        for token in tokens
        if token.startswith("--") and token.split("=")[0] not in known
    ]


def check(path: Path) -> list[str]:
    """
    Every documented invocation in one file that the CLI would refuse.

    Parameters
    ----------
    path : Path
        A Markdown file.

    Returns
    -------
    list[str]
        Empty when every command line in the file resolves.
    """
    problems: list[str] = []
    for number, tokens in _invocations(path):
        command, subpath, failures = _resolve(tokens)
        problems += [f"{path.name}:{number} {failure}" for failure in failures]
        if failures:
            continue
        rest = tokens[len(subpath) :]
        problems += [
            f"{path.name}:{number} {failure}" for failure in _flag_problems(command, subpath, rest)
        ]
    return problems


def leaf_commands(command: click.Command = ROOT, path: tuple[str, ...] = ()) -> list[str]:
    """
    Every public command that actually runs something, as a subcommand chain.

    Groups are not included: `lightweight` on its own prints help, and a
    recipe for it would demonstrate nothing. Hidden commands are skipped
    because they are not part of the promise.

    Parameters
    ----------
    command : click.Command
        Where to start; the root group by default.
    path : tuple[str, ...]
        Subcommand names consumed so far, used by the recursion.

    Returns
    -------
    list[str]
        Space-joined chains such as ``"lightweight plan"``, sorted within
        each level.
    """
    if isinstance(command, click.Group):
        found: list[str] = []
        for name, sub in sorted(command.commands.items()):
            if not getattr(sub, "hidden", False):
                found += leaf_commands(sub, (*path, name))
        return found
    return [" ".join(path)]


def invoked_commands(path: Path) -> set[str]:
    """Every leaf command one document actually demonstrates."""
    found: set[str] = set()
    for _, tokens in _invocations(path):
        command, subpath, problems = _resolve(tokens)
        if subpath and not problems and not isinstance(command, click.Group):
            found.add(" ".join(subpath))
    return found


def documents() -> list[Path]:
    """Root Markdown files whose command lines are resolved, in a stable order."""
    return [path for path in sorted(_REPO.glob("*.md")) if path.name not in _EXCLUDED]


def _doc(tmp_path: Path, body: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "DOC.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_defect_this_was_written_for(tmp_path: Path) -> None:
    """The real line, verbatim: a flag the README itself says does not exist."""
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\nbest-engine-ai-helper lightweight plan --kind llm "
        "--compression 4bit --batch 8\n```\n",
    )
    problems = check(doc)
    assert len(problems) == 1
    assert "`lightweight plan` has no option --compression" in problems[0]


def test_a_command_that_resolves_is_silent(tmp_path: Path) -> None:
    """A checker that cannot pass is as useless as one that cannot fail."""
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\nbest-engine-ai-helper lightweight plan --kind llm --batch 8\n```\n",
    )
    assert check(doc) == []


def test_an_unknown_subcommand_is_caught(tmp_path: Path) -> None:
    """A renamed command is the other half of the same failure."""
    doc = _doc(tmp_path, "# T\n\n```sh\nbest-engine-ai-helper recomend --kind llm\n```\n")
    assert any("no subcommand 'recomend'" in problem for problem in check(doc))


def test_a_nested_group_resolves_to_its_own_options(tmp_path: Path) -> None:
    """`lightweight status` and `lightweight plan` do not share an option set.

    Checking a flag against the group rather than the leaf would pass
    `--measure` everywhere and `--kind` nowhere, which is no check at all.
    """
    good = _doc(
        tmp_path / "a", "# T\n\n```sh\nbest-engine-ai-helper lightweight status --measure\n```\n"
    )
    bad = _doc(
        tmp_path / "b", "# T\n\n```sh\nbest-engine-ai-helper lightweight status --kind llm\n```\n"
    )
    assert check(good) == []
    assert any("has no option --kind" in problem for problem in check(bad))


def test_a_backslash_continuation_is_one_command(tmp_path: Path) -> None:
    """Two of these documents wrap a long invocation, and the tail carries flags.

    Read line by line, the continuation half starts with `--` and never looks
    like a command at all, so every flag past the wrap escapes the check.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\nbest-engine-ai-helper report \\\n  --kind llm --nonsense x\n```\n",
    )
    assert any("has no option --nonsense" in problem for problem in check(doc))


def test_a_shell_prompt_and_a_trailing_comment_are_not_arguments(tmp_path: Path) -> None:
    """Both idioms appear in these documents; neither is part of the command."""
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\n$ best-engine-ai-helper lightweight status --measure   "
        "# measure the disk\n```\n",
    )
    assert check(doc) == []


def test_a_pipeline_tail_belongs_to_another_program(tmp_path: Path) -> None:
    """`… --json | jq '.llm'` must not charge `jq`'s arguments to our CLI."""
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\nbest-engine-ai-helper lightweight plan --json | jq '.--fake'\n```\n",
    )
    assert check(doc) == []


@pytest.mark.parametrize("doc", documents(), ids=lambda p: p.name)
def test_every_documented_command_resolves(doc: Path) -> None:
    """The gate itself: a reader copying any line out of these files gets a run."""
    problems = check(doc)
    assert not problems, "command lines the CLI would refuse:\n" + "\n".join(problems)


@pytest.mark.parametrize("doc", ["EXAMPLES.md", "EXEMPLES.md"])
def test_every_public_command_has_a_runnable_recipe(doc: str) -> None:
    """`CODING.md` promises one per public command. Nothing was checking.

    Two had slipped, and the way they slipped is worth keeping: neither was
    undocumented. `catalog update` had a README table cell and a paragraph of
    prose describing all five of its flags; `hardware update` had a table cell.
    What neither had was a line a reader could copy, which is what "runnable
    recipe" means and what a table cell can never be.

    Both languages, because a recipe present in one and absent in the other is
    the drift the parity checker was built for -- and it would pass this one,
    since a missing block in a section that has no block is not a difference it
    can see without being told which blocks ought to exist.
    """
    missing = sorted(set(leaf_commands()) - invoked_commands(_REPO / doc))
    assert not missing, (
        f"{doc} has no runnable recipe for: {', '.join(missing)}. "
        "A backticked name in a table is documentation; a line a reader can "
        "copy is a recipe, and CODING.md promises the second."
    )


def test_the_gate_actually_reaches_the_command_lines() -> None:
    """A gate that silently matched nothing would pass forever.

    These documents are mostly command lines, so a parser that quietly stopped
    finding them would turn green and stay green.
    """
    total = sum(len(_invocations(doc)) for doc in documents())
    assert total > 60, f"only {total} invocations found; the parser has stopped seeing them"
    reached = {
        " ".join(_resolve(tokens)[1]) for doc in documents() for _, tokens in _invocations(doc)
    }
    assert len(reached) > 20, f"only {len(reached)} distinct commands reached"
