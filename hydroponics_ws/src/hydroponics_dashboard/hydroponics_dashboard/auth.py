"""Authentication for the AIdroponics dashboard.

Password is stored as a salted SHA-256 hash — never in plain text.
Control endpoints require a valid bearer token obtained via /api/auth/login.
Read-only endpoints remain open for shared viewer access.
"""

import hashlib
import secrets
from typing import Set

_SALT = "aidroponics_auth_salt_v1"
_PASSWORD_HASH = "0b4a4c945b77c4eb0aa2bc61ffd1b294693484d3a1092fdb886fb0fcf0143126"

_active_tokens: Set[str] = set()


def verify_password(password: str) -> bool:
    computed = hashlib.sha256((_SALT + password).encode()).hexdigest()
    return secrets.compare_digest(computed, _PASSWORD_HASH)


def create_token() -> str:
    token = secrets.token_hex(32)
    _active_tokens.add(token)
    return token


def verify_token(token: str) -> bool:
    return token in _active_tokens


def revoke_token(token: str) -> None:
    _active_tokens.discard(token)
