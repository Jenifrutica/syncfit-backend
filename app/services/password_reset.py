"""Password-reset tokens: only the SHA-256 hash is persisted."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from syncfit_database import PasswordResetToken, User

from ..config import settings
from .auth import revoke_tokens


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    # SQLite drops the timezone; Postgres keeps it.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def issue_token(session: Session, user: User) -> str:
    """Invalidate older links and create a fresh single-use token."""
    now = datetime.now(timezone.utc)
    session.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now})
    raw = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(raw),
            expires_at=now + timedelta(minutes=settings.password_reset_minutes),
        )
    )
    session.commit()
    return raw


def valid_token(session: Session, raw: str) -> PasswordResetToken | None:
    row = session.query(PasswordResetToken).filter_by(token_hash=_hash(raw)).one_or_none()
    if row is None or row.used_at is not None:
        return None
    if _aware(row.expires_at) <= datetime.now(timezone.utc):
        return None
    return row


def apply_reset(session: Session, row: PasswordResetToken, password_hash: str) -> bool:
    """Use the token and change the password in one transaction.

    The conditional UPDATE makes a second parallel request lose cleanly.
    """
    now = datetime.now(timezone.utc)
    updated = (
        session.query(PasswordResetToken)
        .filter(PasswordResetToken.id == row.id, PasswordResetToken.used_at.is_(None))
        .update({PasswordResetToken.used_at: now})
    )
    if updated != 1:
        session.rollback()
        return False
    user = session.get(User, row.user_id)
    if user is None:
        session.rollback()
        return False
    user.password_hash = password_hash
    revoke_tokens(user)
    session.commit()
    return True


__all__ = ["apply_reset", "issue_token", "valid_token"]
