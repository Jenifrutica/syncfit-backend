import re

from app.services.credentials import client_digest


def test_digest_is_64_hex_characters():
    assert re.fullmatch(r"[0-9a-f]{64}", client_digest("ana@example.com", "secret123"))


def test_digest_never_contains_the_password():
    assert "secret123" not in client_digest("ana@example.com", "secret123")


def test_same_input_gives_same_digest_and_email_case_is_ignored():
    assert client_digest("Ana@Example.com ", "secret123") == client_digest("ana@example.com", "secret123")


def test_email_acts_as_salt():
    assert client_digest("ana@example.com", "secret123") != client_digest("bea@example.com", "secret123")


def test_known_vector_shared_with_the_frontend():
    # The frontend test uses the same vector; if one changes, the other must too.
    assert client_digest("test@syncfit.dev", "Secret123!") == (
        "e8e6873f309fd3e28a0a45480ec4015d965017d54bc6db13e5ac5dce49765868"
    )
