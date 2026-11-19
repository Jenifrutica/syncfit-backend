"""Authentication routes: register, login and current user."""

from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from syncfit_database import User

from ..config import settings
from ..db import get_session
from ..rate_limit import limiter
from ..services import account_flows as accounts
from ..services.auth import (
    AccountInactive,
    InvalidAccountData,
    InvalidCredentials,
    RegistrationConflict,
    authenticate_password,
    change_user_password,
    create_access_token,
    logout_user,
    register_user,
)
from .deps import current_user

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
    try:
        user = register_user(session, email=payload.email, password=payload.password,
                             display_name=payload.display_name, document_id=payload.document_id)
    except InvalidAccountData as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RegistrationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginIn, session: Session = Depends(get_session)) -> dict:
    try:
        user = authenticate_password(session, payload.email, payload.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccountInactive as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


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
    try:
        user = accounts.get_demo_user(session, payload.role, settings)
    except RegistrationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    try:
        accounts.send_password_reset(session, payload.email, settings)
    except accounts.ResetDeliveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent"}


@router.post("/forgot/simulated")
@limiter.limit("10/minute")
def forgot_password_simulated(
    request: Request, payload: ForgotPasswordIn, session: Session = Depends(get_session)
) -> dict:
    """Evaluation only: for the demo accounts with made-up addresses, hand the
    reset link to the screen instead of emailing it. Never for a super admin,
    and 404 for every other address (those get the real email)."""
    try:
        return accounts.simulate_password_reset(session, payload.email, settings)
    except accounts.InvalidResetToken as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reset/{token}")
def check_reset_token(token: str, session: Session = Depends(get_session)) -> dict:
    try:
        email = accounts.password_reset_email(session, token)
    except accounts.InvalidResetToken as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"valid": True, "email": email}


@router.post("/reset", status_code=204)
@limiter.limit("10/minute")
def reset_password(
    request: Request, payload: ResetPasswordIn, session: Session = Depends(get_session)
) -> None:
    try:
        accounts.reset_user_password(session, payload.token, payload.password)
    except accounts.InvalidResetToken as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAccountData as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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

    try:
        user = accounts.get_or_create_google_user(session, email, info.get("name"))
    except AccountInactive as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
    logout_user(session, user)
    return Response(status_code=204)


@router.put("/password")
@limiter.limit("5/minute")
def change_password(request: Request, payload: ChangePasswordIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    try:
        change_user_password(session, user, payload.current_password, payload.new_password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidAccountData as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@account_router.delete("", status_code=204)
@limiter.limit("5/minute")
def delete_account(request: Request, payload: DeleteAccountIn, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Response:
    try:
        accounts.delete_own_account(session, user, payload.password, payload.confirm)
    except accounts.AccountDeletionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidAccountData as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


__all__ = ["router", "account_router"]
