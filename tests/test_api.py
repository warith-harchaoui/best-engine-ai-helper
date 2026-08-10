"""
Tests for best_engine_ai_helper.api (the FastAPI HTTP surface).

Uses FastAPI's TestClient (no live server). fastapi/uvicorn are core
dependencies, so no skip-if-absent handling is needed here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from best_engine_ai_helper.api import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_system_and_recommend_endpoints(client: TestClient) -> None:
    system = client.get("/api/system")
    assert system.status_code == 200
    data = system.json()
    assert set(data) == {
        "platform",
        "chip_vendor",
        "memory",
        "compute",
        "memory_budget_gb",
        "hardware",
    }
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert set(data["compute"]) == {"accelerator", "chip", "bandwidth_gbs"}
    assert data["memory_budget_gb"] > 0
    # "hardware" is the raw os_helper snapshot (cores, model names, VRAM, plus
    # live load: cpu.percent, available_ram_gb, disk, gpu_utilization_percent),
    # distinct from the AI-throughput-derived "compute" above.
    assert set(data["hardware"]) == {
        "platform",
        "cpu",
        "ram_gb",
        "available_ram_gb",
        "disk",
        "gpu_vendor",
        "gpus",
        "gpu_utilization_percent",
        "apple_chip",
        "apple_unified_gb",
    }

    # No task -> LLM-only; the chosen candidate carries the fields the GUI reads
    # (including structured_output).
    llm_only = client.post("/api/recommend", json={}).json()
    assert llm_only["task"]["kinds"] == ["llm"] and "vlm" not in llm_only["recommendations"]
    chosen = llm_only["recommendations"]["llm"]["chosen"]
    assert {"id", "kind", "ram_gb", "score", "fits", "structured_output", "est_tokens_per_s"} <= (
        chosen.keys()
    )

    # A vision task adds a VLM and echoes the headroom.
    vision = client.post(
        "/api/recommend",
        json={"task": "product descriptions and image-quality checks", "headroom": 0.5},
    ).json()
    assert set(vision["task"]["kinds"]) == {"llm", "vlm"} and "image" in vision["task"]["matched"]
    assert vision["headroom"] == 0.5

    # A malformed body is a 422.
    assert client.post("/api/recommend", json={"headroom": "nope"}).status_code == 422

    # `live: true` includes a real server-load snapshot in the report; off by
    # default (the base `{}` request above has no "server_load" key at all).
    assert "server_load" not in llm_only
    live = client.post("/api/recommend", json={"live": True}).json()
    assert {
        "available_ram_gb",
        "cpu_percent",
        "disk_free_gb",
        "disk_percent_used",
        "running_engines",
    } <= live["server_load"].keys()


def test_activity_gui_and_static_endpoints(client: TestClient, tmp_path: Path) -> None:
    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # Enabled up front, at a tmp path: `/api/activity` falls back to opening
    # the DEFAULT-path ledger read-only when none is active (so a plain
    # `uvicorn api:app`, with no CLI/MCP auto-enable, still sees history) —
    # without this, the "empty" check below would touch the real
    # ~/.best-engine-ai-helper/usage.db instead of this test's tmp_path.
    ledger = observe.enable(str(tmp_path / "usage.db"))

    empty = client.get("/api/activity").json()
    assert empty == {
        "total_calls": 0,
        "total_cost_usd": 0.0,
        "error_rate": 0.0,
        "by_user": [],
        "by_model": [],
        "recent_errors": [],
    }

    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")

    activity_data = client.get("/api/activity").json()
    assert activity_data["total_calls"] == 1
    assert activity_data["by_model"] == [{"model": "qwen3:8b", "calls": 1, "cost_usd": 0.0}]
    ledger.close()

    fr = client.get("/gui")
    assert fr.status_code == 200 and "text/html" in fr.headers["content-type"]
    assert '<html lang="fr"' in fr.text and "Meilleur moteur local" in fr.text
    assert 'href="/gui?lang=en"' in fr.text and "/api/recommend" in fr.text

    en = client.get("/gui", params={"lang": "en"}).text
    assert '<html lang="en"' in en and "Best local engine" in en
    assert "Meilleur moteur local" not in en
    # The EN placeholder's double quotes must be HTML-escaped (regression guard).
    assert "&quot;write product descriptions" in en and 'placeholder="e.g. "write' not in en

    # An unknown language falls back to French rather than erroring.
    assert '<html lang="fr"' in client.get("/gui", params={"lang": "zz"}).text

    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code in (307, 308) and redirect.headers["location"] == "/gui"
    assert client.get("/static/icons/favicon.ico").status_code == 200
    manifest = client.get("/static/site.webmanifest")
    assert manifest.status_code == 200 and manifest.json()["name"] == "Best Engine AI Helper"
