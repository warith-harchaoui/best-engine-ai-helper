"""
Tests for best_engine_ai_helper.imagine — picking and running an image model.

A diffusion model breaks the assumption every other test file here rests on:
it is not one stack of layers but three or four networks taking turns, so its
footprint depends on *how* they take turns and its speed is steps rather than
tokens. These tests pin both, plus the two catalogue facts that make an
auto-selected image model usable at all — the native resolution and the step
count, neither of which is a preference.

No diffusers, no torch, no weights: the runtime is faked through sys.modules
in the three tests that reach for it.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from best_engine_ai_helper import catalog, imagine

SD15 = {
    "id": "sd15",
    "kind": "image",
    "size_b": 1.07,
    "denoiser_size_b": 0.86,
    "dtype": "fp16",
    "native_size": "512x512",
    "steps": 28,
    "hf_id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
    "benchmarks": {"image": 58},
}
SDXL = {
    "id": "sdxl",
    "kind": "image",
    "size_b": 3.5,
    "denoiser_size_b": 2.6,
    "dtype": "fp16",
    "native_size": "1024x1024",
    "steps": 28,
    "hf_id": "stabilityai/stable-diffusion-xl-base-1.0",
    "benchmarks": {"image": 75},
}
TURBO = {**SDXL, "id": "sdxl-turbo", "steps": 4, "native_size": "512x512", "hf_id": "x/turbo"}
FLUX = {
    "id": "flux1-schnell",
    "kind": "image",
    "size_b": 16.9,
    "denoiser_size_b": 11.9,
    "dtype": "bf16",
    "native_size": "1024x1024",
    "steps": 4,
    "hf_id": "black-forest-labs/FLUX.1-schnell",
    "benchmarks": {"image": 88},
}


# ---------------------------------------------------------------------------
# Sizing: the components take turns, or they do not
# ---------------------------------------------------------------------------


def test_offloading_sizes_the_largest_component_not_the_sum() -> None:
    """The trade that gets a 17B pipeline onto a consumer card.

    ``diffusers`` can keep only the component currently computing on the
    device, so the peak becomes the denoiser rather than denoiser plus text
    encoders plus VAE. On FLUX, where 8.4B of the 16.9B is a T5 text encoder
    used once per image, that is the difference between running it and not.
    """
    resident = imagine.footprint_gb(FLUX)
    swapped = imagine.footprint_gb(FLUX, offload=True)

    assert resident > swapped
    # The offloaded figure tracks the declared denoiser, not a fraction of the
    # total — the catalogue says 11.9B of 16.9B and that is what is sized.
    assert swapped == pytest.approx(11.9 * 2 * 1.25 + 1.049, abs=0.2)


def test_an_entry_that_names_no_components_still_sizes_conservatively() -> None:
    """Over-estimating the biggest component is the safe direction."""
    bare = {"id": "mystery", "kind": "image", "size_b": 10.0, "native_size": "1024x1024"}

    assert imagine.footprint_gb(bare, offload=True) < imagine.footprint_gb(bare)
    # 70% of the total, which is where every current architecture's denoiser
    # sits, rather than a guess that happens to fit.
    assert imagine.footprint_gb(bare, offload=True) == pytest.approx(
        10.0 * 0.7 * 2 * 1.25 + 1.049, abs=0.2
    )


def test_resolution_is_priced_because_it_is_not_free() -> None:
    """Latents and attention maps scale with the output, not with the model."""
    small = imagine.footprint_gb(SDXL, width=512, height=512)
    large = imagine.footprint_gb(SDXL, width=1024, height=1024)

    assert large > small
    # The weights are identical; only the latent term moved.
    assert large - small == pytest.approx(
        imagine.megapixels(1024, 1024) - imagine.megapixels(512, 512), abs=0.1
    )


def test_an_unsized_entry_reports_infinity_rather_than_fitting_everywhere() -> None:
    """Absent is not zero, here as everywhere else in this package."""
    assert imagine.footprint_gb({"id": "x", "kind": "image"}) == float("inf")
    assert imagine.seconds_per_image({"id": "x", "kind": "image"}, 1000.0) is None


def test_the_dtype_is_what_the_pipeline_runs_in() -> None:
    """A 4-bit FLUX is a different proposition from a bf16 one."""
    assert imagine.footprint_gb(FLUX, dtype="nf4") < imagine.footprint_gb(FLUX, dtype="fp16")
    assert imagine.bytes_per_param(FLUX) == 2.0
    assert imagine.bytes_per_param(FLUX, dtype="nf4") == 0.5


# ---------------------------------------------------------------------------
# Time: steps, not tokens
# ---------------------------------------------------------------------------


def test_the_step_count_is_the_biggest_lever_and_comes_from_the_catalogue() -> None:
    """A distilled checkpoint at 28 steps is slower AND worse.

    So the step count is a property of the weights, not a default to be
    overridden — which is exactly why it is catalogue data here. The same
    denoiser at 4 steps instead of 28 is the whole difference between a
    one-second image and a ten-second one.
    """
    assert imagine.steps_for(TURBO) == 4
    assert imagine.steps_for(SDXL) == 28

    # Compared on SDXL rather than on Turbo: at a tenth of a second the
    # one-decimal rounding dominates the ratio, and the claim under test is
    # "steps are the lever", not a constant.
    fast = imagine.seconds_per_image({**SDXL, "steps": 4}, 1000.0)
    slow = imagine.seconds_per_image(SDXL, 1000.0)
    assert fast is not None and slow is not None
    assert slow / fast == pytest.approx(7.0, rel=0.05)


def test_time_scales_with_bandwidth_and_with_area() -> None:
    """Both halves of "will I wait seconds or minutes" on this machine."""
    fast_gpu = imagine.seconds_per_image(SDXL, 1000.0)
    slow_gpu = imagine.seconds_per_image(SDXL, 250.0)
    assert fast_gpu is not None and slow_gpu is not None
    assert slow_gpu / fast_gpu == pytest.approx(4.0, abs=0.1)

    big = imagine.seconds_per_image(SDXL, 1000.0, width=1024, height=1024)
    small = imagine.seconds_per_image(SDXL, 1000.0, width=512, height=512)
    assert big is not None and small is not None
    assert big > small

    # An unknown accelerator yields no estimate rather than a fabricated one.
    assert imagine.seconds_per_image(SDXL, None) is None


def test_a_model_too_slow_to_wait_for_is_flagged_rather_than_hidden() -> None:
    """Fitting in memory is half the question; the other half is patience."""
    plan = imagine.plan(FLUX, budget_gb=64.0, bandwidth_gbs=30.0)

    assert plan["fits"] is True
    assert plan["usable"] is False
    assert any("per image" in blocker for blocker in plan["blockers"])


# ---------------------------------------------------------------------------
# The pick
# ---------------------------------------------------------------------------


def test_the_plan_falls_back_to_offloading_before_rejecting_a_model() -> None:
    """The knob exists and the runtime exposes it, so it has to be tried."""
    resident_only = imagine.plan(FLUX, budget_gb=64.0, bandwidth_gbs=1000.0)
    needs_offload = imagine.plan(FLUX, budget_gb=34.0, bandwidth_gbs=1000.0)

    assert resident_only["offload"] is False
    assert needs_offload["offload"] is True
    assert needs_offload["fits"] is True


def test_the_pick_prefers_quality_then_size_among_what_runs() -> None:
    """And reports why the ones that do not, do not."""
    plans = imagine.rank([SD15, SDXL, FLUX], budget_gb=11.0, bandwidth_gbs=1000.0)
    chosen = imagine.pick(plans)

    assert chosen is not None
    # FLUX needs more than 11 GB even offloaded, so the best that runs wins.
    assert chosen["catalog_id"] == "sdxl"
    rejected = [p for p in plans if not p["fits"]]
    assert rejected and all(p["blockers"] for p in rejected)


def test_a_small_machine_gets_the_small_model_rather_than_nothing() -> None:
    """The fallback that matters: an image on a 4 GB card beats no image."""
    chosen = imagine.pick(imagine.rank([SD15, SDXL, FLUX], budget_gb=3.7, bandwidth_gbs=1000.0))

    assert chosen is not None
    assert chosen["catalog_id"] == "sd15"
    assert chosen["size"] == "512x512"  # its own resolution, not a house default


def test_nothing_is_picked_when_nothing_fits() -> None:
    """None is the honest answer; the endpoint turns it into a 503."""
    assert imagine.pick([]) is None
    assert imagine.pick(imagine.rank([FLUX], budget_gb=1.0, bandwidth_gbs=1000.0)) is None


def test_non_image_kinds_are_not_candidates() -> None:
    """The LLM picker ignores image models; the favour has to be returned."""
    rows = [SD15, {"id": "qwen3:8b", "kind": "llm", "size_b": 8, "ram_gb": 5.6}]
    assert [p["catalog_id"] for p in imagine.rank(rows, budget_gb=24.0)] == ["sd15"]


def test_the_bundled_catalogue_carries_image_models_that_actually_run() -> None:
    """A capability with nothing to point it at is not a capability."""
    entries = [e for e in catalog.load_catalog() if e.get("kind") == "image"]

    assert len(entries) >= 4
    for entry in entries:
        assert imagine.hf_id(entry), entry["id"]
        assert entry.get("backends") == ["diffusers"], entry["id"]
        assert imagine.steps_for(entry) >= 1
        # Sized, and sized small enough that a consumer card can offload it.
        assert imagine.footprint_gb(entry, offload=True) < 40, entry["id"]

    # And the small end of the range reaches a genuinely modest machine, or the
    # endpoint would 503 on most laptops.
    smallest = min(entries, key=lambda e: imagine.footprint_gb(e))
    assert imagine.footprint_gb(smallest) < 4.0


def test_native_size_is_read_from_the_catalogue_and_defaults_sanely() -> None:
    """The one size a diffusion model is good at, so `auto` resolves to it."""
    assert imagine.native_size(SD15) == (512, 512)
    assert imagine.native_size(SDXL) == (1024, 1024)
    assert imagine.native_size({"id": "x"}) == (1024, 1024)
    assert imagine.native_size({"id": "x", "native_size": "bad"}) == (1024, 1024)


# ---------------------------------------------------------------------------
# The adapter, with a fake diffusers
# ---------------------------------------------------------------------------


class _FakeImage:
    """Stands in for a PIL image: all `generate` needs is `.save`."""

    def save(self, buffer: Any, format: str = "PNG") -> None:  # noqa: A002 - PIL's own name
        buffer.write(b"\x89PNG\r\n\x1a\n" + format.encode())


@pytest.fixture()
def fake_torch(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """A torch stand-in, for the dtype and device decisions `load` makes.

    The adapter asks torch three things — is there CUDA, is there MPS, and what
    is float16 — before it asks diffusers for anything, so faking the pipeline
    alone leaves the import failing on the line above it.
    """
    module = types.ModuleType("torch")
    module.float16 = "float16"  # type: ignore[attr-defined]
    module.float32 = "float32"  # type: ignore[attr-defined]
    module.bfloat16 = "bfloat16"  # type: ignore[attr-defined]
    module.cuda = types.SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    module.backends = types.SimpleNamespace(  # type: ignore[attr-defined]
        mps=types.SimpleNamespace(is_available=lambda: False)
    )

    class _Generator:
        def __init__(self, device: str = "cpu") -> None:
            self.device = device

        def manual_seed(self, seed: int) -> _Generator:
            self.seed = seed
            return self

    module.Generator = _Generator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", module)
    return module


@pytest.fixture()
def fake_diffusers(
    monkeypatch: pytest.MonkeyPatch, fake_torch: types.ModuleType
) -> types.ModuleType:
    """Install a module named ``diffusers`` that answers the adapter's calls."""

    class _Pipeline:
        calls: list[dict[str, Any]] = []
        offloaded = False
        device = "cpu"

        def __call__(self, **kwargs: Any) -> Any:
            _Pipeline.calls.append(kwargs)
            return types.SimpleNamespace(images=[_FakeImage()])

        def enable_model_cpu_offload(self) -> None:
            _Pipeline.offloaded = True

        def to(self, _device: str) -> _Pipeline:
            return self

    class _AutoPipeline:
        loads: list[tuple[str, dict[str, Any]]] = []

        @staticmethod
        def from_pretrained(model: str, **kwargs: Any) -> _Pipeline:
            _AutoPipeline.loads.append((model, kwargs))
            return _Pipeline()

    module = types.ModuleType("diffusers")
    module.AutoPipelineForText2Image = _AutoPipeline  # type: ignore[attr-defined]
    _Pipeline.calls = []
    _Pipeline.offloaded = False
    monkeypatch.setitem(sys.modules, "diffusers", module)
    return module


