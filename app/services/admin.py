"""Super admin bootstrap and gym-admin management."""

from __future__ import annotations

from sqlalchemy.orm import Session
from syncfit_database import (
    AthleteMachine,
    CycleLog,
    EnergyCheckIn,
    Gym,
    Profile,
    Routine,
    SessionRecord,
    ShareLink,
    SupplementIntake,
    User,
)

from ..config import settings
from . import gyms
from .auth import InvalidAccountData, hash_password, identity_transaction, verify_password
from .validation import validate_document_id, validate_person_name
from .credentials import client_digest


def ensure_superadmin(session: Session) -> User | None:
    """Create/ensure the super admin from environment variables (idempotent)."""
    email = settings.superadmin_email
    password = settings.superadmin_password
    if not email or not password:
        return None
    # The browser logs in with the digest, so that is what must be stored.
    digest = client_digest(email, password)
    user = session.query(User).filter_by(email=email.lower()).one_or_none()
    if user is None:
        user = User(
            email=email.lower(),
            password_hash=hash_password(digest),
            display_name=settings.superadmin_name,
            role="SUPER_ADMIN",
        )
        session.add(user)
    else:
        user.role = "SUPER_ADMIN"
        # Only migrate a hash stored before the browser digest existed (it
        # verifies with the plain env password). A password the super admin
        # changed (e.g. through "forgot password") is theirs: never overwrite it
        # on startup, or every deploy would undo the reset.
        if not verify_password(digest, user.password_hash) and verify_password(password, user.password_hash):
            user.password_hash = hash_password(digest)
            user.token_version += 1
    session.flush()
    return user


def create_gym_admin(
    session: Session, email: str, password: str, display_name: str, document_id: str | None = None
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        document_id=document_id,
        role="GYM_ADMIN",
    )
    session.add(user)
    session.flush()
    return user


def provision_gym_admin(session: Session, payload: dict) -> User:
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    try:
        name = validate_person_name(payload.get("display_name", "Gym Admin"))
        document = validate_document_id(payload["document_id"]) if payload.get("document_id") else None
    except ValueError as exc:
        raise InvalidAccountData(str(exc)) from exc
    if "@" not in email or not 8 <= len(password) <= 128:
        raise InvalidAccountData("email and password (8-128 chars) required")
    with identity_transaction(session, email, document):
        user = create_gym_admin(session, email, password, name, document)
    session.refresh(user)
    return user


def edit_user_identity(session: Session, user: User, payload: dict) -> User:
    data = {}
    try:
        if "display_name" in payload:
            data["display_name"] = validate_person_name(payload["display_name"])
        if "document_id" in payload:
            document = payload["document_id"]
            data["document_id"] = validate_document_id(document) if document else None
    except ValueError as exc:
        raise InvalidAccountData(str(exc)) from exc
    if "email" in payload:
        email = str(payload["email"]).strip().lower()
        if "@" not in email:
            raise InvalidAccountData("invalid email")
        data["email"] = email
    with identity_transaction(session, data.get("email"), data.get("document_id"), user.id):
        update_user(session, user, data)
    session.refresh(user)
    return user


def list_gym_admins(session: Session) -> list[User]:
    return session.query(User).filter_by(role="GYM_ADMIN").all()


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "document_id": user.document_id,
        "role": user.role,
        "active": getattr(user, "active", True) is not False,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def list_users(session: Session, role: str | None = None, search: str | None = None) -> list[User]:
    query = session.query(User)
    if role:
        query = query.filter_by(role=role)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.filter(
            User.email.ilike(pattern) | User.display_name.ilike(pattern)
        )
    return query.order_by(User.created_at.desc()).all()


def get_user(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def update_user(session: Session, user: User, data: dict) -> User:
    for field in ("display_name", "email"):
        if field in data and data[field] is not None:
            setattr(user, field, data[field])
    if "document_id" in data:
        user.document_id = data["document_id"]
    session.flush()
    return user


def set_active(session: Session, user: User, active: bool) -> User:
    user.active = active
    session.flush()
    return user


def reset_password(session: Session, user: User, password: str) -> User:
    user.password_hash = hash_password(password)
    session.flush()
    return user


def set_role(session: Session, user: User, role: str) -> User:
    user.role = role
    session.flush()
    return user


def delete_user(session: Session, user: User) -> None:
    """Hard delete a user and all their data (ordered to satisfy FK constraints)."""
    profile_ids = [p.id for p in session.query(Profile).filter_by(user_id=user.id).all()]
    for gym in session.query(Gym).filter_by(owner_user_id=user.id).order_by(Gym.id).with_for_update():
        gyms.delete_gym(session, gym)
    for routine in session.query(Routine).filter_by(user_id=user.id).all():
        session.delete(routine)  # cascades routine_exercises
    for record in session.query(SessionRecord).filter_by(user_id=user.id).all():
        session.delete(record)  # cascades telemetry samples
    if profile_ids:
        session.query(AthleteMachine).filter(AthleteMachine.profile_id.in_(profile_ids)).delete(synchronize_session=False)
    for profile in session.query(Profile).filter_by(user_id=user.id).all():
        session.delete(profile)  # cascades loads + memberships
    session.query(EnergyCheckIn).filter_by(user_id=user.id).delete()
    session.query(CycleLog).filter_by(user_id=user.id).delete()
    session.query(SupplementIntake).filter_by(user_id=user.id).delete()
    session.query(ShareLink).filter_by(owner_user_id=user.id).delete()
    session.delete(user)
    session.flush()


__all__ = [
    "ensure_superadmin",
    "create_gym_admin",
    "list_gym_admins",
    "serialize_user",
    "list_users",
    "get_user",
    "update_user",
    "set_active",
    "reset_password",
    "set_role",
    "delete_user",
]
