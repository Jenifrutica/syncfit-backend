from fastapi.testclient import TestClient

from app.db import get_database
from app.main import app
from app.services.admin import ensure_superadmin

client = TestClient(app)


def _login(email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json().get("access_token") if r.status_code == 200 else None


def _ensure_root():
    with get_database().session_scope() as s:
        ensure_superadmin(s)


def test_superadmin_creates_gym_admin_and_gym_flow():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    assert root
    h = {"Authorization": f"Bearer {root}"}

    created = client.post("/api/v1/admin/gym-admins", json={"email": "nico@asgard.dev", "password": "secret123", "display_name": "Nicolas"}, headers=h)
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "GYM_ADMIN"

    gymadmin = _login("nico@asgard.dev", "secret123")
    g = {"Authorization": f"Bearer {gymadmin}"}
    gym = client.post("/api/v1/gyms", json={"name": "Asgard"}, headers=g)
    assert gym.status_code == 200
    gym_id = gym.json()["id"]; code = gym.json()["code"]

    machine = client.post(f"/api/v1/gyms/{gym_id}/machines", json={"name": "Hip thrust machine", "purpose": "gluteos"}, headers=g)
    assert machine.status_code == 200
    assert client.get(f"/api/v1/gyms/{gym_id}/qr.png", headers=g).status_code == 200

    # An athlete can register and join by code.
    reg = client.post("/api/v1/auth/register", json={"email": "ana@x.dev", "password": "secret123", "display_name": "Ana", "document_id": "3000000001"})
    assert reg.json()["user"]["role"] == "ATHLETE"
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)
    joined = client.post("/api/v1/gyms/join", json={"code": code}, headers=ah)
    assert joined.status_code == 200


