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


@dataclass(frozen=True)
class Settings:
    title: str = "SyncFit Edge Backend"
    version: str = "0.2.0"
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    secret_key: str = "change-me-in-production"
    token_expire_minutes: int = 60 * 24 * 7
    database_url: str = DEFAULT_DATABASE_URL

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        origins = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")
        return cls(
            secret_key=os.environ.get("BACKEND_SECRET_KEY", "change-me-in-production"),
            token_expire_minutes=int(os.environ.get("BACKEND_TOKEN_EXPIRE_MINUTES", 10080)),
            database_url=os.environ.get("SYNCFIT_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or DEFAULT_DATABASE_URL,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )


settings = Settings.from_env()

__all__ = ["Settings", "settings", "DEFAULT_DATABASE_URL"]

