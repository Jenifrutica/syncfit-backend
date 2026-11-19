"""Bulk deletes and the athlete's own machines.

Every removal is a ``DELETE``. Bulk routes take ``{"ids": [...]}`` in the body
(the same convention as ``DELETE /admin/users/{id}``) and answer
``{"deleted": [...], "missing": [...]}``. Each entity keeps the semantics of
its single delete: catalog items and options are deactivated (so old routines
still resolve them) and are reactivated with ``PATCH``; the rest are removed.

This router is mounted before the main one so ``/gyms/memberships`` is not
captured by ``/gyms/{gym_id}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from syncfit_database import AppOption, GymMachine, Profile, User

from ..db import get_session
from ..services import admin as admin_service
from ..services import athlete_machines
from ..services import gyms as gyms_service
from ..services import options as options_service
from ..services import profiles_db
from ..services.auth import verify_password
from .deps import current_user, require_super_admin
from ..services.catalog_db import KINDS, load_registry, set_active
from ..services.sharing import delete_share

router = APIRouter()

MAX_IDS = 200


def _ids(payload: dict[str, Any] | None, key: str = "ids") -> list[str]:
    raw = (payload or {}).get(key)
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=422, detail=f"{key} must be a non-empty list")
    if len(raw) > MAX_IDS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_IDS} ids per request")
    seen: list[str] = []
    for item in raw:
        value = str(item).strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _result(deleted: list[str], missing: list[str]) -> dict[str, Any]:
    return {"deleted": deleted, "missing": missing}


def _profile(session: Session, user: User):
    profile = profiles_db.get_profile(session, user)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not set up")
    return profile


def _locked_profile(session: Session, profile_id: str) -> Profile:
    """Fresh copy of the profile for a read-modify-write of its JSON lists.

    Ends the current read transaction first, so the row is re-read with the
    latest committed value, and locks it (SELECT ... FOR UPDATE on Postgres).
    """
    session.commit()
    return session.query(Profile).filter_by(id=profile_id).with_for_update().populate_existing().one()


# --- Athlete ---------------------------------------------------------------


@router.get("/profile/machines")
def my_machines(language: str = Query(default="EN"), user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return athlete_machines.list_selected(session, _profile(session, user), language)


@router.post("/profile/machines")
def add_my_machines(payload: dict[str, Any], language: str = Query(default="EN"), user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Add catalog machines (``{"ids": [...]}``) or one typed by name (``{"name": "..."}``)."""
    profile_id = _profile(session, user).id
    name = str(payload.get("name") or "").strip()
    info: dict[str, Any] | None = None
    ids: list[str] = []
    if name:
        if len(name) > 80:
            raise HTTPException(status_code=422, detail="name too long")
        from .routes import _machine_ai

        info = athlete_machines.infer_typed(name, language, _machine_ai)  # slow: outside the lock
    else:
        ids = _ids(payload)
    with athlete_machines.profile_lock(profile_id):
        profile = _locked_profile(session, profile_id)
        if info is not None:
            athlete_machines.add_typed(session, profile, name, info)
        else:
            unknown = athlete_machines.add_catalog(session, profile, ids)
            if unknown:
                session.rollback()
                raise HTTPException(status_code=422, detail=f"unknown machines: {', '.join(unknown)}")
        session.commit()
    return athlete_machines.list_selected(session, profile, language)