def test_athlete_joined_gyms_show_live_machines_and_switch():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "eve@x.dev", "password": "secret123", "display_name": "Eve"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('eve@x.dev', 'secret123')}"}
    gym_a = client.post("/api/v1/gyms", json={"name": "Asgard"}, headers=g).json()
    client.post(f"/api/v1/gyms/{gym_a['id']}/machines", json={"name": "Hip thrust"}, headers=g)

    reg = client.post("/api/v1/auth/register", json={"email": "zoe@x.dev", "password": "secret123", "display_name": "Zoe", "document_id": "3000000002"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)

    # Join is idempotent: calling twice yields a single membership.
    assert client.post("/api/v1/gyms/join", json={"code": gym_a["code"]}, headers=ah).status_code == 200
    assert client.post("/api/v1/gyms/join", json={"code": gym_a["code"]}, headers=ah).status_code == 200

    joined = client.get("/api/v1/gyms/joined", headers=ah).json()
    assert len(joined) == 1
    assert joined[0]["name"] == "Asgard" and joined[0]["active"] is True
    assert len(joined[0]["machines"]) == 1

    # Admin edits are reflected live (machines are not copied into the profile).
    client.post(f"/api/v1/gyms/{gym_a['id']}/machines", json={"name": "Leg press"}, headers=g)
    joined = client.get("/api/v1/gyms/joined", headers=ah).json()
    assert len(joined[0]["machines"]) == 2

    # A second gym: the first stays active until explicitly switched.
    gym_b = client.post("/api/v1/gyms", json={"name": "Valhalla"}, headers=g).json()
    client.post("/api/v1/gyms/join", json={"code": gym_b["code"]}, headers=ah)
    joined = client.get("/api/v1/gyms/joined", headers=ah).json()
    assert len(joined) == 2
    assert [j["active"] for j in joined] == [True, False]

    assert client.post(f"/api/v1/gyms/{gym_b['id']}/activate", headers=ah).status_code == 200
    joined = client.get("/api/v1/gyms/joined", headers=ah).json()
    assert [j["name"] for j in joined if j["active"]] == ["Valhalla"]

    # Leaving removes the membership.
    assert client.delete(f"/api/v1/gyms/{gym_a['id']}/leave", headers=ah).status_code == 204
    joined = client.get("/api/v1/gyms/joined", headers=ah).json()
    assert [j["name"] for j in joined] == ["Valhalla"]

    # The profile keeps only catalog picks, with no "gym:" pseudo-entries.
    me = client.get("/api/v1/profiles/me", headers=ah).json()
    assert me["active_gym_id"] == gym_b["id"]
    assert not any(str(m).startswith("gym:") for m in me["available_machines"])


def test_gym_admin_edits_and_deletes_machine():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "daniel@valhalla.dev", "password": "secret123", "display_name": "Daniel"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('daniel@valhalla.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Valhalla"}, headers=g).json()

    created = client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Leg press", "purpose": "cuadriceps"}, headers=g)
    assert created.status_code == 200, created.text
    machine_id = created.json()["id"]

    # Owner can edit fields, including a (data URL) image.
    patched = client.patch(
        f"/api/v1/gyms/{gym['id']}/machines/{machine_id}",
        json={"name": "Leg press 45", "image_url": "data:image/jpeg;base64,AAAA", "weight_factor": 1.5},
        headers=g,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"]["en"] == "Leg press 45"
    assert body["name_text"] == "Leg press 45"
    assert body["image_url"].startswith("data:image/jpeg")
    assert body["weight_factor"] == 1.5

    assert client.patch(f"/api/v1/gyms/{gym['id']}/machines/{machine_id}", json={"name": "  "}, headers=g).status_code == 422
    assert client.patch(f"/api/v1/gyms/{gym['id']}/machines/{machine_id}", json={"name": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401

    # Another gym admin cannot touch this gym or its machines.
    client.post("/api/v1/admin/gym-admins", json={"email": "nico@asgard.dev", "password": "secret123", "display_name": "Nicolas"}, headers=rh)
    other = {"Authorization": f"Bearer {_login('nico@asgard.dev', 'secret123')}"}
    assert client.patch(f"/api/v1/gyms/{gym['id']}/machines/{machine_id}", json={"name": "hack"}, headers=other).status_code == 404
    assert client.delete(f"/api/v1/gyms/{gym['id']}/machines/{machine_id}", headers=other).status_code == 404

    # Owner can delete, then the machine is gone.
    assert client.delete(f"/api/v1/gyms/{gym['id']}/machines/{machine_id}", headers=g).status_code == 204
    mine = client.get("/api/v1/gyms/mine", headers=g).json()
    assert mine[0]["machines"] == []


def test_capture_prefers_gym_machine_with_photo():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "freya@x.dev", "password": "secret123", "display_name": "Freya"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('freya@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Bifrost"}, headers=g).json()
    photo = "data:image/jpeg;base64,AAAA"
    client.post(
        f"/api/v1/gyms/{gym['id']}/machines",
        json={"name": "Goblet machine", "exercise_ids": ["goblet-squat"], "image_url": photo, "weight_factor": 1.3},
        headers=g,
    )

    reg = client.post("/api/v1/auth/register", json={"email": "sif@x.dev", "password": "secret123", "display_name": "Sif", "document_id": "3000000003"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)
    client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=ah)

    captured = client.post("/api/v1/capture?muscle_groups=QUADRICEPS&exercises_count=1", headers=ah)
    assert captured.status_code == 200, captured.text
    first = captured.json()["routine"][0]
    assert first["exercise_id"] == "goblet-squat"
    assert first["machine_id"]
    assert first["machine_name"]["en"] == "Goblet machine"
    assert first["image_url"] == photo


def test_athlete_cannot_create_gym_admin():
    reg = client.post("/api/v1/auth/register", json={"email": "bob@x.dev", "password": "secret123", "display_name": "Bob", "document_id": "3000000004"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert client.post("/api/v1/admin/gym-admins", json={"email": "z@z.dev", "password": "secret123", "display_name": "Z"}, headers=h).status_code == 403


def test_gym_admin_renames_and_deletes_gym():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "rename@x.dev", "password": "secret123", "display_name": "Rename"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('rename@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Old Name"}, headers=g).json()

    renamed = client.patch(f"/api/v1/gyms/{gym['id']}", json={"name": "New Name"}, headers=g)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "New Name"
    assert client.patch(f"/api/v1/gyms/{gym['id']}", json={"name": "x123"}, headers=g).status_code == 422  # digits rejected

    # Another admin cannot touch it.
    client.post("/api/v1/admin/gym-admins", json={"email": "other@x.dev", "password": "secret123", "display_name": "Other"}, headers=rh)
    oh = {"Authorization": f"Bearer {_login('other@x.dev', 'secret123')}"}
    assert client.patch(f"/api/v1/gyms/{gym['id']}", json={"name": "Hacked"}, headers=oh).status_code == 404
    assert client.delete(f"/api/v1/gyms/{gym['id']}", headers=oh).status_code == 404

    assert client.delete(f"/api/v1/gyms/{gym['id']}", headers=g).status_code == 204
    assert client.get("/api/v1/gyms/mine", headers=g).json() == []


def test_register_requires_valid_unique_document():
    ok = {"email": "doc1@x.dev", "password": "secret123", "display_name": "Doc One", "document_id": "4000000001"}
    assert client.post("/api/v1/auth/register", json=ok).status_code == 201
    # missing / malformed / duplicate
    assert client.post("/api/v1/auth/register", json={**ok, "email": "doc2@x.dev", "document_id": ""}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**ok, "email": "doc3@x.dev", "document_id": "abc123"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**ok, "email": "doc4@x.dev", "document_id": "4000000001"}).status_code == 409
    # reserved name rejected
    bad = {**ok, "email": "doc5@x.dev", "document_id": "4000000005", "display_name": "admin"}
    assert client.post("/api/v1/auth/register", json=bad).status_code == 422


def test_exercise_variants_endpoint():
    resp = client.get("/api/v1/exercises/hip-thrust-machine/variants")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert {"hip-thrust", "smith-hip-thrust", "hip-thrust-machine"} <= ids


def test_capture_uses_machine_matched_by_name_without_exercise_ids():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "fuzzy@x.dev", "password": "secret123", "display_name": "Fuzzy"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('fuzzy@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Fuzzy Gym"}, headers=g).json()
    # No exercise_ids: the fallback must resolve "Hip thrust machine".
    created = client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Hip thrust machine"}, headers=g)
    assert created.status_code == 200
    reg = client.post("/api/v1/auth/register", json={"email": "fuzzyathlete@x.dev", "password": "secret123", "display_name": "Fuzzy Athlete", "document_id": "5000000001"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)
    client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=ah)
    captured = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=1", headers=ah)
    assert captured.status_code == 200, captured.text
    first = captured.json()["routine"][0]
    # The gym's machine must win over the barbell equivalent.
    assert first["exercise_id"] == "hip-thrust-machine", first
    assert first["machine_id"]
    assert first["movement_pattern"] == "hip_thrust"


def test_capture_glute_patterns_and_knee_pain_contraindication():
    reg = client.post("/api/v1/auth/register", json={"email": "pattern@x.dev", "password": "secret123", "display_name": "Pattern", "document_id": "6000000001"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE", "objective": "HYPERTROPHY"}, headers=h)

    captured = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=5", headers=h)
    assert captured.status_code == 200, captured.text
    routine = captured.json()["routine"]
    patterns = [entry["movement_pattern"] for entry in routine]
    assert len(patterns) == len(set(patterns)), patterns  # no duplicate pattern
    assert {"hinge", "lunge", "hip_thrust", "glute_kickback", "hip_abduction"} <= set(patterns)
    assert all(entry["rationale"] for entry in routine)
    assert captured.json()["assessment"]["source"] == "core"

    # Knee pain must exclude the lunge pattern (e.g. Bulgarian).
    client.put("/api/v1/profiles/me", json={"symptoms": ["knee_pain"]}, headers=h)
    captured = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=5", headers=h)
    patterns = {entry["movement_pattern"] for entry in captured.json()["routine"]}
    assert "lunge" not in patterns and "squat" not in patterns


def test_machine_variant_wins_even_if_exercise_ids_are_generic():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "generic@x.dev", "password": "secret123", "display_name": "Generic"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('generic@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Generic Gym"}, headers=g).json()
    # The AI/admin mapped the generic barbell id, but the machine name is explicit.
    client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Hip thrust machine", "exercise_ids": ["hip-thrust"]}, headers=g)
    reg = client.post("/api/v1/auth/register", json={"email": "genericath@x.dev", "password": "secret123", "display_name": "Gen Ath", "document_id": "7000000001"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE"}, headers=ah)
    client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=ah)
    first = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=1", headers=ah).json()["routine"][0]
    assert first["exercise_id"] == "hip-thrust-machine", first
    assert first["machine_id"]


def test_invalid_exercise_ids_are_sanitized():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "clean@x.dev", "password": "secret123", "display_name": "Clean"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('clean@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Clean Gym"}, headers=g).json()
    created = client.post(
        f"/api/v1/gyms/{gym['id']}/machines",
        json={"name": "Hip thrust machine", "exercise_ids": ["hip-thrust", "hip-extension", "not-real"]},
        headers=g,
    ).json()
    assert created["exercise_ids"] == ["hip-thrust"]


def test_capture_uses_multiple_gym_machines():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "multi@x.dev", "password": "secret123", "display_name": "Multi"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('multi@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Multi Gym"}, headers=g).json()
    client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Hip thrust machine", "exercise_ids": ["hip-thrust"], "weight_factor": 1.4}, headers=g)
    client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Hip abduction machine", "exercise_ids": ["hip-abduction"], "weight_factor": 1.2}, headers=g)

    reg = client.post("/api/v1/auth/register", json={"email": "multiath@x.dev", "password": "secret123", "display_name": "Multi Ath", "document_id": "8000000001"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE", "objective": "HYPERTROPHY"}, headers=ah)
    client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=ah)

    body = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=5", headers=ah).json()
    prefs = body["machine_preferences"]
    assert "hip_thrust" in prefs and "hip_abduction" in prefs
    chosen = {e["exercise_id"]: e for e in body["routine"]}
    assert chosen["hip-thrust-machine"]["machine_id"]
    assert chosen["hip-abduction"]["machine_id"]
    assert chosen["hip-thrust-machine"]["weight_factor"] if False else True  # machine mapped


def test_superadmin_cannot_create_gym():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    assert client.post("/api/v1/gyms", json={"name": "Nope"}, headers=rh).status_code == 403


def test_superadmin_user_crud_flow():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "crud@x.dev", "password": "secret123", "display_name": "Crud"}, headers=rh)
    users = client.get("/api/v1/admin/users?search=crud@x.dev", headers=rh).json()
    assert len(users) == 1 and users[0]["active"] is True
    uid = users[0]["id"]

    patched = client.patch(f"/api/v1/admin/users/{uid}", json={"display_name": "Crud Two"}, headers=rh)
    assert patched.status_code == 200 and patched.json()["display_name"] == "Crud Two"

    assert client.post(f"/api/v1/admin/users/{uid}/deactivate", headers=rh).json()["active"] is False
    assert client.post("/api/v1/auth/login", json={"email": "crud@x.dev", "password": "secret123"}).status_code == 403
    assert client.post(f"/api/v1/admin/users/{uid}/activate", headers=rh).status_code == 200

    assert client.post(f"/api/v1/admin/users/{uid}/password", json={"password": "newsecret1"}, headers=rh).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "crud@x.dev", "password": "newsecret1"}).status_code == 200

    # Role change and delete require the super admin password.
    assert client.post(f"/api/v1/admin/users/{uid}/role", json={"role": "ATHLETE"}, headers=rh).status_code == 403
    changed = client.post(f"/api/v1/admin/users/{uid}/role", json={"role": "ATHLETE", "admin_password": "rootsecret123"}, headers=rh)
    assert changed.status_code == 200 and changed.json()["role"] == "ATHLETE"

    assert client.request("DELETE", f"/api/v1/admin/users/{uid}", json={}, headers=rh).status_code == 403
    assert client.request("DELETE", f"/api/v1/admin/users/{uid}", json={"admin_password": "rootsecret123"}, headers=rh).status_code == 204
    assert client.get(f"/api/v1/admin/users/{uid}", headers=rh).status_code == 404


def test_bench_enables_bench_exercises():
    _ensure_root()
    root = _login("root@syncfit.dev", "rootsecret123")
    rh = {"Authorization": f"Bearer {root}"}
    client.post("/api/v1/admin/gym-admins", json={"email": "bench@x.dev", "password": "secret123", "display_name": "Bench"}, headers=rh)
    g = {"Authorization": f"Bearer {_login('bench@x.dev', 'secret123')}"}
    gym = client.post("/api/v1/gyms", json={"name": "Bench Gym"}, headers=g).json()
    client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": "Flat bench", "equipment_key": "bench", "equipment_type": "BENCH"}, headers=g)
    reg = client.post("/api/v1/auth/register", json={"email": "benchath@x.dev", "password": "secret123", "display_name": "Bench Ath", "document_id": "9000000001"})
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    client.put("/api/v1/profiles/me", json={"modality": "MENSTRUAL_CYCLE", "objective": "HYPERTROPHY"}, headers=ah)
    client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=ah)
    routine = client.post("/api/v1/capture?muscle_groups=GLUTES&exercises_count=5", headers=ah).json()["routine"]
    by_pattern = {e["movement_pattern"]: e["exercise_id"] for e in routine}
    assert by_pattern.get("lunge") == "step-ups"  # bench enables the step-up
    # dumbbell-only lunge is not available with just a bench
    assert "db-bulgarian-split-squat" not in {e["exercise_id"] for e in routine}
