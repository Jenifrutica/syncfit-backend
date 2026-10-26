"""Client-side password digest.

The browser never sends the typed password: it derives this digest first, so
the plain text does not show up in the network tab or in proxy logs. The server
treats the digest as the password and still hashes it with Argon2 before storing
it. The frontend (`lib/password.ts`) must keep the same algorithm and parameters.
"""

from __future__ import annotations

import hashlib

ITERATIONS = 100_000
SALT_PREFIX = "syncfit:"


def client_digest(email: str, password: str) -> str:
    """PBKDF2-HMAC-SHA256 of the password, salted with the lower-cased email (64 hex chars)."""
    salt = f"{SALT_PREFIX}{email.strip().lower()}".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()


__all__ = ["client_digest", "ITERATIONS", "SALT_PREFIX"]
