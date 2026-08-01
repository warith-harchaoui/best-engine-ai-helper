"""
Tests for best_engine_ai_helper.api (the FastAPI HTTP surface).

Uses FastAPI's TestClient (httpx-backed), so no live server is started. The
[api] extra is optional, so the whole module is skipped when fastapi is not
installed, matching the graceful-fall-through style used elsewhere in this
suite rather than making the extra mandatory for the base test run.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from best_engine_ai_helper.api import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/system
# ---------------------------------------------------------------------------

def test_system_returns_200(client: TestClient) -> None:
    res = client.get("/api/system")
    assert res.status_code == 200


def test_system_shape(client: TestClient) -> None:
    data = client.get("/api/system").json()
    assert set(data.keys()) == {
        "platform", "chip_vendor", "memory", "compute", "memory_budget_gb",
    }
    assert set(data["memory"].keys()) == {"unified_gb", "vram_gb", "ram_gb"}
    assert set(data["compute"].keys()) == {"accelerator", "chip", "bandwidth_gbs"}
    assert data["memory_budget_gb"] > 0


# ---------------------------------------------------------------------------
# POST /api/recommend
# ---------------------------------------------------------------------------

def test_recommend_defaults_to_llm_only(client: TestClient) -> None:
    res = client.post("/api/recommend", json={})
    assert res.status_code == 200
    report = res.json()
    assert report["task"]["kinds"] == ["llm"]
    assert "llm" in report["recommendations"]
    assert "vlm" not in report["recommendations"]


def test_recommend_vision_task_adds_vlm(client: TestClient) -> None:
    report = client.post(
        "/api/recommend",
        json={"task": "product descriptions and image-quality checks"},
    ).json()
    assert set(report["task"]["kinds"]) == {"llm", "vlm"}
    assert "vlm" in report["recommendations"]
    assert "image" in report["task"]["matched"]


def test_recommend_chosen_candidate_has_expected_fields(client: TestClient) -> None:
    report = client.post("/api/recommend", json={"task": "write python code"}).json()
    chosen = report["recommendations"]["llm"]["chosen"]
    assert chosen is not None
    assert {"id", "kind", "ram_gb", "score", "fits", "est_tokens_per_s"} <= chosen.keys()


def test_recommend_headroom_is_echoed(client: TestClient) -> None:
    report = client.post("/api/recommend", json={"headroom": 0.5}).json()
    assert report["headroom"] == 0.5


def test_recommend_rejects_malformed_body(client: TestClient) -> None:
    res = client.post("/api/recommend", json={"headroom": "not-a-number"})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# GUI page + redirect + static assets
# ---------------------------------------------------------------------------

def test_gui_serves_html(client: TestClient) -> None:
    res = client.get("/gui")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Best Engine AI Helper" in res.text
    assert "/api/recommend" in res.text


def test_root_redirects_to_gui(client: TestClient) -> None:
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (307, 308)
    assert res.headers["location"] == "/gui"


def test_static_favicon_is_served(client: TestClient) -> None:
    res = client.get("/static/icons/favicon.ico")
    assert res.status_code == 200


def test_static_webmanifest_is_served(client: TestClient) -> None:
    res = client.get("/static/site.webmanifest")
    assert res.status_code == 200
    assert res.json()["name"] == "Best Engine AI Helper"
