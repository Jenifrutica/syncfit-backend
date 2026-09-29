"""Super admin bootstrap and gym-admin management."""

from __future__ import annotations

from sqlalchemy.orm import Session
from syncfit_database import (
    CycleLog,
    EnergyCheckIn,
    Gym,
    GymMembership,
    Profile,
    Routine,
    SessionRecord,
    ShareLink,
    SupplementIntake,
    User,
)

from ..config import settings
from .auth import hash_password


def ensure_superadmin(session: Session) -> User | None:
    """Create/ensure the super admin from environment variables (idempotent)."""
    email = settings.superadmin_email
    password = settings.superadmin_password
    if not email or not password:
        return None
    user = session.query(User).filter_by(email=email.lower()).one_or_none()
    if user is None:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=settings.superadmin_name,
            role="SUPER_ADMIN",
        )
        session.add(user)
    else:
        user.role = "SUPER_ADMIN"
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
    for gym in session.query(Gym).filter_by(owner_user_id=user.id).all():
        session.query(GymMembership).filter_by(gym_id=gym.id).delete()
        session.delete(gym)  # cascades machines
    for routine in session.query(Routine).filter_by(user_id=user.id).all():
        session.delete(routine)  # cascades routine_exercises
    for record in session.query(SessionRecord).filter_by(user_id=user.id).all():
        session.delete(record)  # cascades telemetry samples
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
