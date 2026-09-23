"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    title: str = "SyncFit Edge Backend"
    version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")
        return cls(cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()))


settings = Settings.from_env()

__all__ = ["Settings", "settings"]
