"""A claim about another repository, in the handover, must carry its check.

`.private/die.md` is the one document in this project with no gate. Parity,
worked examples, links, commands and Python recipes are each read by a script
in the suite; the handover is read by a human and believed. Highest trust,
zero verification — and that is exactly where the one false premise of
iterations 11 to 17 came from.

The sentence was *"`ai-bunker` reads this descriptor, so it wants a deliberate
moment."* It is false: that repository contains no occurrence of
`disk_peak_gb` or `disk_steady_gb`, and `llm.engine*.yaml` appears there only
in `.gitignore`. It was inherited, acted on, and written into a **published**
`CHANGELOG.md` before anyone opened the repository it describes.

So this is narrow on purpose. It does not check prose, or paths, or anything
about this repository. It fires on one shape: **a sentence saying what another
project does, with no command beside it that would settle the question.** A
concurrent session built the path-based half of this and reported that its own
barrier would not have caught the sentence above, because that sentence names
no file. This closes the half theirs cannot.

Why it is a test and not another gate script: there is nothing to run it on in
CI. `.private/` is gitignored, so a fresh clone has no handover and the
repository assertion skips — stated here rather than discovered later, because
a check that silently passes on nothing is the failure mode these iterations
spent their time on. The unit tests below carry the real coverage and run
everywhere.

This is the one check added after the loop was declared converged, and the
reason is in the asymmetry: the other probes of iterations 15 and 16 found
five of their own bugs for one real defect, while this one targets a defect
that demonstrably happened and reached a published file.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

#: The handover. Absent from any fresh clone, by design.
HANDOVER = _REPO / ".private" / "die.md"

#: Sibling projects on this machine that the handover may talk about. A name
#: here is a name whose behaviour cannot be checked from inside this
#: repository, which is the whole point.
_SIBLINGS = r"ai-bunker|ai-helpers|ai-dangers|sprezzature[\w-]*|saggio|deraison|notes-helper"

#: Verbs that turn a mention into an assertion about behaviour. "that project
#: being `ai-bunker`" is a cross-reference and stays silent; "`ai-bunker` reads
#: this descriptor" is a claim and does not.
_VERBS = r"reads?|writes?|uses?|consumes?|imports?|depends?|calls?|parses?|loads?|serves?|needs?"

_CLAIM = re.compile(rf"\b({_SIBLINGS})\b[^.\n]{{0,80}}?\b({_VERBS})\b", re.I)

#: What counts as carrying the check: an inline command in backticks, or a
#: fenced block. Deliberately generous -- the point is to make the author go
#: and look, not to police the spelling of the command they came back with.
_CHECK = re.compile(r"`[^`]*\b(grep|rg|ls|cat|sed|awk|git|python|find|gh)\b[^`]*`|```")

#: A paragraph that already marks a claim wrong is a record, not a claim.
#: Striking a sentence through and saying why is the correct repair -- deleting
#: it quietly is not -- so the corrected form must not keep firing, or the rule
#: pushes authors toward the silent deletion. Negations are here for the same
#: reason: "it does not" reports a claim rather than making one, and the
#: paragraph stating this very rule was the first thing the check fired on.
_RETRACTED = re.compile(
    r"~~|\bFALSE\b|\bno longer true\b|\bcorrected\b"
    r"|\bdoes not\b|\bdo not\b|\bis not\b|\bnever\b|\bno occurrence\b",
    re.I,
)


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Blank-line-separated blocks, with the 1-based line each one starts on."""
    blocks: list[tuple[int, str]] = []
    line = 1
    for block in text.split("\n\n"):
        if block.strip():
            blocks.append((line, block))
        line += block.count("\n") + 2
    return blocks


