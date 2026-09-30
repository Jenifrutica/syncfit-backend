"""Rate limiting to prevent brute-force attacks."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)

__all__ = ["limiter"]
