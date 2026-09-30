"""Authentication: password hashing, JWT tokens and the current-user dependency."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from syncfit_database import User

from ..config import settings
from ..db import get_session

ALGORITHM = "HS256"
_LEGACY_PREFIX = "pbkdf2_sha256$"

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password")
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def _verify_pbkdf2(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except ValueError: 
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith(_LEGACY_PREFIX):
        return _verify_pbkdf2(password=password, stored=stored)
    try:
        return _ph.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    """True for legacy PBKDF2 hashes or Argon2 hashes with outdated parameters."""
    return stored.startswith(_LEGACY_PREFIX) or _ph.check_needs_rehash(stored)


def spend_password_check(password: str) -> None:
    """Take as long as a real check, so unknown emails can't be told apart by timing."""
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if getattr(user, "active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
    return user


def require_super_admin(user: User = Depends(current_user)) -> User:
    if getattr(user, "role", None) != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user


def require_gym_admin(user: User = Depends(current_user)) -> User:
    # Gym creation/management belongs to gym admins only; the super admin is a
    # purely administrative role and cannot create gyms or machines.
    if getattr(user, "role", None) != "GYM_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gym admin required")
    return user


__all__ = [
    "require_super_admin",
    "require_gym_admin",
    "hash_password",
    "verify_password",
    "needs_rehash",
    "spend_password_check",
    "create_access_token",
    "decode_token",
    "current_user",
]
