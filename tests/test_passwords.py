"""Password hashing tests (Argon2 + legacy PBKDF2).

They only exercise `app.services.auth`, so they can run without the private
`syncfit-database` package: if it is not installed, a minimal stand-in module
is registered just so the import succeeds. CI installs the real package, so
there the stand-in is never used. Run locally with:

    pytest tests/test_passwords.py
"""

import hashlib
import sys
import types

try:
    import syncfit_database  # noqa: F401
except ModuleNotFoundError:
    _stub = types.ModuleType("syncfit_database")
    _stub.User = type("User", (), {})
    _stub.Database = type("Database", (), {})
    sys.modules["syncfit_database"] = _stub

from app.services.auth import hash_password, needs_rehash, verify_password


def _legacy_hash(password: str) -> str:
    """Build a hash in the old format: pbkdf2_sha256$<iterations>$<salt>$<digest>."""
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def test_new_hashes_use_argon2id():
    assert hash_password("secreta123").startswith("$argon2id$")


def test_argon2_correct_password():
    assert verify_password("secreta123", hash_password("secreta123")) is True


def test_argon2_wrong_password():
    assert verify_password("otra-clave", hash_password("secreta123")) is False


def test_legacy_pbkdf2_correct_password():
    assert verify_password("vieja123", _legacy_hash("vieja123")) is True


def test_legacy_pbkdf2_wrong_password():
    assert verify_password("otra-clave", _legacy_hash("vieja123")) is False


def test_corrupt_hash_returns_false():
    assert verify_password("secreta123", "not-a-real-hash") is False
    assert verify_password("secreta123", "pbkdf2_sha256$roto") is False


def test_needs_rehash_flags_only_legacy_hashes():
    assert needs_rehash(_legacy_hash("vieja123")) is True
    assert needs_rehash(hash_password("secreta123")) is False
