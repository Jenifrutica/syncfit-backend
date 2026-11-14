"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql+psycopg://syncfit:syncfit@localhost:5432/syncfit"


def _load_dotenv() -> None:
    """Load the nearest `.env` without overriding real environment variables."""
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return
    
# Personalized exception
class InvalidSecretKeyError(RuntimeError):
    """ Raised when a required settings is missing"""
@dataclass(frozen=True)
class Settings:
    title: str = "SyncFit Edge Backend"
    version: str = "0.2.0"
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    cors_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    secret_key: str = "change-me-in-production"
    token_expire_minutes: int = 60 * 24
    database_url: str = DEFAULT_DATABASE_URL
    superadmin_email: str | None = None
    superadmin_password: str | None = None
    superadmin_name: str = "Super Admin"
    routine_engine: str = "ai"
    rate_limit_enabled: bool = True
    google_client_id: str | None = None
    # Public app URL used in emails (the reset link has to point at the frontend).
    app_base_url: str = "http://localhost:3000"
    password_reset_minutes: int = 30
    # AWS SES SMTP. Without a host/user/password the endpoint reports the mail
    # service as unavailable instead of silently dropping the message.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    demo_login_enabled: bool = False
    demo_superadmin_email: str | None = None
    demo_admin_email: str | None = None
    demo_admin_name: str = "Demo Admin"
    demo_admin_gym_name: str = "Valhalla"
    demo_athlete_name: str = "Nicolasa"
    demo_athlete_email: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        origins = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")

        secret_key = os.environ.get("BACKEND_SECRET_KEY", "")

        if len(secret_key) < 32 or secret_key.startswith("change-me") or secret_key is None:
            raise InvalidSecretKeyError (
                "BACKEND_SECRET_KEY must be a random string of at least 32 characters"
            )

        rate_limit_enabled = (
            os.environ.get("BACKEND_RATE_LIMIT_ENABLED", "true").lower() == "true"
        )

        return cls(
            routine_engine=os.environ.get("BACKEND_ROUTINE_ENGINE", "ai"),
            rate_limit_enabled=rate_limit_enabled,
            secret_key=secret_key,
            token_expire_minutes=int(os.environ.get("BACKEND_TOKEN_EXPIRE_MINUTES", 1440)),
            database_url=os.environ.get("SYNCFIT_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or DEFAULT_DATABASE_URL,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            superadmin_email=os.environ.get("SUPERADMIN_EMAIL"),
            superadmin_password=os.environ.get("SUPERADMIN_PASSWORD"),
            superadmin_name=os.environ.get("SUPERADMIN_NAME", "Super Admin"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID") or None,
            app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:3000").rstrip("/"),
            password_reset_minutes=int(os.environ.get("PASSWORD_RESET_MINUTES", "30")),
            smtp_host=os.environ.get("SMTP_HOST") or None,
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER") or None,
            smtp_password=os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_PASS") or None,
            smtp_from=os.environ.get("SMTP_FROM") or None,
            demo_login_enabled=os.environ.get("DEMO_LOGIN_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            demo_superadmin_email=os.environ.get("DEMO_SUPERADMIN_EMAIL") or None,
            demo_admin_email=os.environ.get("DEMO_ADMIN_EMAIL") or None,
            demo_admin_name=os.environ.get("DEMO_ADMIN_NAME", "Demo Admin"),
            demo_admin_gym_name=os.environ.get("DEMO_ADMIN_GYM_NAME", "Valhalla"),
            demo_athlete_name=os.environ.get("DEMO_ATHLETE_NAME", "Nicolasa"),
            demo_athlete_email=os.environ.get("DEMO_ATHLETE_EMAIL") or None,
            cors_origin_regex=os.environ.get(
                "BACKEND_CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
            ),
        )


settings = Settings.from_env()

__all__ = ["Settings", "settings", "DEFAULT_DATABASE_URL", "InvalidSecretKeyError"]

