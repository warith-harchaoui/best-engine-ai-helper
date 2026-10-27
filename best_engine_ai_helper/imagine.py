"""
imagine — pick and run a local text-to-image model for this machine.

The third kind of model this package chooses. ``llm`` and ``vlm`` answer with
text; ``embed`` answers with a vector; ``image`` answers with pixels. The job
is the same one as everywhere else here — *given this hardware, which model
should run, and will it be usable?* — and so is the shape of the answer: a
footprint measured against the accelerator's real budget, a speed estimate in
the unit a human waits in, and a catalogue entry rather than a hardcoded name.

What is different about a diffusion model
-----------------------------------------
A language model is one stack of layers. A diffusion model is **three or four
separate networks** that take turns: one or two text encoders turn the prompt
into conditioning, a denoiser (a UNet for the Stable Diffusion 1.x/XL
generation, a transformer for SD3 and FLUX) runs the sampling loop, and a VAE
decodes the final latent into an image. Two consequences, both load-bearing
here:

1. **Memory depends on how they take turns.** Held all at once, the footprint is
   the sum of every component. Handed to ``diffusers``'
   ``enable_model_cpu_offload()``, only the component currently computing stays
   resident and the peak becomes the *largest* one — the same trade layer
   streaming makes for an LLM (see :mod:`best_engine_ai_helper.offload`), at a
   much smaller penalty, because the components swap a handful of times per
   image rather than once per token.
2. **Time is steps, not tokens.** The sampling loop runs a fixed number of
   denoising steps, each one a full pass through the denoiser, so the honest
   unit is *seconds per image* and the biggest lever on it is the step count —
   which is a property of the model, not a preference: SDXL-Turbo and
   FLUX.1-schnell are distilled for 1-4 steps where SD 1.5 wants 25-30.

The runtime is ``diffusers``, imported lazily and a core dependency of this
package (torch is already here for layer streaming, so the incremental cost is
a few megabytes of Python). Nothing in this module reimplements sampling: it
decides *which* model and *whether*, and :func:`generate` is a thin adapter.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import importlib
import math
from typing import Any

import os_helper as osh

#: Name of the upstream runtime, spelled once.
PACKAGE = "diffusers"

#: What to tell a caller whose interpreter cannot import it. A core dependency,
#: so reaching this means an incomplete install rather than a missing opt-in.
INSTALL_HINT = "pip install --upgrade --force-reinstall best-engine-ai-helper"

#: Bytes per parameter by the dtype the pipeline RUNS in. Unlike a streamed
#: language model, where the figure that matters is what sits on disk, a
#: diffusion pipeline is sized by what sits in memory while it samples — so
#: this is the compute dtype, and fp16/bf16 is what every current pipeline
#: defaults to on a GPU.
_BYTES_PER_PARAM: dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "fp8": 1.0,
    "int8": 1.0,
    "nf4": 0.5,
    "int4": 0.5,
}

#: Dtype assumed when an entry does not declare one.
_DEFAULT_DTYPE = "fp16"

#: Multiplier over raw weights for the pipeline's own buffers: the scheduler's
#: state, the attention workspace, and the copies ``diffusers`` makes while
#: moving a component onto the device. Deliberately above 1 by a visible
#: margin, because a pipeline that only just fits spends its time thrashing.
_RUNTIME_OVERHEAD = 1.25

#: Latent and activation memory, in GB per megapixel of output. The sampling
#: loop holds the latent plus the attention maps of the resolution it is
#: working at, so this term — not the weights — is what makes 1024x1024
#: markedly heavier than 512x512 on the same model. A megapixel is the SDXL
#: reference resolution (1024x1024 is 1.05 MP), which is why the unit is that
#: rather than pixels.
_LATENT_GB_PER_MEGAPIXEL = 1.0

#: Fraction of total parameters the denoiser accounts for when an entry does
#: not name its components. The denoiser dominates every current architecture
#: (SDXL: 2.6B of 3.5B; FLUX: 12B of ~17B), and this figure is what
#: :func:`footprint_gb` uses to size a component-offloaded run. Conservative on
#: purpose: over-estimating the biggest component is the safe direction.
_DENOISER_SHARE = 0.7

#: Seconds per denoising step per billion denoiser parameters, at one
#: megapixel, on a GPU doing roughly one teraflop-second of useful work per
#: second. A crude single-constant model, and labelled as such: step time is
#: compute-bound, this package measures memory bandwidth rather than FLOPS, and
#: the two correlate only loosely across vendors. It is here to answer "seconds
#: or minutes?" — the question that decides whether a model is usable at all —
#: and never to compare two GPUs with each other.
#:
#: Anchored on a measured point rather than derived: an SDXL UNet (2.6B) at
#: 1024x1024 runs about 0.35 s/step on an RTX 4090 (~1000 GB/s), which gives
#: 0.35 / 2.6 * (1000/1000) ~= 0.135.
_STEP_SECONDS_PER_B_PER_MP = 0.135

#: Memory bandwidth (GB/s) the constant above is calibrated at, so a slower
#: accelerator scales up from it.
_REFERENCE_BANDWIDTH_GBS = 1000.0

#: Default steps when a catalogue entry does not say. 28 is the Stable
#: Diffusion family's own default for a non-distilled model; a distilled one
#: (Turbo, schnell, Lightning) declares its 1-4 and must, because running it at
#: 28 is slower AND worse.
_DEFAULT_STEPS = 28

#: Seconds per image past which generating locally stops being worth it.
#: Ninety seconds is about the point where a person stops waiting and starts
#: doing something else, which changes the job from interactive to batch.
#: Reported as a blocker rather than enforced: a batch job may well accept it.
COMFORT_SECONDS_PER_IMAGE: float = 90.0

#: Output sizes the OpenAI image API names, mapped to pixel dimensions.
#: ``auto`` resolves to the model's own native resolution, which is the only
#: size a diffusion model is actually good at — asking SD 1.5 for 1024x1024
#: produces duplicated limbs rather than more detail.
OPENAI_SIZES: dict[str, tuple[int, int]] = {
    "256x256": (256, 256),
    "512x512": (512, 512),
    "768x768": (768, 768),
    "1024x1024": (1024, 1024),
    "1024x1792": (1024, 1792),
    "1792x1024": (1792, 1024),
    "1536x1024": (1536, 1024),
    "1024x1536": (1024, 1536),
}


def is_image_model(entry: dict[str, Any]) -> bool:
    """
    Whether a catalog entry is a text-to-image model.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.

    Returns
    -------
    bool
        True when its ``kind`` is ``image``.

    Examples
    --------
    >>> is_image_model({"id": "sdxl", "kind": "image"})
    True
    >>> is_image_model({"id": "qwen3:8b", "kind": "llm"})
    False
    """
    return str(entry.get("kind") or "").strip().lower() == "image"


def hf_id(entry: dict[str, Any]) -> str | None:
    """
    The HuggingFace repository ``diffusers`` would load.

    Image models have no Ollama registry to fall back on, so an entry that
    names no repository names nothing that can run. ``hf_id`` is preferred;
    ``vllm_id`` is accepted because the catalog has always spelled a Hub id
    that way.

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
    >>> hf_id({"id": "sdxl", "hf_id": "stabilityai/stable-diffusion-xl-base-1.0"})
    'stabilityai/stable-diffusion-xl-base-1.0'
    >>> hf_id({"id": "sdxl"}) is None
    True
    """
    for key in ("hf_id", "vllm_id"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return None


def native_size(entry: dict[str, Any]) -> tuple[int, int]:
    """
    The resolution a model was trained for.

    The one size a diffusion model is actually good at. Asking SD 1.5 for
    1024x1024 does not add detail, it duplicates limbs; asking SDXL for
    512x512 loses composition. So ``size: "auto"`` on the image endpoint
    resolves to this rather than to a house default.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; reads ``native_size`` (``"WxH"``), else falls back to
        1024x1024.

    Returns
    -------
    tuple[int, int]
        ``(width, height)`` in pixels.

    Examples
    --------
    >>> native_size({"id": "sd15", "native_size": "512x512"})
    (512, 512)
    >>> native_size({"id": "sdxl"})
    (1024, 1024)
    >>> native_size({"id": "broken", "native_size": "nonsense"})
    (1024, 1024)
    """
    raw = str(entry.get("native_size") or "").strip().lower()
    if "x" in raw:
        width, _, height = raw.partition("x")
        try:
            return int(width), int(height)
        except ValueError:
            osh.debug(f"Unparseable native_size {raw!r} on {entry.get('id', '?')}.")
    return 1024, 1024


def steps_for(entry: dict[str, Any]) -> int:
    """
    Denoising steps the model expects.

    A property of the checkpoint, not a taste: a distilled model (Turbo,
    schnell, Lightning) is trained to converge in 1-4 steps, and running it for
    28 is both slower and worse. Getting this from the catalog rather than from
    a global default is what makes an auto-selected image model usable.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; reads ``steps``.

    Returns
    -------
    int
        Step count. A declared 0 is treated as absent rather than honoured:
        zero denoising steps returns noise, so it can only be a data error.

    Examples
    --------
    >>> steps_for({"id": "sdxl-turbo", "steps": 4})
    4
    >>> steps_for({"id": "sd15"})
    28
    >>> steps_for({"id": "weird", "steps": 0})
    28
    """
    declared = entry.get("steps")
    if declared:
        return max(1, int(declared))
    return _DEFAULT_STEPS


def bytes_per_param(entry: dict[str, Any], dtype: str | None = None) -> float:
    """
    Bytes each parameter occupies while the pipeline samples.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; reads ``dtype`` (default fp16).
    dtype : str or None
        Override, for a caller who is going to load the pipeline in something
        else (``nf4`` for a 4-bit FLUX, say).

    Returns
    -------
    float
        Bytes per parameter.

    Examples
    --------
    >>> bytes_per_param({})
    2.0
    >>> bytes_per_param({"dtype": "fp32"})
    4.0
    >>> bytes_per_param({"dtype": "fp16"}, dtype="nf4")
    0.5
    >>> bytes_per_param({"dtype": "nonsense"})
    2.0
    """
    name = str(dtype or entry.get("dtype") or _DEFAULT_DTYPE).strip().lower()
    if name not in _BYTES_PER_PARAM:
        osh.debug(f"Unknown dtype {name!r} on {entry.get('id', '?')}; assuming {_DEFAULT_DTYPE}.")
        name = _DEFAULT_DTYPE
    return _BYTES_PER_PARAM[name]


def megapixels(width: int, height: int) -> float:
    """
    Output area in megapixels, the unit the latent term is priced in.

    Parameters
    ----------
    width, height : int
        Output dimensions in pixels.

    Returns
    -------
    float
        Megapixels, rounded to three decimals.

    Examples
    --------
    >>> megapixels(1024, 1024)
    1.049
    >>> megapixels(512, 512)
    0.262
    """
    return round(width * height / 1e6, 3)


def footprint_gb(
    entry: dict[str, Any],
    *,
    dtype: str | None = None,
    offload: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> float:
    """
    Resident memory (GB) a pipeline needs to produce one image.

    ``weights x overhead + latents``, where *which* weights depends on how the
    components take turns:

    - **All resident** (``offload=False``, the fast path): every component at
      once, so the weight term is the whole parameter count.
    - **Component offloaded** (``offload=True``): ``diffusers`` keeps only the
      component currently computing on the device, so the peak is the largest
      one — the denoiser, at :data:`_DENOISER_SHARE` of the total unless the
      entry names its components. Slower by the handful of transfers per image
      that costs, and the difference between running FLUX on a 24 GB card and
      not running it.

    The latent term is what makes resolution expensive: it scales with the
    output area, not with the model.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry; needs ``size_b``.
    dtype : str or None
        Compute dtype override.
    offload : bool
        Size for a component-offloaded run rather than an all-resident one.
    width, height : int or None
        Output size. None uses the model's :func:`native_size`, which is the
        size it is good at anyway.

    Returns
    -------
    float
        Resident GB, or ``inf`` when the entry carries no parameter count —
        infinity rather than zero, so an unsized entry can never read as
        "fits everywhere" and win every comparison.

    Examples
    --------
    >>> sdxl = {"id": "sdxl", "kind": "image", "size_b": 3.5, "native_size": "1024x1024"}
    >>> footprint_gb(sdxl)
    9.8
    >>> footprint_gb(sdxl, offload=True)
    7.2
    >>> footprint_gb(sdxl, width=512, height=512)
    9.0
    >>> footprint_gb({"id": "sd15", "size_b": 1.07, "native_size": "512x512"})
    2.9
    >>> footprint_gb({"id": "unsized", "kind": "image"})
    inf
    """
    size_b = float(entry.get("size_b", 0) or 0)
    if size_b <= 0:
        return math.inf

    if offload:
        declared = float(entry.get("denoiser_size_b", 0) or 0)
        size_b = declared if declared > 0 else size_b * _DENOISER_SHARE

    if width is None or height is None:
        native_w, native_h = native_size(entry)
        width = width or native_w
        height = height or native_h

    weights = size_b * bytes_per_param(entry, dtype)
    latents = _LATENT_GB_PER_MEGAPIXEL * megapixels(width, height)
    return round(weights * _RUNTIME_OVERHEAD + latents, 1)


def seconds_per_image(
    entry: dict[str, Any],
    bandwidth_gbs: float | None,
    *,
    steps: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> float | None:
    """
    Estimate how long one image takes on this machine.

    ``steps x denoiser passes``, each pass proportional to the denoiser's size
    and to the output area. The constant behind it
    (:data:`_STEP_SECONDS_PER_B_PER_MP`) is anchored on one measured point and
    scaled by memory bandwidth, which is the only compute proxy this package
    has — so treat the result as "seconds or minutes?", never as a benchmark.
    It is still the figure that decides usability: a model needing four minutes
    an image is a different tool from one needing four seconds.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    bandwidth_gbs : float or None
        Memory bandwidth from :func:`detect.compute_profile`. None returns
        None: no estimate rather than a fabricated one.
    steps : int or None
        Override the catalog's step count.
    width, height : int or None
        Output size; None uses the native one.

    Returns
    -------
    float or None
        Seconds per image, rounded to one decimal, or None when bandwidth or
        model size is unknown.

    Examples
    --------
    >>> sdxl = {"id": "sdxl", "size_b": 3.5, "denoiser_size_b": 2.6,
    ...         "steps": 28, "native_size": "1024x1024"}
    >>> seconds_per_image(sdxl, 1000.0)
    10.3
    >>> # The same model distilled to 4 steps is the same arithmetic, 7x less of it.
    >>> seconds_per_image({**sdxl, "steps": 4}, 1000.0)
    1.5
    >>> # Half the bandwidth, twice the wait.
    >>> seconds_per_image(sdxl, 500.0)
    20.6
    >>> seconds_per_image(sdxl, None) is None
    True
    >>> seconds_per_image({"id": "unsized"}, 1000.0) is None
    True
    """
    if not bandwidth_gbs or bandwidth_gbs <= 0:
        return None
    denoiser_b = float(entry.get("denoiser_size_b", 0) or 0)
    if denoiser_b <= 0:
        total = float(entry.get("size_b", 0) or 0)
        if total <= 0:
            return None
        denoiser_b = total * _DENOISER_SHARE

    if width is None or height is None:
        native_w, native_h = native_size(entry)
        width = width or native_w
        height = height or native_h

    per_step = (
        _STEP_SECONDS_PER_B_PER_MP
        * denoiser_b
        * megapixels(width, height)
        * (_REFERENCE_BANDWIDTH_GBS / bandwidth_gbs)
    )
    return round(per_step * (steps if steps else steps_for(entry)), 1)


#: Memoized result of :func:`available`; importing diffusers drags torch in.
_AVAILABLE: bool | None = None


def available() -> bool:
    """
    Whether the ``diffusers`` runtime is importable in this interpreter.

    Normally True: it is a core dependency. Checked rather than assumed for the
    same reason :func:`offload.available` is — declared and importable are
    different claims, and a stripped container separates them. A real import
    rather than ``find_spec`` for the same reason too: a package whose
    ``__init__`` raises has a findable spec and is still unusable, which is how
    airllm behaves on a Mac without ``mlx``.

    Returns
    -------
    bool
        True when ``import diffusers`` succeeds.

    Examples
    --------
    >>> available() in (True, False)
    True
    """
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            importlib.import_module(PACKAGE)
            _AVAILABLE = True
        except Exception as exc:  # noqa: BLE001 — any import failure means unusable
            osh.debug(f"The {PACKAGE} runtime cannot be imported here: {exc!r}")
            _AVAILABLE = False
    return _AVAILABLE


def plan(
    entry: dict[str, Any],
    *,
    budget_gb: float | None = None,
    bandwidth_gbs: float | None = None,
    dtype: str | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
) -> dict[str, Any]:
    """
    Everything known about running ONE image model on this machine.

    Tries the all-resident footprint first and falls back to the
    component-offloaded one when that does not fit — the same escalation
    :func:`offload.rank` makes with prefetching, for the same reason: the knob
    exists, the runtime exposes it, and trying it before rejecting a model is
    the difference between running FLUX on a 24 GB card and reporting that it
    cannot be done.

    Parameters
    ----------
    entry : dict[str, Any]
        Catalog entry.
    budget_gb : float or None
        Memory budget from :func:`score.effective_budget`. None skips the fit
        verdict.
    bandwidth_gbs : float or None
        Memory bandwidth, for the time estimate.
    dtype : str or None
        Compute dtype override.
    width, height : int or None
        Output size; None uses the model's native one.
    steps : int or None
        Step override.

    Returns
    -------
    dict[str, Any]
        ``model``, ``catalog_id``, ``resident_gb``, ``offload`` (whether the fit
        needed it), ``size``, ``steps``, ``seconds_per_image``, ``fits``,
        ``usable`` and ``blockers``.

    Examples
    --------
    >>> sdxl = {"id": "sdxl", "kind": "image", "size_b": 3.5, "denoiser_size_b": 2.6,
    ...         "steps": 28, "native_size": "1024x1024",
    ...         "hf_id": "stabilityai/stable-diffusion-xl-base-1.0"}
    >>> p = plan(sdxl, budget_gb=11.0, bandwidth_gbs=1000.0)
    >>> p["resident_gb"], p["offload"], p["seconds_per_image"], p["usable"]
    (9.8, False, 10.3, True)
    >>> # An 8 GB budget only fits it with the components taking turns.
    >>> tight = plan(sdxl, budget_gb=8.0, bandwidth_gbs=1000.0)
    >>> tight["resident_gb"], tight["offload"], tight["fits"]
    (7.5, True, True)
    >>> plan(sdxl, budget_gb=2.0)["blockers"][0][:38]
    'needs 7.5 GB resident even with the co'
    """
    width_px, height_px = native_size(entry)
    width = width or width_px
    height = height or height_px
    step_count = steps or steps_for(entry)

    resident = footprint_gb(entry, dtype=dtype, offload=False, width=width, height=height)
    offloaded = False
    if budget_gb is not None and math.isfinite(resident) and resident > budget_gb:
        swapped = footprint_gb(entry, dtype=dtype, offload=True, width=width, height=height)
        if swapped <= budget_gb or not math.isfinite(resident):
            resident, offloaded = swapped, True
        else:
            # Report the offloaded figure either way: it is the smallest this
            # model can be made, so it is the number a caller needs to know
            # how far off they are.
            resident, offloaded = swapped, True

    seconds = seconds_per_image(entry, bandwidth_gbs, steps=step_count, width=width, height=height)
    fits = bool(budget_gb is not None and math.isfinite(resident) and resident <= budget_gb)

    blockers: list[str] = []
    if not math.isfinite(resident):
        blockers.append(
            "the catalog entry carries no parameter count, so its footprint cannot be sized"
        )
    elif budget_gb is not None and not fits:
        how = " even with the components taking turns" if offloaded else ""
        blockers.append(
            f"needs {resident:.1f} GB resident{how}, above this machine's {budget_gb:.1f} GB budget"
        )
    if seconds is None:
        blockers.append(
            "this machine's memory bandwidth is unknown, so no time per image can be given"
        )
    elif seconds > COMFORT_SECONDS_PER_IMAGE:
        blockers.append(
            f"about {seconds:.0f} s per image, past the {COMFORT_SECONDS_PER_IMAGE:.0f} s "
            "point where this stops being interactive"
        )
    if not hf_id(entry):
        blockers.append(
            "the entry names no HuggingFace repository (`hf_id`), and diffusers loads "
            "pipelines from the Hub"
        )

    return {
        "model": hf_id(entry) or entry.get("id"),
        "catalog_id": entry.get("id"),
        "resident_gb": resident if math.isfinite(resident) else None,
        "offload": offloaded,
        "size": f"{width}x{height}",
        "width": width,
        "height": height,
        "steps": step_count,
        "seconds_per_image": seconds,
        "score": (entry.get("benchmarks") or {}).get("image"),
        "size_b": float(entry.get("size_b", 0) or 0),
        "fits": fits,
        "usable": bool(
            fits
            and seconds is not None
            and seconds <= COMFORT_SECONDS_PER_IMAGE
            and hf_id(entry) is not None
        ),
        "blockers": blockers,
    }


def rank(
    entries: list[dict[str, Any]],
    *,
    budget_gb: float,
    bandwidth_gbs: float | None = None,
    dtype: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> list[dict[str, Any]]:
    """
    Rank the image models this machine could run, best first.

    Parameters
    ----------
    entries : list of dict
        Catalog entries; non-image kinds are dropped.
    budget_gb : float
        Memory budget from :func:`score.effective_budget`.
    bandwidth_gbs : float or None
        Memory bandwidth, for the time estimates.
    dtype : str or None
        Compute dtype override.
    width, height : int or None
        Output size; None lets each model use its own native one, which is the
        fair comparison — a model is not worse for being a 512px model, it is
        cheaper.

    Returns
    -------
    list[dict[str, Any]]
        :func:`plan` dicts, usable first, then by image-quality score, then by
        parameter count.

    Examples
    --------
    >>> rows = [
    ...     {"id": "sd15", "kind": "image", "size_b": 1.07, "steps": 28,
    ...      "native_size": "512x512", "hf_id": "x/sd15",
    ...      "benchmarks": {"image": 60}},
    ...     {"id": "sdxl", "kind": "image", "size_b": 3.5, "steps": 28,
    ...      "native_size": "1024x1024", "hf_id": "x/sdxl",
    ...      "benchmarks": {"image": 75}},
    ...     {"id": "chat", "kind": "llm", "size_b": 8},
    ... ]
    >>> [r["catalog_id"] for r in rank(rows, budget_gb=11.0, bandwidth_gbs=1000.0)]
    ['sdxl', 'sd15']
    >>> # On a 4 GB card only the small one runs, and it says why about the other.
    >>> tight = rank(rows, budget_gb=4.0, bandwidth_gbs=1000.0)
    >>> [(r["catalog_id"], r["usable"]) for r in tight]
    [('sd15', True), ('sdxl', False)]
    """
    plans = [
        plan(
            entry,
            budget_gb=budget_gb,
            bandwidth_gbs=bandwidth_gbs,
            dtype=dtype,
            width=width,
            height=height,
        )
        for entry in entries
        if is_image_model(entry)
    ]
    plans.sort(
        key=lambda r: (r["usable"], r.get("score") or 0.0, r["size_b"]),
        reverse=True,
    )
    return plans


def pick(plans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Choose one image model: the best that runs, else the fastest that fits.

    Parameters
    ----------
    plans : list of dict
        :func:`plan` dicts, typically from :func:`rank`.

    Returns
    -------
    dict or None
        The chosen plan, or None when nothing fits at all.

    Examples
    --------
    >>> rows = [
    ...     {"id": "sd15", "kind": "image", "size_b": 1.07, "steps": 28,
    ...      "native_size": "512x512", "hf_id": "x/sd15", "benchmarks": {"image": 60}},
    ...     {"id": "sdxl", "kind": "image", "size_b": 3.5, "steps": 28,
    ...      "native_size": "1024x1024", "hf_id": "x/sdxl", "benchmarks": {"image": 75}},
    ... ]
    >>> pick(rank(rows, budget_gb=11.0, bandwidth_gbs=1000.0))["catalog_id"]
    'sdxl'
    >>> pick(rank(rows, budget_gb=4.0, bandwidth_gbs=1000.0))["catalog_id"]
    'sd15'
    >>> pick([]) is None
    True
    """
    fitting = [p for p in plans if p["fits"]]
    if not fitting:
        return None
    usable = [p for p in fitting if p["usable"]]
    if usable:
        return max(usable, key=lambda p: (p.get("score") or 0.0, p["size_b"]))
    fastest = min(
        fitting, key=lambda p: p["seconds_per_image"] if p["seconds_per_image"] else math.inf
    )
    osh.warning(
        "No image model on this machine clears the "
        f"{COMFORT_SECONDS_PER_IMAGE:.0f} s per image mark; offering the quickest, "
        f"{fastest['model']} at about {fastest['seconds_per_image']} s."
    )
    return fastest


