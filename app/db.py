"""Database wiring for the backend."""

from __future__ import annotations

from typing import Iterator

from syncfit_database import Database

from .config import settings

_DATABASE: Database | None = None


def get_database() -> Database:
    global _DATABASE
    if _DATABASE is None:
        _DATABASE = Database(settings.database_url)
        _DATABASE.init_db()
    return _DATABASE


def get_session() -> Iterator:
    """FastAPI dependency yielding a database session."""
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()


__all__ = ["get_database", "get_session"]
