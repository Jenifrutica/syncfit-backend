"""The athlete suggests an exercise by name; the API ranks catalog replacements."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.exercise_suggest import suggest
from tests.test_bulk import _athlete

client = TestClient(app)


def test_typos_and_spanish_names_match_and_same_pattern_ranks_first():
    options = suggest("back-squat", "sentadila goblet", "ES")
    assert options and options[0]["id"] == "goblet-squat"
    assert options[0]["fit"] == "same_pattern" and "patrón" in options[0]["reason"]


def test_other_muscles_are_flagged_and_nonsense_finds_nothing():
    options = suggest("back-squat", "curl de biceps", "ES")
    assert options and options[0]["fit"] == "different"
    assert suggest("back-squat", "zzqqxx", "ES") == []


def test_endpoint_validates_and_answers():
    h = _athlete()
    r = client.post("/api/v1/exercises/back-squat/suggest?language=ES", json={"text": "prensa"}, headers=h)
    assert r.status_code == 200 and r.json()["options"]
    assert client.post("/api/v1/exercises/back-squat/suggest", json={"text": "x"}, headers=h).status_code == 422
    assert client.post("/api/v1/exercises/back-squat/suggest", json={"text": "prensa"}).status_code == 401
