import zlib

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register(email: str) -> str:
    document_id = f"{zlib.crc32(email.encode()) % 10**10:010d}"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "display_name": "Ana", "document_id": document_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fake_analysis(*_args, **_kwargs):
    return {
        "symptom_ids": ["knee_pain", "invented"],
        "severity": {"knee_pain": 7},
        "avoid_patterns": ["lunge", "fake_pattern"],
        "guidance": "  evita el impacto  ",
        "absolute_contraindication": False,
    }


def test_analyze_symptoms_validates_and_merges_catalog(monkeypatch):
    token = _register("symptom-analyze@example.com")
    monkeypatch.setattr("syncfit_ai.interpret_symptom_text", _fake_analysis)

    response = client.post(
        "/api/v1/symptoms/analyze",
        json={"text": "me duele la rodilla al bajar escaleras", "language": "ES", "pain_level": 5},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["symptom_ids"] == ["knee_pain"]
    assert data["severity"] == {"knee_pain": 7}
    assert data["guidance"] == "evita el impacto"
    assert "fake_pattern" not in data["avoid_patterns"]
    # Catalog patterns for knee_pain are merged with the model's valid ones.
    assert {"lunge", "squat", "leg_extension", "plyometric"} <= set(data["avoid_patterns"])
    assert data["block_training"] is False
    assert data["matched"][0]["id"] == "knee_pain"
    assert data["matched"][0]["advice"]


def test_analyze_symptoms_filters_gestational_only(monkeypatch):
    token = _register("symptom-gestational@example.com")
    monkeypatch.setattr(
        "syncfit_ai.interpret_symptom_text",
        lambda *_args, **_kwargs: {
            "symptom_ids": ["dilation"],
            "severity": {"dilation": 9},
            "avoid_patterns": [],
            "guidance": "",
            "absolute_contraindication": True,
        },
    )

    menstrual = client.post(
        "/api/v1/symptoms/analyze", json={"text": "sangrado"}, headers=_auth(token)
    )
    assert menstrual.status_code == 200
    assert menstrual.json()["symptom_ids"] == []
    assert menstrual.json()["block_training"] is False

    client.put("/api/v1/profile", json={"modality": "GESTATIONAL"}, headers=_auth(token))
    pregnancy = client.post(
        "/api/v1/symptoms/analyze", json={"text": "sangrado"}, headers=_auth(token)
    )
    assert pregnancy.status_code == 200
    assert pregnancy.json()["symptom_ids"] == ["dilation"]
    assert pregnancy.json()["block_training"] is True


def test_analyze_symptoms_requires_auth_and_valid_text(monkeypatch):
    token = _register("symptom-validation@example.com")
    monkeypatch.setattr("syncfit_ai.interpret_symptom_text", _fake_analysis)

    assert client.post("/api/v1/symptoms/analyze", json={"text": "dolor"}).status_code == 401
    empty = client.post("/api/v1/symptoms/analyze", json={"text": "  "}, headers=_auth(token))
    assert empty.status_code == 422
    too_long = client.post(
        "/api/v1/symptoms/analyze", json={"text": "x" * 1001}, headers=_auth(token)
    )
    assert too_long.status_code == 422


def test_analyze_symptoms_returns_503_when_ai_fails(monkeypatch):
    token = _register("symptom-ai-down@example.com")

    def boom(**_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("syncfit_ai.interpret_symptom_text", boom)
    response = client.post(
        "/api/v1/symptoms/analyze", json={"text": "me duele la rodilla"}, headers=_auth(token)
    )
    assert response.status_code == 503


def test_capture_respects_symptom_avoid_patterns(monkeypatch):
    token = _register("symptom-capture@example.com")
    client.put(
        "/api/v1/profile",
        json={
            "modality": "MENSTRUAL_CYCLE",
            "last_period_date": "2026-09-10",
            "cycle_length_days": 28,
            "symptom_avoid_patterns": ["squat"],
        },
        headers=_auth(token),
    )
    response = client.post(
        "/api/v1/capture", params={"muscle_groups": "QUADRICEPS", "language": "EN"}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    patterns = {item.get("movement_pattern") for item in response.json()["routine"]}
    assert "squat" not in patterns
