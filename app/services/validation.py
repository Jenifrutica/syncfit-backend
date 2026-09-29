"""Name and identity validation shared by registration, gyms and users.

Names are restricted to letters (Unicode, so accents work), spaces and a few
punctuation marks; digits and other symbols are rejected. A configurable list of
**reserved** names is blocked unless the (lower-cased) name is explicitly listed
in ``BACKEND_NAME_EXCEPTIONS``.
"""

from __future__ import annotations

import os
import re

# Letters (Unicode, so accents work), with single separators between letter runs.
# `[^\W\d_]` matches a letter (never a digit or underscore).
_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+)*\.?$", re.UNICODE)
_DOCUMENT_RE = re.compile(r"^[0-9]{6,15}$")

_MIN_NAME = 2
_MAX_NAME = 60

_RESERVED_DEFAULT = {
    "admin", "administrator", "root", "system", "syncfit", "support",
    "null", "none", "test", "gym", "gimnasio",
}


def _reserved() -> set[str]:
    return _RESERVED_DEFAULT | {
        n.strip().lower() for n in os.environ.get("BACKEND_RESERVED_NAMES", "").split(",") if n.strip()
    }


def _exceptions() -> set[str]:
    return {n.strip().lower() for n in os.environ.get("BACKEND_NAME_EXCEPTIONS", "").split(",") if n.strip()}


def normalize_name(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def validate_name(value: str, *, field: str = "name", reserved: bool = True) -> str:
    """Return the normalized name or raise ``ValueError`` with a clear message."""
    name = normalize_name(value)
    if not (_MIN_NAME <= len(name) <= _MAX_NAME):
        raise ValueError(f"{field} must be {_MIN_NAME}-{_MAX_NAME} characters")
    if not _NAME_RE.match(name):
        raise ValueError(f"{field} may only contain letters, spaces, apostrophes, hyphens and dots")
    if reserved and name.lower() in _reserved() and name.lower() not in _exceptions():
        raise ValueError(f"{field} '{name}' is reserved")
    return name


def validate_person_name(value: str) -> str:
    return validate_name(value, field="display_name")


def validate_gym_name(value: str) -> str:
    return validate_name(value, field="gym name")


def validate_document_id(value: str) -> str:
    document = str(value or "").strip()
    if not _DOCUMENT_RE.match(document):
        raise ValueError("document_id must be 6-15 digits")
    return document


__all__ = [
    "normalize_name",
    "validate_name",
    "validate_person_name",
    "validate_gym_name",
    "validate_document_id",
    "RESERVED_DEFAULT",
]
