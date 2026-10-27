"""
offload — run a model that does NOT fit in memory, by streaming its layers.

Every other backend in this package answers the same question: *which model
fits?* This one answers the question that follows when the honest answer is
"none of the good ones": **a transformer never needs all of its layers resident
at once.** Decoding reads layer 1, then layer 2, then layer 3; only the layer
being computed has to be in memory. Keep one shard resident, stream the rest
off the disk, and the memory a model needs stops scaling with its parameter
count and starts scaling with its *widest single layer* — a 70B model becomes a
~5 GB resident footprint instead of a 141 GB one.

That idea, and the runtime that implements it, come from **airllm**
(https://github.com/lyogavin/airllm, Apache-2.0). This module is the seam
between it and the rest of this package:

- **The arithmetic is here.** Which model a machine can stream, what it will
  cost in resident memory, how many seconds per token the disk will impose, and
  whether streaming is worth activating at all are *selection* questions, which
  is this package's entire job. They are re-derived from first principles below
  (see :func:`footprint_gb` and :func:`estimated_tokens_per_second`) and checked
  against airllm's own published figures.
- **The runtime is imported, not copied.** :func:`load` and :func:`generate`
  are a thin adapter over ``airllm.AutoModel``, which is a **core dependency**
  of this package: streaming is available on every install, not behind an
  extra. Nothing here reimplements layer sharding.

Why imported rather than vendored
---------------------------------
1. **The weight is the price of the capability, and it is paid up front.**
   airllm needs torch, transformers, accelerate, safetensors, scipy and
   sentencepiece, so this install is a gigabyte-scale download rather than the
   seconds-long one it used to be. That cost is accepted deliberately: "which
   model can this machine run" and "which model can this machine run if it
   streams the layers" are the same question, and a capability behind an extra
   is a capability most callers never discover. Vendoring would not have
   avoided the weight either — airllm's own dependencies are the weight — so
   this is an argument about *declaring* it, not about copying it. The import
   stays lazy: nothing imports airllm until a model is actually loaded, so the
   cost is install size and never startup time.
2. **It is a moving target.** airllm's value is per-family sharding code
   (Llama, Qwen, DeepSeek, Mixtral, ChatGLM, Kimi), rewritten as each new
   family ships. Vendored, it would be frozen at the day it was copied and rot
   from the first release after.
3. **Licence hygiene.** airllm is Apache-2.0; this package is BSD-3-Clause.
   Importing keeps the two trees, and their notice obligations, separate.
4. **The division of labour is real, not a dodge.** airllm decides *how* to
   stream. Nothing in it decides *whether* this machine should, which model it
   should stream, or what the user should expect in tokens per second — and
   those are the three questions a caller of this package is actually asking.

Activation
----------
Streaming is never the default: it trades two to three orders of magnitude of
speed for capability, and a machine that can comfortably run a 14B model should
run it. :func:`decide` is the policy, and it fires on exactly two triggers:

- **Automatic** — the conventional backend found nothing that fits this
  machine's memory budget for a kind the caller needs. Streaming is then the
  difference between a model and no model, so it is proposed with its cost
  stated in seconds per token.
- **Manual** — a human asks for it, by ``--backend airllm``, by
  ``airllm: always`` in the brief, or by ``BEST_ENGINE_AIRLLM=always`` in the
  environment. A human who wants a 235B model on a laptop overnight is making a
  legitimate choice that no automatic rule should have to guess.

``BEST_ENGINE_AIRLLM=never`` switches the whole path off, including the
automatic trigger.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import math
import os
from typing import Any, Literal

import os_helper as osh

#: Name of the upstream distribution, used in every install hint so the string
#: is spelled once.
PACKAGE = "airllm"

#: What to tell a caller whose interpreter cannot import the runtime. airllm is
#: a CORE dependency, so this is no longer an "opt in" message: reaching it
#: means the install is incomplete — a stripped environment, a failed wheel
#: build, a vendored subset — rather than a choice the user made. The command
#: that fixes that is a reinstall, not an extra.
INSTALL_HINT = "pip install --upgrade --force-reinstall best-engine-ai-helper"

#: Environment variable that forces the policy :func:`decide` applies.
#: ``auto`` (the default) activates streaming only as a last resort; ``always``
#: activates it whenever the runtime can, ``never`` disables it outright.
ENV_VAR = "BEST_ENGINE_AIRLLM"

#: Accepted values of :data:`ENV_VAR` and of a brief's ``airllm:`` key, plus the
#: booleans people actually type.
_REQUEST_ALIASES: dict[str, str] = {
    "auto": "auto",
    "always": "always",
    "on": "always",
    "true": "always",
    "yes": "always",
    "1": "always",
    "never": "never",
    "off": "never",
    "false": "never",
    "no": "never",
    "0": "never",
}

#: Bytes per parameter, by the dtype the weights are *stored* in. A streaming
#: backend reads the checkpoint as published, so this is the number that sets
#: both the shard size and the per-token disk traffic — not the dtype the
#: arithmetic happens in. ``q4``/``q8`` are airllm's own block-wise
#: compression, which quantises the weights only (the bottleneck is the disk,
#: not the multiply) and is therefore a disk-traffic *divider*.
_BYTES_PER_PARAM: dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "fp8": 1.0,
    "int8": 1.0,
    "q8": 1.0,
    "q4": 0.5,
    "int4": 0.5,
}

#: Dtype assumed for an entry that does not declare one. Every open-weight
#: checkpoint published in the last three years ships bf16/fp16 unless it says
#: otherwise, and the two cost the same per parameter.
_DEFAULT_DTYPE = "bf16"

#: airllm's ``compression`` argument mapped onto the stored-dtype key above.
_COMPRESSION_DTYPE: dict[str, str] = {"4bit": "q4", "8bit": "q8"}

#: Decoder depth at known parameter counts, for an entry that does not declare
#: ``layers``. Depth grows roughly logarithmically with width across every
#: dense open-weight family (Llama, Qwen, Gemma, Mistral), so interpolating
#: between measured points beats any closed-form guess. Figures are the
#: published ``num_hidden_layers`` of the reference checkpoint at each size.
_DEPTH_BY_SIZE_B: tuple[tuple[float, int], ...] = (
    (1.0, 16),
    (3.0, 28),
    (7.0, 32),
    (8.0, 32),
    (13.0, 40),
    (14.0, 48),
    (27.0, 62),
    (32.0, 64),
    (70.0, 80),
    (120.0, 96),
    (405.0, 126),
)

#: How much larger the biggest shard is than the average one. Shards are not
#: equal: the token-embedding matrix (and the untied output head beside it) is
#: ``vocab x hidden``, and a modern 128k-152k vocabulary makes that bigger than
#: one decoder layer. Checked against Llama-3-70B — 80 layers, 1.76 GB average
#: shard, 2.1 GB embedding shard — and against Qwen3-32B, both near 1.2.
_PEAK_SHARD_RATIO = 1.25

#: Shards resident at once. With prefetching, the next shard is read while the
#: current one computes, which is where airllm's ~10% speed-up comes from and
#: what makes two shards resident rather than one. Without it, one.
_RESIDENT_SHARDS_PREFETCH = 2.0
_RESIDENT_SHARDS_SERIAL = 1.0

#: Flat allowance (GB) for activations and the runtime's own buffers. Small and
#: constant on purpose: those ARE bounded by one layer's working set, which is
#: what makes the whole scheme fit.
_ACTIVATION_GB = 0.5

#: KV cache, in MB per decoder layer per 1024 tokens of context. The cache is
#: NOT bounded by the layer in flight: autoregressive decoding cannot recompute
#: earlier keys and values, so every layer's slice stays resident for the whole
#: generation, and on a deep model it ends up the second-largest term after the
#: shard itself.
#:
#: 4 MB/layer/1k is the grouped-query-attention arithmetic of every current
#: open-weight family: 2 tensors (K and V) x 1024 KV channels (8 KV heads x 128
#: head dim) x 1024 tokens x 2 bytes = 4 MiB. Checked both ways — Llama-3-70B
#: at 4k context measures 1.25 GB against its true 1.31 GB, and an 8B model
#: 0.5 GB against its 0.54 GB.
_KV_MB_PER_LAYER_PER_K = 4.0

#: Context length (in units of 1024 tokens) the KV term is sized for when the
#: caller names none. 4k is the figure the catalog's own ``ram_gb`` estimates
#: assume (see catalog.estimate_ram), so the two backends' footprints stay
#: comparable rather than being quoted at different context lengths.
#:
#: It is ALSO what :func:`load` configures on the runtime, which matters more
#: than it looks: airllm's own ``max_seq_len`` default is **512 tokens**, and it
#: truncates rather than failing. Leaving that default in place would have made
#: this package price a 4k context while quietly running a 512-token one — the
#: documentation and the behaviour disagreeing, in the direction where the user
#: loses the end of their prompt without being told. The two numbers are now the
#: same number.
_DEFAULT_CONTEXT_K = 4.0

#: Tokens per unit of :data:`_DEFAULT_CONTEXT_K`.
_TOKENS_PER_K = 1024

#: Fraction of raw disk bandwidth a streaming decode achieves. Every forward
#: pass re-reads the whole checkpoint, so the ceiling is ``read_gbs /
#: checkpoint_gb``; per-shard opens, deserialisation and the un-overlapped tail
#: of each layer's compute pull it under that ceiling. Prefetching recovers
#: most of the gap, which is the difference between the two figures.
_STREAM_EFFICIENCY_PREFETCH = 0.85
_STREAM_EFFICIENCY_SERIAL = 0.70

#: Further derating when the shards are compressed, because quantised weights
#: have to be *dequantised* on the way in and that work is not free.
#:
#: Pinned to upstream's own claim rather than to the arithmetic: 4-bit divides
#: the bytes read by four, and airllm reports a "3x speed up", so three
#: quarters of the byte saving survives the dequantisation. The 8-bit figure is
#: inferred from the same shape — half the bytes, a lighter unpack — and is the
#: one number here with no published anchor behind it.
_COMPRESSION_EFFICIENCY: dict[str, float] = {"4bit": 0.75, "8bit": 0.85}

#: Prompt length past which the prefill pass stops being purely I/O-bound.
#: One pass reads the checkpoint once whatever the prompt length, so a long
#: prompt is close to free in disk terms — the lever this backend offers that
#: no other does. The compute inside each layer, however, scales with the
#: number of tokens in the pass, and somewhere above a few thousand it
#: overtakes the read. Rather than invent a FLOPs model this package has no
#: input for, :func:`generation_time` says so when the prompt crosses this
#: line.
_PREFILL_IO_BOUND_TOKENS = 4096

#: Disk multiplier for the one-off split. airllm decomposes the checkpoint into
#: per-layer shards beside the original, so the cache needs room for both at
#: once; ``delete_original=True`` releases the original afterwards, which is why
#: the steady-state figure is lower than the peak.
_SPLIT_DISK_PEAK = 2.1
_SPLIT_DISK_STEADY = 1.1

#: Floor below which streaming stops being worth proposing even as a batch job.
#: 0.01 tok/s is one token every hundred seconds: a paragraph in three hours, an
#: overnight answer, which IS the trade airllm offers and plenty of people take.
#: Under it, a single sentence costs most of a day and a caller is better served
#: by a smaller model or a cloud call — so the floor reports a blocker rather
#: than offering a technically-correct eternity.
#:
#: Deliberately NOT ``score.COMFORT_TPS`` (15 tok/s), and deliberately not a
#: tenth of it either. Streaming never clears an interactive floor; judging it
#: by one rejects every candidate and hides the capability behind a rule written
#: for a different backend. A floor an order of magnitude too *strict* is the
#: same mistake in miniature: at 0.2 tok/s this gate admitted nothing above an
#: 8B checkpoint, which is to say nothing worth streaming, since an 8B model
#: runs natively at a hundred times the speed.
COMFORT_TPS_STREAMING: float = 0.01

#: Runtimes airllm can stream on, in the order they are preferred when a
#: machine offers more than one.
_RUNTIMES = ("cuda", "rocm", "mlx", "cpu")


def normalize_request(value: object) -> str:
    """
    Normalise a human's streaming request into ``auto``/``always``/``never``.

    Accepts what people actually write in a brief or an environment variable —
    ``yes``, ``1``, ``off``, a real bool, ``None`` — and refuses to guess at
    anything else.

    Parameters
    ----------
    value : object
        Raw value from a brief key, a CLI flag, or :data:`ENV_VAR`. ``None``
        means "did not say" and yields ``auto``.

    Returns
    -------
    str
        One of ``'auto'``, ``'always'``, ``'never'``.

    Raises
    ------
    ValueError
        When the value is neither empty nor a recognised alias. Silently
        reading an unknown word as ``auto`` would turn a typo
        (``airllm: alwyas``) into a quietly disabled feature.

    Examples
    --------
    >>> normalize_request(None)
    'auto'
    >>> normalize_request(True), normalize_request(False)
    ('always', 'never')
    >>> normalize_request(' Always ')
    'always'
    >>> normalize_request("maybe")
    Traceback (most recent call last):
    ValueError: airllm request must be one of auto/always/never, got 'maybe'
    """
    if value is None or value == "":
        return "auto"
    if isinstance(value, bool):
        return "always" if value else "never"
    key = str(value).strip().lower()
    if key in _REQUEST_ALIASES:
        return _REQUEST_ALIASES[key]
    raise ValueError(f"airllm request must be one of auto/always/never, got {value!r}")


def requested(brief_value: object = None, env: dict[str, str] | None = None) -> str:
    """
    Resolve the effective streaming request, brief first, environment second.

    Precedence mirrors every other setting in this package: an explicit value in
    the brief (or on the command line) wins, the environment is the fallback,
    and ``auto`` is the default.

    Parameters
    ----------
    brief_value : object
        The brief's ``airllm:`` key, or a CLI flag's value. ``None`` defers to
        the environment.
    env : dict[str, str] or None
        Environment mapping to read :data:`ENV_VAR` from. None uses
        ``os.environ``; tests pass a dict.

    Returns
    -------
    str
        One of ``'auto'``, ``'always'``, ``'never'``.

    Examples
    --------
    >>> requested(None, env={})
    'auto'
    >>> requested(None, env={'BEST_ENGINE_AIRLLM': 'never'})
    'never'
    >>> requested('always', env={'BEST_ENGINE_AIRLLM': 'never'})
    'always'
    """
    if brief_value is not None and brief_value != "":
        return normalize_request(brief_value)
    source = os.environ if env is None else env
    return normalize_request(source.get(ENV_VAR))


def hf_id(entry: dict[str, Any]) -> str | None:
    """
    The HuggingFace repository a streaming backend would load.

    airllm reads safetensors from the Hub, not GGUF from Ollama's registry, so a
    catalog entry is only streamable when it names a Hub repo. ``hf_id`` is
    preferred; ``vllm_id`` is the same thing under the name this catalog has
    always used for it, and is accepted so no entry has to be edited twice.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.

    Returns
    -------
    str or None
        The repository id, or None when the entry names none.

    Examples
    --------
    >>> hf_id({"id": "llama3:70b", "vllm_id": "meta-llama/Llama-3.3-70B-Instruct"})
    'meta-llama/Llama-3.3-70B-Instruct'
    >>> hf_id({"id": "llama3:70b", "hf_id": "a/b", "vllm_id": "c/d"})
    'a/b'
    >>> hf_id({"id": "gemma3:12b"}) is None
    True
    """
    for key in ("hf_id", "vllm_id"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return None


def layer_count(entry: dict[str, Any]) -> tuple[int | None, bool]:
    """
    Decoder depth of a catalog entry, and whether it had to be estimated.

    Depth is the divisor of the whole footprint model, so where it comes from
    matters as much as its value. A declared ``layers`` is used as given; a
    dense model without one is interpolated from :data:`_DEPTH_BY_SIZE_B`; a
    **mixture-of-experts** model without one is refused, because MoE breaks the
    depth-versus-size relation outright (DeepSeek-V3 is 671B across 61 layers,
    where the dense trend would predict well over 120) and an interpolated
    guess there would be wrong by a factor of two in the direction that
    over-promises.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; reads ``layers``, ``size_b`` and ``moe``.

    Returns
    -------
    tuple[int | None, bool]
        ``(layers, estimated)``. ``layers`` is None when depth is unknowable
        from the entry; ``estimated`` is True when the figure was interpolated
        rather than declared.

    Examples
    --------
    >>> layer_count({"layers": 80})
    (80, False)
    >>> layer_count({"size_b": 70})
    (80, True)
    >>> layer_count({"size_b": 20})          # between the 14B and 27B points
    (56, True)
    >>> layer_count({"size_b": 671, "moe": True})
    (None, False)
    >>> layer_count({"id": "mystery"})
    (None, False)
    """
    declared = entry.get("layers")
    if declared:
        return int(declared), False

    if entry.get("moe"):
        osh.debug(
            f"{entry.get('id', '?')} is a mixture-of-experts model and declares no "
            "`layers`; depth cannot be interpolated from its parameter count."
        )
        return None, False

    size_b = float(entry.get("size_b", 0) or 0)
    if size_b <= 0:
        return None, False

    points = _DEPTH_BY_SIZE_B
    if size_b <= points[0][0]:
        return points[0][1], True
    if size_b >= points[-1][0]:
        return points[-1][1], True
    for (lo_size, lo_depth), (hi_size, hi_depth) in zip(points, points[1:]):
        if lo_size <= size_b <= hi_size:
            # Interpolate in log(size): depth tracks width, and width tracks the
            # logarithm of the parameter count across every family in the table.
            span = math.log(hi_size) - math.log(lo_size)
            position = 0.0 if span <= 0 else (math.log(size_b) - math.log(lo_size)) / span
            return int(round(lo_depth + position * (hi_depth - lo_depth))), True
    return None, False


def bytes_per_param(entry: dict[str, Any], compression: str | None = None) -> float:
    """
    Bytes each parameter occupies on disk for a streaming load.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; reads ``dtype`` (default bf16).
    compression : {'4bit', '8bit', None}
        airllm's block-wise weight compression. When given it REPLACES the
        checkpoint dtype: the shards airllm writes are the quantised ones, and
        they are what gets read per token.

    Returns
    -------
    float
        Bytes per parameter.

    Examples
    --------
    >>> bytes_per_param({})
    2.0
    >>> bytes_per_param({"dtype": "fp8"})
    1.0
    >>> bytes_per_param({"dtype": "bf16"}, compression="4bit")
    0.5
    >>> bytes_per_param({"dtype": "nonsense"})
    2.0
    """
    if compression:
        key = _COMPRESSION_DTYPE.get(str(compression).strip().lower())
        if key:
            return _BYTES_PER_PARAM[key]
        osh.warning(f"Unknown airllm compression {compression!r}; sizing at the checkpoint dtype.")
    dtype = str(entry.get("dtype") or _DEFAULT_DTYPE).strip().lower()
    if dtype not in _BYTES_PER_PARAM:
        osh.debug(f"Unknown dtype {dtype!r} on {entry.get('id', '?')}; assuming {_DEFAULT_DTYPE}.")
        dtype = _DEFAULT_DTYPE
    return _BYTES_PER_PARAM[dtype]


def checkpoint_gb(entry: dict[str, Any], compression: str | None = None) -> float:
    """
    Size of the whole checkpoint a streaming backend reads per token (GB).

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; needs ``size_b``.
    compression : {'4bit', '8bit', None}
        See :func:`bytes_per_param`.

    Returns
    -------
    float
        Checkpoint size in GB, or ``inf`` when the entry carries no parameter
        count. Infinity, not zero: an unsized entry must never read as "free"
        and win every comparison, the defect this package hunts by name.

    Examples
    --------
    >>> checkpoint_gb({"size_b": 70})
    140.0
    >>> checkpoint_gb({"size_b": 70}, compression="4bit")
    35.0
    >>> checkpoint_gb({"id": "unsized"})
    inf
    """
    size_b = float(entry.get("size_b", 0) or 0)
    if size_b <= 0:
        return math.inf
    return round(size_b * bytes_per_param(entry, compression), 3)


def kv_cache_gb(layers: int | None, context_k: float = _DEFAULT_CONTEXT_K) -> float:
    """
    KV-cache size (GB) for a streamed decode at a given context length.

    Parameters
    ----------
    layers : int or None
        Decoder depth. None yields 0.0 — an unknown depth is reported as an
        unsized footprint upstream, so adding a guessed cache here would only
        obscure that.
    context_k : float
        Context length in units of 1024 tokens.

    Returns
    -------
    float
        GB of KV cache.

    Examples
    --------
    >>> kv_cache_gb(80)              # a 70B at 4k context
    1.25
    >>> kv_cache_gb(32)
    0.5
    >>> kv_cache_gb(80, context_k=32)
    10.0
    >>> kv_cache_gb(None)
    0.0
    """
    if not layers:
        return 0.0
    return round(layers * _KV_MB_PER_LAYER_PER_K * context_k / 1024.0, 3)


def footprint_gb(
    entry: dict[str, Any],
    compression: str | None = None,
    prefetching: bool = True,
    context_k: float = _DEFAULT_CONTEXT_K,
    batch: int = 1,
) -> float:
    """
    Resident memory (GB) a model needs when its layers are streamed.

    The whole point of the backend, and the one number that decides whether a
    machine can run a model it could never load. Derivation:

    1. A checkpoint of ``size_b`` parameters at :func:`bytes_per_param` bytes
       each, split across :func:`layer_count` shards, gives an **average shard**
       of ``checkpoint / layers``.
    2. The **biggest** shard is the embedding/output matrix rather than a
       decoder layer, about :data:`_PEAK_SHARD_RATIO` times the average on a
       modern large-vocabulary model, and peak memory follows the biggest.
    3. With prefetching, **two** shards are resident (the one computing and the
       one arriving); without it, one.
    4. Plus the **KV cache**, which streaming does not shrink: every layer's
       keys and values stay resident for the whole generation (see
       :func:`kv_cache_gb`), so this term grows with context and with depth,
       and on a deep model it is the second-largest one.
    5. Plus :data:`_ACTIVATION_GB` for activations and runtime buffers, which
       *are* bounded by one layer.

    Checked against airllm's published figures, and the check is worth stating
    precisely, because the headline "70B on a 4 GB GPU" is true at a context
    length nobody mentions. A Llama-3-70B comes to 3.0 GB serially at a 1k
    context — which is the demo, and it fits a 4 GB card — 3.9 GB serially at
    4k, and 6.1 GB at 4k with prefetching on. The weights are the same in all
    three; what moves is the cache that is not streamed. So the useful way to
    read this function is backwards: a card of a given size buys a context
    length, and :func:`plan` is where that shows up as a verdict.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; needs ``size_b``, and ``layers`` when it is a MoE model.
    compression : {'4bit', '8bit', None}
        airllm's block-wise weight compression, which shrinks every shard.
    prefetching : bool
        Whether airllm's prefetch is on (its default). Off halves the resident
        shard count at some cost in speed, and is the knob that gets a 70B model
        onto a 4 GB card.
    context_k : float
        Context length in units of 1024 tokens, for the KV term. Long contexts
        are expensive under streaming in a way they are not elsewhere: the cache
        is the one thing that does not get streamed.
    batch : int
        Sequences generated together. Multiplies the KV term, and only it —
        which is exactly the trade :func:`generation_time` describes from the
        other side: a batch of 8 answers arrives 8x sooner and costs 8 KV
        caches.

    Returns
    -------
    float
        Resident GB, or ``inf`` when the entry cannot be sized.

    Examples
    --------
    >>> footprint_gb({"size_b": 70, "layers": 80})
    6.1
    >>> footprint_gb({"size_b": 70, "layers": 80}, prefetching=False)
    3.9
    >>> footprint_gb({"size_b": 70, "layers": 80}, compression="4bit")
    2.8
    >>> footprint_gb({"size_b": 32, "layers": 64})
    4.0
    >>> # A 32k context costs more than the weights do.
    >>> footprint_gb({"size_b": 70, "layers": 80}, context_k=32)
    14.9
    >>> # Eight answers at once: eight KV caches, one set of shards.
    >>> footprint_gb({"size_b": 70, "layers": 80}, batch=8)
    14.9
    >>> footprint_gb({"size_b": 671, "moe": True})     # depth unknown -> unsized
    inf
    """
    total = checkpoint_gb(entry, compression)
    layers, _ = layer_count(entry)
    if not math.isfinite(total) or not layers:
        return math.inf
    average_shard = total / layers
    resident = _RESIDENT_SHARDS_PREFETCH if prefetching else _RESIDENT_SHARDS_SERIAL
    shards = average_shard * _PEAK_SHARD_RATIO * resident
    # Batching is free in TIME (B sequences ride through one pass) but not in
    # memory: each sequence keeps its own keys and values for every layer. This
    # is the whole cost of the biggest speed lever the backend has, so it is
    # priced here rather than left for the caller to discover at an OOM.
    cache = kv_cache_gb(layers, context_k) * max(1, int(batch))
    # One decimal: resident memory estimated to the 100 MB would be false
    # precision on a figure built from an interpolated layer count.
    return round(shards + cache + _ACTIVATION_GB, 1)


def disk_required_gb(entry: dict[str, Any], compression: str | None = None) -> dict[str, float]:
    """
    Free disk the split needs, at its peak and once settled.

    airllm writes per-layer shards beside the downloaded checkpoint, so the
    cache briefly holds both. This is the constraint that actually bites in
    practice — the memory side of streaming is easy, the disk side is where a
    235B model stops being possible on a 512 GB laptop.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    compression : {'4bit', '8bit', None}
        Compression applied to the shards. The ORIGINAL download is unaffected,
        so a compressed split needs the full checkpoint on disk first either
        way; only the steady-state figure shrinks.

    Returns
    -------
    dict[str, float]
        ``peak_gb`` : during the split, original plus shards.
        ``steady_gb`` : afterwards, shards only (``delete_original=True``).

    Examples
    --------
    >>> disk_required_gb({"size_b": 70})
    {'peak_gb': 294.0, 'steady_gb': 154.0}
    >>> disk_required_gb({"size_b": 70}, compression="4bit")
    {'peak_gb': 178.5, 'steady_gb': 38.5}
    >>> disk_required_gb({"id": "unsized"})
    {'peak_gb': inf, 'steady_gb': inf}
    """
    native = checkpoint_gb(entry, None)
    shards = checkpoint_gb(entry, compression)
    if not math.isfinite(native):
        return {"peak_gb": math.inf, "steady_gb": math.inf}
    # The download is always at the checkpoint's own dtype; compression happens
    # on the way out, so the peak is "original + compressed shards", not twice
    # the compressed size.
    peak = native + shards * (_SPLIT_DISK_PEAK - 1.0)
    return {"peak_gb": round(peak, 1), "steady_gb": round(shards * _SPLIT_DISK_STEADY, 1)}


def stream_efficiency(compression: str | None = None, prefetching: bool = True) -> float:
    """
    Fraction of raw disk bandwidth a streaming pass actually achieves.

    Two independent deratings, multiplied: the I/O one (prefetching overlaps
    the next shard's read with the current layer's compute, or it does not) and
    the dequantisation one (compressed shards are smaller but have to be
    unpacked, which is why airllm reports 3x for 4-bit rather than the 4x the
    byte count alone would suggest).

    Parameters
    ----------
    compression : {'4bit', '8bit', None}
        airllm's block-wise weight compression.
    prefetching : bool
        Whether airllm's prefetch is on.

    Returns
    -------
    float
        Multiplier on ``read_gbs``, between 0 and 1.

    Examples
    --------
    >>> stream_efficiency()
    0.85
    >>> stream_efficiency(prefetching=False)
    0.7
    >>> stream_efficiency("4bit")
    0.637
    >>> # Net of dequantisation, 4-bit is a 3x speed-up, not a 4x one.
    >>> round(4 * stream_efficiency("4bit") / stream_efficiency(), 2)
    3.0
    """
    efficiency = _STREAM_EFFICIENCY_PREFETCH if prefetching else _STREAM_EFFICIENCY_SERIAL
    if compression:
        efficiency *= _COMPRESSION_EFFICIENCY.get(str(compression).strip().lower(), 1.0)
    return round(efficiency, 3)


def seconds_per_pass(
    entry: dict[str, Any],
    read_gbs: float | None,
    compression: str | None = None,
    prefetching: bool = True,
) -> float | None:
    """
    Seconds for ONE forward pass through a streamed model.

    The atom of every timing here, and the reason those timings are not what
    intuition suggests. A streamed forward pass walks the layers in order,
    reading each shard, computing it over *every token in the pass*, then
    freeing it. So a pass costs what reading the checkpoint once costs —
    independent of how many tokens rode through it.

    Every byte is charged to the drive, and that is correct rather than
    conservative. The tempting correction is to credit the operating system's
    page cache with the shards it still holds, so a machine with free memory
    pays memory speed for part of the pass. It does not work, and the reason is
    the access pattern: a pass reads layers 1..N in order and the next pass
    starts again at layer 1, which the tail of the previous pass evicted. A
    cyclic scan over a working set larger than the cache is the textbook
    pathology for least-recently-used eviction, and Linux's active/inactive
    approximation does not rescue it either -- nothing is touched twice within
    a pass, so nothing is ever promoted to the active list. The expected hit
    rate is near zero, not ``free_memory / checkpoint``.

    And the regime where it *would* help is the regime where this backend is
    the wrong choice: memory that can cache the whole checkpoint is memory that
    can hold it, where a memory-mapped resident engine wins outright. So there
    is no mixing term here on purpose, and :func:`decide` is what steers a
    caller with that much memory back to a native backend.

    Two consequences worth knowing before choosing this backend:

    - **One generated token costs one pass.** Decoding is autoregressive, so
      token N+1 needs its own walk through every layer. That is where the
      seconds-per-token figure comes from.
    - **The prompt is nearly free.** A 2000-token prompt is processed in the
      same single pass as a 10-token one, because its tokens ride through each
      layer together. No other backend has that property: under Ollama or vLLM
      a long prompt is real prefill work. It makes streaming comparatively good
      at *large prompt, short answer* jobs — classification, extraction,
      judging, a one-line verdict over a long document — and comparatively
      terrible at long answers.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    read_gbs : float or None
        Sequential disk read bandwidth in GB/s. None returns None.
    compression : {'4bit', '8bit', None}
        airllm's block-wise weight compression.
    prefetching : bool
        Whether airllm's prefetch is on.

    Returns
    -------
    float or None
        Seconds per pass, or None when the drive or the model cannot be sized.

    Examples
    --------
    >>> seconds_per_pass({"size_b": 70}, 4.0)
    41.176
    >>> seconds_per_pass({"size_b": 70}, 4.0, compression="4bit")
    13.736
    >>> seconds_per_pass({"size_b": 70}, None) is None
    True
    """
    if not read_gbs or read_gbs <= 0:
        return None
    total = checkpoint_gb(entry, compression)
    if not math.isfinite(total) or total <= 0:
        return None
    return round(total / read_gbs / stream_efficiency(compression, prefetching), 3)


def generation_time(
    entry: dict[str, Any],
    read_gbs: float | None,
    *,
    new_tokens: int = 128,
    prompt_tokens: int = 0,
    batch: int = 1,
    compression: str | None = None,
    prefetching: bool = True,
) -> dict[str, Any] | None:
    """
    How long one streamed generation actually takes, end to end.

    "What is this model's speed under airllm" has three different answers, and
    quoting the wrong one is how a batch job gets planned as an interactive one:

    - ``decode_tps`` — the steady-state rate, one token per pass. The headline
      number, and the pessimistic one.
    - ``time_to_first_token_s`` — one pass, prompt included. Under streaming
      this is **the same as the time for any other token**, which is unusual:
      on every other backend a long prompt makes the first token the expensive
      one.
    - ``effective_tps`` — tokens actually delivered per second of wall clock,
      counting the whole batch. This is the one that decides whether a job
      finishes overnight, and the only one a caller can improve without
      changing the model.

    And the lever that falls out of the pass model: because a pass costs the
    same whatever rides through it, **a batch of B prompts costs one pass, not
    B passes**. B independent questions answered together go B times faster per
    answer. 4-bit compression gives ~3x; a batch of 8 gives 8x. For a real
    batch job that is the larger of the two, and it costs nothing but the KV
    cache (which :func:`footprint_gb` sizes with the same argument).

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    read_gbs : float or None
        Sequential disk read bandwidth in GB/s.
    new_tokens : int
        Tokens to generate per sequence. The first comes out of the prefill
        pass, so N tokens cost N passes.
    prompt_tokens : int
        Prompt length. Costs no extra pass; reported so a caller can see that
        it does not, and warned about past :data:`_PREFILL_IO_BOUND_TOKENS`,
        where per-layer compute starts to overtake the read.
    batch : int
        Independent sequences generated together. Multiplies the tokens
        delivered per pass.
    compression : {'4bit', '8bit', None}
        airllm's block-wise weight compression.
    prefetching : bool
        Whether airllm's prefetch is on.

    Returns
    -------
    dict[str, Any] or None
        ``seconds_per_pass``, ``passes``, ``time_to_first_token_s``,
        ``total_seconds``, ``decode_tps``, ``effective_tps``,
        ``tokens_delivered``, ``prompt_tokens``, ``prompt_is_free`` and
        ``batch``. None when the drive or the model cannot be sized.

    Examples
    --------
    >>> t = generation_time({"size_b": 70}, 4.0, new_tokens=100)
    >>> t["seconds_per_pass"], t["passes"], t["decode_tps"]
    (41.176, 100, 0.024)
    >>> round(t["total_seconds"] / 3600, 2)        # hours for 100 tokens
    1.14
    >>> t["time_to_first_token_s"] == t["seconds_per_pass"]
    True
    >>> # A 2000-token prompt adds nothing: the pass reads the same bytes.
    >>> long_prompt = generation_time({"size_b": 70}, 4.0, new_tokens=100,
    ...                               prompt_tokens=2000)
    >>> long_prompt["total_seconds"] == t["total_seconds"]
    True
    >>> # Eight questions at once cost the same passes and deliver eight times
    >>> # the tokens.
    >>> batched = generation_time({"size_b": 70}, 4.0, new_tokens=100, batch=8)
    >>> batched["total_seconds"] == t["total_seconds"]
    True
    >>> round(batched["effective_tps"] / t["effective_tps"], 1)
    8.1
    >>> generation_time({"size_b": 70}, None) is None
    True
    """
    per_pass = seconds_per_pass(entry, read_gbs, compression, prefetching)
    if per_pass is None:
        return None

    new_tokens = max(1, int(new_tokens))
    batch = max(1, int(batch))
    # N tokens cost N passes: the prefill pass emits the first one, and every
    # token after it needs its own walk through every layer.
    passes = new_tokens
    total = per_pass * passes
    delivered = new_tokens * batch
    prompt_is_free = prompt_tokens <= _PREFILL_IO_BOUND_TOKENS
    if not prompt_is_free:
        osh.warning(
            f"A {prompt_tokens}-token prompt is past the point where one streamed "
            f"pass stays bound by the disk ({_PREFILL_IO_BOUND_TOKENS} tokens): the "
            "per-layer compute starts to matter, so the first pass takes longer than "
            "reported here. The decode figures are unaffected."
        )
    return {
        "seconds_per_pass": per_pass,
        "passes": passes,
        "time_to_first_token_s": per_pass,
        "total_seconds": round(total, 1),
        "decode_tps": round(1.0 / per_pass, 3),
        "effective_tps": round(delivered / total, 3),
        "tokens_delivered": delivered,
        "prompt_tokens": prompt_tokens,
        "prompt_is_free": prompt_is_free,
        "batch": batch,
    }


def human_duration(seconds: float | None) -> str:
    """
    Render a duration the way a person would say it.

    Streaming timings span six orders of magnitude — a second, a minute, an
    afternoon, a week — and "20361.6 s" communicates none of them.

    Parameters
    ----------
    seconds : float or None
        Duration in seconds.

    Returns
    -------
    str
        A short human reading, or ``'?'`` when the duration is unknown.

    Examples
    --------
    >>> human_duration(0.4), human_duration(42)
    ('0.4 s', '42 s')
    >>> human_duration(185), human_duration(7200)
    ('3 min', '2.0 h')
    >>> human_duration(200000), human_duration(None)
    ('2.3 days', '?')
    """
    if seconds is None:
        return "?"
    if seconds < 1:
        return f"{seconds:.1f} s"
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def estimated_tokens_per_second(
    entry: dict[str, Any],
    read_gbs: float | None,
    compression: str | None = None,
    prefetching: bool = True,
) -> float | None:
    """
    Estimate streaming decode throughput (tokens/s) from DISK bandwidth.

    Under every other backend, decode is memory-bandwidth bound. Under
    streaming it is **disk** bound, and by a much harder bound: the weights do
    not stay anywhere, so each token costs one full forward pass over the
    checkpoint — see :func:`seconds_per_pass`, of which this is the reciprocal.

    This is the steady-state decode rate for ONE sequence, which is the
    pessimistic reading of "how fast is it". :func:`generation_time` gives the
    other two readings: the time to the first token (one pass, and a long
    prompt barely changes it) and the effective rate for a batch (B sequences
    ride through each pass together, so B answers arrive in the time of one).

    This is also why the honest unit is often *seconds per token* — see
    :func:`seconds_per_token`. A 70B model at bf16 on a 4 GB/s NVMe drive is
    about 0.024 tok/s: forty seconds a token. 4-bit compression makes it three
    times faster — not four, because the weights have to be dequantised — and
    it is still a batch job.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    read_gbs : float or None
        Sequential read bandwidth in GB/s, from
        :func:`detect.disk_profile`. None means "not estimated" and returns
        None rather than a fabricated rate.
    compression : {'4bit', '8bit', None}
        Compression of the shards on disk. Divides the bytes read per pass, net
        of dequantisation (see :func:`stream_efficiency`): ~3x at 4-bit, the
        biggest lever available on a single sequence. Batching is a bigger one
        still, and orthogonal to it.
    prefetching : bool
        Whether reads overlap compute.

    Returns
    -------
    float or None
        Tokens per second, rounded to three decimals, or None when bandwidth or
        model size is unknown.

    Examples
    --------
    >>> estimated_tokens_per_second({"size_b": 70}, 4.0)
    0.024
    >>> estimated_tokens_per_second({"size_b": 70}, 4.0, compression="4bit")
    0.073
    >>> estimated_tokens_per_second({"size_b": 7}, 4.0)
    0.243
    >>> estimated_tokens_per_second({"size_b": 70}, None) is None
    True
    >>> estimated_tokens_per_second({"id": "unsized"}, 4.0) is None
    True
    """
    seconds = seconds_per_pass(entry, read_gbs, compression, prefetching)
    if seconds is None:
        return None
    return round(1.0 / seconds, 3)


def seconds_per_token(tps: float | None) -> float | None:
    """
    Invert a streaming rate into the unit humans can picture.

    "0.024 tokens per second" reads as a small number; "41 seconds per token"
    reads as what it is. Every user-facing surface shows both.

    Parameters
    ----------
    tps : float or None
        Tokens per second, typically from :func:`estimated_tokens_per_second`.

    Returns
    -------
    float or None
        Seconds per token rounded to one decimal, or None when the rate is
        unknown or non-positive.

    Examples
    --------
    >>> seconds_per_token(0.024)
    41.7
    >>> seconds_per_token(2.0)
    0.5
    >>> seconds_per_token(None) is None
    True
    >>> seconds_per_token(0.0) is None
    True
    """
    if not tps or tps <= 0:
        return None
    return round(1.0 / tps, 1)


def available() -> bool:
    """
    Whether the airllm runtime is importable in this interpreter.

    Normally True: airllm is a core dependency, not an extra. It is still
    checked rather than assumed, because a dependency being *declared* and a
    module being *importable* are different claims — a stripped container, a
    failed wheel build or a partially-installed environment separates them, and
    finding that out at resolution beats finding it out inside a job.

    Returns
    -------
    bool
        True when ``import airllm`` succeeds.

    Examples
    --------
    >>> available() in (True, False)
    True
    """
    from importlib.util import find_spec

    try:
        return find_spec(PACKAGE) is not None
    except (ImportError, ValueError):  # a broken/partial install is "not available"
        return False


def runtime(compute: dict[str, Any] | None = None, allow_cpu: bool = False) -> str | None:
    """
    Which streaming runtime this machine offers, if any.

    airllm streams on CUDA (its primary path), on Apple Silicon through MLX, and
    on CPU experimentally. ROCm rides the same torch path as CUDA and is treated
    as capable; the figure that matters there is disk bandwidth anyway, which is
    vendor-independent.

    Parameters
    ----------
    compute : dict or None
        Output of :func:`detect.compute_profile`. None probes it.
    allow_cpu : bool
        Whether to count a CPU-only machine as capable. False by default:
        airllm's CPU path is experimental and only works for unsharded models,
        so proposing it automatically would promise something that often does
        not load. A human can still ask for it.

    Returns
    -------
    str or None
        ``'cuda'``, ``'rocm'``, ``'mlx'``, ``'cpu'``, or None when this machine
        has no runtime streaming can use.

    Examples
    --------
    >>> runtime({"accelerator": "gpu-cuda"})
    'cuda'
    >>> runtime({"accelerator": "gpu-metal"})
    'mlx'
    >>> runtime({"accelerator": "cpu"}) is None
    True
    >>> runtime({"accelerator": "cpu"}, allow_cpu=True)
    'cpu'
    """
    if compute is None:
        from . import detect as _detect

        compute = _detect.compute_profile()
    accelerator = str(compute.get("accelerator") or "")
    if accelerator == "gpu-cuda":
        return "cuda"
    if accelerator == "gpu-rocm":
        return "rocm"
    if accelerator == "gpu-metal":
        return "mlx"
    return "cpu" if allow_cpu else None


def budget_gb(
    hw: dict[str, float | None] | None = None, load: dict[str, Any] | None = None
) -> float:
    """
    Memory budget (GB) a streamed model may occupy on this machine.

    Deliberately the accelerator's whole usable pool
    (:func:`score.usable_pool_gb`) rather than the headroom-reduced
    :func:`score.effective_budget` every other backend sizes against. Two
    reasons, and they are the same reason twice: what the headroom reserves is
    already accounted for here. It exists to leave room for KV-cache growth —
    which :func:`footprint_gb` now sizes explicitly, per layer, at a named
    context length — and for the OS and the caller's own workload, which the
    Metal cap (66-75%) and the VRAM fraction (92%) inside ``usable_pool_gb``
    already hold back. Applying it a second time reserves the same gigabytes
    twice and rejects exactly the models this backend exists to run: a 70B needs
    about 4 GB resident, which clears a 4 GB card's real budget and fails a
    doubly-discounted one.

    Parameters
    ----------
    hw : dict or None
        Output of :func:`detect.available_memory`. None probes it.
    load : dict or None
        Live load from :func:`detect.server_load`. When given, the budget is
        additionally capped at the RAM actually free right now — a shard still
        has to fit beside whatever else is running.

    Returns
    -------
    float
        Budget in GB.

    Examples
    --------
    >>> budget_gb({'unified_gb': 8.0, 'vram_gb': None, 'ram_gb': 8.0})
    5.28
    >>> budget_gb({'unified_gb': None, 'vram_gb': 4.0, 'ram_gb': 32.0})
    3.68
    >>> budget_gb({'unified_gb': 96.0, 'vram_gb': None, 'ram_gb': 96.0},
    ...           load={'available_ram_gb': 12.0})
    12.0
    """
    from .score import usable_pool_gb

    if hw is None:
        from . import detect as _detect

        hw = _detect.available_memory()
    budget = usable_pool_gb(hw)
    live = (load or {}).get("available_ram_gb")
    if live is not None:
        budget = min(budget, float(live))
    return round(budget, 3)


def plan(
    entry: dict[str, Any],
    *,
    budget_gb: float | None = None,
    disk: dict[str, Any] | None = None,
    compression: str | None = None,
    prefetching: bool = True,
    context_k: float = _DEFAULT_CONTEXT_K,
    batch: int = 1,
    new_tokens: int = 300,
) -> dict[str, Any]:
    """
    Everything known about streaming ONE model on this machine.

    One call per candidate, so the caller never has to keep the footprint, the
    disk requirement and the throughput estimate in step by hand.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    budget_gb : float or None
        The memory budget from :func:`score.effective_budget`. None skips the
        fit verdict.
    disk : dict or None
        Output of :func:`detect.disk_profile`. None probes it (table lookup, no
        measurement).
    compression : {'4bit', '8bit', None}
        airllm's weight compression.
    prefetching : bool
        Whether airllm's prefetch is on.
    context_k : float
        Context length in units of 1024 tokens, for the KV term.
    batch : int
        Sequences generated together: multiplies the KV term and the tokens
        delivered per pass (see :func:`generation_time`).
    new_tokens : int
        Answer length ``answer_seconds`` is reported for. 300 tokens is about a
        long paragraph — short enough to be a realistic streamed job, long
        enough that the wait is the real one.

    Returns
    -------
    dict[str, Any]
        ``model`` (HuggingFace id or the raw tag), ``resident_gb``,
        ``checkpoint_gb``, ``layers``/``layers_estimated``, ``disk``
        (:func:`disk_required_gb`), ``disk_fits``, ``est_tokens_per_s``,
        ``seconds_per_token``, ``seconds_per_pass``,
        ``time_to_first_token_s``, ``answer_seconds`` / ``answer_human`` for
        ``new_tokens``, ``effective_tps``, ``fits``, ``usable`` (fits memory
        AND disk AND clears :data:`COMFORT_TPS_STREAMING`), and ``blockers``:
        the plain-text reasons it would not work here.

    Examples
    --------
    >>> p = plan(
    ...     {"id": "llama3.3:70b", "size_b": 70, "layers": 80,
    ...      "vllm_id": "meta-llama/Llama-3.3-70B-Instruct"},
    ...     budget_gb=11.0,
    ...     disk={"read_gbs": 4.0, "free_gb": 900.0, "basis": "declared"},
    ... )
    >>> p["resident_gb"], p["fits"], p["est_tokens_per_s"]
    (6.1, True, 0.024)
    >>> p["answer_human"], p["time_to_first_token_s"]
    ('3.4 h', 41.176)
    >>> p["seconds_per_token"], p["usable"], p["blockers"]
    (41.7, True, [])
    >>> slow = plan({"id": "y", "size_b": 671, "layers": 61, "dtype": "fp8",
    ...              "hf_id": "deepseek-ai/DeepSeek-V3"}, budget_gb=50.0,
    ...             disk={"read_gbs": 4.0, "free_gb": 4000.0})
    >>> slow["usable"], slow["blockers"]
    (False, ['estimated 0.005 tok/s (200.0 s/token) is below the 0.01 tok/s batch floor'])
    >>> tight = plan({"id": "x", "size_b": 70, "layers": 80}, budget_gb=2.0,
    ...              disk={"read_gbs": 4.0, "free_gb": 20.0})
    >>> tight["fits"], tight["disk_fits"]
    (False, False)
    """
    if disk is None:
        from . import detect as _detect

        disk = _detect.disk_profile()

    layers, estimated = layer_count(entry)
    resident = footprint_gb(entry, compression, prefetching, context_k, batch)
    total = checkpoint_gb(entry, compression)
    space = disk_required_gb(entry, compression)
    free_gb = disk.get("free_gb")
    read_gbs = disk.get("read_gbs")
    tps = estimated_tokens_per_second(entry, read_gbs, compression, prefetching)
    timing = generation_time(
        entry,
        read_gbs,
        new_tokens=new_tokens,
        batch=batch,
        compression=compression,
        prefetching=prefetching,
    )

    fits = bool(budget_gb is not None and math.isfinite(resident) and resident <= budget_gb)
    disk_fits = bool(
        free_gb is not None
        and math.isfinite(space["peak_gb"])
        and space["peak_gb"] <= float(free_gb)
    )

    blockers: list[str] = []
    if not math.isfinite(resident):
        blockers.append(
            "the catalog entry carries no parameter count (or no `layers` for a "
            "mixture-of-experts model), so its resident footprint cannot be sized"
        )
    elif budget_gb is not None and not fits:
        blockers.append(
            f"one resident shard needs {resident:.1f} GB, above this machine's "
            f"{budget_gb:.1f} GB budget"
        )
    if free_gb is not None and not disk_fits and math.isfinite(space["peak_gb"]):
        blockers.append(
            f"the split needs {space['peak_gb']:.0f} GB free during the layer split "
            f"({space['steady_gb']:.0f} GB after), and {float(free_gb):.0f} GB is free"
        )
    if tps is None:
        blockers.append("disk read bandwidth is unknown on this machine, so no rate can be given")
    elif tps < COMFORT_TPS_STREAMING:
        spt = seconds_per_token(tps)
        blockers.append(
            f"estimated {tps} tok/s ({spt} s/token) is below the "
            f"{COMFORT_TPS_STREAMING} tok/s batch floor"
        )
    if not hf_id(entry):
        blockers.append(
            "the entry names no HuggingFace repository (`hf_id`/`vllm_id`), and "
            "streaming reads safetensors from the Hub, never a GGUF pull tag"
        )

    return {
        "model": hf_id(entry) or entry.get("id"),
        "catalog_id": entry.get("id"),
        "resident_gb": resident if math.isfinite(resident) else None,
        "checkpoint_gb": total if math.isfinite(total) else None,
        "layers": layers,
        "layers_estimated": estimated,
        "compression": compression,
        "prefetching": prefetching,
        "context_k": context_k,
        "kv_cache_gb": kv_cache_gb(layers, context_k),
        "disk": space,
        "disk_free_gb": free_gb,
        "disk_read_gbs": read_gbs,
        "disk_basis": disk.get("basis"),
        "disk_fits": disk_fits,
        "est_tokens_per_s": tps,
        "seconds_per_token": seconds_per_token(tps),
        # What the caller actually waits for, which a per-token rate does not
        # say on its own: one pass to the first token however long the prompt,
        # then one pass per token after it.
        "seconds_per_pass": (timing or {}).get("seconds_per_pass"),
        "time_to_first_token_s": (timing or {}).get("time_to_first_token_s"),
        "answer_tokens": new_tokens,
        "answer_seconds": (timing or {}).get("total_seconds"),
        "answer_human": human_duration((timing or {}).get("total_seconds")),
        "effective_tps": (timing or {}).get("effective_tps"),
        "batch": batch,
        "fits": fits,
        "usable": bool(fits and disk_fits and tps is not None and tps >= COMFORT_TPS_STREAMING),
        "blockers": blockers,
    }


def decide(
    *,
    request: object = None,
    conventional_resolved: bool = True,
    compute: dict[str, Any] | None = None,
    disk: dict[str, Any] | None = None,
    allow_cpu: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Decide whether to stream layers on this machine, and say why.

    The activation policy, in one place, returning a verdict rather than
    performing it — so the CLI, the HTTP API and :func:`engine.resolve` all ask
    the same question and get the same answer, and so the reasoning is
    inspectable (``best-engine-ai-helper airllm status``) instead of implied.

    The rule:

    - ``never`` → off, unconditionally. The escape hatch.
    - ``always`` → on, provided the machine has a runtime (:func:`runtime`) and
      the package is installed. A human asking for streaming is not second-
      guessed on whether it is wise, only told what it will cost.
    - ``auto`` → on **only** when the conventional backend resolved nothing for
      a kind the caller needs. Streaming is two to three orders of magnitude
      slower than loading a model that fits, so it is the answer to "no model at
      all", never a preference.

    Parameters
    ----------
    request : object
        ``'auto'``/``'always'``/``'never'`` or an alias, from a brief, a flag,
        or :data:`ENV_VAR`. None resolves through :func:`requested`.
    conventional_resolved : bool
        Whether Ollama/vLLM already found a model that fits. True (the default)
        means the automatic trigger does not fire — there is nothing to rescue.
    compute : dict or None
        :func:`detect.compute_profile` output. None probes it.
    disk : dict or None
        :func:`detect.disk_profile` output. None probes it.
    allow_cpu : bool
        Count a CPU-only machine as capable (airllm's CPU path is
        experimental).
    env : dict[str, str] or None
        Environment for :data:`ENV_VAR`; None uses ``os.environ``.

    Returns
    -------
    dict[str, Any]
        ``activate`` : bool — the verdict.
        ``request`` : the normalised request that produced it.
        ``trigger`` : ``'manual'``, ``'fallback'``, ``'disabled'`` or
        ``'not-needed'`` — which branch of the rule fired.
        ``reason`` : one sentence, written for a human.
        ``installed`` / ``runtime`` / ``blockers`` : capability facts, kept even
        when ``activate`` is False so a caller can say what to fix.

    Examples
    --------
    >>> d = decide(request='never', conventional_resolved=False, env={})
    >>> d['activate'], d['trigger']
    (False, 'disabled')
    >>> d = decide(request='auto', conventional_resolved=True,
    ...            compute={'accelerator': 'gpu-cuda'}, disk={'read_gbs': 2.5}, env={})
    >>> d['activate'], d['trigger']
    (False, 'not-needed')
    >>> d = decide(request='auto', conventional_resolved=False,
    ...            compute={'accelerator': 'gpu-cuda'}, disk={'read_gbs': 2.5}, env={})
    >>> d['trigger'], d['runtime']
    ('fallback', 'cuda')
    >>> d = decide(request='always', compute={'accelerator': 'cpu'},
    ...            disk={'read_gbs': 2.5}, env={})
    >>> d['activate'], d['blockers'][0][:34]
    (False, 'this machine offers no runtime air')
    """
    wanted = requested(request, env=env)
    runtime_name = runtime(compute, allow_cpu=allow_cpu)
    installed = available()
    if disk is None:
        from . import detect as _detect

        disk = _detect.disk_profile()

    blockers: list[str] = []
    if runtime_name is None:
        blockers.append(
            "this machine offers no runtime airllm can stream on (a CUDA/ROCm GPU, "
            "or Apple Silicon through MLX); its CPU path is experimental and must "
            "be asked for explicitly"
        )
    if not installed:
        blockers.append(
            f"the {PACKAGE} runtime cannot be imported, though it is a dependency of "
            f"this package — the install looks incomplete: {INSTALL_HINT}"
        )
    if not disk.get("read_gbs"):
        blockers.append(
            "disk read bandwidth is unknown here, and streaming throughput is "
            "bounded by it — run `airllm status --measure` to measure it"
        )

    if wanted == "never":
        return {
            "activate": False,
            "request": wanted,
            "trigger": "disabled",
            "reason": f"Layer streaming is switched off ({ENV_VAR}=never or airllm: never).",
            "installed": installed,
            "runtime": runtime_name,
            "disk": disk,
            "blockers": blockers,
        }

    if wanted == "auto" and conventional_resolved:
        return {
            "activate": False,
            "request": wanted,
            "trigger": "not-needed",
            "reason": (
                "A model already fits this machine's memory, so streaming its layers "
                "off disk would trade two to three orders of magnitude of speed for "
                "nothing. Ask for it explicitly (--backend airllm) to override."
            ),
            "installed": installed,
            "runtime": runtime_name,
            "disk": disk,
            "blockers": blockers,
        }

    trigger = "manual" if wanted == "always" else "fallback"
    # A blocker is fatal to activation but is still reported on the way out: the
    # caller's next move is usually to fix one, and a bare False never says which.
    fatal = [b for b in blockers if "bandwidth is unknown" not in b]
    if fatal:
        return {
            "activate": False,
            "request": wanted,
            "trigger": trigger,
            "reason": "Layer streaming cannot run here: " + fatal[0],
            "installed": installed,
            "runtime": runtime_name,
            "disk": disk,
            "blockers": blockers,
        }

    reason = (
        "No model fits this machine's memory budget, so layer streaming is the "
        "difference between a model and none — expect seconds per token, not tokens "
        "per second."
        if trigger == "fallback"
        else f"Layer streaming was requested explicitly and runs here on {runtime_name}."
    )
    return {
        "activate": True,
        "request": wanted,
        "trigger": trigger,
        "reason": reason,
        "installed": installed,
        "runtime": runtime_name,
        "disk": disk,
        "blockers": blockers,
    }


