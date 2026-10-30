"""Tests for ``scripts/check_doc_links.py``, the link gate.

A link is a claim that something is *there*. Nothing re-read those claims
after the things moved, and two were wrong: `CONTRIBUTING.md` and `GUI.md`
both linked ``locales/i18n.yaml``, which has no existence at the repository
root. The catalogue lives inside the package, and `CHANGELOG.md` records the
move that put it there. Both links had returned a 404 on GitHub ever since, in
the two documents whose subject is where that file is.

The sharpest detail is that this repository already *knew*:
`tests/test_gui_i18n.py::test_the_catalogue_sits_inside_the_package` asserts
the file is in the package while two documents pointed outside it. A test and a
document disagreed about one path, and nothing compared them. That is the same
shape as every finding of the last four iterations, and the reason the fix is a
checker rather than two edits.

Two kinds of test here, as with the other document gates: unit tests that build
a tiny document each and assert the rule fires on the breach it was written for
(including the three conventions an earlier draft mistook for breaches), and a
repository test that runs the real thing over the real files.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import doctest
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "check_doc_links.py"


def _load() -> ModuleType:
    """Import the checker by path; it is a dev tool and not part of the wheel."""
    spec = importlib.util.spec_from_file_location("check_doc_links", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


linker = _load()


def _doc(tmp_path: Path, body: str, name: str = "DOC.md") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_a_link_to_a_file_that_does_not_exist_is_caught(tmp_path: Path) -> None:
    """The defect this was written for, in the spelling both documents used."""
    doc = _doc(tmp_path, "# T\n\nSee [`locales/i18n.yaml`](locales/i18n.yaml).\n")
    problems = linker.check(doc)
    assert len(problems) == 1
    assert "locales/i18n.yaml, which does not exist" in problems[0]


def test_a_link_to_a_file_that_exists_is_silent(tmp_path: Path) -> None:
    """A checker that cannot pass is as useless as one that cannot fail."""
    doc = _doc(tmp_path, "# T\n\nSee [the catalogue](best_engine_ai_helper/locales/i18n.yaml).\n")
    assert linker.check(doc) == []


def test_an_anchor_with_no_heading_behind_it_is_caught(tmp_path: Path) -> None:
    """A renamed section leaves every link to it pointing at nothing."""
    doc = _doc(tmp_path, "# Title\n\n## Setup\n\nJump to [install](#installation).\n")
    assert any("#installation" in problem for problem in linker.check(doc))


def test_an_accented_anchor_is_not_a_breach(tmp_path: Path) -> None:
    """GitHub keeps accented letters, and stripping them condemns every French link.

    An earlier draft normalised through NFKD and dropped combining marks,
    which reported nineteen anchors in the French documents as broken. All
    nineteen were correct.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n## Ce que la machine peut exécuter\n\n[go](#ce-que-la-machine-peut-exécuter)\n",
    )
    assert linker.check(doc) == []


def test_french_spacing_before_a_colon_leaves_a_double_hyphen(tmp_path: Path) -> None:
    """French puts a space before `:`, so dropping it leaves two spaces.

    `LISEZMOI.md` has exactly one such heading and two links to it, and
    collapsing whitespace with `\\s+` reports both as broken. A comma carries
    no space before it and leaves a single hyphen, which is why the rule has to
    be per-space rather than per-run: the two cases must not agree.
    """
    assert linker.anchor_of("Trop gros : exécutable") == "trop-gros--exécutable"
    assert linker.anchor_of("Trop gros, exécutable") == "trop-gros-exécutable"
    doc = _doc(tmp_path, "# T\n\n## Trop gros : exécutable\n\n[v](#trop-gros--exécutable)\n")
    assert linker.check(doc) == []


def test_a_badge_that_is_deliberately_not_a_link_is_not_a_breach(tmp_path: Path) -> None:
    """The shields row in both READMEs writes `](#)` for a decorative badge."""
    doc = _doc(
        tmp_path, "# T\n\n[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](#)\n"
    )
    assert linker.check(doc) == []


def test_an_external_url_is_left_alone(tmp_path: Path) -> None:
    """Reaching the network would make this verdict depend on somebody's uptime.

    A gate that goes red because a third party is down is a gate people learn
    to skip, and skipping this one skips the lint and the tests with it.
    """
    doc = _doc(tmp_path, "# T\n\n[gone](https://example.invalid/nothing) [mail](mailto:a@b.test)\n")
    assert linker.check(doc) == []


def test_a_url_inside_a_fence_is_not_a_link(tmp_path: Path) -> None:
    """Example output full of paths must not be read as navigation."""
    doc = _doc(tmp_path, "# T\n\n```\nWrote [out](nowhere/at/all.yaml)\n```\n")
    assert linker.check(doc) == []


def test_a_cross_document_anchor_is_checked_against_the_target(tmp_path: Path) -> None:
    """`OTHER.md#section` has to exist *in OTHER.md*, not in the file linking it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "OTHER.md").write_text("# Other\n\n## Real Section\n", encoding="utf-8")
    good = tmp_path / "A.md"
    good.write_text("# A\n\n[x](OTHER.md#real-section)\n", encoding="utf-8")
    bad = tmp_path / "B.md"
    bad.write_text("# B\n\n[x](OTHER.md#imaginary)\n", encoding="utf-8")
    # The checker resolves paths against the repository root, so point it here.
    original = linker._REPO
    linker._REPO = tmp_path
    try:
        assert linker.check(good) == []
        assert any("has no such heading" in problem for problem in linker.check(bad))
    finally:
        linker._REPO = original


def test_the_changelog_is_deliberately_out_of_scope() -> None:
    """It names paths as they were per release; a since-moved file is history."""
    assert "CHANGELOG.md" in linker.EXCLUDED
    assert all(path.name != "CHANGELOG.md" for path in linker.documents())


@pytest.mark.parametrize("doc", linker.documents(), ids=lambda p: p.name)
def test_every_documented_link_resolves(doc: Path) -> None:
    """The gate itself: a reader clicking anything in these files lands somewhere."""
    problems = linker.check(doc)
    assert not problems, "broken link(s):\n" + "\n".join(problems)


def test_the_gate_actually_reaches_the_links() -> None:
    """A gate that silently matched nothing would pass forever.

    These documents are dense with links, so a parser that stopped seeing them
    would turn green and stay green. Counting both the links found and the
    local ones among them catches the two ways that can happen.
    """
    everything = [target for doc in linker.documents() for _, target in linker.links(doc)]
    local = [t for t in everything if not t.startswith(("http", "mailto:")) and t != "#"]
    assert len(everything) > 100, f"only {len(everything)} links found"
    assert len(local) > 20, f"only {len(local)} local targets found"


def test_the_i18n_catalogue_is_where_the_documents_now_say_it_is() -> None:
    """The specific claim the two broken links got wrong, pinned.

    `tests/test_gui_i18n.py` already asserts the catalogue sits inside the
    package. This asserts the path the documents now use is that same place,
    so the two cannot drift apart again without one of them going red.
    """
    assert (_REPO / "best_engine_ai_helper" / "locales" / "i18n.yaml").is_file()
    assert not (_REPO / "locales").exists()


def test_the_checkers_own_examples_run() -> None:
    """The script is not collected by ``--doctest-modules``; run its Examples here."""
    results = doctest.testmod(linker, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest failure(s) in {_SCRIPT.name}"
