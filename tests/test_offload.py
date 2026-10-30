"""
Tests for best_engine_ai_helper.offload — the layer-streaming backend.

Streaming is the one backend whose arithmetic cannot be checked against a
running server here, so these tests pin it against two outside anchors instead:
the published configuration of real checkpoints (decoder depth, stored dtype)
and lightweight's own published memory figures. Where the two disagree, the comment
says which way and by how much.

Everything is synthetic and offline. No test imports lightweight, and the three that
exercise the adapter inject a fake runtime through ``sys.modules`` — the point
being that the whole decision layer has to work on a machine where the extra
was never installed, which is most machines.
"""

from __future__ import annotations

import math
import types
from typing import Any

import pytest

from best_engine_ai_helper import catalog, engine, offload, score

# Real checkpoints, with the two fields that drive every figure below taken
# from each model's published config: `layers` is `num_hidden_layers`, `dtype`
# is what the safetensors actually hold.
LLAMA_70B = {
    "id": "llama3.3:70b",
    "kind": "llm",
    "size_b": 70,
    "layers": 80,
    "dtype": "bf16",
    # What a conventional backend would need to hold it resident -- carried so
    # these entries are sizeable under every backend, like real ones.
    "ram_gb": 155,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
    "benchmarks": {"general": 86},
}
QWEN_32B = {"id": "qwen3:32b", "kind": "llm", "size_b": 32, "layers": 64, "hf_id": "Qwen/Qwen3-32B"}
DEEPSEEK_V3 = {
    "id": "deepseek-v3:671b",
    "kind": "llm",
    "size_b": 671,
    "layers": 61,
    "dtype": "fp8",
    "moe": True,
    "hf_id": "deepseek-ai/DeepSeek-V3",
}
VLM_72B = {
    "id": "qwen2.5-vl:72b",
    "kind": "vlm",
    "size_b": 73,
    "layers": 80,
    "hf_id": "Qwen/Qwen2.5-VL-72B-Instruct",
}
SMALL = {
    "id": "qwen3:8b",
    "kind": "llm",
    "size_b": 8,
    "layers": 32,
    "ram_gb": 5.6,
    "hf_id": "Qwen/Qwen3-8B",
    "benchmarks": {"general": 74},
}

# A fast NVMe with room to spare, and the same drive on a nearly-full machine.
FAST_DISK = {"storage": "nvme", "read_gbs": 4.0, "basis": "declared", "free_gb": 4000.0}
FULL_DISK = {"storage": "nvme", "read_gbs": 4.0, "basis": "declared", "free_gb": 40.0}

MAC_8GB = {"unified_gb": 8.0, "vram_gb": None, "ram_gb": 8.0}
GPU_4GB = {"unified_gb": None, "vram_gb": 4.0, "ram_gb": 32.0}
GPU_24GB = {"unified_gb": None, "vram_gb": 24.0, "ram_gb": 64.0}

CUDA = {"accelerator": "gpu-cuda", "chip": "NVIDIA GeForce RTX 4090", "bandwidth_gbs": 1008.0}
METAL = {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0}
CPU_ONLY = {"accelerator": "cpu", "chip": None, "bandwidth_gbs": None}


# ---------------------------------------------------------------------------
# The footprint, against lightweight's own published figures
# ---------------------------------------------------------------------------


def test_the_footprint_brackets_airllms_published_figure_for_a_70b() -> None:
    """A 70B must land near lightweight's "~4 GB", not near its 141 GB checkpoint.

    This is the claim the whole backend rests on, so it is pinned from both
    sides: the serial figure is what fits on the 4 GB card lightweight advertises,
    and the prefetched one is the price of its ~10% speed-up.
    """
    serial = offload.footprint_gb(LLAMA_70B, prefetching=False)
    prefetched = offload.footprint_gb(LLAMA_70B, prefetching=True)

    assert 3.0 < serial < 4.5, serial
    assert prefetched == pytest.approx(serial * 2 - 1.75, abs=0.2)
    # And both are two orders of magnitude under the resident footprint the
    # same weights would need on any other backend.
    assert offload.checkpoint_gb(LLAMA_70B) == 140.0
    assert prefetched < offload.checkpoint_gb(LLAMA_70B) / 20


def test_a_smaller_checkpoint_dtype_shrinks_the_layer_and_the_traffic() -> None:
    """The dtype is the checkpoint's, not a knob: nothing here requantises.

    This used to be a `compression="4bit"` argument, and it was a lie -- the
    planner divided the bytes while the runtime read the repository exactly as
    published, so a 4-bit plan quoted a third of a run it would never deliver.
    The honest version is that a smaller dtype is a property of the repository
    you point at, which is why it arrives through the catalog entry.
    """
    plain = offload.footprint_gb(LLAMA_70B)
    small = offload.footprint_gb({**LLAMA_70B, "dtype": "q4"})

    assert offload.checkpoint_gb({**LLAMA_70B, "dtype": "q4"}) == 35.0
    assert small < plain
    # The KV cache and the activation allowance do not shrink with the weights,
    # so the saving is on the layer term only -- which is why it is not 4x.
    assert small > plain / 4


def test_the_kv_cache_is_not_streamed_and_a_long_context_shows_it() -> None:
    """Keys and values stay resident for every layer, so context costs memory.

    The failure this guards is the flattering one: treat the cache as "one
    layer's worth" and a 32k-context plan looks like a 4k-context plan, which
    is how a machine OOMs halfway through a long job.
    """
    short = offload.footprint_gb(LLAMA_70B, context_k=4)
    long = offload.footprint_gb(LLAMA_70B, context_k=32)

    assert offload.kv_cache_gb(80, 4) == pytest.approx(1.25)
    growth = offload.kv_cache_gb(80, 32) - offload.kv_cache_gb(80, 4)
    assert long - short == pytest.approx(growth, abs=0.1)  # footprints round to a tenth
    assert long > short * 2


def test_an_unsizeable_entry_reports_infinity_rather_than_nothing() -> None:
    """Absent is not zero: a model with no size must not fit every machine."""
    assert offload.footprint_gb({"id": "mystery"}) == float("inf")
    assert offload.checkpoint_gb({"id": "mystery"}) == float("inf")
    # A MoE model without a declared depth is the real-world case: the dense
    # depth-versus-size trend does not hold for it, so guessing is refused.
    assert offload.footprint_gb({"id": "x", "size_b": 671, "moe": True}) == float("inf")
    assert offload.layer_count({"id": "x", "size_b": 671, "moe": True}) == (None, False)
    # Declared, it sizes fine.
    assert offload.footprint_gb(DEEPSEEK_V3) < 30


