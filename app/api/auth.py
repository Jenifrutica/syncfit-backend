"""Authentication routes: register, login and current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from syncfit_database import User

from ..db import get_session
from ..services.auth import (
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)
from ..services.validation import validate_document_id, validate_person_name

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=1)
    document_id: str = Field(min_length=6, max_length=15)


class LoginIn(BaseModel):
    email: str
    password: str


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
def register(payload: RegisterIn, session: Session = Depends(get_session)) -> dict:
    if "@" not in payload.email:
        raise HTTPException(status_code=422, detail="invalid email")
    try:
        display_name = validate_person_name(payload.display_name)
        document_id = validate_document_id(payload.document_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = session.query(User).filter_by(email=payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    if session.query(User).filter_by(document_id=document_id).one_or_none() is not None:
        raise HTTPException(status_code=409, detail="document_id already registered")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=display_name,
        document_id=document_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/login")
def login(payload: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.query(User).filter_by(email=payload.email.lower()).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if getattr(user, "active", True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account deactivated")
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _public_user(user)


__all__ = ["router"]
