from syncfit_database import User

from app.db import get_database
from app.services.admin import ensure_superadmin
from app.services.auth import hash_password, verify_password
from app.services.credentials import client_digest

EMAIL = "root@syncfit.dev"


def _root(session) -> User:
    return session.query(User).filter_by(email=EMAIL).one()


def test_seeded_super_admin_verifies_with_the_digest_not_the_plain_password():
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        stored = _root(s).password_hash
    assert verify_password(client_digest(EMAIL, "rootsecret123"), stored)
    assert not verify_password("rootsecret123", stored)


def test_seed_resyncs_a_super_admin_stored_with_the_old_plain_hash():
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        root = _root(s)
        root.password_hash = hash_password("rootsecret123")
        version = root.token_version
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        root = _root(s)
        assert verify_password(client_digest(EMAIL, "rootsecret123"), root.password_hash)
        assert root.token_version == version + 1


def test_seed_leaves_a_correct_hash_alone():
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        before = _root(s).password_hash
    with get_database().session_scope() as s:
        ensure_superadmin(s)
        assert _root(s).password_hash == before
