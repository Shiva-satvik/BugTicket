"""One command to get 200 employees fully working in BugPilot.

Run from backend/:
    python -m app.database.seed_employees_200

What it does (idempotent - safe to run repeatedly):
1. Ensures departments and roles exist (same master data as the original seeds).
2. Tops the active headcount up to TARGET_TOTAL (200), filling each department
   to its configured size before distributing any remainder.
3. Assigns roles to users that have none, following ROLE_DISTRIBUTION
   (2 ADMIN, 15 MANAGER, 35 DEVELOPER, 30 SUPPORT, 105 EMPLOYEE, 13 VIEWER).
   Existing role assignments are never changed or removed.
4. Gives every account without a real password (TEMP placeholders) the shared
   password from EMPLOYEE_DEFAULT_PASSWORD (.env) or --password.
   Use --reset-passwords to force the shared password onto ALL non-admin
   accounts (admins stay untouched unless --include-admin).
5. Writes employee_credentials.csv with login details for distribution.

The script is deterministic: it uses a fixed random seed, so re-running it
produces the same names for the same starting database.
"""

import argparse
import csv
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv

from app.auth.password import hash_password, verify_password
from app.database.connection import get_connection
from app.database.seed_master_data import seed_departments, seed_roles
from app.database.seed_users import (
    COMPANY_DOMAIN,
    DEPARTMENT_CONFIG,
    FIRST_NAMES,
    LAST_NAMES,
    generate_employee_id,
    generate_username,
)

load_dotenv()

TARGET_TOTAL = 200

ROLE_DISTRIBUTION = {
    "ADMIN": 2,
    "MANAGER": 15,
    "DEVELOPER": 35,
    "SUPPORT": 30,
    "EMPLOYEE": 105,
    "VIEWER": 13,
}

DEFAULT_PASSWORD = os.getenv("EMPLOYEE_DEFAULT_PASSWORD", "BugPilot@2026")

GENERIC_DESIGNATIONS = [
    "Systems Engineer",
    "Senior Systems Engineer",
    "Software Engineer",
    "Senior Software Engineer",
    "Technical Lead",
]


def _placeholder_hash(hash_value: str | None) -> bool:
    value = (hash_value or "").strip()
    if not value:
        return True
    return value.upper().startswith("TEMP")


def _load_role_ids(connection) -> dict[str, int]:
    roles = {
        row["role_code"]: row["role_id"]
        for row in connection.execute(
            "SELECT role_id, role_code FROM roles WHERE is_active = 1"
        ).fetchall()
    }
    missing = [code for code in ROLE_DISTRIBUTION if code not in roles]
    if missing:
        raise SystemExit(
            f"Roles missing from the database: {', '.join(missing)}. "
            "Run python -m app.database.seed_master_data first."
        )
    return roles


def _existing_state(connection) -> dict:
    users = connection.execute(
        """
        SELECT u.employee_id, u.username, u.full_name, u.email,
               u.department_id, u.designation, u.password_hash,
               d.department_code
        FROM users u
        LEFT JOIN departments d ON d.department_id = u.department_id
        WHERE u.is_active = 1
        """
    ).fetchall()

    role_rows = connection.execute(
        """
        SELECT ur.employee_id, r.role_code
        FROM user_roles ur
        INNER JOIN roles r ON r.role_id = ur.role_id
        WHERE r.is_active = 1
        """
    ).fetchall()

    roles_by_employee: dict[str, list[str]] = {}
    for row in role_rows:
        roles_by_employee.setdefault(row["employee_id"], []).append(row["role_code"])

    department_counts: dict[int | None, int] = {}
    for user in users:
        department_counts[user["department_id"]] = (
            department_counts.get(user["department_id"], 0) + 1
        )

    return {
        "users": users,
        "roles_by_employee": roles_by_employee,
        "department_counts": department_counts,
    }


