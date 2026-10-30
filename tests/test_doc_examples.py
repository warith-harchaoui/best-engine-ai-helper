"""Tests for ``scripts/check_doc_examples.py``, the worked-example gate.

The parity gate added in iteration 7 compares the two languages against each
other. It is structurally blind to the one thing both can be wrong about at
once: an example that was correct when it was pasted and has not been re-run
since. Parity saw ``disk_peak_gb: 16.8`` in ``EXAMPLES.md`` and
``disk_peak_gb: 16.8`` in ``EXEMPLES.md``, agreed they were identical, and was
right -- while nine lines of the same document narrated the removal of the
scratch copy that figure is made of.

Two kinds of test here, the same split the parity tests use:

* the **unit** tests build one tiny fenced block each and assert that the
  invariant fires on the incoherence it was written for -- and, for the pairs
  that are easy to over-fit, that it stays silent on the coherent version;
* the **repository** test runs the real checker over the real documents.

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
_SCRIPT = _REPO / "scripts" / "check_doc_examples.py"


def _load() -> ModuleType:
    """Import ``scripts/check_doc_examples.py`` by path, not as an installed module.

    It is a development tool and deliberately not part of the wheel.
    Registering it in ``sys.modules`` before execution is not optional:
    ``@dataclass`` resolves a class's own module through ``sys.modules`` to
    decide whether an annotation is ``KW_ONLY``.
    """
    spec = importlib.util.spec_from_file_location("check_doc_examples", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


examples = _load()


def _doc(tmp_path: Path, body: str, name: str = "DOC.md") -> Path:
    """Write one synthetic Markdown file holding ``body`` and return its path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _names(path: Path) -> list[str]:
    """The invariant names that fired on ``path``, in order."""
    return [problem.split("[", 1)[1].split("]", 1)[0] for problem in examples.check(path)]


def test_the_defect_this_was_written_for(tmp_path: Path) -> None:
    """The real block, verbatim: a 2.1x peak over a steady that is not the checkpoint.

    Both figures are fossils of the runtime that decomposed a checkpoint into
    per-layer shards beside the original. `streaming.py` stopped doing that and
    `disk_required_gb` returns the checkpoint for both keys, so the example had
    been promising a reader a transient their drive would never see.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nllm:\n  checkpoint_gb: 8.0\n"
        "  disk_peak_gb: 16.8\n  disk_steady_gb: 8.8\n```\n",
    )
    assert sorted(_names(doc)) == ["peak-is-steady", "steady-is-the-checkpoint"]


def test_the_corrected_block_is_silent(tmp_path: Path) -> None:
    """A checker that cannot pass is as useless as one that cannot fail."""
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nllm:\n  checkpoint_gb: 8.0\n"
        "  disk_peak_gb: 8.0\n  disk_steady_gb: 8.0\n```\n",
    )
    assert examples.check(doc) == []


def test_a_rate_updated_without_its_inverse_is_caught(tmp_path: Path) -> None:
    """``est_tokens_per_s`` and ``seconds_per_token`` are one measurement, twice.

    The drift this anticipates is the cheap one: a reading refreshed on faster
    hardware, with the line underneath left as it was.
    """
    stale = _doc(
        tmp_path / "a",
        "# T\n\n```yaml\nllm:\n  est_tokens_per_s: 0.8\n  seconds_per_token: 2.4\n```\n",
    )
    fresh = _doc(
        tmp_path / "b",
        "# T\n\n```yaml\nllm:\n  est_tokens_per_s: 0.425\n  seconds_per_token: 2.4\n```\n",
    )
    assert _names(stale) == ["rate-inverts"]
    assert examples.check(fresh) == []


def test_a_streaming_example_whose_resident_is_not_below_the_file_is_caught(
    tmp_path: Path,
) -> None:
    """Streaming's whole claim is that memory holds a layer rather than the file.

    This one is a rule about the *documentation* rather than a theorem about
    the code -- an enormous context could in principle push a small model's
    resident figure past its checkpoint -- so it only applies where the block
    itself says ``streaming: true``.
    """
    streamed = _doc(
        tmp_path / "a",
        "# T\n\n```yaml\nllm:\n  streaming: true\n  ram_gb: 9.0\n  checkpoint_gb: 8.0\n```\n",
    )
    resident = _doc(
        tmp_path / "b",
        "# T\n\n```yaml\nllm:\n  ram_gb: 9.0\n  checkpoint_gb: 8.0\n```\n",
    )
    assert _names(streamed) == ["resident-below-checkpoint"]
    assert examples.check(resident) == []


def test_a_lightweight_descriptor_that_publishes_a_port_is_caught(tmp_path: Path) -> None:
    """The backend is a library in the caller's process; a port points at nothing."""
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nbackend: lightweight\nbase_url: http://localhost:11434\n```\n",
    )
    assert _names(doc) == ["lightweight-has-no-port"]


