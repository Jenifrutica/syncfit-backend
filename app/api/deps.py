"""FastAPI authentication and role dependencies."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from syncfit_database import User

from ..db import get_session
from ..services.auth import AccountInactive, InvalidCredentials, authenticate_token

_bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return authenticate_token(session, credentials.credentials)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccountInactive as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def require_super_admin(user: User = Depends(current_user)) -> User:
    if getattr(user, "role", None) != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super admin required")
    return user


def require_gym_admin(user: User = Depends(current_user)) -> User:
    if getattr(user, "role", None) != "GYM_ADMIN":
        raise HTTPException(status_code=403, detail="Gym admin required")
    return user
