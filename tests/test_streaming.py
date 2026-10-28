"""
Tests for best_engine_ai_helper.streaming — this project's own layer streaming.

The interesting ones build a **real** transformers model, tiny enough to be
free (two layers, hidden size 32), save it to a temp directory and stream it
back. Nothing is downloaded and nothing is mocked on the path that matters,
which is deliberate: the bugs this module actually had were all of the shape
"it runs and produces confident nonsense", and the only thing that catches
those is comparing a streamed generation against an ordinary one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from best_engine_ai_helper import streaming

torch = pytest.importorskip("torch", reason="the streaming runtime needs torch")
transformers = pytest.importorskip("transformers", reason="the streaming runtime needs it")


# ---------------------------------------------------------------------------
# A tiny real checkpoint, built once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def tiny_llama(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A two-layer Llama saved as safetensors. Small enough to be free."""
    from transformers import LlamaConfig, LlamaForCausalLM

    torch.manual_seed(0)
    config = LlamaConfig(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=4,
        # Untied, so there is a real `lm_head` tensor to place -- the tied case
        # has its own test below, because it is where airllm fell over.
        tie_word_embeddings=False,
    )
    model = LlamaForCausalLM(config).eval()
    path = tmp_path_factory.mktemp("tiny-llama")
    model.save_pretrained(path, safe_serialization=True)
    return path


def _ids() -> Any:
    return torch.tensor([[1, 2, 3, 4]])


# ---------------------------------------------------------------------------
# The claim: same answer, a fraction of the memory
# ---------------------------------------------------------------------------


def test_a_streamed_forward_equals_an_ordinary_one(tiny_llama: Path) -> None:
    """Bit for bit, which is the only assertion that catches the real bugs.

    Every defect this module had produced fluent, plausible, WRONG output and
    never an exception: a rotary table left on the CPU while the rest ran on
    the accelerator, a generation config that was never read, a post-hook that
    evicted computed buffers, an output head whose checkpoint name had changed
    so it was silently skipped. A smoke test passes through all four.
    """
    from transformers import AutoModelForCausalLM

    reference = AutoModelForCausalLM.from_pretrained(tiny_llama, dtype=torch.float32).eval()
    with torch.no_grad():
        expected = reference(_ids()).logits

    model = streaming.StreamedModel(
        str(tiny_llama), device="cpu", dtype=torch.float32, prefetching=False
    )
    with torch.no_grad():
        got = model.model(_ids()).logits
    model.close()

    assert torch.equal(expected, got)


def test_no_decoder_layer_stays_resident(tiny_llama: Path) -> None:
    """The whole point: what is resident is one layer, not the checkpoint."""
    model = streaming.StreamedModel(
        str(tiny_llama), device="cpu", dtype=torch.float32, prefetching=False
    )

    def materialised() -> int:
        return sum(
            1 for layer in model.layers for p in layer.parameters() if p.device.type != "meta"
        )

    assert materialised() == 0
    with torch.no_grad():
        model.model(_ids())
    # And freed again afterwards, or the second token would cost what the
    # first one saved.
    assert materialised() == 0
    model.close()


def test_prefetching_changes_the_timing_and_not_the_answer(tiny_llama: Path) -> None:
    """A read overlapped with compute is still the same read."""
    plain = streaming.StreamedModel(
        str(tiny_llama), device="cpu", dtype=torch.float32, prefetching=False
    )
    with torch.no_grad():
        without = plain.model(_ids()).logits
    plain.close()

    fetched = streaming.StreamedModel(
        str(tiny_llama), device="cpu", dtype=torch.float32, prefetching=True
    )
    with torch.no_grad():
        with_prefetch = fetched.model(_ids()).logits
    fetched.close()

    assert torch.equal(without, with_prefetch)


def test_generation_survives_the_free_and_reload_cycle(tiny_llama: Path) -> None:
    """Token two reuses layers that token one returned to ``meta``.

    The pre-hook and the post-hook have to be exact inverses for this to hold.
    They were not: the post-hook used ``module.to("meta")``, which also evicted
    buffers that are computed at construction and are not in the checkpoint,
    so nothing restored them.
    """
    from transformers import AutoModelForCausalLM

    reference = AutoModelForCausalLM.from_pretrained(tiny_llama, dtype=torch.float32).eval()
    with torch.no_grad():
        expected = reference.generate(_ids(), max_new_tokens=6, do_sample=False)

    model = streaming.StreamedModel(
        str(tiny_llama), device="cpu", dtype=torch.float32, prefetching=False
    )
    with torch.no_grad():
        got = model.generate(_ids(), max_new_tokens=6, do_sample=False)
    model.close()

    assert expected.tolist() == got.tolist()


def test_tied_embeddings_load_without_an_lm_head_tensor(tmp_path: Path) -> None:
    """A tied head has no second copy to find, and must not be looked for.

    Llama 3.2 ties its embeddings, and the previous runtime died reading an
    ``lm_head`` shard that does not exist in such a checkpoint.
    """
    from transformers import AutoModelForCausalLM, LlamaConfig, LlamaForCausalLM

    torch.manual_seed(1)
    config = LlamaConfig(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=4,
        tie_word_embeddings=True,
    )
    LlamaForCausalLM(config).eval().save_pretrained(tmp_path, safe_serialization=True)

    reference = AutoModelForCausalLM.from_pretrained(tmp_path, dtype=torch.float32).eval()
    with torch.no_grad():
        expected = reference(_ids()).logits

    model = streaming.StreamedModel(
        str(tmp_path), device="cpu", dtype=torch.float32, prefetching=False
    )
    with torch.no_grad():
        got = model.model(_ids()).logits
    model.close()

    assert torch.equal(expected, got)