def test_the_backend_condition_reaches_down_from_the_block(tmp_path: Path) -> None:
    """``backend`` sits at the top level and ``structured_output`` under ``llm``.

    A rule that only looked inside one mapping would never see the pair, which
    is exactly how the descriptor is written.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nbackend: lightweight\nllm:\n  structured_output: true\n```\n",
    )
    assert _names(doc) == ["lightweight-has-no-schema"]


def test_an_ollama_descriptor_keeps_its_port_and_its_schema(tmp_path: Path) -> None:
    """Both lightweight rules are conditioned on the backend, not on the key."""
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nbackend: ollama\nbase_url: http://localhost:11434\n"
        "llm:\n  structured_output: true\n```\n",
    )
    assert examples.check(doc) == []


def test_sibling_mappings_do_not_bleed_into_each_other(tmp_path: Path) -> None:
    """``llm`` and ``vlm`` each carry a ``checkpoint_gb``, and they differ.

    A flat key table would compare one kind's disk figure against the other
    kind's checkpoint and report a breach that is not there.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nllm:\n  checkpoint_gb: 8.0\n  disk_steady_gb: 8.0\n"
        "vlm:\n  checkpoint_gb: 24.0\n  disk_steady_gb: 24.0\n```\n",
    )
    assert examples.check(doc) == []


def test_a_fence_indented_inside_a_list_is_still_read(tmp_path: Path) -> None:
    """``README.md`` puts its engine descriptor inside a numbered list.

    The fence and every key under it carry the list's indentation, so a
    reader anchored at column zero sees no fence at all and the whole
    descriptor escapes the gate.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n1. Step\n\n   ```yaml\n   llm:\n     checkpoint_gb: 8.0\n"
        "     disk_steady_gb: 8.8\n   ```\n",
    )
    assert _names(doc) == ["steady-is-the-checkpoint"]


def test_a_one_line_flow_mapping_is_read_like_the_expanded_form(tmp_path: Path) -> None:
    """``llm: {model: gemma3:12b, ...}`` is how the README compresses a descriptor.

    Splitting each comma-item at its *first* colon is what keeps the model tag
    whole; splitting at the last would make the key ``model: gemma3``.
    """
    doc = _doc(
        tmp_path,
        "# T\n\n```yaml\nllm: {model: gemma3:12b, checkpoint_gb: 8.0, disk_steady_gb: 8.8}\n```\n",
    )
    assert _names(doc) == ["steady-is-the-checkpoint"]
    scope = [s for s in examples.scopes(doc) if s.name == "llm"][0]
    assert scope.values["model"] == "gemma3:12b"


def test_a_url_fragment_survives_comment_stripping(tmp_path: Path) -> None:
    """``#section`` is part of an address; `` # note`` is not."""
    assert examples.strip_comment("url: https://x.test/p#frag") == "url: https://x.test/p#frag"
    assert examples.strip_comment("base_url: ''   # a library") == "base_url: ''"


def test_a_shell_fence_is_not_read_as_data(tmp_path: Path) -> None:
    """``--flag: value`` in a command is not a mapping, and neither is prose output."""
    doc = _doc(
        tmp_path,
        "# T\n\n```sh\ntool run --out llm.engine.yaml\n```\n\n"
        "```\ncheckpoint_gb: 8.0\ndisk_steady_gb: 8.8\n```\n",
    )
    assert examples.scopes(doc) == []


def test_a_partial_example_is_not_penalised_for_being_partial(tmp_path: Path) -> None:
    """Most blocks show a few keys. A rule applies only where its keys are present."""
    doc = _doc(tmp_path, "# T\n\n```yaml\nllm:\n  disk_steady_gb: 8.8\n```\n")
    assert examples.check(doc) == []


def test_the_documents_are_discovered_rather_than_listed() -> None:
    """A new root document is in scope the moment it lands.

    The subject of this whole checker is a figure nobody remembered to re-read,
    so a hand-written list of files to read would have been the same mistake in
    a different place. The three mirrored pairs and the two standalone guides
    have to be among what discovery returns.
    """
    found = {path.name for path in examples.documents()}
    assert {
        "README.md",
        "LISEZMOI.md",
        "EXAMPLES.md",
        "EXEMPLES.md",
        "LANDSCAPE.md",
        "PAYSAGE.md",
        "GUI.md",
        "CONTRIBUTING.md",
    } <= found


def test_the_changelog_is_deliberately_out_of_scope() -> None:
    """It records what the numbers *were*; correcting history there is the error."""
    assert "CHANGELOG.md" in examples.EXCLUDED
    assert all(path.name != "CHANGELOG.md" for path in examples.documents())


def test_the_shipped_examples_are_coherent() -> None:
    """The gate itself: every fenced example in this repository obeys the invariants."""
    problems = [problem for path in examples.documents() for problem in examples.check(path)]
    assert not problems, "incoherent documented example(s):\n" + "\n".join(problems)


def test_the_gate_actually_reaches_the_descriptor_it_was_built_for() -> None:
    """A gate that silently matched nothing would pass forever.

    The worked lightweight descriptor is the block this checker exists for, so
    at least one real document has to supply both disk keys and the checkpoint
    beside them.
    """
    reached = [
        scope
        for path in examples.documents()
        for scope in examples.scopes(path)
        if {"disk_peak_gb", "disk_steady_gb", "checkpoint_gb"} <= set(scope.values)
    ]
    assert reached, "no shipped document carries a full disk descriptor any more"
    for scope in reached:
        assert scope.values["disk_peak_gb"] == scope.values["disk_steady_gb"]


def test_the_checkers_own_examples_run() -> None:
    """The script is not collected by ``--doctest-modules``; run its Examples here."""
    results = doctest.testmod(examples, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest failure(s) in {_SCRIPT.name}"