def test_depth_is_interpolated_for_a_dense_model_and_marked_as_estimated() -> None:
    """A caller has to be able to tell a declared depth from a guessed one."""
    assert offload.layer_count(LLAMA_70B) == (80, False)
    assert offload.layer_count({"size_b": 70}) == (80, True)
    # Monotone between the table's points, which is the property that matters:
    # a bigger model never reports a shallower network.
    depths = [offload.layer_count({"size_b": s})[0] for s in (1, 3, 8, 14, 32, 70, 405)]
    assert None not in depths
    assert depths == sorted(d for d in depths if d is not None)


# ---------------------------------------------------------------------------
# Throughput: the disk, not the memory bus
# ---------------------------------------------------------------------------


def test_throughput_is_bounded_by_the_disk_and_reported_in_both_units() -> None:
    """Every token re-reads the checkpoint, so the drive sets the rate."""
    tps = offload.estimated_tokens_per_second(LLAMA_70B, 4.0)
    assert tps is not None
    assert tps == pytest.approx(4.0 / 140.0 * 0.85, rel=0.02)
    assert offload.seconds_per_token(tps) == pytest.approx(41.7, abs=0.5)

    # Halve the drive and the rate halves: nothing else enters the estimate.
    assert offload.estimated_tokens_per_second(LLAMA_70B, 2.0) == pytest.approx(tps / 2, rel=0.02)
    # A spinning disk is the difference between a batch job and a fortnight.
    hdd = offload.seconds_per_token(offload.estimated_tokens_per_second(LLAMA_70B, 0.12))
    assert hdd is not None and hdd >= 1000


def test_an_unknown_drive_yields_no_rate_rather_than_a_confident_zero() -> None:
    """The distinction this package keeps everywhere: unknown is not small."""
    assert offload.estimated_tokens_per_second(LLAMA_70B, None) is None
    assert offload.estimated_tokens_per_second(LLAMA_70B, 0.0) is None
    assert offload.estimated_tokens_per_second({"id": "unsized"}, 4.0) is None
    assert offload.seconds_per_token(None) is None


def test_score_routes_the_streaming_backend_to_the_disk_bound_estimate() -> None:
    """`score` is the seam every surface calls, so the switch must happen there.

    Handing the streaming backend a memory-bandwidth figure would report a rate
    a thousand times too high — the single most misleading number this feature
    could produce.
    """
    # An 8B model, so both backends can actually serve it and the two numbers
    # describe the same job rather than two different ones.
    memory_bound = score.estimated_tokens_per_second(SMALL, 400.0, "ollama", calibrated=False)
    disk_bound = score.estimated_tokens_per_second(
        SMALL, 400.0, "lightweight", calibrated=False, disk_read_gbs=4.0
    )

    assert disk_bound is not None and memory_bound is not None
    assert disk_bound < memory_bound / 100
    assert disk_bound == offload.estimated_tokens_per_second(SMALL, 4.0)
    # And the footprint switches with it.
    assert score.model_footprint_gb(LLAMA_70B, "lightweight") == offload.footprint_gb(LLAMA_70B)