def test_a_renamed_output_head_is_recovered_rather_than_skipped(tiny_llama: Path) -> None:
    """The bug that motivated the whole verification step.

    ``pythia`` stores its output projection as ``embed_out.weight``; current
    transformers calls that module ``lm_head``. Skipped silently, the head
    stayed uninitialised and the model ran with every hidden state correct and
    only the final projection garbage. Here the rename is simulated directly:
    one unused checkpoint tensor whose shape matches exactly one stranded
    parameter is adopted, and said out loud.
    """
    from safetensors.torch import load_file, save_file

    renamed = tiny_llama.parent / "renamed-head"
    renamed.mkdir(exist_ok=True)
    for item in tiny_llama.iterdir():
        if item.suffix == ".json":
            (renamed / item.name).write_text(item.read_text())
    tensors = load_file(str(tiny_llama / "model.safetensors"))
    tensors["embed_out.weight"] = tensors.pop("lm_head.weight")
    save_file(tensors, str(renamed / "model.safetensors"))

    model = streaming.StreamedModel(
        str(renamed), device="cpu", dtype=torch.float32, prefetching=False
    )
    assert model.model.get_parameter("lm_head.weight").device.type == "cpu"
    model.close()


def test_a_weight_that_cannot_be_matched_refuses_instead_of_running(tiny_llama: Path) -> None:
    """Fluent nonsense is the failure mode; an exception is the fix."""
    from safetensors.torch import load_file, save_file

    broken = tiny_llama.parent / "missing-head"
    broken.mkdir(exist_ok=True)
    for item in tiny_llama.iterdir():
        if item.suffix == ".json":
            (broken / item.name).write_text(item.read_text())
    tensors = load_file(str(tiny_llama / "model.safetensors"))
    # Dropped entirely, so there is nothing of the right shape to adopt.
    tensors.pop("lm_head.weight")
    save_file(tensors, str(broken / "model.safetensors"))

    with pytest.raises(RuntimeError, match="could not be matched"):
        streaming.StreamedModel(str(broken), device="cpu", dtype=torch.float32, prefetching=False)


# ---------------------------------------------------------------------------
# The pieces, where a unit test is sharper than an end-to-end one
# ---------------------------------------------------------------------------


def test_the_tensor_index_reads_a_shard_map_and_a_single_file(
    tiny_llama: Path, tmp_path: Path
) -> None:
    """Both layouts, because real checkpoints come in both."""
    single = streaming.tensor_index(tiny_llama)
    assert single
    assert all(path.name == "model.safetensors" for path in single.values())

    sharded = tmp_path / "sharded"
    sharded.mkdir()
    (sharded / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"a.weight": "part-1.safetensors"}})
    )
    assert streaming.tensor_index(sharded) == {"a.weight": sharded / "part-1.safetensors"}


def test_a_pickle_only_checkpoint_is_refused_by_name(tmp_path: Path) -> None:
    """Reading one layer out of a pickle means reading all of it, per layer."""
    (tmp_path / "pytorch_model.bin").write_bytes(b"not safetensors")
    with pytest.raises(FileNotFoundError, match="safetensors"):
        streaming.tensor_index(tmp_path)


def test_the_decoder_stack_is_found_by_shape_not_by_name() -> None:
    """A per-family table of module paths is the thing this avoids keeping."""
    import types

    import torch.nn as nn

    class _Model(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.somewhere = nn.ModuleList([nn.Linear(2, 2) for _ in range(3)])

    layers = streaming._decoder_layers(_Model(), types.SimpleNamespace(num_hidden_layers=3))
    assert len(layers) == 3

    # A config whose layer count does not match anything yields nothing, which
    # the constructor turns into a refusal rather than a half-empty model.
    assert streaming._decoder_layers(_Model(), types.SimpleNamespace(num_hidden_layers=9)) == []
    # And a config that declares no layer count at all.
    assert streaming._decoder_layers(_Model(), types.SimpleNamespace()) == []


def test_layer_names_are_split_by_prefix_longest_first() -> None:
    """So ``layers.1`` never swallows ``layers.11``."""
    import types

    one, eleven = types.SimpleNamespace(), types.SimpleNamespace()
    index = {
        "m.layers.1.w": Path("f"),
        "m.layers.11.w": Path("f"),
        "m.embed": Path("f"),
    }
    out = streaming._names_by_layer(
        index, [one, eleven], {id(one): "m.layers.1", id(eleven): "m.layers.11"}
    )
    assert out[id(one)] == ["m.layers.1.w"]
    assert out[id(eleven)] == ["m.layers.11.w"]


def test_the_device_and_dtype_defaults_are_half_precision_off_cpu() -> None:
    """Half everywhere there is an accelerator; CPU half precision is emulated."""
    assert streaming.default_device() in ("cuda", "mps", "cpu")
    assert streaming.default_dtype("cpu") is torch.float32
    assert streaming.default_dtype("cuda") is torch.float16
    assert streaming.default_dtype("mps") is torch.float16


def test_resolve_checkpoint_passes_a_local_directory_straight_through(tiny_llama: Path) -> None:
    """A path that exists is never a repository id, so nothing is fetched."""
    assert streaming.resolve_checkpoint(str(tiny_llama)) == tiny_llama