def rank(
    entries: list[dict[str, Any]],
    *,
    budget_gb: float,
    disk: dict[str, Any] | None = None,
    compression: str | None = None,
    prefetching: bool = True,
    kind: Literal["llm", "vlm"] | None = None,
    batch: int = 1,
    new_tokens: int = 300,
) -> list[dict[str, Any]]:
    """
    Rank catalog entries by what streaming unlocks on this machine.

    Streaming inverts the usual ranking. With memory no longer the binding
    constraint, leanness stops being a virtue: what is wanted is the most
    capable model whose shards still fit and whose rate clears the batch floor,
    with parameter count deciding only where no benchmark does. The trade being
    made here is explicitly "slower for better", so "better" is the sort key —
    see :func:`pick` for why that is not the same as "biggest".

    Parameters
    ----------
    entries : list of dict
        Catalog entries.
    budget_gb : float
        Memory budget from :func:`score.effective_budget`.
    disk : dict or None
        :func:`detect.disk_profile` output. None probes it.
    compression : {'4bit', '8bit', None}
        airllm's weight compression.
    prefetching : bool
        Whether airllm's prefetch is on. When it is and a candidate does not
        fit, that candidate is re-planned WITHOUT it before being rejected —
        see the comment in the body.
    kind : {'llm', 'vlm', None}
        Restrict to one kind. A VLM satisfies an ``llm`` request (vision implies
        text), the same rule the rest of the catalog follows.
    batch : int
        Sequences generated together, passed to :func:`plan`.
    new_tokens : int
        Answer length each plan's ``answer_seconds`` is for.

    Returns
    -------
    list[dict[str, Any]]
        :func:`plan` dicts, usable ones first and most capable first within
        that, each carrying the entry's ``size_b`` and benchmark ``score`` for
        display.

    Examples
    --------
    >>> rows = [
    ...     {"id": "a", "kind": "llm", "size_b": 70, "layers": 80, "hf_id": "x/a"},
    ...     {"id": "b", "kind": "llm", "size_b": 7, "layers": 32, "hf_id": "x/b"},
    ... ]
    >>> ranked = rank(rows, budget_gb=11.0,
    ...               disk={"read_gbs": 4.0, "free_gb": 900.0})
    >>> [(r["catalog_id"], r["usable"]) for r in ranked]
    [('a', True), ('b', True)]
    >>> # Tighten the disk and the 70B stops being an option at all.
    >>> [(r["catalog_id"], r["usable"]) for r in
    ...  rank(rows, budget_gb=11.0, disk={"read_gbs": 4.0, "free_gb": 100.0})]
    [('b', True), ('a', False)]
    """
    if disk is None:
        from . import detect as _detect

        disk = _detect.disk_profile()

    pool = entries
    if kind == "vlm":
        pool = [e for e in entries if e.get("kind") == "vlm"]
    elif kind == "llm":
        pool = [e for e in entries if e.get("kind") in ("llm", "vlm")]

    plans: list[dict[str, Any]] = []
    for entry in pool:
        row = plan(
            entry,
            budget_gb=budget_gb,
            disk=disk,
            compression=compression,
            prefetching=prefetching,
            batch=batch,
            new_tokens=new_tokens,
        )
        if prefetching and not row["fits"]:
            # Prefetching keeps two shards resident to overlap the next read
            # with the current layer's compute. Turning it off halves that term
            # and costs ~15% of an already slow decode — a trade worth making
            # when it is the difference between running the model and not, and
            # the single knob behind airllm's "70B on a 4 GB card". Only tried
            # when the prefetched plan failed, so nothing is slowed down for a
            # machine that had room anyway.
            serial = plan(
                entry,
                budget_gb=budget_gb,
                disk=disk,
                compression=compression,
                prefetching=False,
                batch=batch,
                new_tokens=new_tokens,
            )
            if serial["fits"]:
                osh.debug(
                    f"{entry.get('id', '?')} does not fit with prefetching "
                    f"({row['resident_gb']} GB) but does without it "
                    f"({serial['resident_gb']} GB); offering the serial plan."
                )
                row = serial
        row["size_b"] = float(entry.get("size_b", 0) or 0)
        row["kind"] = entry.get("kind")
        row["score"] = (entry.get("benchmarks") or {}).get("general")
        plans.append(row)

    # Usable first, then by the same key `pick` uses, so the table's top row
    # and the chosen candidate are never two different models.
    plans.sort(key=lambda r: (r["usable"], r.get("score") or 0.0, r["size_b"]), reverse=True)
    return plans


