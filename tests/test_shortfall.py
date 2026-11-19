"""When fewer exercises than requested come out, the response says why."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.capture import _family_count, _shortfall
from tests.test_bulk import _athlete

client = TestClient(app)


def test_shortfall_lists_concrete_reasons():
    out = _shortfall("ES", 8, 5, ["CALVES"], ["Gemelos"], ["lunge"], True, 30, True, "LOW")
    codes = [r["code"] for r in out["reasons"]]
    assert out["requested"] == 8 and out["delivered"] == 5
    assert codes[:1] == ["FAMILIES"] or "FAMILIES" not in codes  # only if the catalog is short
    assert {"SYMPTOMS", "TIME", "IMPACT", "EQUIPMENT"} <= set(codes)
    assert out["summary"].startswith("Pediste 8 ejercicios y salieron 5. Por qué:")
    assert "lunge" in out["summary"] and "30 min" in out["summary"]


def test_no_shortfall_when_complete_or_empty():
    assert _shortfall("ES", 5, 5, ["GLUTES"], ["Glúteos"], [], False, None, False, None) is None
    assert _shortfall("ES", 5, 0, ["GLUTES"], ["Glúteos"], [], False, None, False, None) is None


def test_capture_explains_a_short_routine_for_a_narrow_group():
    h = _athlete()
    families = _family_count(["CALVES"])
    assert families < 8
    body = client.post("/api/v1/capture", params={"muscle_groups": "CALVES", "exercises_count": 8, "use_live": "false", "language": "ES"}, headers=h).json()
    delivered = sum(1 for e in body["routine"] if not e["blocked"])
    assert delivered < 8
    short = body["shortfall"]
    assert short and short["requested"] == 8 and short["delivered"] == delivered
    assert any(r["code"] == "FAMILIES" for r in short["reasons"])
    assert "Gemelos" in short["summary"] or "gemelos" in short["summary"].lower()
    assert body["alerts"][0] == short["summary"]
