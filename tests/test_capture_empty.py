import zlib

from fastapi.testclient import TestClient

from app.main import app
from syncfit_ai.routine import _family
from syncfit_contracts import get_exercise

client = TestClient(app)


def _register(
    email: str,
    symptoms: list[str] | None = None,
    pain_levels: dict[str, int] | None = None,
) -> dict:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Ana", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    profile = {"modality": "MENSTRUAL_CYCLE"}
    if symptoms:
        profile["symptoms"] = symptoms
    if pain_levels:
        profile["pain_levels"] = pain_levels
    assert client.put("/api/v1/profile", json=profile, headers=headers).status_code == 200
    return headers


def test_capture_explains_an_empty_routine():
    # Knee pain blocks every quad pattern (squat, lunge, leg extension).
    headers = _register("empty-knee@example.com", symptoms=["knee_pain"])

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=5", headers=headers)
    assert captured.status_code == 200, captured.text
    body = captured.json()

    assert body["routine"] == []
    assert body["empty_reason"] == "SYMPTOMS_BLOCK_ALL"
    assert body["alerts"], "the reason must reach the app"
    # The warm-up block is still there, but the main routine is empty.
    assert isinstance(body["warmup"], list)


def test_capture_without_symptoms_is_not_empty():
    headers = _register("empty-free@example.com")

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=5", headers=headers)
    assert captured.status_code == 200, captured.text
    body = captured.json()

    assert body["empty_reason"] is None
    assert body["routine"], "routine must not be empty"
    families = [_family(get_exercise(entry["exercise_id"])) for entry in body["routine"]]
    assert len(families) == len(set(families)), families
    for entry in body["routine"]:
        assert "QUADRICEPS" in entry.get("muscle_groups", [])


def test_mild_knee_pain_keeps_training_quads():
    # 3/10: the model (or the fallback) may keep controlled quad work; it must
    # not return an empty routine or a blanket block.
    headers = _register("pain-mild@example.com", symptoms=["knee_pain"], pain_levels={"OVERALL": 3})

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=5", headers=headers)
    assert captured.status_code == 200, captured.text
    body = captured.json()

    assert body["empty_reason"] is None
    assert body["routine"], "mild pain must keep training"
    families = [_family(get_exercise(entry["exercise_id"])) for entry in body["routine"]]
    assert len(families) == len(set(families)), families
    for entry in body["routine"]:
        assert "QUADRICEPS" in entry.get("muscle_groups", [])
        exercise = get_exercise(entry.get("exercise_id"))
        assert exercise is not None and str(exercise.impact) != "HIGH", entry.get("name")
    assert any("3/10" in alert for alert in body["alerts"])


def test_severe_knee_pain_stays_conservative():
    headers = _register("pain-severe@example.com", symptoms=["knee_pain"], pain_levels={"OVERALL": 8})

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=5", headers=headers)
    assert captured.status_code == 200, captured.text
    body = captured.json()

    assert body["routine"] == []
    assert body["empty_reason"] == "SYMPTOMS_BLOCK_ALL"
