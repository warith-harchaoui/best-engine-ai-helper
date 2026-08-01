"""
Tests for best_engine_ai_helper.api (the FastAPI HTTP surface).

Uses FastAPI's TestClient (no live server). The [api] extra is optional, so the
whole module is skipped when fastapi is absent, matching the graceful-skip style
used elsewhere rather than making the extra mandatory for the base test run.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from best_engine_ai_helper.api import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_system_endpoint_shape(client: TestClient) -> None:
    res = client.get("/api/system")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"platform", "chip_vendor", "memory", "compute", "memory_budget_gb"}
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert set(data["compute"]) == {"accelerator", "chip", "bandwidth_gbs"}
    assert data["memory_budget_gb"] > 0


def test_recommend_endpoint(client: TestClient) -> None:
    # No task -> LLM-only; the chosen candidate carries the fields the GUI reads
    # (including structured_output).
    llm_only = client.post("/api/recommend", json={}).json()
    assert llm_only["task"]["kinds"] == ["llm"] and "vlm" not in llm_only["recommendations"]
    chosen = llm_only["recommendations"]["llm"]["chosen"]
    assert {"id", "kind", "ram_gb", "score", "fits", "structured_output",
            "est_tokens_per_s"} <= chosen.keys()

    # A vision task adds a VLM and echoes the headroom.
    vision = client.post(
        "/api/recommend",
        json={"task": "product descriptions and image-quality checks", "headroom": 0.5},
    ).json()
    assert set(vision["task"]["kinds"]) == {"llm", "vlm"} and "image" in vision["task"]["matched"]
    assert vision["headroom"] == 0.5

    # A malformed body is a 422.
    assert client.post("/api/recommend", json={"headroom": "nope"}).status_code == 422


def test_gui_is_bilingual_and_escaped(client: TestClient) -> None:
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


def test_root_redirect_and_static_assets(client: TestClient) -> None:
    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code in (307, 308) and redirect.headers["location"] == "/gui"
    assert client.get("/static/icons/favicon.ico").status_code == 200
    manifest = client.get("/static/site.webmanifest")
    assert manifest.status_code == 200 and manifest.json()["name"] == "Best Engine AI Helper"