def test_a_measured_ollama_rate_is_never_reused_as_a_streaming_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A measurement is per (model, machine) but emphatically not per backend."""
    from best_engine_ai_helper import throughput

    monkeypatch.setattr(throughput, "measured_tps", lambda *a, **k: 30.0)

    [ollama_row] = score.rank(GPU_24GB, [SMALL], "llm", bandwidth_gbs=400.0)
    [stream_row] = score.rank(
        GPU_24GB, [SMALL], "llm", backend="lightweight", bandwidth_gbs=400.0, disk_read_gbs=4.0
    )

    assert ollama_row["_tps"] == 30.0 and ollama_row["_tps_basis"] == "measured"
    assert stream_row["_tps_basis"] == "estimated"
    assert stream_row["_tps"] is not None and stream_row["_tps"] < 1.0


# ---------------------------------------------------------------------------
# Disk space, the constraint that actually bites
# ---------------------------------------------------------------------------


def test_streaming_needs_the_checkpoint_and_no_scratch_space() -> None:
    """The hard half of streaming used to be the disk, and no longer is.

    The previous runtime decomposed the checkpoint into per-layer shards
    beside the original before anything ran, so the cache held both at once:
    ~294 GB free to stream a 70B that only weighs ~140. That is what made
    nearly every row of `lightweight plan` read `runs: NO` on a normal
    laptop -- the models fit in memory-per-layer terms and failed on scratch.

    `streaming.py` reads one tensor at a time out of the original
    safetensors, which are memory-mapped and carry their own index. Nothing
    is copied, so peak and steady are both just the checkpoint.
    """
    space = offload.disk_required_gb(LLAMA_70B)

    assert space["peak_gb"] == offload.checkpoint_gb(LLAMA_70B)
    assert space["steady_gb"] == space["peak_gb"]
    # What is on disk is whatever the checkpoint ships: this runtime does not
    # requantise, so the only way to need less disk is a smaller repository.
    assert offload.disk_required_gb({**LLAMA_70B, "dtype": "q4"}) == {
        "peak_gb": space["peak_gb"] / 4,
        "steady_gb": space["steady_gb"] / 4,
    }


def test_peak_equals_steady_for_every_model_in_the_catalogue() -> None:
    """The equality is a property of the runtime, not a coincidence of one model.

    `ai-bunker` reads `disk_peak_gb` and `disk_steady_gb` out of the engine
    descriptor, and a consumer holding two keys that happen to match has no way
    to tell whether to budget for a transient. Asserting it on one checkpoint
    (the test above) shows the function returns the same value twice; asserting
    it on all 51 shows there is no entry shape -- no dtype, no mixture of
    experts, no missing parameter count -- that makes them diverge.

    Infinity is the honest answer for an unsized entry and has to stay equal
    too, which is why the comparison is written to survive it.
    """
    rows = catalog.load_catalog()
    assert len(rows) > 20, "the catalogue shrank; this test is no longer a sweep"
    for row in rows:
        space = offload.disk_required_gb(row)
        peak, steady = space["peak_gb"], space["steady_gb"]
        assert repr(peak) == repr(steady), f"{row.get('id')}: {peak} != {steady}"
        checkpoint = offload.checkpoint_gb(row)
        if math.isfinite(checkpoint):
            assert steady == round(checkpoint, 1), row.get("id")


def test_a_nearly_full_drive_blocks_a_model_that_fits_memory_easily() -> None:
    """The most common real refusal, and it has nothing to do with memory."""
    roomy = offload.plan(LLAMA_70B, budget_gb=24.0, disk=FAST_DISK)
    cramped = offload.plan(LLAMA_70B, budget_gb=24.0, disk=FULL_DISK)

    assert roomy["usable"] and roomy["blockers"] == []
    assert cramped["fits"] is True  # memory was never the problem
    assert cramped["disk_fits"] is False
    assert cramped["usable"] is False
    # The reason has to name the real constraint. It used to say "free during
    # the layer split", describing a step that no longer happens -- and quoting
    # the same number twice as though one were a transient peak.
    assert any("the checkpoint is" in b and "is free" in b for b in cramped["blockers"])
    assert not any("split" in b for b in cramped["blockers"])


# ---------------------------------------------------------------------------
# The budget: why streaming does not pay the headroom twice
# ---------------------------------------------------------------------------


def test_streaming_sizes_against_the_whole_usable_pool() -> None:
    """A transient shard must not be discounted by a margin held for a resident model.

    With the headroom applied, a 4 GB card's budget is 1.84 GB and a 70B model
    -- lightweight's own headline claim -- is rejected on the very hardware it was
    demonstrated on.
    """
    assert offload.budget_gb(GPU_4GB) == pytest.approx(score.usable_pool_gb(GPU_4GB))
    assert offload.budget_gb(GPU_4GB) > score.effective_budget(GPU_4GB)
    # lightweight's headline claim, stated exactly: a 70B fits a 4 GB card at the
    # short context its demo uses, and the KV cache is what takes it over at 4k.
    short_ctx = offload.footprint_gb(LLAMA_70B, prefetching=False, context_k=1)
    assert short_ctx < offload.budget_gb(GPU_4GB)
    assert offload.footprint_gb(LLAMA_70B, prefetching=False, context_k=4) > short_ctx

    # Live load still caps it: a shard shares the machine with everything else.
    assert offload.budget_gb(GPU_24GB, load={"available_ram_gb": 3.0}) == 3.0


def test_a_candidate_that_misses_with_prefetching_is_retried_without_it() -> None:
    """The one knob behind "70B on a 4 GB card", and it must be tried, not assumed."""
    # 4.6 GB sits between the serial footprint (3.9) and the prefetched one
    # (6.1), which is exactly the window the retry exists for.
    gpu_5gb = {"unified_gb": None, "vram_gb": 5.0, "ram_gb": 32.0}
    plans = offload.rank([LLAMA_70B], budget_gb=offload.budget_gb(gpu_5gb), disk=FAST_DISK)

    assert len(plans) == 1
    assert plans[0]["fits"] is True
    assert plans[0]["prefetching"] is False  # the retry is what made it fit
    # Serial reads overlap nothing, so the honest rate is lower too.
    serial_rate = offload.estimated_tokens_per_second(LLAMA_70B, 4.0, prefetching=False)
    assert plans[0]["est_tokens_per_s"] == serial_rate


# ---------------------------------------------------------------------------
# The pick: bigger, not leaner
# ---------------------------------------------------------------------------


def test_the_pick_prefers_the_biggest_runnable_model_not_the_leanest() -> None:
    """The inversion that makes streaming worth having at all.

    Every other backend takes the leanest model within a quality band, because
    a gigabyte of residency is paid on every run. Under streaming residency is
    one shard whatever the size, so leanness buys nothing and the anti-greed
    rule lands on an 8B model -- which runs natively a hundred times faster and
    has no business being streamed.
    """
    pool = [SMALL, QWEN_32B, LLAMA_70B]
    chosen = offload.pick(offload.rank(pool, budget_gb=24.0, disk=FAST_DISK))

    assert chosen is not None
    assert chosen["catalog_id"] == "llama3.3:70b"
    assert chosen["size_b"] == 70


def test_when_nothing_clears_the_batch_floor_the_least_slow_option_wins() -> None:
    """ "Everything here is too slow" is better answered with the fastest, not the biggest."""
    slow_disk = {"storage": "hdd", "read_gbs": 0.12, "basis": "declared", "free_gb": 4000.0}
    plans = offload.rank([SMALL, LLAMA_70B], budget_gb=24.0, disk=slow_disk)
    chosen = offload.pick(plans)

    assert chosen is not None
    assert chosen["catalog_id"] == "qwen3:8b"
    assert chosen["usable"] is False


def test_nothing_is_picked_when_nothing_fits_memory_or_disk() -> None:
    """A None here is the honest answer, and the caller reports it as such."""
    assert offload.pick([]) is None
    assert offload.pick(offload.rank([LLAMA_70B], budget_gb=0.5, disk=FAST_DISK)) is None


def test_the_batch_floor_admits_the_models_streaming_exists_for() -> None:
    """A floor an order of magnitude too strict hides the whole capability.

    At 0.2 tok/s nothing above an 8B checkpoint passed on a 4 GB/s drive, which
    is to say nothing worth streaming. The floor has to sit where a slow answer
    is still an answer.
    """
    assert offload.COMFORT_TPS_STREAMING == 0.01
    assert offload.plan(LLAMA_70B, budget_gb=24.0, disk=FAST_DISK)["usable"] is True
    assert offload.plan(VLM_72B, budget_gb=24.0, disk=FAST_DISK)["usable"] is True
    # And it still refuses the genuinely absurd: 200 s/token.
    assert offload.plan(DEEPSEEK_V3, budget_gb=50.0, disk=FAST_DISK)["usable"] is False


def test_a_vlm_satisfies_an_llm_request_but_never_the_reverse() -> None:
    """The same kind rule the rest of the catalogue follows."""
    pool = [SMALL, VLM_72B]
    as_llm = offload.rank(pool, budget_gb=24.0, disk=FAST_DISK, kind="llm")
    as_vlm = offload.rank(pool, budget_gb=24.0, disk=FAST_DISK, kind="vlm")

    assert {p["catalog_id"] for p in as_llm} == {"qwen3:8b", "qwen2.5-vl:72b"}
    assert [p["catalog_id"] for p in as_vlm] == ["qwen2.5-vl:72b"]


# ---------------------------------------------------------------------------
# The activation policy
# ---------------------------------------------------------------------------


def test_streaming_is_not_offered_when_a_model_already_fits() -> None:
    """The automatic trigger fires on "no model at all", never on preference."""
    decision = offload.decide(conventional_resolved=True, compute=CUDA, disk=FAST_DISK, env={})

    assert decision["activate"] is False
    assert decision["trigger"] == "not-needed"
    assert "already fits" in decision["reason"]


def test_streaming_is_offered_when_the_conventional_backend_found_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rescue case: streaming is the difference between a model and none."""
    monkeypatch.setattr(offload, "available", lambda: True)
    decision = offload.decide(conventional_resolved=False, compute=CUDA, disk=FAST_DISK, env={})

    assert decision["activate"] is True
    assert decision["trigger"] == "fallback"
    assert decision["runtime"] == "cuda"
    assert "seconds per token" in decision["reason"]