def _top_up_users(connection, state: dict, target_total: int) -> list[dict]:
    """Create users until the active headcount reaches target_total."""
    departments = {
        row["department_code"]: row["department_id"]
        for row in connection.execute(
            "SELECT department_id, department_code FROM departments WHERE is_active = 1"
        ).fetchall()
    }

    used_employee_ids = {user["employee_id"] for user in state["users"]}
    used_usernames = {user["username"] for user in state["users"]}
    used_emails = {user["email"] for user in state["users"]}

    plan: list[tuple[int, str | None]] = []

    # Fill each configured department up to its planned size first.
    for department_code, config in DEPARTMENT_CONFIG.items():
        department_id = departments.get(department_code)
        if department_id is None:
            continue
        current = state["department_counts"].get(department_id, 0)
        deficit = max(0, config["count"] - current)
        for _ in range(deficit):
            plan.append((department_id, department_code))

    # Distribute any remainder round-robin across active departments.
    remaining = target_total - (len(state["users"]) + len(plan))
    if remaining > 0:
        active_codes = [code for code in DEPARTMENT_CONFIG if code in departments]
        index = 0
        while remaining > 0 and active_codes:
            code = active_codes[index % len(active_codes)]
            plan.append((departments[code], code))
            index += 1
            remaining -= 1

    created = []
    for department_id, department_code in plan:
        designations = DEPARTMENT_CONFIG.get(department_code, {}).get(
            "designations", GENERIC_DESIGNATIONS
        )

        for _attempt in range(50):
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            employee_id = generate_employee_id(used_employee_ids)
            username = generate_username(first_name, last_name, used_usernames)
            email = f"{username}@{COMPANY_DOMAIN}"
            if email not in used_emails:
                break
        else:
            continue

        used_emails.add(email)
        full_name = f"{first_name} {last_name}"
        designation = random.choice(designations)

        connection.execute(
            """
            INSERT OR IGNORE INTO users (
                employee_id, username, full_name, email,
                password_hash, department_id, designation
            )
            VALUES (?, ?, ?, ?, '', ?, ?)
            """,
            (employee_id, username, full_name, email, department_id, designation),
        )
        created.append(
            {
                "employee_id": employee_id,
                "username": username,
                "full_name": full_name,
                "email": email,
                "department_id": department_id,
                "department_code": department_code,
                "designation": designation,
                "password_hash": "",
                "is_new": True,
            }
        )

    connection.commit()
    return created


def _assign_roles(connection, state: dict, created: list[dict], role_ids: dict[str, int]) -> int:
    """Give every role-less user a role, honouring the target distribution."""
    current_counts = {code: 0 for code in ROLE_DISTRIBUTION}
    for roles in state["roles_by_employee"].values():
        for role in roles:
            role_upper = role.upper()
            if role_upper in current_counts:
                current_counts[role_upper] += 1

    deficits = {
        code: max(0, target - current_counts[code])
        for code, target in ROLE_DISTRIBUTION.items()
    }

    roleless_ids = [
        user["employee_id"]
        for user in state["users"]
        if not state["roles_by_employee"].get(user["employee_id"])
    ]
    roleless_ids.extend(user["employee_id"] for user in created)

    random.shuffle(roleless_ids)

    assignments = []
    cursor_position = 0
    for role_code, deficit in deficits.items():
        for _ in range(deficit):
            if cursor_position >= len(roleless_ids):
                break
            employee_id = roleless_ids[cursor_position]
            cursor_position += 1
            assignments.append((employee_id, role_ids[role_code], "SYSTEM"))

    if assignments:
        connection.executemany(
            """
            INSERT OR IGNORE INTO user_roles (employee_id, role_id, assigned_by)
            VALUES (?, ?, ?)
            """,
            assignments,
        )
        connection.commit()

    return len(assignments)


