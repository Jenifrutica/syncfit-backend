"""Account use cases with persistent users and no HTTP transport dependencies."""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session
from syncfit_database import Gym, Profile, User

from ..config import Settings
from . import admin as admin_service
from . import gyms as gym_service
from . import mailer, password_reset
from .auth import AccountInactive, InvalidAccountData, InvalidCredentials, RegistrationConflict, hash_password, verify_password

logger = logging.getLogger(__name__)


class ResetDeliveryUnavailable(Exception):
    """The email delivery service is not configured."""


class InvalidResetToken(Exception):
    """The reset token or simulation request cannot be used."""


class AccountDeletionForbidden(Exception):
    """The account cannot be deleted under the current policy."""


def _demo_athlete(session: Session, settings: Settings) -> User:
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


def _demo_admin(session: Session, settings: Settings) -> User:
    """The demo gym admin: reuse an existing admin or create one with a gym."""
    email = (settings.demo_admin_email or "asgardcito@asgard.com").strip().lower()
    user = session.query(User).filter(func.lower(User.email) == email).one_or_none()
    if user is not None and user.role != "GYM_ADMIN":
        if settings.demo_admin_email:
            # The configured address belongs to another role: creating it again
            # would hit the unique email constraint.
            raise RegistrationConflict("demo admin email has another role")
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
        gym_service.create_gym(session, user, settings.demo_admin_gym_name or "Asgard")
    session.commit()
    return user


def get_demo_user(session: Session, role: str, settings: Settings) -> User | None:
    if role == "ATHLETE":
        return _demo_athlete(session, settings)
    if role == "GYM_ADMIN":
        return _demo_admin(session, settings)
    email = settings.demo_superadmin_email
    user = session.query(User).filter_by(email=email.strip().lower()).one_or_none() if email else None
    if user is None:
        user = session.query(User).filter_by(role=role, active=True).first()
    return user


def send_password_reset(session: Session, email: str, settings: Settings) -> None:
    if not mailer.is_configured():
        raise ResetDeliveryUnavailable("email service unavailable")
    user = session.query(User).filter(func.lower(User.email) == email.strip().lower()).one_or_none()
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


def simulate_password_reset(session: Session, email: str, settings: Settings) -> dict:
    email = email.strip().lower()
    if not settings.demo_login_enabled or email not in settings.demo_simulated_emails:
        raise InvalidResetToken("not a simulated address")
    user = session.query(User).filter(func.lower(User.email) == email).one_or_none()
    if user is None or user.role == "SUPER_ADMIN" or getattr(user, "active", True) is False:
        raise InvalidResetToken("not a simulated address")
    raw = password_reset.issue_token(session, user)
    return {
        "simulated": True,
        "to": user.email,
        "token": raw,
        "link": f"{settings.app_base_url}/recuperar/?token={raw}",
        "expires_minutes": settings.password_reset_minutes,
    }


def password_reset_email(session: Session, token: str) -> str:
    row = password_reset.valid_token(session, token)
    user = session.get(User, row.user_id) if row is not None else None
    if row is None or user is None:
        raise InvalidResetToken("invalid or expired token")
    # The token holder already owns this inbox; the email is needed to digest
    # the new password client-side, exactly like login and register do.
    return user.email


def reset_user_password(session: Session, token: str, password: str) -> None:
    row = password_reset.valid_token(session, token)
    if row is None:
        raise InvalidResetToken("invalid or expired token")
    user = session.get(User, row.user_id)
    if user is None or getattr(user, "active", True) is False:
        raise InvalidResetToken("invalid or expired token")
    if verify_password(password, user.password_hash):
        raise InvalidAccountData("new password must differ from the current one")
    if not password_reset.apply_reset(session, row, hash_password(password)):
        raise InvalidResetToken("invalid or expired token")


def get_or_create_google_user(session: Session, email: str, name: object) -> User:
    user = session.query(User).filter_by(email=email).one_or_none()
    if user is None:
        display_name = str(name or email.split("@")[0])[:120]
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            display_name=display_name,
            role="ATHLETE",
            token_version=0,
        )
        session.add(user)
    if getattr(user, "active", True) is False:
        raise AccountInactive("account deactivated")
    session.commit()
    session.refresh(user)
    return user


_DELETE_VERBS = ("eliminar", "delete", "删除")


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _delete_phrase_matches(user: User, confirm: str) -> bool:
    name = _normalize_text(user.display_name)
    expected = {f"{verb} {name}" for verb in _DELETE_VERBS}
    return _normalize_text(confirm) in expected


def delete_own_account(session: Session, user: User, password: str | None, confirm: str | None) -> None:
    if getattr(user, "role", None) == "SUPER_ADMIN":
        # The platform must always keep its super admin account.
        raise AccountDeletionForbidden("super admin cannot delete itself")
    if password:
        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("invalid credentials")
    elif confirm:
        if not _delete_phrase_matches(user, confirm):
            raise AccountDeletionForbidden("confirmation phrase does not match")
    else:
        raise InvalidAccountData("password or confirmation phrase required")
    admin_service.delete_user(session, user)
    session.commit()
