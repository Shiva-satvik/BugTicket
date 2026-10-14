"""Password hashing with PBKDF2-SHA256 and legacy bcrypt verification.

New passwords use the standard-library PBKDF2 implementation so setup works
without a compiled extension. Existing bcrypt hashes remain verifiable during
migration if bcrypt is installed in the backend environment.
"""
import base64
import hashlib
import hmac
import os

_ITERATIONS = 310_000
_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 1:
        raise ValueError("Password must not be empty.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "$".join((
        _PREFIX,
        str(_ITERATIONS),
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    ))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password and hashed_password.startswith(_PREFIX + "$"):
        try:
            _, iterations, salt_text, digest_text = hashed_password.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
            expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
            actual = hashlib.pbkdf2_hmac(
                "sha256", plain_password.encode("utf-8"), salt, int(iterations)
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    # Compatibility path for bcrypt hashes already in a database.
    if hashed_password and hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (ImportError, ValueError):
            return False
    return False
