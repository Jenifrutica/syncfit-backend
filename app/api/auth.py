"""Authentication routes: register, login and current user."""

from __future__ import annotations

import logging
import secrets

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from syncfit_database import Gym, Profile, User

from ..config import settings
from ..db import get_session
from ..rate_limit import limiter
from ..services import admin as admin_service
from ..services import gyms as gym_service
from ..services import mailer, password_reset
from ..services.auth import (
    create_access_token,
    current_user,
    hash_password,
    needs_rehash,
    revoke_tokens,
    spend_password_check,
    verify_password,
)
from ..services.validation import validate_document_id, validate_person_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
# The signed-in person's own account: the token already says who it is, so no /me.
account_router = APIRouter(prefix="/account", tags=["account"])


class RegisterIn(BaseModel):
    email: EmailStr
    # max_length caps the hashing work: Argon2 processes the whole password.
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1)
    document_id: str = Field(min_length=6, max_length=15)


class LoginIn(BaseModel):
    # Plain str on purpose: accounts created before EmailStr validation must
    # still be able to log in even if their email would now be rejected.
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    # Two ways to confirm: the current password (accounts that have one) or the
    # typed phrase "eliminar <display name>" (works for Google accounts, which
    # never know their random password). No min_length on the password so older
    # accounts with shorter passwords can still delete themselves.
    password: str | None = Field(default=None, max_length=128)
    confirm: str | None = Field(default=None, max_length=200)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class DemoLoginIn(BaseModel):
    role: str = Field(pattern="^(SUPER_ADMIN|GYM_ADMIN|ATHLETE)$")


class GoogleIn(BaseModel):
    """Google credential from the browser: an ID token or an OAuth access token."""

    credential: str | None = Field(default=None, min_length=20)
    access_token: str | None = Field(default=None, min_length=20)


_DELETE_VERBS = ("eliminar", "delete", "删除")


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _delete_phrase_matches(user: User, confirm: str) -> bool:
    name = _normalize_text(user.display_name)
    expected = {f"{verb} {name}" for verb in _DELETE_VERBS}
    return _normalize_text(confirm) in expected


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "document_id": user.document_id,
        "role": user.role,
        "active": getattr(user, "active", True) is not False,
    }


@router.post("/register", status_code=201)
@limiter.limit("10/hour")
def register(request: Request, payload: RegisterIn, session: Session = Depends(get_session)) -> dict:
    email = payload.email.lower()
    try:
        display_name = validate_person_name(payload.display_name)
        document_id = validate_document_id(payload.document_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = session.query(User).filter_by(email=email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    if session.query(User).filter_by(document_id=document_id).one_or_none() is not None:
        raise HTTPException(status_code=409, detail="document_id already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=display_name,
        document_id=document_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.query(User).filter_by(email=payload.email.strip().lower()).one_or_none()
    if user is None:
        spend_password_check(payload.password)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if getattr(user, "active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account deactivated")
    if needs_rehash(user.password_hash):
        # Only now do we know the plain password is correct, so it is safe to re-hash it.
        user.password_hash = hash_password(payload.password)
        session.commit()
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


def _demo_athlete(session: Session) -> User:
    """The demo athlete (Nicolasa), created with a minimal profile if missing."""
    name = (settings.demo_athlete_name or "Nicolasa").strip()
    user = None
    if settings.demo_athlete_email:
        user = session.query(User).filter_by(email=settings.demo_athlete_email.strip().lower()).one_or_none()
    if user is None:
        user = (
            session.query(User)
            .filter(User.role == "ATHLETE", func.lower(User.display_name) == name.lower())
            .first()
        )
    if user is None:
        email = settings.demo_athlete_email or "nicolasa@syncfit.dev"
        user = User(
            email=email.strip().lower(),
            password_hash=hash_password(secrets.token_urlsafe(32)),
            display_name=name,
            role="ATHLETE",
            active=True,
        )
        session.add(user)
        session.flush()
    profile = session.query(Profile).filter_by(user_id=user.id).one_or_none()
    if profile is None:
        session.add(
            Profile(
                user_id=user.id,
                language="ES",
                modality="MENSTRUAL_CYCLE",
                objective="HYPERTROPHY",
                goal_phase="VOLUME",
                weekly_training_goal=4,
                rest_days_allowance=3,
                cycle_length_days=28,
            )
        )
    session.commit()
    return user


def _demo_admin(session: Session) -> User:
    """The demo gym admin: reuse an existing admin or create one with a gym."""
    email = (settings.demo_admin_email or "demo-admin@syncfit.dev").strip().lower()
    user = session.query(User).filter_by(email=email).one_or_none()
    if user is not None and user.role != "GYM_ADMIN":
        user = None
    if user is None and not settings.demo_admin_email:
        # No dedicated demo address configured: reuse any active gym admin.
        user = session.query(User).filter_by(role="GYM_ADMIN", active=True).first()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            display_name=settings.demo_admin_name or "Demo Admin",
            role="GYM_ADMIN",
            active=True,
        )
        session.add(user)
        session.flush()
    if session.query(Gym).filter_by(owner_user_id=user.id).first() is None:
        gym_service.create_gym(session, user, settings.demo_admin_gym_name or "Valhalla")
    session.commit()
    return user


def _demo_user(session: Session, role: str) -> User | None:
    if role == "ATHLETE":
        return _demo_athlete(session)
    if role == "GYM_ADMIN":
        return _demo_admin(session)
    email = settings.demo_superadmin_email
    user = session.query(User).filter_by(email=email.strip().lower()).one_or_none() if email else None
    if user is None:
        user = session.query(User).filter_by(role=role, active=True).first()
    return user


def _google_info_from_access_token(access_token: str, client_id: str) -> dict:
    """Validate an OAuth access token with Google's tokeninfo endpoint."""
    try:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="google verification unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid google token")
    info = response.json()
    if info.get("aud") != client_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid google token")
    return info


@router.post("/demo")
@limiter.limit("30/minute")
def demo_login(request: Request, payload: DemoLoginIn, session: Session = Depends(get_session)) -> dict:
    """One-click access for the evaluation build; off unless DEMO_LOGIN_ENABLED."""
    if not settings.demo_login_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="demo login disabled")
    user = _demo_user(session, payload.role)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="demo account not found")
    if getattr(user, "active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account deactivated")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/forgot", status_code=202)
