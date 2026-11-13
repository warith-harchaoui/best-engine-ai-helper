"""
The browser target: a ladder planned here, walked in the visitor's page.

Offline: the plan reads the bundled catalog, never the Hub, and the device is
simulated. These are the criteria the server-side picker never had — download
against observed bandwidth, shader-f16, deviceMemory, mobile, data saver,
storage, the cache — each pinned by a case.

Author
------
Warith HARCHAOUI <warithmetics@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from best_engine_ai_helper import browser as b
from best_engine_ai_helper.cli import cli

NO_CACHE = Path("/nonexistent/browser_cache.yaml")


@pytest.fixture()
def the_plan():
    return b.plan("rag-answer", catalog=b.load_browser_catalog(cache=NO_CACHE))


def _rung(c):
    return (c["model"].split("/")[1], c["dtype"])


def test_the_ladder_is_ordered_best_first_f16_first(the_plan):
    rungs = [_rung(c) for c in the_plan["candidates"]]
    assert rungs[:2] == [("gemma-4-E4B-it-ONNX", "q4f16"), ("gemma-4-E4B-it-ONNX", "q4")]
    assert rungs[-1] == ("gemma-4-E2B-it-ONNX", "q4")
    assert all(c["files"] and c["files"][0].startswith(b.HUB) for c in the_plan["candidates"])


def test_every_variant_lists_its_weight_shards():
    # The E4B weights are split over several shards; a missing shard is a model
    # that loads on the curator's machine and nowhere else. And weights kept
    # inside a single graph do not load in a browser at all (Qwen3-1.7B, left
    # out of the catalog for it): every variant must have external shards.
    for e in b.load_browser_catalog(cache=NO_CACHE):
        for v in e["variants"].values():
            graphs = [f for f in v["files"] if f.endswith(".onnx")]
            data = [f for f in v["files"] if ".onnx_data" in f]
            assert graphs and data, e["id"]
    e4b = next(e for e in b.load_browser_catalog(cache=NO_CACHE) if "E4B" in e["id"])
    assert any(f.endswith("_data_1") for f in e4b["variants"]["q4f16"]["files"])


def test_a_model_measured_below_the_floor_leaves_the_ladder(the_plan):
    # LFM2 1.2B scored 0.167 on rag-answer: kept in the catalog, out of the plan.
    assert all("LFM2" not in c["model"] for c in the_plan["candidates"])
    assert the_plan["excluded"] == [
        {"model": "onnx-community/LFM2-1.2B-ONNX", "reason": "measured 0.167 < 0.5"}
    ]
    p = b.plan("rag-answer", catalog=b.load_browser_catalog(cache=NO_CACHE), min_score=0.1)
    assert any("LFM2" in c["model"] for c in p["candidates"])


def test_a_measured_score_outranks_the_prior():
    cat = b.load_browser_catalog(cache=NO_CACHE)
    for e in cat:
        if "LFM2" in e["id"]:
            e["measured"] = {"rag-answer": 0.9}
    p = b.plan("rag-answer", catalog=cat)
    assert "LFM2" in p["candidates"][0]["model"]


def test_languages_filter_the_pool(the_plan):
    cat = b.load_browser_catalog(cache=NO_CACHE)
    assert b.plan("rag-answer", languages=["fr", "tlh"], catalog=cat)["candidates"] == []


def test_unknown_usage_raises():
    with pytest.raises(KeyError):
        b.plan("no-such-usage")


@pytest.mark.parametrize(
    ("device", "expected"),
    [
        ({}, (None, "webgpu")),
        ({"webgpu": True, "mobile": True}, (None, "mobile")),
        ({"webgpu": True, "save_data": True}, (None, "network")),
        ({"webgpu": True, "effective_type": "3g"}, (None, "network")),
        (
            {"webgpu": True, "f16": True, "bandwidth_Bps": 50e6},
            (("gemma-4-E4B-it-ONNX", "q4f16"), "ok"),
        ),
        (
            {"webgpu": True, "f16": False, "bandwidth_Bps": 50e6},
            (("gemma-4-E4B-it-ONNX", "q4"), "ok"),
        ),
        (
            {"webgpu": True, "f16": True, "bandwidth_Bps": 20e6},
            (("gemma-4-E2B-it-ONNX", "q4f16"), "ok"),
        ),
        ({"webgpu": True, "f16": True, "bandwidth_Bps": 5e6}, (None, "download")),
        # 4 GB of device memory is a small machine: Gemma (floor 8) is out.
        (
            {"webgpu": True, "f16": True, "bandwidth_Bps": 50e6, "device_memory_gb": 4},
            (None, "device"),
        ),
        (
            {"webgpu": True, "f16": True, "bandwidth_Bps": 50e6, "storage_free_bytes": 4e9},
            (("gemma-4-E2B-it-ONNX", "q4f16"), "ok"),
        ),
        (
            {"webgpu": True, "f16": True, "bandwidth_Bps": 50e6, "storage_free_bytes": 2e9},
            (None, "device"),
        ),
        # A cached rung is free, whatever its size and the line.
        (
            {
                "webgpu": True,
                "f16": True,
                "bandwidth_Bps": 1e5,
                "cached": ["onnx-community/gemma-4-E2B-it-ONNX|q4f16"],
            },
            (("gemma-4-E2B-it-ONNX", "q4f16"), "cached"),
        ),
    ],
)
def test_choose(the_plan, device, expected):
    r = b.choose(the_plan, device)
    got = (_rung(r["candidate"]) if r["candidate"] else None, r["reason"])
    assert got == expected


def test_unknown_bandwidth_is_assumed_modest(the_plan):
    # 20 Mbit/s assumed: even Gemma 4 E2B (3.1 GB) takes 21 min, so a page that
    # could not measure its line offers no download at all. Silence buys nothing.
    r = b.choose(the_plan, {"webgpu": True, "f16": True})
    assert r == {"candidate": None, "reason": "download", "seconds": None}


def test_refresh_reads_sizes_and_skips_encoders():
    tree = [
        {"path": "onnx/model_q4f16.onnx", "size": 1},
        {"path": "onnx/model_q4f16.onnx_data", "lfs": {"size": 99}},
        {"path": "onnx/vision_encoder_q4f16.onnx_data", "lfs": {"size": 1000}},
        {"path": "onnx/model_q4.onnx", "size": 7},
    ]
    cat = [{"id": "a/b", "variants": {"q4f16": {"needs_f16": True}, "q4": {"needs_f16": False}}}]
    out = b.refresh(cat, fetch=lambda repo: tree, cache=None)[0]["variants"]
    assert out["q4f16"]["bytes"] == 100 and len(out["q4f16"]["files"]) == 2
    assert out["q4"]["bytes"] == 7


def test_cli_plan_and_choose(tmp_path):
    out = tmp_path / "plan.json"
    r = CliRunner().invoke(cli, ["browser", "plan", "--out", str(out)])
    assert r.exit_code == 0 and out.exists() and "left out: onnx-community/LFM2" in r.output
    r = CliRunner().invoke(cli, ["browser", "choose", "--plan", str(out), "--mbps", "400"])
    assert r.exit_code == 0 and "gemma-4-E4B" in r.output
    r = CliRunner().invoke(cli, ["browser", "choose", "--plan", str(out), "--mobile"])
    assert r.exit_code == 1 and "mobile" in r.output