def test_a_human_can_ask_for_streaming_on_a_machine_that_does_not_need_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual activation is not second-guessed, only costed."""
    monkeypatch.setattr(offload, "available", lambda: True)
    decision = offload.decide(
        request="always", conventional_resolved=True, compute=METAL, disk=FAST_DISK, env={}
    )

    assert decision["activate"] is True
    assert decision["trigger"] == "manual"
    assert decision["runtime"] == "mps"


def test_never_wins_over_everything_including_the_automatic_trigger() -> None:
    """The escape hatch has to be absolute or it is not one."""
    for request in ("never", "off", "0", False):
        decision = offload.decide(
            request=request, conventional_resolved=False, compute=CUDA, disk=FAST_DISK, env={}
        )
        assert decision["activate"] is False
        assert decision["trigger"] == "disabled"

    # And from the environment, with no brief involved at all.
    env_off = offload.decide(
        conventional_resolved=False,
        compute=CUDA,
        disk=FAST_DISK,
        env={"BEST_ENGINE_LIGHTWEIGHT": "never"},
    )
    assert env_off["activate"] is False


def test_the_brief_outranks_the_environment() -> None:
    """Same precedence as every other setting here: explicit beats ambient."""
    assert offload.requested("always", env={"BEST_ENGINE_LIGHTWEIGHT": "never"}) == "always"
    assert offload.requested(None, env={"BEST_ENGINE_LIGHTWEIGHT": "never"}) == "never"
    assert offload.requested(None, env={}) == "auto"


def test_a_typo_in_the_request_is_an_error_not_a_silent_default() -> None:
    """`lightweight: alwyas` must not read as "streaming quietly disabled"."""
    with pytest.raises(ValueError, match="auto/always/never"):
        offload.normalize_request("alwyas")


def test_a_machine_with_no_streaming_runtime_says_so_before_the_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CPU-only box is told at resolution, not at generate() time."""
    monkeypatch.setattr(offload, "available", lambda: True)
    decision = offload.decide(request="always", compute=CPU_ONLY, disk=FAST_DISK, env={})

    assert decision["activate"] is False
    assert decision["runtime"] is None
    assert any("no accelerator to stream on" in b for b in decision["blockers"])
    # Experimental, so it has to be asked for by name rather than assumed.
    assert offload.runtime(CPU_ONLY, allow_cpu=True) == "cpu"


