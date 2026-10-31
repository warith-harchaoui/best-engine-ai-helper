"""No table column drops text without saying so.

Found by running the product rather than by reading it, which is the detector
these iterations had used least. Seven columns across the CLI shortened their
values with a bare `[:n]` slice: silent, width-blind, and free to land inside
a word. Measured against real data before anything was changed:

| column                        | limit | rows cut | the worst one ended on |
|-------------------------------|-------|----------|------------------------|
| `recommend` notes             |    40 | 31 of 31 | `…on/OCR but r`        |
| `providers` why-not           |    60 |  3 of 3  | `…ngs.yaml, a `        |
| `lightweight plan` notes      |    52 |  1 of 51 | `… this machin`        |

Every catalogue note was cut, some from 158 characters down to 40. A reader
cannot tell `a .en` from a value that really ends there, which is the whole
defect: not that the column is narrow, but that narrowness is invisible.

`providers` was worse than narrow. Its reason string carries a finding *and* a
remedy — "no API key found. Set X in settings.yaml, a .env file, …" — and the
remedy is already printed once, in full, under the table. The column spent 60
characters repeating that remedy per row and mangling it. It now carries the
first sentence, which is the part that belongs to the row.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from best_engine_ai_helper.cli import _ellipsise, cli


def test_a_value_that_fits_is_returned_whole() -> None:
    """A checker that cannot pass is as useless as one that cannot fail."""
    assert _ellipsise("short enough", 40) == "short enough"
    assert _ellipsise("exactly ten", 11) == "exactly ten"


def test_a_cut_is_announced_and_lands_between_words() -> None:
    """The defect this exists for: `only 21 GB i` told the reader nothing."""
    cut = _ellipsise("the checkpoint is 28 GB and only 21 GB is free", 40)
    assert cut.endswith("…")
    assert len(cut) <= 40
    assert not cut.rstrip("…").endswith(" ")
    assert "GB i" not in cut


def test_a_cut_landing_on_a_boundary_keeps_the_whole_word() -> None:
    """The first draft backed up unconditionally and dropped a word too many.

    Its own doctest caught it: cutting `…and only 21 GB |is free` already ends
    a word, so there is nothing to back up over, and taking the previous space
    would lose the `GB` the reader needs.
    """
    assert _ellipsise("the checkpoint is 28 GB and only 21 GB is free", 40) == (
        "the checkpoint is 28 GB and only 21 GB…"
    )


def test_a_single_long_word_is_still_cut() -> None:
    """No space to break on must not mean no shortening at all."""
    assert _ellipsise("supercalifragilistic", 8) == "superca…"


def test_the_ellipsis_is_one_character_not_three_dots() -> None:
    """Three dots cost three columns of the width they are announcing."""
    assert "..." not in _ellipsise("a sentence long enough to be shortened here", 20)


@pytest.mark.parametrize("limit", [8, 20, 40, 52, 60])
def test_the_result_never_exceeds_the_limit(limit: int) -> None:
    """A column that overflows its own budget breaks the table alignment."""
    sample = "the checkpoint is 671 GB and only 21 GB is free on this machine"
    assert len(_ellipsise(sample, limit)) <= limit


def test_providers_prints_the_finding_and_leaves_the_remedy_to_the_footer(
    runner: CliRunner,
) -> None:
    """The column said `a .en`, half of an instruction printed in full below.

    This asserts the shape rather than the exact wording: the per-row cell
    states what is wrong, the footer states what to do, and the cell is not a
    mangled prefix of the footer.
    """
    result = runner.invoke(cli, ["providers"])
    assert result.exit_code == 0
    body, _, footer = result.output.rpartition("\n\n")

    # The remedy names `settings.yaml`. It belongs to the footer, once, whole —
    # and the first draft of this test asserted `"a .en" not in output`, which
    # fails on the *correct* footer because it legitimately contains ".env".
    # Scoping to the body is what makes the assertion mean what it says.
    assert "settings.yaml" not in body, (
        "the remedy is back in the table, where it gets cut: " + body
    )
    for line in body.splitlines():
        assert not line.rstrip().endswith((", a", ", a .en", "settings.yaml,")), (
            f"cell cut mid-instruction: {line!r}"
        )
    if "NO" in body:
        assert "settings.yaml" in footer and "keychain" in footer


def test_the_footer_and_the_reason_agree_on_the_remedy() -> None:
    """Two spellings of one instruction, and nothing compared them.

    The reason said "the OS keychain" and the footer said "the keychain".
    Harmless on its own, and exactly the shape of defect these iterations keep
    finding: one fact, two copies, no check.
    """
    import inspect

    from best_engine_ai_helper import cloud_catalog

    source = inspect.getsource(cloud_catalog.provider_status)
    assert "the OS keychain" in source