def load(
    model: str,
    *,
    dtype: str | None = None,
    offload: bool = False,
    hf_token: str | None = None,
) -> Any:
    """
    Load a diffusers pipeline.

    The adapter, and the only function here that touches the upstream package.

    Parameters
    ----------
    model : str
        HuggingFace repository id, or a local path to a saved pipeline.
    dtype : str or None
        Compute dtype (``fp16``, ``bf16``, ``fp32``). None lets torch pick
        float16 on an accelerator and float32 on CPU, which is the only pair
        that works on both without producing black images.
    offload : bool
        Hand the pipeline to ``enable_model_cpu_offload()``, so only the
        component currently computing stays on the device. Slower per image,
        and what makes a large pipeline fit at all.
    hf_token : str or None
        HuggingFace token, for a gated repository (FLUX is gated).

    Returns
    -------
    Any
        The ``diffusers`` pipeline, untouched.

    Raises
    ------
    ImportError
        When ``diffusers`` cannot be imported, with the command that fixes it.

    Examples
    --------
    >>> load("stabilityai/sdxl-turbo")   # doctest: +SKIP
    """
    try:
        import torch
        from diffusers import AutoPipelineForText2Image as _Pipeline
    except ImportError as exc:
        raise ImportError(
            f"Image generation needs the {PACKAGE} runtime, which IS a dependency of "
            f"best-engine-ai-helper — so reaching this means the install is incomplete "
            f"rather than that a feature was not opted into: {INSTALL_HINT}. Text "
            "models (Ollama, vLLM, layer streaming) keep working meanwhile, since "
            "this import is lazy."
        ) from exc

    accelerated = bool(torch.cuda.is_available() or torch.backends.mps.is_available())
    torch_dtype = {
        "fp32": torch.float32,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }.get(str(dtype or "").strip().lower(), torch.float16 if accelerated else torch.float32)

    osh.info(
        f"Loading image pipeline {model} (dtype={torch_dtype}, offload={offload}, "
        f"accelerated={accelerated})."
    )
    kwargs: dict[str, Any] = {"torch_dtype": torch_dtype}
    if hf_token:
        kwargs["token"] = hf_token
    # Through an `Any` rather than called directly: diffusers ships partial
    # type information, so `from_pretrained` is untyped and mypy's strict mode
    # rejects the call — but only when diffusers is actually installed, which
    # is why this passed locally and failed in CI. An inline `type: ignore`
    # would then be flagged as unused on a machine without it; the indirection
    # is correct in both states.
    factory: Any = _Pipeline
    pipeline = factory.from_pretrained(model, **kwargs)

    if offload:
        # Components take turns on the device; the peak becomes the largest one.
        pipeline.enable_model_cpu_offload()
    elif torch.cuda.is_available():
        pipeline = pipeline.to("cuda")
    elif torch.backends.mps.is_available():
        pipeline = pipeline.to("mps")
    return pipeline