def test_an_unimportable_runtime_is_reported_with_the_command_that_fixes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocker nobody can act on is just a refusal."""
    monkeypatch.setattr(offload, "available", lambda: False)
    decision = offload.decide(request="always", compute=CUDA, disk=FAST_DISK, env={})

    assert decision["activate"] is False
    assert decision["installed"] is False
    assert any(offload.INSTALL_HINT in b for b in decision["blockers"])


# ---------------------------------------------------------------------------
# What the catalogue will and will not offer to streaming
# ---------------------------------------------------------------------------


def test_only_entries_naming_a_hub_repository_can_be_streamed() -> None:
    """lightweight downloads safetensors; a pull tag names nothing it can read."""
    assert catalog.servable(LLAMA_70B, "lightweight") is True
    assert catalog.servable({"id": "gemma3:12b"}, "lightweight") is False
    # `vllm_id` is the same repository under the name this catalogue has
    # always used, so no entry has to be edited twice.
    assert catalog.servable({"id": "x", "vllm_id": "a/b"}, "lightweight") is True


def test_the_bundled_catalogue_carries_models_only_streaming_can_run() -> None:
    """Otherwise the backend is a capability with nothing to point it at."""
    entries = catalog.load_catalog()
    streaming_only = [e for e in entries if e.get("backends") == ["lightweight"]]

    assert len(streaming_only) >= 5
    for entry in streaming_only:
        # Each one must be sizeable for streaming...
        assert offload.footprint_gb(entry) < 30, entry["id"]
        # ...and genuinely out of reach of the backends it is withheld from,
        # which is what justifies withholding it.
        assert score.model_footprint_gb(entry, "ollama") > 100, entry["id"]
        assert catalog.servable(entry, "ollama") is False
        assert offload.hf_id(entry) is not None


# ---------------------------------------------------------------------------
# Resolution: the engine file a consumer actually reads
# ---------------------------------------------------------------------------


def _streamable_catalog() -> list[dict[str, Any]]:
    # No VLM: one legitimately satisfies an `llm` request (vision subsumes
    # text), and the 73B winning over the 70B is correct but not what this
    # test is about.
    return [SMALL, QWEN_32B, LLAMA_70B]


def test_resolving_for_streaming_writes_the_facts_a_caller_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Including the two that decide whether the job is feasible at all."""
    monkeypatch.setattr(offload, "available", lambda: True)
    descriptor = engine.resolve(
        {"kind": "llm", "task": "general assistant", "structured_output": False},
        backend="lightweight",
        catalog=_streamable_catalog(),
        hw=GPU_24GB,
        compute=CUDA,
        disk=FAST_DISK,
    )

    assert descriptor["backend"] == "lightweight"
    # No URL: lightweight is a library, and a localhost port would send a consumer
    # looking for a daemon that will never exist.
    assert descriptor["base_url"] == ""
    section = descriptor["llm"]
    assert section["model"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert section["streaming"] is True
    assert section["structured_output"] is False
    assert section["seconds_per_token"] > 1
    # Equal, not greater: there is no split copy to make room for any more.
    assert section["disk_peak_gb"] == section["checkpoint_gb"]
    assert descriptor["min_tps"] == offload.COMFORT_TPS_STREAMING
    assert descriptor["serve"] == [
        "best-engine-ai-helper lightweight prepare --model meta-llama/Llama-3.3-70B-Instruct"
    ]


def test_a_kind_with_nothing_fitting_is_rescued_and_the_rest_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mixed descriptor is the honest outcome, and `model_for` has to read it.

    The catalogue here holds one Ollama-servable VLM too heavy for the machine
    and one streamable LLM that fits as shards. So the VLM finds nothing and is
    rescued; the LLM is resolved conventionally and must be left exactly as it
    was. A rescue that dragged the whole descriptor onto a streaming backend
    would cost the LLM a hundredfold in speed for no reason.
    """
    monkeypatch.setattr(offload, "available", lambda: True)
    rows = [
        # Fits Ollama's 11 GB budget on this card: the kind that needs no rescue.
        {
            "id": "small-llm:1b",
            "kind": "llm",
            "size_b": 1,
            "ram_gb": 1.5,
            "benchmarks": {"general": 50},
        },
        # A VLM far over that budget, and no smaller one exists here.
        {
            "id": "huge-vlm:72b",
            "kind": "vlm",
            "size_b": 72,
            "ram_gb": 52.0,
            "benchmarks": {"general": 88, "vision": 91},
        },
        VLM_72B,  # streamable: names a Hub repository and declares its depth
    ]
    descriptor = engine.resolve(
        {"kind": "both", "task": "describe images", "structured_output": False},
        backend="ollama",
        catalog=rows,
        hw=GPU_24GB,
        compute=CUDA,
        disk=FAST_DISK,
    )

    assert descriptor["backend"] == "ollama"
    assert descriptor["lightweight"]["activate"] is True
    assert descriptor["lightweight"]["trigger"] == "fallback"
    assert descriptor["lightweight"]["rescued"] == ["vlm"]

    # The rescued kind carries its own backend...
    assert engine.model_for(descriptor, "vlm") == (
        "lightweight",
        "",
        "Qwen/Qwen2.5-VL-72B-Instruct",
    )
    # ...and the kind that never needed one is untouched.
    backend, base_url, model = engine.model_for(descriptor, "llm")
    assert (backend, model) == ("ollama", "small-llm:1b")
    assert base_url.startswith("http")


def test_an_activated_rescue_that_rescues_nothing_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A machine too small for a model can be too small for a shard, too.

    `activate: true` with an empty `rescued` is that case. Left implicit, a
    consumer would read the activation as a promise and find the kind still
    null.
    """
    monkeypatch.setattr(offload, "available", lambda: True)
    descriptor = engine.resolve(
        {"kind": "llm", "task": "general assistant", "structured_output": False},
        backend="ollama",
        catalog=catalog.load_catalog(),
        hw={"unified_gb": None, "vram_gb": None, "ram_gb": 1.0},
        compute=CUDA,
        disk=FULL_DISK,
    )

    assert descriptor["lightweight"]["activate"] is True
    assert descriptor["lightweight"]["rescued"] == []


def test_a_machine_with_room_never_hears_about_streaming() -> None:
    """Silence is the feature: the escalation must not editorialise."""
    descriptor = engine.resolve(
        {"kind": "llm", "task": "general assistant"},
        backend="ollama",
        catalog=catalog.load_catalog(),
        hw={"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0},
        compute=METAL,
        disk=FAST_DISK,
    )

    assert "lightweight" not in descriptor
    assert descriptor["backend"] == "ollama"


def test_never_in_the_brief_suppresses_the_rescue_entirely() -> None:
    """Even on a machine where nothing fits, which is where it would fire."""
    descriptor = engine.resolve(
        {"kind": "llm", "task": "general assistant", "lightweight": "never"},
        backend="ollama",
        catalog=catalog.load_catalog(),
        hw={"unified_gb": None, "vram_gb": None, "ram_gb": 2.0},
        compute=CUDA,
        disk=FAST_DISK,
    )

    assert "lightweight" not in descriptor


def test_an_unusable_machine_records_why_instead_of_staying_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine file is where a consumer looks; a bare absence explains nothing."""
    monkeypatch.setattr(offload, "available", lambda: False)
    descriptor = engine.resolve(
        {"kind": "llm", "task": "general assistant"},
        backend="ollama",
        catalog=catalog.load_catalog(),
        hw={"unified_gb": None, "vram_gb": None, "ram_gb": 2.0},
        compute=CUDA,
        disk=FAST_DISK,
    )

    assert descriptor["lightweight"]["activate"] is False
    assert any(offload.INSTALL_HINT in b for b in descriptor["lightweight"]["blockers"])
    # The conventional pick is untouched: a failed rescue must not break what
    # already worked.
    assert descriptor["llm"]["model"]


# ---------------------------------------------------------------------------
# The adapter, with a fake runtime standing in for lightweight
# ---------------------------------------------------------------------------


class _FakeTokens(dict[Any, Any]):
    """Minimal stand-in for a tokenizer's batch-encoding mapping."""

    def to(self, _device: str) -> _FakeTokens:  # noqa: D102 - mirrors torch's API
        return self


@pytest.fixture()
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stand in for :class:`streaming.StreamedModel`, which `load` now builds.

    The adapter used to be tested by injecting a module named ``airllm`` into
    ``sys.modules``, because that is what it imported. It imports this
    project's own runtime now, so the seam moved from "a third-party package"
    to "a class we own" -- which is the whole point of the change.
    """

    class _Tokenizer:
        """Echoes the prompt back from `decode`, as every causal LM does."""

        last: str = ""

        def __call__(self, prompts: list[str], **_: Any) -> _FakeTokens:
            _Tokenizer.last = prompts[0]
            return _FakeTokens({"input_ids": _FakeTokens({0: prompts[0]})})

        def decode(self, sequence: Any, **_: Any) -> str:
            return f"{_Tokenizer.last} the streamed answer"

    built: list[tuple[str, dict[str, Any]]] = []
    generated: list[dict[str, Any]] = []

    class _Streamed:
        device = "cpu"

        def __init__(self, model: str, **kwargs: Any) -> None:
            self.tokenizer = _Tokenizer()
            built.append((model, kwargs))

        def generate(self, _ids: Any, **kwargs: Any) -> Any:
            generated.append(kwargs)
            return types.SimpleNamespace(sequences=[[1, 2, 3]])

    monkeypatch.setattr("best_engine_ai_helper.streaming.StreamedModel", _Streamed, raising=True)
    return {"built": built, "generated": generated}


def test_the_adapter_passes_the_runtimes_arguments_through_unrenamed(
    fake_runtime: dict[str, Any],
) -> None:
    """The streaming runtime's own vocabulary stays the reference for them."""
    offload.load(
        "meta-llama/Llama-3.3-70B-Instruct",
        prefetching=False,
        hf_token="hf_xxx",
    )

    model, kwargs = fake_runtime["built"][-1]
    assert model == "meta-llama/Llama-3.3-70B-Instruct"
    assert kwargs["prefetching"] is False
    assert kwargs["hf_token"] == "hf_xxx"


def test_the_split_options_are_gone_rather_than_silently_ignored(
    fake_runtime: dict[str, Any],
) -> None:
    """They described a pre-split this runtime does not have.

    airllm wrote a second copy of the checkpoint, one file per layer, before
    anything ran -- which is why `compare` used to refuse 70B models on a
    laptop for want of ~294 GB of scratch. Reading per-tensor out of the
    original safetensors needs none of it, so `layer_shards_saving_path`,
    `delete_original` and `compression` have nothing left to mean. They are
    removed rather than accepted-and-ignored: a silent no-op lets a caller go
    on believing the option did something, and the only honest answer to
    "write the shards to my fast volume" is that there are no shards to write.
    """
    for dead in ("layer_shards_saving_path", "delete_original", "compression"):
        with pytest.raises(TypeError):
            offload.load("x/y", **{dead: "whatever"})


def test_the_context_length_configured_is_the_one_that_was_priced(
    fake_runtime: dict[str, Any],
) -> None:
    """The footprint is quoted for a 4k context, so 4k is what is configured.

    Left implicit, this package would quote a footprint for one context and
    run another -- the documentation and the behaviour disagreeing in the
    direction where a user loses the end of their prompt without being told.
    """
    offload.load("x/y")
    _, kwargs = fake_runtime["built"][-1]
    assert kwargs["max_seq_len"] == 4096

    # And a caller who wants more says so, in the same unit the footprint uses.
    offload.load("x/y", max_seq_len=32768)
    _, longer = fake_runtime["built"][-1]
    assert longer["max_seq_len"] == 32768
    # The KV term is what that costs, and it is already priced.
    assert offload.footprint_gb({"size_b": 70, "layers": 80}, context_k=32) > offload.footprint_gb(
        {"size_b": 70, "layers": 80}
    )


def test_generate_strips_the_echoed_prompt(fake_runtime: dict[str, Any]) -> None:
    """transformers returns prompt + continuation; `chat` wants the answer."""
    assert offload.generate("Hello", model="x/y") == "the streamed answer"


def test_generate_uses_one_contract_for_every_runtime(
    fake_runtime: dict[str, Any],
) -> None:
    """There used to be two, and the second one was broken everywhere it ran.

    airllm returned a transformers model on CUDA and, on macOS, a different
    class with no ``.device`` that took an mlx array and returned pre-decoded
    text. `generate` assumed the first for both, so every Apple Silicon
    machine raised ``AttributeError: 'AirLLMLlamaMlx' object has no attribute
    'device'`` at the first call. Owning the runtime collapses that into one
    contract: a transformers model with hooks on it, wherever it runs.
    """
    offload.generate("Hello", model="x/y", max_new_tokens=8)

    call = fake_runtime["generated"][-1]
    assert call["max_new_tokens"] == 8
    assert call["use_cache"] is True


def test_an_unimportable_runtime_raises_the_repair_command() -> None:
    """lightweight is a core dependency, so this path means a broken install.

    Which changes what the error has to say: not "opt into the extra" — there is
    no extra — but "your install is incomplete, here is the command". A message
    that tells someone to install what they already depend on sends them in a
    circle.
    """
    if offload.available():  # pragma: no cover - the normal case, lightweight is a dep
        pytest.skip("lightweight imports here, so the broken-install path cannot run")

    with pytest.raises(ImportError, match="install is incomplete"):
        offload.load("meta-llama/Llama-3.3-70B-Instruct")


def test_the_chat_transport_refuses_images_and_schemas_rather_than_faking_them(
    fake_runtime: dict[str, Any],
) -> None:
    """Both would be answered wrongly in a way nobody would notice.

    An image silently answered from the text alone, or a schema honoured in
    name only, are the two failure modes a streaming transport could hide. It
    raises instead, and the engine descriptor's `structured_output: false`
    keeps schema-driven calls off this path in the first place.
    """
    from best_engine_ai_helper import llm

    with pytest.raises(NotImplementedError, match="no vision path"):
        llm._chat_airllm(
            "describe", system=None, images=[b"png"], json_schema=None, model="x/y", temperature=0.0
        )
    with pytest.raises(NotImplementedError, match="JSON schema"):
        llm._chat_airllm(
            "extract",
            system=None,
            images=None,
            json_schema={"type": "object"},
            model="x/y",
            temperature=0.0,
        )
    # And a schema-less text call works, reporting no token counts rather than
    # a character estimate dressed up as one.
    text, usage = llm._chat_airllm(
        "Hello", system="Be brief", images=None, json_schema=None, model="x/y", temperature=0.0
    )
    assert text == "the streamed answer"
    assert usage == {"in_tokens": None, "out_tokens": None}


def test_the_loaded_model_is_reused_across_calls(fake_runtime: dict[str, Any]) -> None:
    """Splitting a 141 GB checkpoint per call would make the transport unusable."""
    from best_engine_ai_helper import llm

    llm._STREAMED.clear()
    before = len(fake_runtime["built"])
    for _ in range(3):
        llm._chat_airllm(
            "Hello", system=None, images=None, json_schema=None, model="x/y", temperature=0.0
        )

    assert len(fake_runtime["built"]) - before == 1
    llm._STREAMED.clear()


# ---------------------------------------------------------------------------
# Storage detection
# ---------------------------------------------------------------------------


def test_the_storage_class_is_named_or_unknown_never_guessed() -> None:
    """A fabricated disk speed would quietly set every streaming estimate."""
    from best_engine_ai_helper import detect

    profile = detect.disk_profile()
    assert profile["storage"] in ("apple-internal", "nvme", "ssd-sata", "hdd", "unknown")
    assert profile["basis"] in ("declared", "measured", "unknown")
    if profile["storage"] == "unknown":
        assert profile["read_gbs"] is None
        assert profile["basis"] == "unknown"
    else:
        assert profile["read_gbs"] > 0


def test_a_measurement_is_labelled_as_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured and assumed are different claims, and the report says which."""
    from best_engine_ai_helper import detect

    monkeypatch.setattr(detect, "measure_disk_read_gbs", lambda **_: 1.23)
    profile = detect.disk_profile(measure=True)

    assert profile == {**profile, "read_gbs": 1.23, "basis": "measured"}

    # A platform that cannot bypass its cache falls back to the class figure
    # rather than reporting a cached read as a disk read.
    monkeypatch.setattr(detect, "measure_disk_read_gbs", lambda **_: None)
    fallback = detect.disk_profile(measure=True)
    assert fallback["basis"] in ("declared", "unknown")


# ---------------------------------------------------------------------------
# The speed model: a forward pass is the unit, not a token
# ---------------------------------------------------------------------------


def test_a_pass_costs_one_read_of_the_checkpoint() -> None:
    """The atom every streamed timing is built from."""
    per_pass = offload.seconds_per_pass(LLAMA_70B, 4.0)

    assert per_pass is not None
    assert per_pass == pytest.approx(140.0 / 4.0 / 0.85, rel=0.01)
    # And the headline rate is exactly its reciprocal, so the two views of the
    # same number can never drift apart.
    tps = offload.estimated_tokens_per_second(LLAMA_70B, 4.0)
    # `rel`, not exact: the rate is published to three decimals, which at
    # these speeds is a 1% quantisation.
    assert tps == pytest.approx(1 / per_pass, rel=0.02)
    assert offload.seconds_per_pass(LLAMA_70B, None) is None


def test_the_prompt_rides_free_because_its_tokens_share_one_pass() -> None:
    """The one axis where streaming beats a resident model, and it is not small.

    A pass reads the checkpoint once whatever rides through it, so prompt
    length is nearly free — which makes streaming comparatively good at "long
    document in, short verdict out" and terrible at long answers. Getting this
    wrong in the other direction (charging per prompt token) would hide the
    only workload shape the backend is actually good at.
    """
    short = offload.generation_time(LLAMA_70B, 4.0, new_tokens=50, prompt_tokens=10)
    long = offload.generation_time(LLAMA_70B, 4.0, new_tokens=50, prompt_tokens=2000)

    assert short is not None and long is not None
    assert short["total_seconds"] == long["total_seconds"]
    assert long["prompt_is_free"] is True
    # Time to first token is one pass, prompt included — unusual, and worth
    # reporting as its own figure.
    assert short["time_to_first_token_s"] == short["seconds_per_pass"]

    # Past a few thousand tokens the per-layer compute stops being negligible,
    # and the estimate says so rather than pretending otherwise.
    huge = offload.generation_time(LLAMA_70B, 4.0, new_tokens=50, prompt_tokens=100_000)
    assert huge is not None and huge["prompt_is_free"] is False


def test_answer_length_is_what_actually_costs_time() -> None:
    """N tokens cost N passes, which is the whole shape of the trade."""
    ten = offload.generation_time(LLAMA_70B, 4.0, new_tokens=10)
    hundred = offload.generation_time(LLAMA_70B, 4.0, new_tokens=100)

    assert ten is not None and hundred is not None
    assert ten["passes"] == 10 and hundred["passes"] == 100
    assert hundred["total_seconds"] == pytest.approx(ten["total_seconds"] * 10, rel=0.01)


def test_batching_multiplies_throughput_in_time_and_costs_kv_in_memory() -> None:
    """The biggest lever the backend has, and it has to be priced on both sides.

    Eight prompts ride through each pass together, so eight answers arrive in
    the time of one. It is the only speed lever the backend actually has, now
    that on-the-fly quantisation is gone. The cost is eight KV caches, which
    `footprint_gb` has to charge or a batch job plans itself into an OOM.
    """
    single = offload.generation_time(LLAMA_70B, 4.0, new_tokens=50, batch=1)
    eight = offload.generation_time(LLAMA_70B, 4.0, new_tokens=50, batch=8)

    assert single is not None and eight is not None
    assert eight["total_seconds"] == single["total_seconds"]
    assert eight["effective_tps"] == pytest.approx(single["effective_tps"] * 8, rel=0.02)
    # Per-sequence decode is unchanged: batching does not make one answer come
    # out faster, it makes eight come out together.
    assert eight["decode_tps"] == single["decode_tps"]

    kv = offload.kv_cache_gb(80)
    assert offload.footprint_gb(LLAMA_70B, batch=8) == pytest.approx(
        offload.footprint_gb(LLAMA_70B) + 7 * kv, abs=0.2
    )


def test_a_quarter_of_the_bytes_is_four_times_the_rate() -> None:
    """Disk traffic is the whole timing model, so the ratio is exactly the bytes.

    There is no dequantisation derate any more, and that is not an omission:
    the old 0.75 factor was calibrated on airllm *doing* the quantisation on
    the way in. This runtime reads a repository already published at that
    dtype, so what it pays is the read and nothing else.
    """
    plain = offload.estimated_tokens_per_second(LLAMA_70B, 4.0)
    small = offload.estimated_tokens_per_second({**LLAMA_70B, "dtype": "q4"}, 4.0)

    assert plain is not None and small is not None
    assert small / plain == pytest.approx(4.0, abs=0.1)


def test_durations_are_rendered_the_way_a_person_would_say_them() -> None:
    """Six orders of magnitude, and "20361.6 s" communicates none of them."""
    assert offload.human_duration(0.5) == "0.5 s"
    assert offload.human_duration(45) == "45 s"
    assert offload.human_duration(600) == "10 min"
    assert offload.human_duration(20361) == "5.7 h"
    assert offload.human_duration(600000) == "6.9 days"
    assert offload.human_duration(None) == "?"


# ---------------------------------------------------------------------------
# Native versus streamed: the decision the backend forces
# ---------------------------------------------------------------------------


def _comparison(
    hw: dict[str, float | None], bandwidth_gbs: float = 1008.0, **kwargs: Any
) -> dict[str, Any]:
    # Two footprints per model, as a real catalogue entry carries: `ram_gb` is
    # the Ollama Q4 figure the native side sizes against, `size_b` drives the
    # bf16 checkpoint the streamed side reads.
    rows = [
        {
            "id": "small:8b",
            "kind": "llm",
            "size_b": 8,
            "layers": 32,
            "ram_gb": 5.6,
            "hf_id": "x/small",
            "benchmarks": {"general": 74},
        },
        {
            "id": "mid:14b",
            "kind": "llm",
            "size_b": 14,
            "layers": 48,
            "ram_gb": 9.9,
            "hf_id": "x/mid",
            "benchmarks": {"general": 79},
        },
        {
            "id": "big:70b",
            "kind": "llm",
            "size_b": 70,
            "layers": 80,
            "ram_gb": 48,
            "hf_id": "x/big",
            "benchmarks": {"general": 86},
        },
    ]
    return offload.compare(rows, hw=hw, disk=FAST_DISK, bandwidth_gbs=bandwidth_gbs, **kwargs)


def test_the_comparison_prices_both_sides_in_the_same_unit() -> None:
    """Benchmark points against seconds, which is the only comparable framing.

    A tokens-per-second column cannot be read across these backends — 26 and
    0.024 do not sit on one scale a person reasons about. Seconds for the same
    answer do.
    """
    report = _comparison(GPU_24GB, new_tokens=300)

    native_best = report["native"]["best"]
    streamed_best = report["streamed"]["best"]
    assert native_best["catalog_id"] == "mid:14b"  # best that fits AND is comfortable
    assert streamed_best["catalog_id"] == "big:70b"  # biggest that streams
    assert report["quality_gain"] == pytest.approx(7.0)
    assert report["slowdown"] > 100
    assert "benchmark points" in report["verdict"]
    assert streamed_best["answer_human"].endswith(("h", "min", "days"))


def test_the_verdict_says_stay_native_when_streaming_buys_nothing() -> None:
    """A capability that is not an improvement must not be recommended.

    On a large machine the best native model outscores anything streamable, so
    the honest verdict is to stay put — and the backend has to be willing to
    say so about itself.
    """
    # A machine that runs the 70B natively AND fast enough to be comfortable:
    # the memory alone is not enough, the comfort floor has to clear too.
    big_machine = {"unified_gb": 512.0, "vram_gb": None, "ram_gb": 512.0}
    report = _comparison(big_machine, bandwidth_gbs=3350.0, new_tokens=300)

    assert report["native"]["best"]["catalog_id"] == "big:70b"
    assert report["quality_gain"] <= 0
    assert "Stay native" in report["verdict"]


def test_when_nothing_fits_natively_streaming_is_not_a_trade() -> None:
    """It is the only option, and the verdict frames it that way."""
    tiny = {"unified_gb": None, "vram_gb": None, "ram_gb": 6.0}
    report = _comparison(tiny, new_tokens=300)

    assert report["native"]["best"] is None
    assert report["streamed"]["best"] is not None
    assert "only option" in report["verdict"]
    assert report["slowdown"] is None  # nothing to divide by


def test_the_comparison_scores_both_sides_on_the_task_axis() -> None:
    """A code brief must not choose between two models on their chat scores."""
    rows = [
        {
            "id": "chatty:8b",
            "kind": "llm",
            "size_b": 8,
            "layers": 32,
            "ram_gb": 5.6,
            "hf_id": "x/chatty",
            "benchmarks": {"general": 80, "code": 40},
        },
        {
            "id": "coder:70b",
            "kind": "llm",
            "size_b": 70,
            "layers": 80,
            "ram_gb": 155,
            "hf_id": "x/coder",
            "benchmarks": {"general": 70, "code": 92},
        },
    ]
    on_code = offload.compare(
        rows,
        hw=GPU_24GB,
        disk=FAST_DISK,
        bandwidth_gbs=1008.0,
        application="code",
        new_tokens=100,
    )

    assert on_code["streamed"]["best"]["score"] == 92
    assert on_code["quality_gain"] > 0  # the coder is worth the wait on code


def test_the_comparison_is_reachable_from_the_package_root() -> None:
    """Downstream packages import from the root, not from submodules."""
    import best_engine_ai_helper as root

    assert root.lightweight_compare is offload.compare
    assert root.lightweight_generation_time is offload.generation_time
    assert root.lightweight_seconds_per_pass is offload.seconds_per_pass


def test_a_bigger_slower_weaker_candidate_never_wins() -> None:
    """Dominated on every axis, so size alone must not carry it.

    The first rule here was "biggest that runs", and the side-by-side
    comparison showed what that costs: a 141B mixture-of-experts scoring 84 beat
    a dense 72B scoring 87 on parameter count, while taking twice as long per
    token. Nobody would choose that. Capability leads; size only decides where
    the benchmark is silent.
    """
    moe = {
        "id": "moe:141b",
        "kind": "llm",
        "size_b": 141,
        "layers": 56,
        "hf_id": "x/moe",
        "benchmarks": {"general": 84},
    }
    dense = {
        "id": "dense:72b",
        "kind": "llm",
        "size_b": 72,
        "layers": 80,
        "hf_id": "x/dense",
        "benchmarks": {"general": 87},
    }
    plans = offload.rank([moe, dense], budget_gb=24.0, disk=FAST_DISK)
    chosen = offload.pick(plans)

    assert chosen is not None
    assert chosen["catalog_id"] == "dense:72b"
    assert chosen["est_tokens_per_s"] > plans[-1]["est_tokens_per_s"]
    # The table's first row and the pick are the same model, or the display
    # contradicts the decision.
    assert plans[0]["catalog_id"] == chosen["catalog_id"]


def test_size_still_decides_when_no_benchmark_does() -> None:
    """An absent score ranks low and is honest; among silent entries, bigger wins."""
    small = {"id": "s", "kind": "llm", "size_b": 8, "layers": 32, "hf_id": "x/s"}
    large = {"id": "l", "kind": "llm", "size_b": 70, "layers": 80, "hf_id": "x/l"}
    scored_small = {**small, "benchmarks": {"general": 74}}

    both_silent = offload.pick(offload.rank([small, large], budget_gb=24.0, disk=FAST_DISK))
    one_scored = offload.pick(offload.rank([scored_small, large], budget_gb=24.0, disk=FAST_DISK))

    assert both_silent is not None and both_silent["catalog_id"] == "l"
    # A measured 74 outranks an unmeasured giant, the same way it does
    # everywhere else in this package.
    assert one_scored is not None and one_scored["catalog_id"] == "s"


def test_the_page_cache_is_not_credited_for_a_cyclic_layer_scan():
    """Charging every byte to the drive is correct, not conservative.

    The tempting "optimisation" is to credit the page cache with the shards it
    still holds, so a machine with free memory pays memory speed for part of a
    pass. It does not work: a pass reads layers 1..N in order and the next pass
    restarts at layer 1, which the tail of the previous pass evicted. A cyclic
    scan over a working set larger than the cache is the textbook
    least-recently-used pathology, and the expected hit rate is near zero
    rather than ``free_memory / checkpoint``.

    Pinned as a test because this was attempted in a sibling project and the
    mixing term shipped there before the access pattern was thought through.
    Anybody adding one here should have to delete this first.
    """
    entry = {"size_b": 70}
    # Same drive, same model, whatever the machine's memory: the figure is a
    # function of the checkpoint and the disk, and of nothing else.
    baseline = offload.seconds_per_pass(entry, 4.0)
    assert baseline == round(offload.checkpoint_gb(entry) / 4.0 / offload.stream_efficiency(), 3)
    # No keyword exists to pass free memory in, and that absence is the point.
    with pytest.raises(TypeError):
        offload.seconds_per_pass(entry, 4.0, free_ram_gb=512.0)  # type: ignore[call-arg]
