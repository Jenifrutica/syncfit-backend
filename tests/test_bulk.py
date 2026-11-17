"""Bulk DELETE on every panel and the athlete's own machines."""

import uuid

from fastapi.testclient import TestClient

from app.db import get_database
from app.main import app
from app.services.admin import ensure_superadmin
from app.services.credentials import client_digest
from app.services.catalog_db import ensure_catalog
from app.services.options import ensure_default_options

client = TestClient(app)
ROOT_PASSWORD = client_digest("root@syncfit.dev", "rootsecret123")


def _token(email: str, password: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _root() -> dict[str, str]:
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        ensure_default_options(s)
        ensure_catalog(s)
    return _token("root@syncfit.dev", ROOT_PASSWORD)


def _athlete() -> dict[str, str]:
    tag = uuid.uuid4().hex[:8]
    doc = str(int(uuid.uuid4().int % 10**10)).rjust(10, "4")
    r = client.post("/api/v1/auth/register", json={"email": f"bulk{tag}@x.dev", "password": "secret123", "display_name": "Ana", "document_id": doc})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.put("/api/v1/profile", json={"modality": "MENSTRUAL_CYCLE"}, headers=h)
    return h


def _gym_admin(rh: dict[str, str]) -> dict[str, str]:
    email = f"gadm{uuid.uuid4().hex[:8]}@x.dev"
    client.post("/api/v1/admin/gym-admins", json={"email": email, "password": "secret123", "display_name": "Gerda"}, headers=rh)
    return _token(email, "secret123")


def test_athlete_machines_add_remove_and_typed():
    h = _athlete()
    catalog = [m["id"] for m in client.get("/api/v1/machines").json()][:3]
    added = client.post("/api/v1/profile/machines", json={"ids": catalog}, headers=h)
    assert added.status_code == 200 and [m["id"] for m in added.json()] == catalog

    typed = client.post("/api/v1/profile/machines", json={"name": "Prensa vieja del sótano"}, headers=h).json()
    custom = [m for m in typed if m["custom"]]
    assert len(custom) == 1 and custom[0]["name"] and custom[0]["id"].startswith("custom-")

    # Removing is a DELETE, and the machine can be chosen again afterwards.
    assert client.delete(f"/api/v1/profile/machines/{catalog[0]}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/profile/machines/{catalog[0]}", headers=h).status_code == 404
    again = client.post("/api/v1/profile/machines", json={"ids": [catalog[0]]}, headers=h).json()
    assert catalog[0] in [m["id"] for m in again]

    everything = [m["id"] for m in again]
    bulk = client.request("DELETE", "/api/v1/profile/machines", json={"ids": everything + ["nope"]}, headers=h).json()
    assert sorted(bulk["deleted"]) == sorted(everything) and bulk["missing"] == ["nope"]
    assert client.get("/api/v1/profile/machines", headers=h).json() == []

    assert client.post("/api/v1/profile/machines", json={"ids": ["not-a-machine"]}, headers=h).status_code == 422
    assert client.request("DELETE", "/api/v1/profile/machines", json={"ids": []}, headers=h).status_code == 422


def test_bulk_delete_gym_machines_shares_and_memberships():
    rh = _root()
    g = _gym_admin(rh)
    gym = client.post("/api/v1/gyms", json={"name": "Bulkheim"}, headers=g).json()
    ids = [client.post(f"/api/v1/gyms/{gym['id']}/machines", json={"name": f"Polea {i}"}, headers=g).json()["id"] for i in range(3)]
    result = client.request("DELETE", f"/api/v1/gyms/{gym['id']}/machines", json={"ids": ids[:2]}, headers=g).json()
    assert sorted(result["deleted"]) == sorted(ids[:2])
    remaining = client.get("/api/v1/gyms/mine", headers=g).json()[0]["machines"]
    assert [m["id"] for m in remaining] == [ids[2]]

    # Another admin cannot touch this gym.
    other = _gym_admin(rh)
    assert client.request("DELETE", f"/api/v1/gyms/{gym['id']}/machines", json={"ids": [ids[2]]}, headers=other).status_code == 404

    h = _athlete()
    assert client.post("/api/v1/gyms/join", json={"code": gym["code"]}, headers=h).status_code == 200
    left = client.request("DELETE", "/api/v1/gyms/memberships", json={"ids": [gym["id"]]}, headers=h).json()
    assert left["deleted"] == [gym["id"]]
    assert client.get("/api/v1/gyms/joined", headers=h).json() == []

    tokens = [client.post("/api/v1/shares", json={"label": "bulk", "permissions": ["PROFILE"]}, headers=h).json()["token"] for _ in range(2)]
    gone = client.request("DELETE", "/api/v1/shares", json={"ids": tokens}, headers=h).json()
    assert sorted(gone["deleted"]) == sorted(tokens)
    assert client.get("/api/v1/shares", headers=h).json() == []


def test_bulk_admin_users_options_and_catalog():
    rh = _root()
    emails = [f"del{uuid.uuid4().hex[:6]}@x.dev" for _ in range(2)]
    ids = [client.post("/api/v1/admin/gym-admins", json={"email": e, "password": "secret123", "display_name": "Del"}, headers=rh).json()["id"] for e in emails]

    assert client.request("DELETE", "/api/v1/admin/users", json={"ids": ids}, headers=rh).status_code == 403
    me = client.get("/api/v1/account", headers=rh).json()["id"]
    assert client.request("DELETE", "/api/v1/admin/users", json={"ids": [me], "admin_password": ROOT_PASSWORD}, headers=rh).status_code == 400
    done = client.request("DELETE", "/api/v1/admin/users", json={"ids": ids, "admin_password": ROOT_PASSWORD}, headers=rh).json()
    assert sorted(done["deleted"]) == sorted(ids)

    options = [o for o in client.get("/api/v1/admin/options", headers=rh).json() if o["category"] == "equipment"][:2]
    option_ids = [o["id"] for o in options]
    client.request("DELETE", "/api/v1/admin/options", json={"ids": option_ids}, headers=rh)
    public = [o["value"] for o in client.get("/api/v1/options").json().get("equipment", [])]
    assert not set(o["value"] for o in options) & set(public)
    assert client.patch("/api/v1/admin/options", json={"ids": option_ids, "active": True}, headers=rh).json()["updated"] == option_ids
    assert client.patch("/api/v1/admin/options", json={"ids": option_ids, "active": False}, headers=rh).status_code == 422

    items = [i["id"] for i in client.get("/api/v1/admin/catalog/symptom", headers=rh).json()][:2]
    assert len(items) == 2
    off = client.request("DELETE", "/api/v1/admin/catalog/symptom", json={"ids": items}, headers=rh).json()
    assert off["deleted"] == items
    rows = {i["id"]: i["active"] for i in client.get("/api/v1/admin/catalog/symptom", headers=rh).json()}
    assert not any(rows[i] for i in items)
    assert client.patch("/api/v1/admin/catalog/symptom", json={"ids": items, "active": True}, headers=rh).json()["updated"] == items


def test_bulk_routes_require_auth_and_roles():
    h = _athlete()
    assert client.request("DELETE", "/api/v1/admin/options", json={"ids": ["x"]}, headers=h).status_code == 403
    assert client.request("DELETE", "/api/v1/profile/machines", json={"ids": ["x"]}).status_code == 401
