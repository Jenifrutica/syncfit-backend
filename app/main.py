"""SyncFit Edge backend application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .api.auth import router as auth_router
from .api.routes import router as api_router
from .ws.routes import router as ws_router

__version__ = settings.version


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title=settings.title, version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(ws_router, prefix=settings.api_prefix)

    @app.on_event("startup")
    def _startup() -> None:
        from .db import get_database
        from .services.admin import ensure_superadmin

        session = get_database().session()
        try:
            ensure_superadmin(session)
            session.commit()
        finally:
            session.close()

    return app


app = create_app()

__all__ = ["create_app", "app", "__version__"]
