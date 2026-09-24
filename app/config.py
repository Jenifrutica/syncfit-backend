"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    title: str = "SyncFit Edge Backend"
    version: str = "0.2.0"
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    secret_key: str = "change-me-in-production"
    token_expire_minutes: int = 60 * 24 * 7
    database_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")
        return cls(
            secret_key=os.environ.get("BACKEND_SECRET_KEY", "change-me-in-production"),
            token_expire_minutes=int(os.environ.get("BACKEND_TOKEN_EXPIRE_MINUTES", 10080)),
            database_url=os.environ.get("SYNCFIT_DATABASE_URL") or os.environ.get("DATABASE_URL"),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )


settings = Settings.from_env()

__all__ = ["Settings", "settings"]