@limiter.limit("5/minute")
def forgot_password(
    request: Request, payload: ForgotPasswordIn, session: Session = Depends(get_session)
) -> dict:
    """Email a single-use reset link. The answer never reveals if the account exists."""
    if not mailer.is_configured():
        raise HTTPException(status_code=503, detail="email service unavailable")
    user = session.query(User).filter(func.lower(User.email) == payload.email.strip().lower()).one_or_none()
    if user is not None and getattr(user, "active", True) is not False:
        raw = password_reset.issue_token(session, user)
        profile = session.query(Profile).filter_by(user_id=user.id).one_or_none()
        language = (profile.language if profile is not None else None) or "ES"
        link = f"{settings.app_base_url}/recuperar/?token={raw}"
        try:
            mailer.send_password_reset(to=user.email, name=user.display_name, link=link, language=language)
        except Exception:
            # Never turn a delivery failure into an account-existence oracle.
            logger.exception("password reset email failed for %s", user.email)
    return {"status": "sent"}


@router.get("/reset/{token}")
def check_reset_token(token: str, session: Session = Depends(get_session)) -> dict:
    row = password_reset.valid_token(session, token)
    user = session.get(User, row.user_id) if row is not None else None
    if row is None or user is None:
        raise HTTPException(status_code=404, detail="invalid or expired token")
    # The token holder already owns this inbox; the email is needed to digest
    # the new password client-side, exactly like login and register do.
    return {"valid": True, "email": user.email}


@router.post("/reset", status_code=204)
@limiter.limit("10/minute")
def reset_password(
    request: Request, payload: ResetPasswordIn, session: Session = Depends(get_session)
) -> None:
    row = password_reset.valid_token(session, payload.token)
    if row is None:
        raise HTTPException(status_code=404, detail="invalid or expired token")
    user = session.get(User, row.user_id)
    if user is None or getattr(user, "active", True) is False:
        raise HTTPException(status_code=404, detail="invalid or expired token")
    if verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=422, detail="new password must differ from the current one")
    if not password_reset.apply_reset(session, row, hash_password(payload.password)):
        raise HTTPException(status_code=404, detail="invalid or expired token")


@router.post("/google")
@limiter.limit("10/minute")
def google_login(request: Request, payload: GoogleIn, session: Session = Depends(get_session)) -> dict:
    """Sign in with a Google credential and link/create the account by email.

    Accepts an ID token (`credential`, from the Google button) or an OAuth
    access token (`access_token`, from a custom-styled button). Google accounts
    never get a usable password: a random one is stored so password login cannot
    be used until the person sets one.
    """
    client_id = settings.google_client_id
    if not client_id:
        raise HTTPException(status_code=503, detail="google sign-in is not configured")
    if payload.credential:
        try:
            info = id_token.verify_oauth2_token(
                payload.credential, google_requests.Request(), client_id
            )
        except Exception as exc:  # invalid signature, wrong audience, expired...
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid google token") from exc
    elif payload.access_token:
        info = _google_info_from_access_token(payload.access_token, client_id)
    else:
        raise HTTPException(status_code=422, detail="credential or access_token required")
    if str(info.get("email_verified")).lower() not in {"true", "1"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="google email not verified")
    email = str(info.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid google token")

    user = session.query(User).filter_by(email=email).one_or_none()
    if user is None:
        display_name = str(info.get("name") or email.split("@")[0])[:120]
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            display_name=display_name,
            role="ATHLETE",
            token_version=0,
        )
        session.add(user)
    if getattr(user, "active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account deactivated")
    session.commit()
    session.refresh(user)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@account_router.get("")
def get_account(user: User = Depends(current_user)) -> dict:
    return _public_user(user)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    # Stateless JWTs can't be deleted, so bump the user's token version: every
    # token issued so far (on any device) stops being accepted.
    revoke_tokens(user)
    session.commit()
    return Response(status_code=204)


@router.put("/password")
@limiter.limit("5/minute")
def change_password(request: Request, payload: ChangePasswordIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=422, detail="new password must differ from the current one")
    # Changing the hash changes the token fingerprint this revokes every existing token access
    user.password_hash = hash_password(payload.new_password)
    session.commit()
    session.refresh(user)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@account_router.delete("", status_code=204)
@limiter.limit("5/minute")
def delete_account(request: Request, payload: DeleteAccountIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    if getattr(user, "role", None) == "SUPER_ADMIN":
        # The platform must always keep its super admin account.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super admin cannot delete itself")
    if payload.password:
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    elif payload.confirm:
        if not _delete_phrase_matches(user, payload.confirm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="confirmation phrase does not match")
    else:
        raise HTTPException(status_code=422, detail="password or confirmation phrase required")
    admin_service.delete_user(session, user)
    session.commit()
    return Response(status_code=204)


__all__ = ["router", "account_router"]
