"""Super admin bootstrap and gym-admin management."""

from __future__ import annotations

from sqlalchemy.orm import Session
from syncfit_database import User

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


def create_gym_admin(session: Session, email: str, password: str, display_name: str) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        role="GYM_ADMIN",
    )
    session.add(user)
    session.flush()
    return user


def list_gym_admins(session: Session) -> list[User]:
    return session.query(User).filter_by(role="GYM_ADMIN").all()


def serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}


__all__ = ["ensure_superadmin", "create_gym_admin", "list_gym_admins", "serialize_user"]