def _apply_passwords(
    connection,
    state: dict,
    created: list[dict],
    password: str,
    reset_passwords: bool,
    include_admin: bool,
) -> list[dict]:
    """Give accounts the shared password and return rows for the CSV."""
    roles_by_employee = state["roles_by_employee"]
    updates = []
    csv_rows = []

    everyone = list(state["users"])
    for user in created:
        everyone.append(
            {
                "employee_id": user["employee_id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "email": user["email"],
                "department_code": user["department_code"],
                "designation": user["designation"],
                "password_hash": "",
            }
        )

    password_set_count = 0
    for user in everyone:
        roles = [r.upper() for r in roles_by_employee.get(user["employee_id"], [])]
        is_admin = "ADMIN" in roles

        needs_password = _placeholder_hash(user["password_hash"])
        force_password = reset_passwords and (include_admin or not is_admin)

        will_set = needs_password or force_password
        if will_set:
            updates.append((hash_password(password), user["employee_id"]))
            password_set_count += 1
            printed_password = password
        else:
            printed_password = "(unchanged)"

        csv_rows.append([
            user["employee_id"],
            user["username"],
            user["full_name"],
            user["email"],
            user["department_code"] or "",
            user["designation"] or "",
            ", ".join(roles) if roles else "UNASSIGNED",
            printed_password,
        ])

    if updates:
        for index in range(0, len(updates), 50):
            connection.executemany(
                """
                UPDATE users
                SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE employee_id = ?
                """,
                updates[index:index + 50],
            )
            print(f"  hashed {min(index + 50, len(updates))}/{len(updates)} users...")
        connection.commit()

    return csv_rows


def run(
    target_total: int = TARGET_TOTAL,
    password: str = DEFAULT_PASSWORD,
    reset_passwords: bool = False,
    include_admin: bool = False,
    csv_path: str = "employee_credentials.csv",
) -> dict:
    if not password or len(password) < 8:
        raise SystemExit("Password must be at least 8 characters long.")

    started = time.monotonic()

    # Deterministic naming/role assignment for reproducible runs.
    random.seed(2026)

    seed_departments()
    seed_roles()

    connection = get_connection()
    try:
        role_ids = _load_role_ids(connection)
        state = _existing_state(connection)
        existing_total = len(state["users"])
        print(f"Active users found: {existing_total}")

        created = []
        if existing_total < target_total:
            created = _top_up_users(connection, state, target_total)
            print(f"Created {len(created)} new employee account(s).")
        else:
            print(f"Target of {target_total} already reached; no new users created.")

        assigned_roles = _assign_roles(connection, state, created, role_ids)
        print(f"Assigned {assigned_roles} role(s) to users that had none.")

        csv_rows = _apply_passwords(
            connection,
            state,
            created,
            password,
            reset_passwords,
            include_admin,
        )

        # Final verification snapshot.
        final_total = connection.execute(
            "SELECT COUNT(*) AS total FROM users WHERE is_active = 1"
        ).fetchone()["total"]
        role_summary = connection.execute(
            """
            SELECT r.role_code, COUNT(*) AS total
            FROM user_roles ur
            INNER JOIN roles r ON r.role_id = ur.role_id
            WHERE r.is_active = 1
            GROUP BY r.role_code
            ORDER BY r.role_code
            """
        ).fetchall()

        output = Path(csv_path)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "employee_id", "username", "full_name", "email",
                "department", "designation", "roles", "password",
            ])
            writer.writerows(csv_rows)

        elapsed = time.monotonic() - started
        print()
        print("=" * 62)
        print("BUGPILOT EMPLOYEE SETUP COMPLETE")
        print("=" * 62)
        print(f"Active users:            {final_total}")
        for row in role_summary:
            print(f"  {row['role_code']:<10} {row['total']}")
        print(f"Shared password set for: {sum(1 for r in csv_rows if r[7] != '(unchanged)')} account(s)")
        print(f"Credentials CSV:         {output.resolve()}")
        print(f"Elapsed:                 {elapsed:.1f}s")
        print("=" * 62)

        return {
            "total_users": final_total,
            "created": len(created),
            "roles_assigned": assigned_roles,
            "csv_path": str(output.resolve()),
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ensure 200 employees exist with roles and one shared password."
    )
    parser.add_argument("--target", type=int, default=TARGET_TOTAL,
                        help=f"Target active headcount (default {TARGET_TOTAL}).")
    parser.add_argument("--password", default=DEFAULT_PASSWORD,
                        help=f"Shared password (default: {DEFAULT_PASSWORD!r} or EMPLOYEE_DEFAULT_PASSWORD).")
    parser.add_argument("--reset-passwords", action="store_true",
                        help="Force the shared password onto ALL non-admin accounts.")
    parser.add_argument("--include-admin", action="store_true",
                        help="Also reset ADMIN accounts (use with --reset-passwords).")
    parser.add_argument("--csv", default="employee_credentials.csv",
                        help="Output CSV path (default: employee_credentials.csv).")
    args = parser.parse_args()

    run(
        target_total=args.target,
        password=args.password,
        reset_passwords=args.reset_passwords,
        include_admin=args.include_admin,
        csv_path=args.csv,
    )


if __name__ == "__main__":
    main()
