"""Tests for ``scripts/check_doc_parity.py``, the EN/FR documentation gate.

Three root documents ship in two languages, roughly 7,000 lines of prose kept
in six files. Nothing checked that the two halves still had the same shape, and
twice they did not. These tests put that check in the pre-push gate and in CI,
which is the only place a structural drift can be caught: each file reads
perfectly well on its own, so no human rereading one of them notices.

Two kinds of test here, and the split is deliberate:

* the **unit** tests build small synthetic documents and assert that each
  invariant fires on the drift it was written for -- a checker that cannot
  fail is not a check;
* the **repository** test runs the real thing over the real files.

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

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "check_doc_parity.py"


def _load() -> ModuleType:
    """Import ``scripts/check_doc_parity.py`` by path, not as an installed module.

    It is a development tool, so it is deliberately not part of the wheel.
    Registering it in ``sys.modules`` before executing it is not optional:
    ``@dataclass`` resolves a class's own module through ``sys.modules`` to
    decide whether an annotation is ``KW_ONLY``, and raises ``AttributeError:
    'NoneType' object has no attribute '__dict__'`` when it is absent.
    """
    spec = importlib.util.spec_from_file_location("check_doc_parity", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parity = _load()


def _write(tmp_path: Path, english: str, french: str) -> tuple[Path, Path]:
    """Write a synthetic pair and return the two paths."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    en, fr = tmp_path / "EN.md", tmp_path / "FR.md"
    en.write_text(english, encoding="utf-8")
    fr.write_text(french, encoding="utf-8")
    return en, fr


def test_identical_structure_passes(tmp_path: Path) -> None:
    """Different words, same skeleton: no complaint."""
    en, fr = _write(
        tmp_path,
        "# Title\n\n## Install\n\n```sh\ntool run --fast\n```\n\nSee [docs](https://x.test/d).\n",
        "# Titre\n\n## Installer\n\n```sh\ntool run --fast\n```\n\nVoir [docs](https://x.test/d).\n",
    )
    assert parity.check_pair(en, fr) == []


def test_a_heading_only_one_language_has_is_caught(tmp_path: Path) -> None:
    """The breach found in LISEZMOI.md: a section with no English counterpart."""
    en, fr = _write(tmp_path, "# T\n\n## A\n", "# T\n\n## A\n\n### Extra\n")
    problems = parity.check_pair(en, fr)
    assert any(p.check == "headings" and "EN.md is missing" in p.message for p in problems)


def test_a_promoted_heading_is_caught(tmp_path: Path) -> None:
    """The other README breach: the same section at two different levels."""
    en, fr = _write(tmp_path, "# T\n\n## A\n\n### B\n", "# T\n\n## A\n\n#### B\n")
    problems = parity.check_pair(en, fr)
    assert any(p.check == "headings" and "h3" in p.message and "h4" in p.message for p in problems)


def test_a_dropped_output_line_is_caught(tmp_path: Path) -> None:
    """The EXEMPLES.md breach: a terminal panel quietly one line shorter.

    Neither the heading outline nor the block count moves, so this is the only
    invariant that can see it.
    """
    en, fr = _write(
        tmp_path,
        "# T\n\n```\nstatus: ok\nRepair: pip install -U thing\n```\n",
        "# T\n\n```\nstatus: ok\n```\n",
    )
    problems = parity.check_pair(en, fr)
    assert any(p.check == "sizes" for p in problems)


def test_a_renamed_flag_is_caught_but_a_translated_argument_is_not(tmp_path: Path) -> None:
    """Flags are an invariant; the prose inside the quotes is not."""
    translated = _write(
        tmp_path / "a",
        '# T\n\n```sh\ntool run --task "invoice lines"\n```\n',
        '# T\n\n```sh\ntool run --task "lignes de facture"\n```\n',
    )
    renamed = _write(
        tmp_path / "b",
        '# T\n\n```sh\ntool run --task "x"\n```\n',
        '# T\n\n```sh\ntool run --job "x"\n```\n',
    )
    assert parity.check_pair(*translated) == []
    assert any(p.check == "commands" for p in parity.check_pair(*renamed))


def test_a_mirrored_asset_name_is_not_a_breach(tmp_path: Path) -> None:
    """``landscape.png`` and ``paysage.png`` are the same picture, by declaration."""
    en, fr = _write(
        tmp_path,
        "# T\n\n![map](assets/landscape.png)\n",
        "# T\n\n![carte](assets/paysage.png)\n",
    )
    assert parity.check_pair(en, fr) == []


def test_an_undeclared_asset_difference_is_a_breach(tmp_path: Path) -> None:
    """An asset that gained a twin has to be declared in MIRROR, not discovered."""
    en, fr = _write(
        tmp_path,
        "# T\n\n![map](assets/sunrise.png)\n",
        "# T\n\n![carte](assets/lever-de-soleil.png)\n",
    )
    assert any(p.check == "links" for p in parity.check_pair(en, fr))


def test_the_badge_idiom_yields_both_of_its_targets(tmp_path: Path) -> None:
    """``[![alt](shield)](target)`` is two links, and both have to be compared.

    Spelled with a character class that cannot nest, the parser returns the
    shield and loses the target; spelled with one that nests, it returns the
    target and loses the shield. Either way a real difference hides inside the
    idiom the README's own header uses.
    """
    doc = parity.parse(
        _write(tmp_path, "# T\n\n[![lic](https://img.test/s.svg)](https://x.test/LICENSE)\n", "")[0]
    )
    assert [target for target, _ in doc.links] == [
        "https://img.test/s.svg",
        "https://x.test/LICENSE",
    ]


def test_a_shell_comment_is_not_a_heading(tmp_path: Path) -> None:
    """``# Run this`` inside a fence is a comment, whatever it looks like."""
    doc = parity.parse(_write(tmp_path, "# Real\n\n```sh\n# Not a heading\nls\n```\n", "")[0])
    assert [text for _, text, _ in doc.headings] == ["Real"]


def test_a_url_inside_a_fence_is_not_a_link(tmp_path: Path) -> None:
    """Example output full of URLs must not inflate the link multiset."""
    doc = parity.parse(_write(tmp_path, "# T\n\n```\nGET https://x.test/api\n```\n", "")[0])
    assert doc.links == []


def test_every_declared_pair_exists() -> None:
    """A pair named in PAIRS but absent from the repo is a configuration bug."""
    for english, french in parity.PAIRS:
        assert (_REPO / english).is_file(), english
        assert (_REPO / french).is_file(), french


def test_the_shipped_documents_agree() -> None:
    """The gate itself: every mirrored pair in this repository has one shape."""
    problems = [
        f"{english} <-> {french}: {problem}"
        for english, french in parity.PAIRS
        for problem in parity.check_pair(_REPO / english, _REPO / french)
    ]
    assert not problems, "EN/FR documentation drift:\n" + "\n".join(problems)


def test_the_checkers_own_examples_run() -> None:
    """The script is not collected by ``--doctest-modules``; run its Examples here."""
    results = doctest.testmod(parity, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest failure(s) in {_SCRIPT.name}"
