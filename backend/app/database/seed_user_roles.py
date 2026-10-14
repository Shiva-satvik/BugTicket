import random

from app.database.connection import get_connection

# ============================================================
# ROLE DISTRIBUTION
# ============================================================

ROLE_DISTRIBUTION = {
    "ADMIN": 2,
    "MANAGER": 15,
    "DEVELOPER": 35,
    "SUPPORT": 30,
    "EMPLOYEE": 105,
    "VIEWER": 13,
}


# ============================================================
# SEED USER ROLES
# ============================================================


def seed_user_roles():
    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get all users
    # --------------------------------------------------------

    cursor.execute("""
        SELECT employee_id, department_id
        FROM users
        WHERE is_active = 1
    """)

    users = cursor.fetchall()

    if not users:
        connection.close()
        return

    # --------------------------------------------------------
    # Get roles
    # --------------------------------------------------------

    cursor.execute("""
        SELECT role_id, role_code
        FROM roles
        WHERE is_active = 1
    """)

    roles = {row["role_code"]: row["role_id"] for row in cursor.fetchall()}

    # --------------------------------------------------------
    # Validate required roles
    # --------------------------------------------------------

    for role_code in ROLE_DISTRIBUTION:

        if role_code not in roles:
            connection.close()
            raise ValueError(f"Role '{role_code}' does not exist.")

    # --------------------------------------------------------
    # Shuffle users
    # --------------------------------------------------------

    user_list = list(users)

    random.shuffle(user_list)

    # --------------------------------------------------------
    # Assign roles
    # --------------------------------------------------------

    user_roles = []

    start_index = 0

    for role_code, count in ROLE_DISTRIBUTION.items():

        role_id = roles[role_code]

        selected_users = user_list[start_index : start_index + count]

        for user in selected_users:

            employee_id = user["employee_id"]

            user_roles.append((employee_id, role_id, "SYSTEM"))

        start_index += count

    # --------------------------------------------------------
    # Insert mappings
    # --------------------------------------------------------

    cursor.executemany(
        """
        INSERT OR IGNORE INTO user_roles (
            employee_id,
            role_id,
            assigned_by
        )
        VALUES (?, ?, ?)
    """,
        user_roles,
    )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_user_roles()
    print("User-role mappings seeded successfully.")
