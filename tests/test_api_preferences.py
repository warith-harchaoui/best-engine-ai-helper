"""
Tests for the HTTP preference routes, ``GET`` and ``POST /api/preferences``.

`tests/test_preferences.py` covers the store underneath. These cover what only
the route decides: the status codes, what pydantic refuses before the store is
ever reached, and that the YAML on disk stays the one source of truth a second
reader agrees with. Every test points the store at its own temporary file, so
nothing here can read or rewrite the preferences of the machine running it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from best_engine_ai_helper import config
from best_engine_ai_helper.api import PreferencesRequest, app
from best_engine_ai_helper.gui import render_gui

DEFAULTS = {
    "quality_vs_cost": 0.7,
    "headroom": 0.5,
    "min_tps": 15.0,
    "local_only": False,
    "live_load": False,
}


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "prefs" / "preferences.yaml"
    monkeypatch.setattr(config, "_PREFERENCES_YAML", path)
    return path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_with_nothing_saved_returns_the_defaults(store: Path, client: TestClient) -> None:
    response = client.get("/api/preferences")

    assert response.status_code == 200
    assert response.json() == DEFAULTS
    assert not store.exists(), "a read must never create the file"


def test_post_returns_the_full_set_and_get_reads_it_back(store: Path, client: TestClient) -> None:
    posted = client.post("/api/preferences", json={"quality_vs_cost": 0.2, "local_only": True})

    assert posted.status_code == 200
    expected = {**DEFAULTS, "quality_vs_cost": 0.2, "local_only": True}
    assert posted.json() == expected
    assert client.get("/api/preferences").json() == expected


def test_a_partial_post_leaves_the_other_values_alone(store: Path, client: TestClient) -> None:
    """The GUI saves on each `change` event, so a post carries what changed."""
    client.post("/api/preferences", json={"quality_vs_cost": 0.2})
    client.post("/api/preferences", json={"headroom": 0.3, "quality_vs_cost": None})

    prefs = client.get("/api/preferences").json()
    assert prefs["quality_vs_cost"] == 0.2, "an explicit null must not reset a saved value"
    assert prefs["headroom"] == 0.3


def test_the_yaml_on_disk_is_what_persists(store: Path, client: TestClient) -> None:
    client.post("/api/preferences", json={"min_tps": 25, "live_load": True})

    on_disk = yaml.safe_load(store.read_text(encoding="utf-8"))
    assert on_disk == {**DEFAULTS, "min_tps": 25.0, "live_load": True}

    # A second client, standing in for a restarted server, reads the same file.
    assert TestClient(app).get("/api/preferences").json()["min_tps"] == 25.0


def test_a_file_edited_by_hand_is_what_get_serves(store: Path, client: TestClient) -> None:
    """The route holds no state of its own: the file is the source of truth."""
    store.parent.mkdir(parents=True)
    store.write_text("headroom: 0.25\n", encoding="utf-8")

    assert client.get("/api/preferences").json() == {**DEFAULTS, "headroom": 0.25}


def test_a_form_posting_a_numeric_string_stores_a_number(store: Path, client: TestClient) -> None:
    response = client.post("/api/preferences", json={"headroom": "0.4"})

    assert response.status_code == 200
    assert response.json()["headroom"] == 0.4
    assert yaml.safe_load(store.read_text(encoding="utf-8"))["headroom"] == 0.4


@pytest.mark.parametrize(
    "body",
    [
        {"headroom": "not-a-number"},
        {"local_only": "maybe"},
        {"min_tps": [15]},
    ],
)
def test_a_value_of_the_wrong_type_is_refused_and_nothing_is_written(
    store: Path, client: TestClient, body: dict[str, object]
) -> None:
    response = client.post("/api/preferences", json=body)

    assert response.status_code == 422
    assert not store.exists()


def test_a_body_that_is_not_an_object_is_refused(store: Path, client: TestClient) -> None:
    response = client.post("/api/preferences", json=[0.5])

    assert response.status_code == 422
    assert not store.exists()


@pytest.mark.parametrize(
    "raw",
    ['{"headroom": NaN}', '{"min_tps": Infinity}', '{"headroom": "nan"}', '{"min_tps": "inf"}'],
)
def test_a_non_finite_number_is_refused_rather_than_served_back_as_null(
    store: Path, client: TestClient, raw: str
) -> None:
    """Python's JSON parser takes `NaN`, and FastAPI encodes it back as `null`.

    Before 1.11.2 this answered 200, wrote `.nan` to the YAML, and every GET
    from then on served `null` for a field documented as a number.
    """
    client.post("/api/preferences", json={"headroom": 0.3, "min_tps": 20})

    response = client.post(
        "/api/preferences", content=raw, headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert client.get("/api/preferences").json() == {**DEFAULTS, "headroom": 0.3, "min_tps": 20.0}


def test_a_nan_left_in_the_file_by_an_older_release_reads_as_the_default(
    store: Path, client: TestClient
) -> None:
    store.parent.mkdir(parents=True)
    store.write_text("headroom: .nan\nmin_tps: .inf\nquality_vs_cost: 0.4\n", encoding="utf-8")

    prefs = client.get("/api/preferences").json()
    assert prefs["headroom"] == DEFAULTS["headroom"]
    assert prefs["min_tps"] == DEFAULTS["min_tps"]
    assert prefs["quality_vs_cost"] == 0.4


def test_an_unknown_field_is_ignored_not_stored(store: Path, client: TestClient) -> None:
    response = client.post("/api/preferences", json={"quality_vs_cost": 0.5, "api_key": "sk-x"})

    assert response.status_code == 200
    assert "api_key" not in response.json()
    assert "sk-x" not in store.read_text(encoding="utf-8")


def test_a_post_writes_only_the_preferences_file(store: Path, client: TestClient) -> None:
    """settings.yaml holds API keys; this route must never be the one to write it."""
    client.post("/api/preferences", json={"quality_vs_cost": 0.5})

    assert [p.name for p in store.parent.iterdir()] == ["preferences.yaml"]


def test_every_field_the_gui_saves_is_one_the_route_accepts() -> None:
    """The page restores its sliders from GET and saves them back through POST.

    A key in the page's `PREF_FIELDS` that the request model does not declare
    would be dropped by pydantic without a word, so the slider would forget
    its position on every reload while each save still answered 200.
    """
    page = render_gui("en")
    assert 'fetch("/api/preferences"' in page

    block = re.search(r"const PREF_FIELDS = \{(.*?)\n    \};", page, re.DOTALL)
    assert block is not None, "the GUI no longer declares PREF_FIELDS where this test looks"
    keys = set(re.findall(r"^\s*(\w+):\s*\{", block.group(1), re.MULTILINE))

    assert keys, "PREF_FIELDS parsed as empty"
    assert keys <= set(PreferencesRequest.model_fields)
    assert keys <= set(DEFAULTS)
