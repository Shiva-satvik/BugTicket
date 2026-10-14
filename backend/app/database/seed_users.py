import random

from app.database.connection import get_connection

# ============================================================
# CONFIGURATION
# ============================================================

COMPANY_DOMAIN = "satven.com"

FIRST_NAMES = [
    "Arjun",
    "Rahul",
    "Vikram",
    "Karthik",
    "Rohit",
    "Aditya",
    "Sandeep",
    "Nikhil",
    "Pranav",
    "Varun",
    "Akshay",
    "Manoj",
    "Harsha",
    "Sai",
    "Tejas",
    "Ananya",
    "Priya",
    "Sneha",
    "Kavya",
    "Divya",
    "Pooja",
    "Swathi",
    "Meghana",
    "Ishita",
    "Aditi",
]

LAST_NAMES = [
    "Reddy",
    "Kumar",
    "Sharma",
    "Rao",
    "Patel",
    "Verma",
    "Iyer",
    "Nair",
    "Joshi",
    "Mehta",
    "Deshmukh",
    "Kulkarni",
    "Singh",
    "Gupta",
    "Das",
    "Chowdhury",
    "Naidu",
    "Varma",
    "Bhat",
    "Mishra",
]


DEPARTMENT_CONFIG = {
    "SYS": {
        "designations": [
            "Systems Engineer",
            "Senior Systems Engineer",
            "Software Engineer",
            "Senior Software Engineer",
            "Technical Lead",
        ],
        "count": 30,
    },
    "FIN": {
        "designations": [
            "Finance Executive",
            "Senior Finance Executive",
            "Finance Analyst",
            "Senior Finance Analyst",
            "Finance Manager",
        ],
        "count": 25,
    },
    "HR": {
        "designations": [
            "HR Executive",
            "Senior HR Executive",
            "HR Analyst",
            "HR Specialist",
            "HR Manager",
        ],
        "count": 15,
    },
    "ENG": {
        "designations": [
            "Engineering Engineer",
            "Senior Engineer",
            "Design Engineer",
            "Senior Design Engineer",
            "Engineering Lead",
        ],
        "count": 35,
    },
    "OPS": {
        "designations": [
            "Operations Executive",
            "Operations Analyst",
            "Senior Operations Analyst",
            "Operations Specialist",
            "Operations Manager",
        ],
        "count": 20,
    },
    "QA": {
        "designations": [
            "QA Engineer",
            "Senior QA Engineer",
            "QA Analyst",
            "Test Engineer",
            "QA Lead",
        ],
        "count": 20,
    },
    "IT": {
        "designations": [
            "IT Support Engineer",
            "System Administrator",
            "Network Engineer",
            "IT Analyst",
            "IT Manager",
        ],
        "count": 20,
    },
    "ADM": {
        "designations": [
            "Administration Executive",
            "Senior Administration Executive",
            "Administrative Officer",
            "Facilities Executive",
            "Administration Manager",
        ],
        "count": 10,
    },
    "PMO": {
        "designations": [
            "Project Coordinator",
            "Project Analyst",
            "Senior Project Analyst",
            "Project Manager",
            "Program Manager",
        ],
        "count": 10,
    },
    "PRC": {
        "designations": [
            "Procurement Executive",
            "Senior Procurement Executive",
            "Procurement Analyst",
            "Purchase Executive",
            "Procurement Manager",
        ],
        "count": 15,
    },
}


# ============================================================
# GENERATE EMPLOYEE ID
# ============================================================


def generate_employee_id(used_ids):
    while True:
        employee_id = f"SVN-{random.randint(10000, 99999)}"

        if employee_id not in used_ids:
            used_ids.add(employee_id)
            return employee_id


# ============================================================
# GENERATE USERNAME
# ============================================================


def generate_username(first_name, last_name, used_usernames):
    base_username = f"{first_name.lower()}.{last_name.lower()}"

    username = base_username
    counter = 1

    while username in used_usernames:
        username = f"{base_username}{counter}"
        counter += 1

    used_usernames.add(username)

    return username


# ============================================================
# SEED USERS
# ============================================================


def seed_users():
    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get departments
    # --------------------------------------------------------

    cursor.execute("""
        SELECT department_id, department_code
        FROM departments
        WHERE is_active = 1
    """)

    departments = {
        row["department_code"]: row["department_id"] for row in cursor.fetchall()
    }

    # --------------------------------------------------------
    # Generate users
    # --------------------------------------------------------

    users = []

    used_employee_ids = set()
    used_usernames = set()

    for department_code, config in DEPARTMENT_CONFIG.items():

        if department_code not in departments:
            continue

        department_id = departments[department_code]

        for _ in range(config["count"]):

            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)

            full_name = f"{first_name} {last_name}"

            employee_id = generate_employee_id(used_employee_ids)

            username = generate_username(first_name, last_name, used_usernames)

            email = f"{username}@{COMPANY_DOMAIN}"

            designation = random.choice(config["designations"])

            # ------------------------------------------------
            # Placeholder password hash
            #
            # Authentication will replace this later with
            # proper bcrypt/argon2 password hashing.
            # ------------------------------------------------

            password_hash = "TEMP_PASSWORD_HASH"

            users.append(
                (
                    employee_id,
                    username,
                    full_name,
                    email,
                    password_hash,
                    department_id,
                    designation,
                )
            )

    # --------------------------------------------------------
    # Insert users
    # --------------------------------------------------------

    cursor.executemany(
        """
        INSERT OR IGNORE INTO users (
            employee_id,
            username,
            full_name,
            email,
            password_hash,
            department_id,
            designation
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        users,
    )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_users()
    print("Users seeded successfully.")
