"""Password hashing with PBKDF2-HMAC-SHA256 and a random salt per password."""

from __future__ import annotations

import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000
SALT_BYTES = 16


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Hash a password for storage.

    Returns "pbkdf2_sha256$<iterations>$<salt hex>$<digest hex>" with a fresh
    random salt, so hashing the same password twice gives different strings.
    """
    if iterations < 1:
        raise ValueError("iterations must be positive")
    salt = os.urandom(SALT_BYTES)
    digest = _derive(password, salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Check a password against a string made by hash_password.

    Malformed hashes and hashes from other algorithms never verify.
    """
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        rounds = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    if algorithm != ALGORITHM or rounds < 1:
        return False
    return hmac.compare_digest(_derive(password, salt, rounds), expected)


def needs_rehash(encoded: str, iterations: int = DEFAULT_ITERATIONS) -> bool:
    """True when a stored hash is malformed or uses fewer iterations than wanted."""
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM or not parts[1].isdigit():
        return True
    return int(parts[1]) < iterations
