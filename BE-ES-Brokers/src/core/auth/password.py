"""Password hashing for the Admin Panel's password-checked login
(``POST /api/core/auth/admin-login``). Stdlib-only (PBKDF2-HMAC-SHA256) —
deliberately no new dependency for a feature used by exactly one login path.

The rest of the app's login (``POST /api/core/auth/login``, used by
``IndustryAI-Insaurance-ES-Brokers`` for junior/senior/admin alike) stays
untouched, unhashed-email-lookup, Phase-0 stub auth — this module is not
wired into it.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ALGORITHM = "sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_str, salt_hex, digest_hex = stored.split("$")
        expected = bytes.fromhex(digest_hex)
        salt = bytes.fromhex(salt_hex)
        iterations = int(iterations_str)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac(algorithm, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)