def check(text: str) -> list[str]:
    """
    Every unverified claim about another repository, as `line: sentence`.

    Parameters
    ----------
    text : str
        A handover document.

    Returns
    -------
    list[str]
        Empty when every such claim sits beside a command that settles it.
    """
    problems: list[str] = []
    blocks = paragraphs(text)
    for index, (line, block) in enumerate(blocks):
        claim = _CLAIM.search(block)
        if not claim or _RETRACTED.search(block):
            continue
        # The command usually follows the sentence it settles, in a fence of
        # its own, so the window is this paragraph and the next one.
        window = block + "\n" + (blocks[index + 1][1] if index + 1 < len(blocks) else "")
        if _CHECK.search(window):
            continue
        sentence = " ".join(block.split())
        problems.append(
            f"line {line}: says what `{claim.group(1)}` does, with nothing to check it "
            f"against — {sentence[:100]}…"
        )
    return problems


def test_the_defect_this_was_written_for() -> None:
    """The exact sentence, which cost an entry in a published changelog."""
    problems = check("`ai-bunker` reads this descriptor, so it wants a deliberate moment.")
    assert len(problems) == 1
    assert "ai-bunker" in problems[0]


def test_the_same_claim_with_its_check_is_silent() -> None:
    """A checker that cannot pass is as useless as one that cannot fail."""
    assert (
        check(
            "`ai-bunker` reads this descriptor "
            "(`grep -rn disk_peak_gb ~/ai-bunker` → 3 hits in engine.py)."
        )
        == []
    )


def test_a_fenced_command_counts_as_the_check() -> None:
    """Most verifications in this handover are fenced, not inline."""
    assert check("`ai-bunker` reads this descriptor.\n\n```sh\ngrep -rn x ~/ai-bunker\n```") == []


def test_a_paragraph_reporting_a_claim_as_false_is_not_making_one() -> None:
    """The rule's own statement was the first thing this fired on.

    A sentence that says another project *does not* do something is a finding,
    not an unverified assertion — and the paragraph describing this very rule
    had to quote the false claim in order to warn about it.
    """
    assert (
        check(
            "The previous version asserted that `ai-bunker` reads the engine "
            "descriptor; it does not, and that claim reached a published changelog."
        )
        == []
    )


def test_a_narrative_mention_is_not_a_claim() -> None:
    """ "That project being `ai-bunker`" asserts nothing about its behaviour.

    This is the line that sat eight lines above the false one and was *true*.
    A rule that fires on both teaches the author to ignore it.
    """
    assert (
        check(
            '…the founding incident of the project downstream." — that project\nbeing `ai-bunker`.'
        )
        == []
    )


def test_a_retracted_claim_stays_quiet() -> None:
    """Striking a sentence through and saying why is the correct repair.

    Deleting it quietly is not, so the corrected paragraph must not keep
    firing and push the author toward the silent deletion instead.
    """
    assert check("~~`ai-bunker` reads this descriptor.~~ **FALSE** — verified, zero hits.") == []


def test_a_claim_about_this_repository_is_out_of_scope() -> None:
    """Everything here is already read by a gate; only the outside is not."""
    assert check("`scripts/gate.sh` reads `pyproject.toml` for the version.") == []


def test_each_unverified_claim_is_reported_once_per_paragraph() -> None:
    """Two paragraphs, two reports; the line numbers have to be usable."""
    text = (
        "`ai-bunker` reads the descriptor.\n\n"
        "Some prose.\n\n"
        "`sprezzature-maps` imports the catalogue."
    )
    problems = check(text)
    assert len(problems) == 2
    assert problems[0].startswith("line 1:")
    assert problems[1].startswith("line 5:")


@pytest.mark.skipif(
    not HANDOVER.is_file(),
    reason=".private/ is gitignored, so a fresh clone and every CI run has no handover to read",
)
def test_the_handover_carries_its_own_checks() -> None:
    """The gate itself, on the real file, when there is one."""
    problems = check(HANDOVER.read_text(encoding="utf-8"))
    assert not problems, (
        "unverified claim(s) about another repository in .private/die.md:\n"
        + "\n".join(problems)
        + "\n\nOpen that repository and paste the command. One line each."
    )
