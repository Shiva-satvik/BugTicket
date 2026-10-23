"""Reset one user's password from the command line.

Run from backend/:
    python reset_user_password.py john.reddy
    python reset_user_password.py SVN-12345 'NewPass@2026'

The password defaults to EMPLOYEE_DEFAULT_PASSWORD from .env
(or BugPilot@2026) when not provided.
"""

import os
import sys

from dotenv import load_dotenv

from app.auth.password import hash_password
from app.database.connection import get_connection

load_dotenv()

DEFAULT_PASSWORD = os.getenv("EMPLOYEE_DEFAULT_PASSWORD", "BugPilot@2026")


def reset_user_password(identifier: str, new_password: str) -> bool:
    """Reset the password of the user matching username or employee_id."""
    if not new_password or len(new_password) < 8:
        raise SystemExit("Password must be at least 8 characters long.")

    connection = get_connection()
    try:
        user = connection.execute(
            "SELECT employee_id, username FROM users WHERE username = ? OR employee_id = ?",
            (identifier, identifier),
        ).fetchone()

        if user is None:
            print(f"No user found for '{identifier}'.")
            return False

        connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE employee_id = ?",
            (hash_password(new_password), user["employee_id"]),
        )
        connection.commit()

        print(f"Password reset for {user['username']} ({user['employee_id']}).")
        return True
    finally:
        connection.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: python reset_user_password.py <username-or-employee-id> [new-password]")
        sys.exit(1)

    identifier = sys.argv[1].strip()
    password = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_PASSWORD

    ok = reset_user_password(identifier, password)
    sys.exit(0 if ok else 1)
