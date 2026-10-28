"""
streaming — run a model that does NOT fit in memory, with no airllm.

A transformer never needs all of its layers resident at once. Decoding reads
layer 1, then layer 2, then layer 3; only the layer being computed has to be in
memory. Keep one decoder layer resident, read the rest off disk as they are
reached, and the memory a model needs stops scaling with its parameter count
and starts scaling with its *widest single layer*.

This module is the runtime that does that. :mod:`best_engine_ai_helper.offload`
is the part that decides *whether* to, sizes it and prices it; this is the part
that actually runs it.

Why it is written here rather than imported
-------------------------------------------
It used to be ``airllm``. That dependency was removed, and the reasons were
measured rather than assumed:

1. **It did not work on Apple Silicon at all.** airllm's
   ``AutoModel.from_pretrained`` dispatches on architecture on every platform
   except macOS, where it hard-returns a hand-written **Llama** transformer in
   MLX whose projections are all ``bias=False``. Qwen, Gemma and Mistral carry
   attention biases; Llama 3.2 ties its embeddings and has no ``lm_head``
   tensor to load; older exports persist ``rotary_emb.inv_freq``, which that
   class has no parameter for. Each of those is a different crash, and the
   platform this suite is developed on hit all three.
2. **It wrote a second copy of the checkpoint to disk.** Its splitter
   materialises one file per layer before anything runs, so streaming a 70B
   model needed ~294 GB free *on top of* the download. That is what made
   almost every row of ``airllm plan`` read ``runs: NO`` on a normal laptop —
   the models fit in memory-per-layer terms and failed on scratch space.
3. It carried MLX, bitsandbytes and a dozen per-family subclasses for
   architectures nobody here asked for.

What this does instead
----------------------
The technique is the same one airllm's generic (non-macOS) path uses, and it is
the right one: build the model on the ``meta`` device so it costs nothing, then
hang a forward pre-hook on every decoder layer that materialises that layer's
weights just before it runs, and a post-hook that returns it to ``meta``
afterwards. **transformers owns the forward pass**, so the architecture is
whatever transformers says it is — which is why this works for Qwen and Gemma
without a line of per-family code.

Three deliberate differences from that design, all of them things this project
needs and that one did not do:

- **No pre-split, and therefore no scratch space.** ``safetensors`` is a
  memory-mapped format with a tensor-level index, so one layer's weights can be
  read straight out of the original shards. Nothing is copied, nothing is
  written, and the disk requirement for streaming drops from "the checkpoint
  again" to zero.
- **Apple Silicon is torch on MPS**, not MLX. torch has supported Metal for
  years; routing through a second framework is what cost airllm every
  non-Llama architecture on this platform.
- **The decoder stack is discovered, not named.** airllm keeps a per-family
  table of module paths (``model.layers`` here, ``transformer.h`` there). This
  looks for the ``ModuleList`` whose length matches the config's layer count,
  which is a property every causal LM has and no table has to be kept current.

What it does NOT do
-------------------
Said plainly, because a runtime that pretends is worse than one that refuses:

- **safetensors only.** A checkpoint published only as ``pytorch_model.bin``
  is refused by name. Pickle has no tensor-level index, so "read one layer"
  would mean reading the whole file per layer.
- **No per-expert MoE streaming.** A sparse mixture-of-experts layer is
  materialised whole, so the resident figure for one is its full expert set
  rather than the handful a token routes to.
- **No weight quantisation on the fly.** The checkpoint is run at the dtype it
  ships in (cast to the compute dtype). Quantise before streaming if the layer
  itself is too wide.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import os_helper as osh

#: Filenames that carry a safetensors tensor index, in the order they are tried.
_INDEX_NAMES = ("model.safetensors.index.json",)

#: Single-file checkpoint name, when there is no shard index.
_SINGLE_NAME = "model.safetensors"

#: What a snapshot download needs: weights, the config that builds the model,
#: and the tokenizer. Nothing else -- no ONNX exports, no duplicate .bin
#: mirrors of tensors already present as safetensors, no TensorFlow copies.
DOWNLOAD_PATTERNS = (
    "*.safetensors",
    "*.safetensors.index.json",
    "*.json",
    "*.model",
    "*.txt",
)


def default_device() -> str:
    """
    The best torch device on this machine for streamed decoding.

    MPS is named explicitly rather than left to a ``cuda``-or-``cpu`` guess:
    that guess is what sent Apple Silicon down a separate framework and cost it
    every architecture that was not Llama.

    Returns
    -------
    str
        ``'cuda'``, ``'mps'`` or ``'cpu'``.

    Examples
    --------
    >>> default_device() in ("cuda", "mps", "cpu")
    True
    """
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def default_dtype(device: str) -> Any:
    """
    The compute dtype to materialise streamed weights in.

    Half precision everywhere there is an accelerator, because the whole point
    is to halve what crosses the disk-to-memory boundary per layer. CPU stays
    in float32: half precision on CPU is emulated and slower, and a machine
    streaming on CPU is already paying enough.

    Parameters
    ----------
    device : str
        Output of :func:`default_device`.

    Returns
    -------
    torch.dtype

    Examples
    --------
    >>> import torch
    >>> default_dtype("cpu") is torch.float32
    True
    >>> default_dtype("mps") is torch.float16
    True
    """
    import torch

    return torch.float32 if device == "cpu" else torch.float16


def resolve_checkpoint(model: str, *, hf_token: str | None = None) -> Path:
    """
    The local directory holding a checkpoint, downloading it if needed.

    Parameters
    ----------
    model : str
        A local path, or a Hugging Face repository id.
    hf_token : str or None
        Token for a gated repository.

    Returns
    -------
    pathlib.Path
        Directory containing the safetensors shards and the config.

    Examples
    --------
    >>> resolve_checkpoint("meta-llama/Llama-3.3-70B-Instruct")  # doctest: +SKIP
    """
    local = Path(model).expanduser()
    if local.is_dir():
        return local

    from huggingface_hub import snapshot_download

    osh.info(f"Resolving {model} from the Hugging Face Hub (weights are cached after the first).")
    return Path(
        snapshot_download(
            model,
            allow_patterns=list(DOWNLOAD_PATTERNS),
            token=hf_token,
        )
    )


def tensor_index(checkpoint: Path) -> dict[str, Path]:
    """
    Map every tensor name in a checkpoint to the file that holds it.

    This is what makes the pre-split unnecessary. A sharded checkpoint already
    ships ``model.safetensors.index.json``, which is exactly the "which file
    holds this tensor" table a splitter would otherwise rebuild by copying
    every byte.

    Parameters
    ----------
    checkpoint : pathlib.Path
        Directory from :func:`resolve_checkpoint`.

    Returns
    -------
    dict[str, pathlib.Path]
        Tensor name -> the ``.safetensors`` file containing it.

    Raises
    ------
    FileNotFoundError
        When the checkpoint ships no safetensors at all, naming the reason.

    Examples
    --------
    >>> tensor_index(Path("/models/llama"))  # doctest: +SKIP
    """
    from safetensors import safe_open

    for name in _INDEX_NAMES:
        index_path = checkpoint / name
        if index_path.exists():
            weight_map = json.loads(index_path.read_text())["weight_map"]
            return {key: checkpoint / filename for key, filename in weight_map.items()}

    single = checkpoint / _SINGLE_NAME
    if single.exists():
        with safe_open(str(single), framework="pt") as handle:
            return {key: single for key in handle.keys()}

    # Named rather than guessed at, because the fix is a different checkpoint
    # and the caller cannot work that out from a KeyError.
    raise FileNotFoundError(
        f"{checkpoint} ships no safetensors ({_SINGLE_NAME} or {_INDEX_NAMES[0]}). "
        "Layer streaming reads one layer at a time out of a memory-mapped "
        "tensor index, which a pickled `pytorch_model.bin` does not have: "
        "reading one layer from it would mean reading the whole file, once per "
        "layer. Use a repository that publishes safetensors."
    )


def _read_tensors(index: dict[str, Path], names: list[str]) -> dict[str, Any]:
    """
    Read a named set of tensors out of the checkpoint, grouped by file.

    Grouped because opening a safetensors file has a cost and a decoder layer's
    tensors are almost always contiguous in one shard: one open per file beats
    one open per tensor.
    """
    from safetensors import safe_open

    by_file: dict[Path, list[str]] = {}
    for name in names:
        by_file.setdefault(index[name], []).append(name)

    out: dict[str, Any] = {}
    for path, keys in by_file.items():
        with safe_open(str(path), framework="pt", device="cpu") as handle:
            for key in keys:
                out[key] = handle.get_tensor(key)
    return out


class StreamedModel:
    """
    A causal LM whose decoder layers live on disk until the moment they run.

    Built on the ``meta`` device, so constructing one costs no memory whatever
    the parameter count. Each decoder layer is materialised by a forward
    pre-hook and returned to ``meta`` by a post-hook, so the resident footprint
    is everything-outside-the-decoder-stack (embeddings, final norm, head) plus
    one layer.

    Parameters
    ----------
    model : str
        Local path or Hugging Face repository id.
    device : str or None
        torch device; None picks :func:`default_device`.
    dtype : torch.dtype or None
        Compute dtype; None picks :func:`default_dtype`.
    prefetching : bool
        Read the next layer on a worker thread while the current one computes.
        Disk is the binding constraint here, so this is the main speed lever
        that costs nothing but one layer of extra host memory.
    hf_token : str or None
        Token for a gated repository.
    trust_remote_code : bool
        Passed to transformers for architectures that ship their own modelling
        code. Off by default: it executes code from the repository.

    Attributes
    ----------
    model : transformers.PreTrainedModel
        The underlying model, with hooks installed.
    tokenizer : transformers.PreTrainedTokenizerBase
    device : str
    layers : list
        The streamed decoder layers, in execution order.

    Examples
    --------
    >>> StreamedModel("meta-llama/Llama-3.3-70B-Instruct")  # doctest: +SKIP
    """

    def __init__(
        self,
        model: str,
        *,
        device: str | None = None,
        dtype: Any | None = None,
        prefetching: bool = True,
        hf_token: str | None = None,
        trust_remote_code: bool = False,
        max_seq_len: int | None = None,
    ) -> None:
        from accelerate import init_empty_weights
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        self.repo = model
        self.device = device or default_device()
        self.dtype = dtype if dtype is not None else default_dtype(self.device)
        self.prefetching = prefetching
        self.max_seq_len = max_seq_len

        self.checkpoint = resolve_checkpoint(model, hf_token=hf_token)
        self.index = tensor_index(self.checkpoint)

        self.config = AutoConfig.from_pretrained(
            self.checkpoint, trust_remote_code=trust_remote_code
        )
        # Best effort, and None is a legitimate outcome. A directory of
        # weights with no tokenizer in it is a real thing -- a local export, a
        # checkpoint split from its tokenizer repository -- and it can still
        # be streamed by a caller who tokenizes elsewhere. Refusing to build
        # the model over it would be refusing the wrong thing; `generate`
        # below is where the absence actually bites, so that is where it is
        # reported.
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.checkpoint, trust_remote_code=trust_remote_code
            )
        except Exception as exc:  # noqa: BLE001 — weights without a tokenizer
            osh.debug(f"{model} carries no loadable tokenizer: {exc!r}")
            self.tokenizer = None

        # include_buffers=False on purpose: a non-persistent buffer such as
        # rotary `inv_freq` is COMPUTED from the config and is not in the
        # checkpoint, so leaving it on meta would produce a model that builds
        # and then fails at the first attention. This is the same trap that
        # made airllm's macOS path die on `rotary_emb` for older exports.
        with init_empty_weights(include_buffers=False):
            self.model = AutoModelForCausalLM.from_config(
                self.config, trust_remote_code=trust_remote_code
            )
        self.model.eval()

        self.layers = _decoder_layers(self.model, self.config)
        if not self.layers:
            raise RuntimeError(
                f"Could not find the decoder stack of {type(self.model).__name__}: no "
                "ModuleList matches the config's layer count. Streaming needs to know "
                "which modules to swap, and guessing one wrongly would silently run a "
                "partly-empty model."
            )

        self._prefixes = _layer_prefixes(self.model, self.layers)
        self._by_module = _names_by_layer(self.index, self.layers, self._prefixes)
        self._streamed = {id(layer) for layer in self.layers}
        self._executor = ThreadPoolExecutor(max_workers=1) if prefetching else None
        self._pending: Future | None = None
        self._pending_for: int | None = None

        self._adopt_generation_config(trust_remote_code=trust_remote_code)
        self._load_resident()
        self._install_hooks()

    def _adopt_generation_config(self, *, trust_remote_code: bool) -> None:
        """Take the checkpoint's own ``generation_config.json``.

        ``from_pretrained`` reads it; ``from_config`` does not, and this builds
        from a config. The gap is not cosmetic: Qwen ships
        ``repetition_penalty: 1.1``, which applies to **greedy** decoding too,
        along with the real end-of-sequence ids. Without it a streamed
        generation diverges from an ordinary one after the first token —
        fluently, which is the hard way to notice.

        Caught exactly that way: a single forward matched the reference to
        ``0.0`` absolute logit difference while the generated sentences
        differed, which rules out the weights and points at the decoding
        policy.
        """
        from transformers import GenerationConfig

        try:
            self.model.generation_config = GenerationConfig.from_pretrained(
                self.checkpoint, trust_remote_code=trust_remote_code
            )
        except Exception as exc:  # noqa: BLE001 — not every repository ships one
            osh.debug(f"{self.repo} ships no generation_config.json, keeping defaults: {exc!r}")

    # -- setup ----------------------------------------------------------------

    def _load_resident(self) -> None:
        """Materialise everything that is NOT a streamed decoder layer, once.

        Embeddings, the final norm and the head. They are read on every token
        whatever happens, so streaming them would buy nothing and cost a disk
        read per token.

        Tied embeddings are handled by ``tie_weights`` rather than by looking
        for a tensor that does not exist — the exact failure that stopped
        Llama 3.2 loading under airllm.
        """
        streamed = {name for names in self._by_module.values() for name in names}
        resident = [name for name in self.index if name not in streamed]

        tensors = _read_tensors(self.index, resident)
        # Only what actually LANDED, never what was merely attempted: a
        # checkpoint tensor the class has no home for has to stay available as
        # a recovery candidate, which is precisely the renamed output head.
        self._resident_loaded = {
            name
            for name, value in tensors.items()
            if _place(self.model, name, value, self.device, self.dtype)
        }

        # Tied heads share the embedding tensor, so there is no second copy to
        # load; re-tying after placement is what makes the head real.
        if bool(getattr(self.config, "tie_word_embeddings", False)):
            self.model.tie_weights()

        self._place_computed_buffers()
        self._verify_resident(self._resident_loaded)

    def _verify_resident(self, loaded: set[str]) -> None:
        """Refuse to run with an unmaterialised weight, and say which one.

        This is the most important safety net in the module, and it exists
        because of a bug it would have caught instantly. A checkpoint key can
        have no home in the class transformers builds today: ``pythia`` stores
        its output projection as ``embed_out.weight`` and current transformers
        calls that module ``lm_head``. The tensor was therefore skipped, the
        head stayed uninitialised, and the model **ran** — every hidden state
        bit-identical to an ordinary load, and only the final projection
        garbage. Fluent, confident, wrong.

        So: anything outside the streamed stack that is still on ``meta``
        after loading is a hard error. Before erroring, one unambiguous
        recovery is attempted — an unused checkpoint tensor whose shape
        matches, and only when exactly one does. That is enough for a pure
        rename and refuses to guess when it is not.

        Deliberately not a table of per-family renames: that is the thing this
        module exists to avoid maintaining. A shape match plus a uniqueness
        requirement is a rule, not a list.
        """
        streamed = {name for names in self._by_module.values() for name in names}
        stranded = [
            name
            for name, param in self.model.named_parameters()
            if param.device.type == "meta" and name not in streamed
        ]
        if not stranded:
            return

        spare = [name for name in self.index if name not in loaded and name not in streamed]
        recovered: list[str] = []
        for name in list(stranded):
            shape = tuple(self.model.get_parameter(name).shape)
            matches = [key for key in spare if _shape_of(self.index, key) == shape]
            if len(matches) != 1:
                continue
            source = matches[0]
            osh.info(f"Checkpoint names {source!r} what this model calls {name!r}; mapping it.")
            value = _read_tensors(self.index, [source])[source]
            _place(self.model, name, value, self.device, self.dtype)
            spare.remove(source)
            recovered.append(name)

        stranded = [name for name in stranded if name not in recovered]
        if stranded:
            raise RuntimeError(
                f"{self.repo}: {len(stranded)} weight(s) outside the streamed layers could "
                f"not be matched to a checkpoint tensor: {stranded[:8]}. Running anyway "
                "would produce a model that generates fluent nonsense rather than one "
                "that fails, so it refuses here instead. Unused checkpoint tensors: "
                f"{spare[:8]}."
            )

    def _place_computed_buffers(self) -> None:
        """Move buffers that were computed rather than loaded onto the device.

        ``init_empty_weights(include_buffers=False)`` deliberately lets a
        non-persistent buffer be computed for real, because it is not in the
        checkpoint and a meta one would fail at the first attention. It is
        computed on the **CPU**, though, and nothing afterwards moves it: the
        loader only places tensors the checkpoint names.

        Left there, a model on MPS or CUDA computes its rotary position table
        on the host and the rest of the forward on the accelerator. That does
        not crash — which is the problem. It produced fluent, confident,
        *different* text, caught only by diffing a streamed generation against
        an ordinary one token for token.

        dtype is deliberately NOT changed: transformers keeps ``inv_freq`` in
        float32 on purpose, and halving it here would re-introduce in
        precision the error just removed in placement.
        """
        for name, buffer in self.model.named_buffers():
            if buffer.device.type not in ("meta", self.device):
                try:
                    _place(self.model, name, buffer.to(self.device), self.device, buffer.dtype)
                except Exception as exc:  # noqa: BLE001 — a buffer that will not move is a warning
                    osh.debug(f"Computed buffer {name!r} stayed on {buffer.device}: {exc!r}")

    def _install_hooks(self) -> None:
        """Hang the load/free pair on every streamed decoder layer."""
        for position, layer in enumerate(self.layers):
            layer._stream_position = position  # type: ignore[attr-defined]
            layer.register_forward_pre_hook(self._pre_hook)
            layer.register_forward_hook(self._post_hook)

    # -- the streaming loop ---------------------------------------------------

    def _tensors_for(self, position: int) -> dict[str, Any]:
        """Read one layer's weights off disk, into host memory."""
        return _read_tensors(self.index, self._by_module[id(self.layers[position])])

    def _pre_hook(self, module: Any, args: Any) -> None:
        """Materialise this layer, and start reading the next one."""
        position = module._stream_position

        if self._pending is not None and self._pending_for == position:
            tensors = self._pending.result()
            self._pending = None
            self._pending_for = None
        else:
            tensors = self._tensors_for(position)

        for name, value in tensors.items():
            _place(self.model, name, value, self.device, self.dtype)

        # The read of layer N+1 overlaps the compute of layer N. Disk is the
        # binding constraint in layer streaming, so this is where the time goes.
        if self._executor is not None and position + 1 < len(self.layers):
            self._pending_for = position + 1
            self._pending = self._executor.submit(self._tensors_for, position + 1)

    def _post_hook(self, module: Any, args: Any, output: Any) -> Any:
        """Free exactly the tensors this layer's pre-hook loaded.

        Not ``module.to("meta")``, which is the obvious spelling and is wrong:
        it would also evict buffers that were **computed** at construction and
        are not in the checkpoint, so nothing would restore them and every
        layer after its first use would run with a destroyed rotary table.
        Freeing what was loaded is the invariant that keeps the pre-hook and
        the post-hook exact inverses of each other.
        """
        from accelerate.utils import set_module_tensor_to_device

        for name in self._by_module[id(module)]:
            try:
                set_module_tensor_to_device(self.model, name, "meta")
            except (KeyError, AttributeError, ValueError):  # never placed, nothing to free
                pass
        return output

    # -- the model surface ----------------------------------------------------

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to transformers, which owns the forward pass."""
        return self.model.generate(*args, **kwargs)

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to transformers."""
        return self.model(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to transformers."""
        return self.model(*args, **kwargs)

    def close(self) -> None:
        """Stop the prefetch thread. Idempotent."""
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None


def _decoder_layers(model: Any, config: Any) -> list[Any]:
    """
    Find the decoder stack by shape rather than by a table of names.

    Every causal LM has one ``ModuleList`` whose length is the config's hidden
    layer count; which attribute holds it (``model.layers``, ``transformer.h``,
    ``gpt_neox.layers``) is a per-family detail that a table has to chase and
    this does not.

    Parameters
    ----------
    model : torch.nn.Module
    config : transformers.PretrainedConfig

    Returns
    -------
    list
        The decoder layers in order, or an empty list when none matches.

    Examples
    --------
    >>> import types
    >>> _decoder_layers(types.SimpleNamespace(named_modules=lambda: []),
    ...                 types.SimpleNamespace(num_hidden_layers=3))
    []
    """
    import torch.nn as nn

    expected = None
    for attribute in ("num_hidden_layers", "n_layer", "num_layers"):
        value = getattr(config, attribute, None)
        if isinstance(value, int) and value > 0:
            expected = value
            break
    if expected is None:
        return []

    for _name, module in model.named_modules():
        if isinstance(module, nn.ModuleList) and len(module) == expected:
            return list(module)
    return []


def _place(model: Any, name: str, value: Any, device: str, dtype: Any) -> bool:
    """
    Put one checkpoint tensor where it belongs, or skip it saying why.

    A checkpoint routinely carries tensors the instantiated class has no home
    for. Old GPT-NeoX exports persist ``attention.bias``, the causal mask that
    current transformers computes instead of storing; a multimodal repository
    carries a vision tower a text-only build does not instantiate. accelerate
    signals all of these with ``ValueError``, which is why the net is this
    wide — catching only ``KeyError`` let a 160M model crash on a mask.

    Skipping is the right answer, and a silent skip is not: a weight that
    genuinely should have loaded and did not would otherwise show up as a
    model that runs and talks nonsense.

    Examples
    --------
    >>> _place(None, "x", None, "cpu", None)   # no model, so nothing is placed
    False
    """
    from accelerate.utils import set_module_tensor_to_device

    if model is None:
        return False
    try:
        set_module_tensor_to_device(model, name, device, value=value, dtype=dtype)
    except (KeyError, AttributeError, ValueError) as exc:
        osh.debug(f"Checkpoint tensor {name!r} has no place in this model, skipped: {exc!r}")
        return False
    return True


def _decoder_layers(model: Any, config: Any) -> list[Any]:
    """
    Find the decoder stack by shape rather than by a table of names.

    Every causal LM has one ``ModuleList`` whose length is the config's hidden
    layer count; which attribute holds it (``model.layers``, ``transformer.h``,
    ``gpt_neox.layers``) is a per-family detail that a table has to chase and
    this does not.

    Parameters
    ----------
    model : torch.nn.Module
    config : transformers.PretrainedConfig

    Returns
    -------
    list
        The decoder layers in order, or an empty list when none matches.

    Examples
    --------
    >>> import types
    >>> _decoder_layers(types.SimpleNamespace(named_modules=lambda: []),
    ...                 types.SimpleNamespace(num_hidden_layers=3))
    []
    """
    import torch.nn as nn

    expected = None
    for attribute in ("num_hidden_layers", "n_layer", "num_layers"):
        value = getattr(config, attribute, None)
        if isinstance(value, int) and value > 0:
            expected = value
            break
    if expected is None:
        return []

    for _name, module in model.named_modules():
        if isinstance(module, nn.ModuleList) and len(module) == expected:
            return list(module)
    return []


def _layer_prefixes(model: Any, layers: list[Any]) -> dict[int, str]:
    """
    The dotted path of each streamed layer, as the checkpoint keys it.

    Parameters
    ----------
    model : torch.nn.Module
    layers : list

    Returns
    -------
    dict[int, str]
        ``id(layer)`` -> ``'model.layers.7'`` and the like.
    """
    wanted = {id(layer) for layer in layers}
    return {id(module): name for name, module in model.named_modules() if id(module) in wanted}


def _names_by_layer(
    index: dict[str, Path], layers: list[Any], prefixes: dict[int, str]
) -> dict[int, list[str]]:
    """
    Split the checkpoint's tensor names across the streamed layers.

    Driven by the **checkpoint** rather than by ``named_parameters()``, which
    is the fix for a real failure: a persistent buffer stored under a decoder
    layer is not a parameter, so a parameter-driven split left it out of the
    layer and then tried to load it as a resident tensor, where it crashed.
    Whatever the checkpoint files under ``model.layers.7.`` belongs to layer 7,
    parameter or buffer.

    Parameters
    ----------
    index : dict[str, pathlib.Path]
        Output of :func:`tensor_index`.
    layers : list
    prefixes : dict[int, str]
        Output of :func:`_layer_prefixes`.

    Returns
    -------
    dict[int, list[str]]
        ``id(layer)`` -> the tensor names it owns.

    Examples
    --------
    >>> import types
    >>> a, b = types.SimpleNamespace(), types.SimpleNamespace()
    >>> idx = {"m.layers.0.w": Path("f"), "m.layers.1.w": Path("f"), "m.embed": Path("f")}
    >>> out = _names_by_layer(idx, [a, b], {id(a): "m.layers.0", id(b): "m.layers.1"})
    >>> out[id(a)], out[id(b)]
    (['m.layers.0.w'], ['m.layers.1.w'])
    """
    out: dict[int, list[str]] = {id(layer): [] for layer in layers}
    # Longest prefix first, so `model.layers.1` never swallows `model.layers.11`.
    ordered = sorted(prefixes.items(), key=lambda kv: len(kv[1]), reverse=True)
    for name in index:
        for key, prefix in ordered:
            if name.startswith(f"{prefix}."):
                out[key].append(name)
                break
    return out


def _shape_of(index: dict[str, Path], key: str) -> tuple[int, ...]:
    """The shape of one checkpoint tensor, read from the header alone.

    ``get_slice`` reads the safetensors metadata rather than the payload, so
    asking the shape of a 2 GB embedding table costs nothing.
    """
    from safetensors import safe_open

    with safe_open(str(index[key]), framework="pt") as handle:
        return tuple(handle.get_slice(key).get_shape())
