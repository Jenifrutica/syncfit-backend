"""Authentication and credential use cases, independent of HTTP."""

from __future__ import annotations

import hashlib
import hmac
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from syncfit_database import User

from ..config import settings
from .validation import validate_document_id, validate_person_name

ALGORITHM = "HS256"
_LEGACY_PREFIX = "pbkdf2_sha256$"

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password")


class InvalidCredentials(Exception):
    """A login, token, or password check failed."""


class AccountInactive(Exception):
    """The account cannot authenticate because it is deactivated."""


class InvalidAccountData(Exception):
    """The account inputs do not satisfy application rules."""


class RegistrationConflict(Exception):
    """An account already uses the requested email or document."""


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
    return stored.startswith(_LEGACY_PREFIX) or _ph.check_needs_rehash(stored)


def spend_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def _password_fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def _token_version(user: User) -> int:
    return getattr(user, "token_version", 0) or 0


def revoke_tokens(user: User) -> None:
    if not hasattr(User, "token_version"):
        # Without the column the bump would only live in memory: logout would do nothing. Fail loudly instead.
        raise RuntimeError("syncfit-database is outdated: users.token_version is missing")
    user.token_version = _token_version(user) + 1


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_expire_minutes),
        "pwv": _password_fingerprint(user),
        "tv": _token_version(user),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "iat", "sub", "pwv", "tv"]},
    )


def authenticate_token(session: Session, token: str) -> User:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise InvalidCredentials("Invalid token") from exc
    user = session.get(User, payload["sub"])
    if user is None:
        raise InvalidCredentials("User not found")
    fingerprint = payload["pwv"]
    if not isinstance(fingerprint, str) or not fingerprint.isascii():
        raise InvalidCredentials("Invalid token")
    if not hmac.compare_digest(fingerprint, _password_fingerprint(user)) or payload["tv"] != _token_version(user):
        raise InvalidCredentials("Token revoked")
    if getattr(user, "active", True) is False:
        raise AccountInactive("Account deactivated")
    return user


def _check_identity(session: Session, email: str | None, document_id: str | None, exclude_id: str | None) -> None:
    users = session.query(User)
    if exclude_id is not None:
        users = users.filter(User.id != exclude_id)
    if email and users.filter_by(email=email).first() is not None:
        raise RegistrationConflict("email already registered")
    if document_id and users.filter_by(document_id=document_id).first() is not None:
        raise RegistrationConflict("document_id already registered")


@contextmanager
def identity_transaction(session: Session, email: str | None, document_id: str | None, exclude_id: str | None = None):
    _check_identity(session, email, document_id, exclude_id)
    try:
        yield
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent write can claim the identity after the initial check.
        _check_identity(session, email, document_id, exclude_id)
        raise


def register_user(session: Session, *, email: str, password: str, display_name: str, document_id: str) -> User:
    email = email.lower()
    try:
        display_name = validate_person_name(display_name)
        document_id = validate_document_id(document_id)
    except ValueError as exc:
        raise InvalidAccountData(str(exc)) from exc
    with identity_transaction(session, email, document_id):
        user = User(email=email, password_hash=hash_password(password), display_name=display_name, document_id=document_id)
        session.add(user)
    session.refresh(user)
    return user


def authenticate_password(session: Session, email: str, password: str) -> User:
    user = session.query(User).filter_by(email=email.strip().lower()).one_or_none()
    if user is None:
        spend_password_check(password)
        raise InvalidCredentials("invalid credentials")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("invalid credentials")
    if getattr(user, "active", True) is False:
        raise AccountInactive("account deactivated")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        session.commit()
    return user


def logout_user(session: Session, user: User) -> None:
    revoke_tokens(user)
    session.commit()


def change_user_password(session: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentials("invalid credentials")
    if new_password == current_password:
        raise InvalidAccountData("new password must differ from the current one")
    user.password_hash = hash_password(new_password)
    session.commit()
    session.refresh(user)


__all__ = [
    "InvalidCredentials",
    "AccountInactive",
    "InvalidAccountData",
    "RegistrationConflict",
    "authenticate_token",
    "authenticate_password",
    "register_user",
    "logout_user",
    "change_user_password",
    "hash_password",
    "verify_password",
    "needs_rehash",
    "spend_password_check",
    "create_access_token",
    "revoke_tokens",
    "decode_token",
]