def pick(plans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Choose one streaming candidate, inverting the usual preference.

    Every other backend in this package picks the LEANEST model within a few
    benchmark points of the best — the anti-greed rule, and the right one when
    a gigabyte of footprint is paid on every run and competes with the caller's
    own workload. Streaming breaks that premise: resident memory is one shard
    whatever the model's size, so leanness buys nothing, and the anti-greed rule
    lands on an 8B model — the one outcome that makes no sense at all, since an
    8B model runs natively a hundred times faster.

    So, among candidates that fit memory AND disk and clear
    :data:`COMFORT_TPS_STREAMING`: the **most capable** one, by benchmark score,
    with parameter count as the tiebreak. Not simply the biggest — that was the
    first rule here and the side-by-side comparison made its error obvious: a
    141B mixture-of-experts scoring 84 beat a dense 72B scoring 87 on size
    alone, while being twice as slow. A candidate that is bigger, slower AND
    weaker is dominated on every axis a caller cares about. Size decides only
    where the benchmark is silent, which is the convention the rest of this
    package follows: an absent score ranks low and is honest, a guessed one
    ranks wrongly and looks authoritative.

    When nothing clears the floor, the **fastest** candidate that still fits,
    because "everything here is too slow" is better answered with the least-slow
    option than with the largest.

    Parameters
    ----------
    plans : list of dict
        :func:`plan` dicts, typically from :func:`rank`.

    Returns
    -------
    dict or None
        The chosen plan, or None when no candidate fits memory and disk.

    Examples
    --------
    >>> disk = {"read_gbs": 4.0, "free_gb": 4000.0}
    >>> rows = [{"id": "s", "size_b": 8, "layers": 32, "hf_id": "x/s"},
    ...         {"id": "m", "size_b": 70, "layers": 80, "hf_id": "x/m"},
    ...         {"id": "xl", "size_b": 671, "layers": 61, "dtype": "fp8",
    ...          "hf_id": "x/xl"}]
    >>> plans = rank(rows, budget_gb=40.0, disk=disk)
    >>> pick(plans)["catalog_id"]          # unscored: size is all there is
    'm'
    >>> # With scores on the table, capability wins over sheer size — here the
    >>> # smaller model is better AND faster, so bigger-but-weaker is dominated.
    >>> scored = [{**rows[1], "benchmarks": {"general": 84}},
    ...           {**rows[0], "benchmarks": {"general": 87}}]
    >>> pick(rank(scored, budget_gb=40.0, disk=disk))["catalog_id"]
    's'
    >>> # Nothing clears the floor on a slow drive: take the least-slow.
    >>> slow = rank(rows, budget_gb=40.0, disk={"read_gbs": 0.12, "free_gb": 4000.0})
    >>> pick(slow)["catalog_id"]
    's'
    >>> pick([]) is None
    True
    """
    eligible = [p for p in plans if p["fits"] and p["disk_fits"]]
    if not eligible:
        return None
    usable = [p for p in eligible if p["usable"]]
    if usable:
        return max(usable, key=lambda p: (p.get("score") or 0.0, p["size_b"]))
    fastest = max(eligible, key=lambda p: p["est_tokens_per_s"] or 0.0)
    osh.warning(
        "No streaming candidate clears the "
        f"{COMFORT_TPS_STREAMING} tok/s batch floor on this machine; offering the "
        f"least slow, {fastest['model']} at {fastest['seconds_per_token']} s/token."
    )
    return fastest


def compare(
    entries: list[dict[str, Any]],
    *,
    hw: dict[str, float | None],
    disk: dict[str, Any],
    bandwidth_gbs: float | None,
    kind: Literal["llm", "vlm"] = "llm",
    application: str | None = None,
    native_backend: str = "ollama",
    new_tokens: int = 300,
    prompt_tokens: int = 0,
    batch: int = 1,
    compression: str | None = None,
    load: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Native model versus streamed model, on the same machine, side by side.

    The decision this backend actually forces, which neither ranking answers
    alone: **is the better model worth the wait?** A machine that fits a 14B
    model comfortably can also stream a 70B one, and the two options differ by
    a handful of benchmark points in one direction and three orders of
    magnitude of latency in the other. Printing both, priced in the same unit —
    seconds for one answer of the same length — is the only way to make that
    call rather than guess at it.

    Both sides are ranked by their own backend's rules (see
    :func:`score.rank` for the native side, :func:`pick` for the streamed one,
    where bigger beats leaner), then compared on two axes only: benchmark score
    on the task's axis, and wall-clock seconds for ``new_tokens``.

    One deliberate bias, stated so it can be discounted: the native timing
    counts decode only and ignores prompt processing, while the streamed timing
    is complete (its prompt rides free in the first pass — see
    :func:`seconds_per_pass`). That flatters the native side, which is the
    right direction for an honest comparison whose conclusion will usually be
    "stay native".

    Parameters
    ----------
    entries : list of dict
        Catalog entries, unfiltered. Each side applies its own servability gate.
    hw : dict[str, float | None]
        Memory pools from :func:`detect.available_memory`.
    disk : dict[str, Any]
        Storage profile from :func:`detect.disk_profile`.
    bandwidth_gbs : float or None
        Memory bandwidth from :func:`detect.compute_profile`, for the native
        side's throughput estimate.
    kind : {'llm', 'vlm'}
        Model kind to compare.
    application : str or None
        Benchmark axis (``code``, ``math``, ``vision``, …), so both sides are
        scored on the task that matters.
    native_backend : {'ollama', 'vllm'}
        The backend to compare against.
    new_tokens : int
        Answer length both timings are computed for.
    prompt_tokens : int
        Prompt length. Reported, and free on the streamed side.
    batch : int
        Sequences at once. A real lever on the streamed side only, which is
        itself part of the answer.
    compression : {'4bit', '8bit', None}
        airllm compression for the streamed side.
    load : dict or None
        Live load from :func:`detect.server_load`, applied to both budgets.

    Returns
    -------
    dict[str, Any]
        ``native`` and ``streamed``, each with ``budget_gb``, ``best`` and
        ``rows``; plus ``quality_gain`` (benchmark points streaming buys),
        ``slowdown`` (how many times longer the answer takes), ``verdict`` (one
        sentence for a human) and the inputs the comparison was made under.

    Examples
    --------
    >>> rows = [
    ...     {"id": "small:8b", "kind": "llm", "size_b": 8, "layers": 32,
    ...      "ram_gb": 5.6, "hf_id": "x/small", "benchmarks": {"general": 74}},
    ...     {"id": "big:70b", "kind": "llm", "size_b": 70, "layers": 80,
    ...      "ram_gb": 155, "hf_id": "x/big", "benchmarks": {"general": 86}},
    ... ]
    >>> out = compare(
    ...     rows,
    ...     hw={"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0},
    ...     disk={"read_gbs": 4.0, "free_gb": 4000.0, "storage": "nvme"},
    ...     bandwidth_gbs=1008.0,
    ... )
    >>> out["native"]["best"]["catalog_id"], out["streamed"]["best"]["catalog_id"]
    ('small:8b', 'big:70b')
    >>> out["quality_gain"]
    12.0
    >>> out["slowdown"] > 1000
    True
    >>> print(out["verdict"])  # doctest: +NORMALIZE_WHITESPACE
    Streaming buys 12 benchmark points (86 vs 74) for 4751x the wait:
    3.4 h instead of 3 s for a 300-token answer.
    """
    from . import catalog as _catalog
    from .recommend import _candidate_row
    from .score import _benchmark_score, effective_budget
    from .score import rank as _rank

    native_rows: list[dict[str, Any]] = []
    native_budget = effective_budget(hw, load=load)
    servable_native = _catalog.servable_only(entries, native_backend)
    if servable_native:
        ranked = _rank(
            hw,
            servable_native,
            kind,
            application=application,
            backend=native_backend,
            load=load,
            bandwidth_gbs=bandwidth_gbs,
        )
        for entry in ranked:
            row = _candidate_row(entry, native_budget, bandwidth_gbs, application or "generalist")
            tps = row["est_tokens_per_s"]
            seconds = round(new_tokens / tps, 1) if tps else None
            native_rows.append(
                {
                    "model": row["id"],
                    "catalog_id": row["id"],
                    "backend": native_backend,
                    "score": row["score"],
                    "resident_gb": row["ram_gb"],
                    "tokens_per_s": tps,
                    "answer_seconds": seconds,
                    "answer_human": human_duration(seconds),
                    "fits": row["fits"],
                    "usable": row["fits"] and row["comfortable"],
                    "size_b": entry.get("size_b"),
                }
            )

    streamed_budget = budget_gb(hw, load)
    plans = rank(
        _catalog.servable_only(entries, "airllm"),
        budget_gb=streamed_budget,
        disk=disk,
        compression=compression,
        kind=kind,
        batch=batch,
        new_tokens=new_tokens,
    )
    # Re-score on the task's axis: `rank` carries the generalist figure, and a
    # vision brief has to compare two streamable giants on vision.
    by_id = {str(e.get("id")): e for e in entries}
    for row in plans:
        scored = by_id.get(str(row["catalog_id"]))
        if scored is not None:
            row["score"] = _benchmark_score(scored, kind, application)

    # The native side's own rule: the best-scoring model that fits AND decodes
    # fast enough to use. Not `_pick_sufficient`'s leanest-within-a-band -- the
    # question here is "what is the best this machine does natively", so the
    # comparison is strongest model against strongest model.
    usable_native = [r for r in native_rows if r["usable"]]
    best_native = max(usable_native, key=lambda r: r["score"] or 0.0) if usable_native else None
    best_streamed = pick(plans)

    quality_gain: float | None = None
    slowdown: float | None = None
    if best_native and best_streamed:
        quality_gain = round(
            float(best_streamed.get("score") or 0.0) - float(best_native["score"] or 0.0), 1
        )
        native_seconds = best_native["answer_seconds"]
        streamed_seconds = best_streamed.get("answer_seconds")
        if native_seconds and streamed_seconds:
            slowdown = round(streamed_seconds / native_seconds, 1)

    return {
        "kind": kind,
        "application": application,
        "new_tokens": new_tokens,
        "prompt_tokens": prompt_tokens,
        "batch": batch,
        "compression": compression,
        "disk": disk,
        "native": {
            "backend": native_backend,
            "budget_gb": native_budget,
            "best": best_native,
            "rows": native_rows,
        },
        "streamed": {
            "backend": PACKAGE,
            "budget_gb": streamed_budget,
            "best": best_streamed,
            "rows": plans,
        },
        "quality_gain": quality_gain,
        "slowdown": slowdown,
        "verdict": _verdict(best_native, best_streamed, quality_gain, slowdown, new_tokens),
    }


def _verdict(
    native: dict[str, Any] | None,
    streamed: dict[str, Any] | None,
    quality_gain: float | None,
    slowdown: float | None,
    new_tokens: int,
) -> str:
    """
    One sentence a human can act on, for :func:`compare`.

    Four cases, because all four happen: nothing runs either way, only
    streaming runs, only native runs, or both do and the trade has to be
    stated as a trade.

    Parameters
    ----------
    native : dict or None
        Best native row.
    streamed : dict or None
        Best streamed plan.
    quality_gain : float or None
        Benchmark points streaming adds.
    slowdown : float or None
        Multiple of the native answer time.
    new_tokens : int
        Answer length both timings describe.

    Returns
    -------
    str
        The verdict line.

    Examples
    --------
    >>> _verdict(None, None, None, None, 300)
    'Neither backend can run a model on this machine.'
    >>> n = {"catalog_id": "a", "score": 74, "answer_human": "2 s"}
    >>> _verdict(n, None, None, None, 300)
    'Nothing can be streamed here, so a:74 natively is the best this machine does.'
    """
    if native is None and streamed is None:
        return "Neither backend can run a model on this machine."
    if streamed is None and native is not None:
        return (
            f"Nothing can be streamed here, so {native['catalog_id']}:"
            f"{native['score']:.0f} natively is the best this machine does."
        )
    if native is None and streamed is not None:
        return (
            f"Nothing fits this machine's memory, so streaming is not a trade but the "
            f"only option: {streamed['model']} answers {new_tokens} tokens in "
            f"{streamed['answer_human']}."
        )
    assert native is not None and streamed is not None  # both, by elimination
    if quality_gain is not None and quality_gain <= 0:
        return (
            f"Streaming buys nothing here: {streamed['model']} scores no higher than "
            f"{native['catalog_id']}, which already fits and answers in "
            f"{native['answer_human']}. Stay native."
        )
    rate = f"{slowdown:.0f}x the wait" if slowdown else "an unmeasured wait"
    return (
        f"Streaming buys {quality_gain:.0f} benchmark points "
        f"({streamed.get('score') or 0:.0f} vs {native['score']:.0f}) for {rate}: "
        f"{streamed['answer_human']} instead of {native['answer_human']} for a "
        f"{new_tokens}-token answer."
    )


def load(
    model: str,
    *,
    compression: str | None = None,
    prefetching: bool = True,
    layer_shards_saving_path: str | None = None,
    hf_token: str | None = None,
    delete_original: bool = False,
    profiling_mode: bool = False,
    max_seq_len: int = int(_DEFAULT_CONTEXT_K * _TOKENS_PER_K),
) -> Any:
    """
    Load a model through airllm's layer-streaming runtime.

    The adapter, and the only function here that touches the upstream package.
    Its arguments are airllm's own, renamed nowhere, so its documentation stays
    the reference for them.

    Parameters
    ----------
    model : str
        HuggingFace repository id (``meta-llama/Llama-3.3-70B-Instruct``), or a
        local path to an already-split checkpoint.
    compression : {'4bit', '8bit', None}
        Block-wise weight compression. Needs ``bitsandbytes``, a core
        dependency on every platform that has a wheel for it (not macOS, where
        the MLX path handles streaming instead).
    prefetching : bool
        Overlap the next shard's read with the current layer's compute.
    layer_shards_saving_path : str or None
        Where the per-layer shards go. None uses airllm's default (beside the
        HuggingFace cache). Point it at a fast volume when the cache is not on
        one — the shard read IS the decode speed.
    hf_token : str or None
        HuggingFace token, for a gated repository.
    delete_original : bool
        Remove the downloaded checkpoint once the shards exist. Halves the disk
        requirement (see :func:`disk_required_gb`) at the cost of re-downloading
        if the shards are ever lost.
    profiling_mode : bool
        Ask airllm to print per-layer timings.
    max_seq_len : int
        Context length to configure, in tokens. Defaults to 4096, matching the
        context :func:`footprint_gb` prices — **not** airllm's own default of
        512, which truncates a longer prompt instead of refusing it. Raising
        this costs KV cache in exactly the proportion
        :func:`kv_cache_gb` describes, so size it against
        :func:`budget_gb` rather than maximising it.

    Returns
    -------
    Any
        The ``airllm.AutoModel`` instance, untouched, carrying its own
        ``.tokenizer``, ``.device`` and ``.generate``.

    Raises
    ------
    ImportError
        When the runtime cannot be imported, with the command that fixes it.

    Examples
    --------
    >>> load("meta-llama/Llama-3.3-70B-Instruct")   # doctest: +SKIP
    """
    try:
        from airllm import AutoModel
    except ImportError as exc:
        raise ImportError(
            f"Layer streaming needs the {PACKAGE} runtime, which IS a dependency of "
            f"best-engine-ai-helper — so reaching this means the install is "
            f"incomplete rather than that a feature was not opted into: "
            f"{INSTALL_HINT}. Everything else here (detection, recommendation, the "
            "Ollama and vLLM backends) keeps working meanwhile, since the import is "
            "lazy and happens only when a model is actually loaded."
        ) from exc

    osh.info(
        f"Loading {model} through airllm layer streaming "
        f"(compression={compression or 'none'}, prefetching={prefetching}, "
        f"max_seq_len={max_seq_len})."
    )
    kwargs: dict[str, Any] = {
        "compression": compression,
        "prefetching": prefetching,
        "profiling_mode": profiling_mode,
        "delete_original": delete_original,
        # Passed explicitly, always: airllm defaults to 512 tokens and
        # truncates past it, which would silently cut the end off a prompt this
        # package has just finished telling the caller is nearly free.
        "max_seq_len": max_seq_len,
    }
    if layer_shards_saving_path:
        kwargs["layer_shards_saving_path"] = layer_shards_saving_path
    if hf_token:
        kwargs["hf_token"] = hf_token
    return AutoModel.from_pretrained(model, **kwargs)


def generate(
    prompt: str,
    *,
    model: str,
    max_new_tokens: int = 128,
    compression: str | None = None,
    prefetching: bool = True,
    layer_shards_saving_path: str | None = None,
    hf_token: str | None = None,
    max_seq_len: int = int(_DEFAULT_CONTEXT_K * _TOKENS_PER_K),
    loaded: Any | None = None,
) -> str:
    """
    Generate text with a streamed model, in this process.

    There is no server to talk to: airllm is a library, not a daemon, so this
    backend runs inside the caller's interpreter. That is also why ``loaded``
    exists — splitting and loading a 70B checkpoint is the expensive part, and a
    caller making several calls should pay it once.

    Parameters
    ----------
    prompt : str
        The text to continue.
    model : str
        HuggingFace repository id, as in :func:`load`.
    max_new_tokens : int
        Tokens to generate. Keep it small: at streaming speeds every token is
        seconds of disk, so a 2000-token answer is an afternoon.
    compression, prefetching, layer_shards_saving_path, hf_token, max_seq_len
        Passed to :func:`load` when it has to load the model itself. Note that
        ``max_seq_len`` bounds prompt AND answer together, and that the
        tokenizer truncates to it — so a prompt near the limit leaves no room
        to answer.
    loaded : Any or None
        An instance from a previous :func:`load`, reused as-is.

    Returns
    -------
    str
        The decoded continuation, with the prompt stripped from the front when
        the runtime echoes it back.

    Raises
    ------
    ImportError
        When the runtime cannot be imported.

    Examples
    --------
    >>> generate("Hello", model="meta-llama/Llama-3.3-70B-Instruct")  # doctest: +SKIP
    """
    instance = (
        loaded
        if loaded is not None
        else load(
            model,
            compression=compression,
            prefetching=prefetching,
            layer_shards_saving_path=layer_shards_saving_path,
            hf_token=hf_token,
            max_seq_len=max_seq_len,
        )
    )
    tokens = instance.tokenizer(
        [prompt], return_tensors="pt", return_attention_mask=False, truncation=True
    )
    output = instance.generate(
        tokens["input_ids"].to(instance.device),
        max_new_tokens=max_new_tokens,
        use_cache=True,
        return_dict_in_generate=True,
    )
    sequences = getattr(output, "sequences", output)
    text = instance.tokenizer.decode(sequences[0], skip_special_tokens=True)
    # airllm returns prompt + continuation, like any HuggingFace `generate`.
    # Callers of `chat` expect the answer alone.
    return str(text)[len(prompt) :].lstrip() if str(text).startswith(prompt) else str(text)
