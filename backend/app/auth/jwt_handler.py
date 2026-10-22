
import os
from datetime import datetime, timedelta, timezone

from jose import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours; reduces mid-session 401s during development/demos.


def _get_secret_key() -> str:
    """Load and validate the JWT signing secret."""
    secret = SECRET_KEY

    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing. "
            "Add a secure JWT_SECRET_KEY to your .env file."
        )

    if len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must contain at least 32 characters."
        )

    return secret


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token with an expiration time."""
    if not isinstance(data, dict):
        raise TypeError("Token data must be a dictionary.")

    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload["exp"] = expire

    return jwt.encode(
        payload,
        _get_secret_key(),
        algorithm=ALGORITHM,
    )
