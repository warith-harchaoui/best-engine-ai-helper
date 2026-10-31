"""No rendered video is tracked, and the film says why.

`assets/film/film.yaml` is a ledger of what the launch film renders *from*,
and its own comment states the principle: *"Nothing licensed, nothing that
exists on one disk only: this film can be rebuilt from a clone, which is the
whole point of the ledger."* The repository then shipped the render as well —
1.6 MB of derived bytes in every clone, forever, for a file no test opens and
no CI step reads.

The ledger lists inputs: the composition, the logo, two derived figures with
the command that makes them. The MP4 was never in it, because it is the
output. Untracking it is the ledger's own rule applied to the one file that
was exempt from it.

Why a test and not just a `.gitignore` rule: an ignore pattern is advice, and
`git add -f` overrides it without comment. This is the part that notices.

It checks the index rather than the disk. The render is expected to exist
locally — it is how anyone looks at the film — so a check on the filesystem
would fail for the author and pass in CI, which is the exact shape of failure
these iterations spent their time removing.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

#: Extensions that are a *render*, never a source. Captions (`.vtt`), the
#: poster (`.jpg`) and the composition (`.html`) stay tracked: they are what
#: the film is rebuilt from, not what rebuilding produces.
RENDERED = (".mp4", ".mov", ".webm", ".m4v", ".mkv", ".avi")


def tracked_files() -> list[str]:
    """Every path in the index, from git itself rather than from a glob."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [name for name in out.stdout.split("\0") if name]


def test_no_rendered_video_is_in_the_index() -> None:
    """The gate: a render that reaches the index reaches every clone."""
    offenders = sorted(f for f in tracked_files() if f.lower().endswith(RENDERED))
    assert not offenders, (
        "rendered video in the index: "
        + ", ".join(offenders)
        + ". The film is rebuilt from `assets/film/film.yaml`, which is the whole "
        "point of the ledger. Untrack it with `git rm --cached <path>`."
    )


def test_what_the_film_is_rebuilt_from_is_still_tracked() -> None:
    """Removing the render must not quietly remove the means to remake it.

    A rule that only forbids is half a rule. If the composition, the ledger,
    the poster or the captions ever left the index, the film would stop being
    rebuildable from a clone and this file would still be green.
    """
    tracked = set(tracked_files())
    required = {
        "assets/film/film.yaml",
        "assets/film/composition/index.html",
        "assets/film/poster.jpg",
        "assets/film/best-engine-ai-helper.en.vtt",
        "assets/film/best-engine-ai-helper.fr.vtt",
    }
    missing = sorted(required - tracked)
    assert not missing, (
        "the film is no longer rebuildable from a clone; these left the index: "
        + ", ".join(missing)
    )


@pytest.mark.parametrize("pattern", ["*.mp4", "*.mov", "*.webm", "*.m4v"])
def test_the_ignore_rule_names_the_renders(pattern: str) -> None:
    """`.gitignore` is the advice; the test above is the enforcement.

    Both are wanted: without the pattern, a render reappears in `git status`
    on every author's machine and eventually gets added by someone staging
    broadly.
    """
    ignored = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert pattern in ignored, f"{pattern} is not ignored, so a render will offer itself again"