def generate(
    prompt: str,
    *,
    model: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = _DEFAULT_STEPS,
    guidance: float | None = None,
    negative_prompt: str | None = None,
    seed: int | None = None,
    dtype: str | None = None,
    offload: bool = False,
    hf_token: str | None = None,
    loaded: Any | None = None,
) -> bytes:
    """
    Generate one image and return it as PNG bytes.

    Parameters
    ----------
    prompt : str
        What to draw.
    model : str
        HuggingFace repository id, as in :func:`load`.
    width, height : int
        Output size. Stay near the model's :func:`native_size`: a diffusion
        model asked for an unfamiliar resolution does not produce more detail,
        it produces duplicated subjects.
    steps : int
        Denoising steps. Use the model's own figure (:func:`steps_for`) — a
        distilled checkpoint at 28 steps is slower *and* worse.
    guidance : float or None
        Classifier-free guidance scale. None uses the pipeline's default,
        which is the right answer for a distilled model (they want 0.0) and for
        a normal one (7.5) alike, and those two defaults are why this is not a
        house constant.
    negative_prompt : str or None
        What to avoid. Ignored by distilled pipelines that run without
        guidance; passed through when given.
    seed : int or None
        Seed for reproducibility. None leaves the generator unseeded.
    dtype, offload, hf_token
        Passed to :func:`load` when it has to load the pipeline.
    loaded : Any or None
        A pipeline from a previous :func:`load`, reused as-is. Loading one is
        seconds to minutes, so a caller making several images should pay it
        once.

    Returns
    -------
    bytes
        The image encoded as PNG.

    Raises
    ------
    ImportError
        When ``diffusers`` cannot be imported.

    Examples
    --------
    >>> generate("a red bicycle", model="stabilityai/sdxl-turbo")  # doctest: +SKIP
    """
    import io

    pipeline = (
        loaded
        if loaded is not None
        else load(model, dtype=dtype, offload=offload, hf_token=hf_token)
    )

    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": max(1, int(steps)),
    }
    if guidance is not None:
        kwargs["guidance_scale"] = guidance
    if negative_prompt:
        kwargs["negative_prompt"] = negative_prompt
    if seed is not None:
        import torch

        kwargs["generator"] = torch.Generator(
            device=getattr(pipeline, "device", "cpu")
        ).manual_seed(int(seed))

    image = pipeline(**kwargs).images[0]
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