@router.delete("/profile/machines/{machine_id}", status_code=204)
def remove_my_machine(machine_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> None:
    profile_id = _profile(session, user).id
    with athlete_machines.profile_lock(profile_id):
        removed, _ = athlete_machines.remove(session, _locked_profile(session, profile_id), [machine_id])
        if not removed:
            session.rollback()
            raise HTTPException(status_code=404, detail="machine not selected")
        session.commit()


@router.delete("/profile/machines")
def remove_my_machines(payload: dict[str, Any], user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    ids = _ids(payload)
    profile_id = _profile(session, user).id
    with athlete_machines.profile_lock(profile_id):
        removed, missing = athlete_machines.remove(session, _locked_profile(session, profile_id), ids)
        session.commit()
    return _result(removed, missing)


@router.delete("/shares")
def remove_shares(payload: dict[str, Any], user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    deleted, missing = [], []
    for token in _ids(payload):
        (deleted if delete_share(session, user, token) else missing).append(token)
    session.commit()
    return _result(deleted, missing)


@router.delete("/gyms/memberships")
def leave_gyms(payload: dict[str, Any], user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    profile = _profile(session, user)
    deleted, missing = [], []
    for gym_id in _ids(payload):
        (deleted if gyms_service.leave_gym(session, profile, gym_id) else missing).append(gym_id)
    session.commit()
    return _result(deleted, missing)


# --- Gym admin ---------------------------------------------------------------


@router.delete("/gyms/{gym_id}/machines")
def delete_gym_machines(gym_id: str, payload: dict[str, Any], user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    gym = gyms_service.get_by_id(session, gym_id)
    if gym is None or gym.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="gym not found")
    deleted, missing = [], []
    for machine_id in _ids(payload):
        # Atomic per row: parallel bulk deletes never count a machine twice.
        removed = (
            session.query(GymMachine)
            .filter_by(id=machine_id, gym_id=gym.id)
            .delete(synchronize_session=False)
        )
        (deleted if removed else missing).append(machine_id)
    session.commit()
    return _result(deleted, missing)


# --- Super admin -------------------------------------------------------------


@router.delete("/admin/users")
def admin_delete_users(payload: dict[str, Any], user: User = Depends(require_super_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    password = str(payload.get("admin_password", ""))
    if not password or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=403, detail="super admin password required")
    ids = _ids(payload)
    if user.id in ids:
        raise HTTPException(status_code=400, detail="cannot delete yourself")
    deleted, missing = [], []
    for user_id in ids:
        target = admin_service.get_user(session, user_id)
        if target is None:
            missing.append(user_id)
            continue
        admin_service.delete_user(session, target)
        deleted.append(user_id)
    session.commit()
    return _result(deleted, missing)


def _set_options_active(session: Session, ids: list[str], active: bool) -> dict[str, Any]:
    done, missing = [], []
    for option_id in ids:
        row = session.get(AppOption, option_id)
        if row is None:
            missing.append(option_id)
            continue
        row.active = active
        done.append(option_id)
    session.commit()
    options_service.sync_engine_options(session)
    return _result(done, missing)


@router.delete("/admin/options")
def admin_delete_options(payload: dict[str, Any], user: User = Depends(require_super_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _set_options_active(session, _ids(payload), False)


@router.patch("/admin/options")
def admin_reactivate_options(payload: dict[str, Any], user: User = Depends(require_super_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    if payload.get("active") is not True:
        raise HTTPException(status_code=422, detail="bulk PATCH only reactivates (active: true); use DELETE to remove")
    result = _set_options_active(session, _ids(payload), True)
    return {"updated": result["deleted"], "missing": result["missing"]}


def _set_catalog_active(session: Session, kind: str, ids: list[str], active: bool) -> tuple[list[str], list[str]]:
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail=f"kind must be one of {list(KINDS)}")
    done, missing = [], []
    for external_id in ids:
        (done if set_active(session, kind, external_id, active) is not None else missing).append(external_id)
    session.commit()
    load_registry(session)
    return done, missing


@router.delete("/admin/catalog/{kind}")
def admin_delete_catalog_items(kind: str, payload: dict[str, Any], user: User = Depends(require_super_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    return _result(*_set_catalog_active(session, kind, _ids(payload), False))


@router.patch("/admin/catalog/{kind}")
def admin_reactivate_catalog_items(kind: str, payload: dict[str, Any], user: User = Depends(require_super_admin), session: Session = Depends(get_session)) -> dict[str, Any]:
    if payload.get("active") is not True:
        raise HTTPException(status_code=422, detail="bulk PATCH only reactivates (active: true); use DELETE to remove")
    done, missing = _set_catalog_active(session, kind, _ids(payload), True)
    return {"updated": done, "missing": missing}


__all__ = ["router"]