def test_generate_returns_png_bytes_and_passes_the_knobs_through(
    fake_diffusers: types.ModuleType,
) -> None:
    """Every argument here is one a local caller can use and a hosted API hides."""
    png = imagine.generate(
        "a red bicycle",
        model="stabilityai/sdxl-turbo",
        width=512,
        height=512,
        steps=4,
        guidance=0.0,
        negative_prompt="blurry",
        seed=11,
    )

    assert png.startswith(b"\x89PNG")
    model, _load_kwargs = fake_diffusers.AutoPipelineForText2Image.loads[-1]
    assert model == "stabilityai/sdxl-turbo"

    pipeline_cls = type(fake_diffusers.AutoPipelineForText2Image.from_pretrained("probe"))
    call = pipeline_cls.calls[-1]
    assert call["prompt"] == "a red bicycle"
    assert call["num_inference_steps"] == 4
    assert call["guidance_scale"] == 0.0
    assert call["negative_prompt"] == "blurry"
    assert call["width"] == 512


def test_a_loaded_pipeline_is_reused_across_images(
    fake_diffusers: types.ModuleType,
) -> None:
    """Loading one is seconds to minutes; paying that per image is unusable."""
    pipeline = imagine.load("x/y")
    before = len(fake_diffusers.AutoPipelineForText2Image.loads)
    for _ in range(3):
        imagine.generate("x", model="x/y", loaded=pipeline)

    assert len(fake_diffusers.AutoPipelineForText2Image.loads) == before


def test_offload_is_requested_on_the_pipeline_when_asked(
    fake_diffusers: types.ModuleType,
) -> None:
    """The sizing promises components take turns; the adapter has to arrange it."""
    imagine.load("x/y", offload=True)

    pipeline_cls = type(fake_diffusers.AutoPipelineForText2Image.from_pretrained("probe"))
    assert pipeline_cls.offloaded is True


def test_a_missing_runtime_raises_the_repair_command() -> None:
    """diffusers is a core dependency, so this path means a broken install."""
    if imagine.available():  # pragma: no cover - the normal case
        pytest.skip("diffusers imports here, so the broken-install path cannot run")

    with pytest.raises(ImportError, match="install is incomplete"):
        imagine.load("stabilityai/sdxl-turbo")
