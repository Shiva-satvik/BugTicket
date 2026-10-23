"""Set ONE shared password for many BugPilot accounts.

Run from backend/:
    python -m app.database.set_uniform_password
    python -m app.database.set_uniform_password --password 'YourPass@123'
    python -m app.database.set_uniform_password --role EMPLOYEE
    python -m app.database.set_uniform_password --include-admin

Default behaviour:
- Password comes from --password, or EMPLOYEE_DEFAULT_PASSWORD from .env,
  or falls back to BugPilot@2026.
- ADMIN-role users are SKIPPED unless --include-admin is passed, so your own
  admin password is never overwritten by accident.
- A credentials CSV (employee_id, username, email, department, roles,
  password) is written for distributing logins. Keep it private.

Note: every user gets an individually salted PBKDF2 hash, so hashing ~200
users takes roughly 30-60 seconds. Progress is printed every 50 users.
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from app.auth.password import hash_password
from app.database.connection import get_connection

load_dotenv()

DEFAULT_PASSWORD = os.getenv("EMPLOYEE_DEFAULT_PASSWORD", "BugPilot@2026")


def _placeholder_hash(hash_value: str | None) -> bool:
    """Detect seeded users that never received a working password."""
    value = (hash_value or "").strip()
    if not value:
        return True
    return value.upper().startswith("TEMP")


def _load_roles(connection) -> dict[str, list[str]]:
    rows = connection.execute(
        """
        SELECT ur.employee_id, r.role_code
        FROM user_roles ur
        INNER JOIN roles r ON r.role_id = ur.role_id
        WHERE r.is_active = 1
        """
    ).fetchall()
    mapping: dict[str, list[str]] = {}
    for row in rows:
        mapping.setdefault(row["employee_id"], []).append(row["role_code"])
    return mapping


def _resolve_department_filter(connection, department: str | None) -> int | None:
    if not department:
        return None
    row = connection.execute(
        "SELECT department_id FROM departments WHERE department_code = ? OR department_name = ?",
        (department, department),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Department '{department}' was not found.")
    return row["department_id"]


def set_uniform_password(
    password: str = DEFAULT_PASSWORD,
    include_admin: bool = False,
    only_role: str | None = None,
    only_department: str | None = None,
    csv_path: str = "employee_credentials.csv",
    only_placeholder: bool = False,
) -> dict:
    """Update the selected accounts and write the credentials CSV."""
    if not password or len(password) < 8:
        raise SystemExit("Password must be at least 8 characters long.")

    connection = get_connection()
    started = time.monotonic()

    try:
        department_id = _resolve_department_filter(connection, only_department)
        roles_by_employee = _load_roles(connection)

        query = """
            SELECT u.employee_id, u.username, u.full_name, u.email,
                   u.department_id, u.designation, u.password_hash,
                   d.department_name
            FROM users u
            LEFT JOIN departments d ON d.department_id = u.department_id
            WHERE u.is_active = 1
        """
        params: list = []
        if department_id is not None:
            query += " AND u.department_id = ?"
            params.append(department_id)
        query += " ORDER BY u.username"
        users = connection.execute(query, tuple(params)).fetchall()

        selected = []
        skipped_admin = 0
        skipped_placeholder = 0

        for user in users:
            roles = [r.upper() for r in roles_by_employee.get(user["employee_id"], [])]

            if only_role and only_role.upper() not in roles:
                continue

            if "ADMIN" in roles and not include_admin:
                skipped_admin += 1
                continue

            if only_placeholder and not _placeholder_hash(user["password_hash"]):
                skipped_placeholder += 1
                continue

            selected.append((user, roles))

        if not selected:
            print("No users matched the given filters. Nothing was changed.")
            return {"updated": 0, "csv_path": None}

        print(f"Updating passwords for {len(selected)} user(s) "
              f"(skipped {skipped_admin} admin, {skipped_placeholder} already-configured)...")

        updates = []
        credential_rows = []
        for index, (user, roles) in enumerate(selected, start=1):
            updates.append(
                (hash_password(password), user["employee_id"])
            )
            credential_rows.append([
                user["employee_id"],
                user["username"],
                user["full_name"],
                user["email"],
                user["department_name"] or "",
                user["designation"] or "",
                ", ".join(roles) if roles else "UNASSIGNED",
                password,
            ])
            if index % 50 == 0:
                print(f"  hashed {index}/{len(selected)} users...")

        connection.executemany(
            """
            UPDATE users
            SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
            WHERE employee_id = ?
            """,
            updates,
        )
        connection.commit()

        output = Path(csv_path)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "employee_id", "username", "full_name", "email",
                "department", "designation", "roles", "password",
            ])
            writer.writerows(credential_rows)

        elapsed = time.monotonic() - started
        print(f"Done in {elapsed:.1f}s. {len(selected)} account(s) now use the shared password.")
        print(f"Credentials saved to: {output.resolve()}")
        print("Keep this CSV private and do not commit it to source control.")

        return {
            "updated": len(selected),
            "skipped_admin": skipped_admin,
            "csv_path": str(output.resolve()),
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set one shared password for many BugPilot accounts and export a credentials CSV."
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Shared password (default: EMPLOYEE_DEFAULT_PASSWORD from .env or {DEFAULT_PASSWORD!r}).",
    )
    parser.add_argument(
        "--include-admin",
        action="store_true",
        help="Also update ADMIN-role accounts (default: admins are skipped).",
    )
    parser.add_argument(
        "--role",
        default=None,
        help="Only update users holding this role code (e.g. EMPLOYEE).",
    )
    parser.add_argument(
        "--department",
        default=None,
        help="Only update users in this department (code or name, e.g. FIN).",
    )
    parser.add_argument(
        "--csv",
        default="employee_credentials.csv",
        help="Output CSV path (default: employee_credentials.csv).",
    )
    parser.add_argument(
        "--only-placeholder",
        action="store_true",
        help="Only update users whose password hash is missing or a TEMP placeholder.",
    )
    args = parser.parse_args()

    set_uniform_password(
        password=args.password,
        include_admin=args.include_admin,
        only_role=args.role,
        only_department=args.department,
        csv_path=args.csv,
        only_placeholder=args.only_placeholder,
    )


if __name__ == "__main__":
    main()
