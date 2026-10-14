"""Assign every demo account a distinct random password.

Run from backend/: python -m app.database.rotate_demo_passwords
This modifies the selected bugpilot.db and writes a private CSV of credentials.
Back up the database first. Do not commit the CSV to source control.
"""
import csv
import secrets
import string
from pathlib import Path
from app.auth.password import hash_password
from app.database.connection import get_connection

ALPHABET = string.ascii_letters + string.digits + "!@#$%*-_"

def make_password(length=16):
    while True:
        value = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if (any(c.islower() for c in value) and any(c.isupper() for c in value)
            and any(c.isdigit() for c in value) and any(c in "!@#$%*-_" for c in value)):
            return value

def main():
    output = Path("demo_user_credentials.csv")
    connection = get_connection()
    try:
        users = connection.execute(
            "SELECT employee_id, username, email FROM users ORDER BY username"
        ).fetchall()
        credentials = []
        for user in users:
            password = make_password()
            connection.execute(
                "UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE employee_id=?",
                (hash_password(password), user["employee_id"]),
            )
            credentials.append((user["employee_id"], user["username"], user["email"], password))
        connection.commit()
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["employee_id", "username", "email", "temporary_password"])
            writer.writerows(credentials)
        print(f"Rotated passwords for {len(credentials)} users.")
        print(f"Credentials saved to {output.resolve()} (keep this file private).")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

if __name__ == "__main__":
    main()
