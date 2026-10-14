from app.database.connection import get_connection


def seed_departments():
    connection = get_connection()
    cursor = connection.cursor()

    departments = [
        (
            "SYS",
            "Systems",
            "ERP systems, internal applications, infrastructure and system development",
        ),
        (
            "FIN",
            "Finance",
            "Payroll, accounting, vendor payments, expenses and financial operations",
        ),
        (
            "HR",
            "Human Resources",
            "Employee records, payroll coordination, recruitment and HR operations",
        ),
        ("ENG", "Engineering", "Engineering and technical operations"),
        ("OPS", "Operations", "Business operations and operational support"),
        ("QA", "Quality Assurance", "Software quality, testing and validation"),
        (
            "IT",
            "Information Technology",
            "IT infrastructure, networking, hardware and technical support",
        ),
        (
            "ADM",
            "Administration",
            "Administration, facilities and general corporate services",
        ),
        (
            "PMO",
            "Project Management Office",
            "Project planning, tracking, coordination and governance",
        ),
        ("PRC", "Procurement", "Purchasing, purchase orders and vendor coordination"),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO departments (
            department_code,
            department_name,
            description
        )
        VALUES (?, ?, ?)
    """,
        departments,
    )

    connection.commit()
    connection.close()


def seed_roles():
    connection = get_connection()
    cursor = connection.cursor()

    roles = [
        ("ADMIN", "Administrator", "Full administrative access to BugPilot"),
        ("MANAGER", "Manager", "Department-level management and ticket oversight"),
        (
            "DEVELOPER",
            "Developer",
            "Software development, bug investigation and resolution",
        ),
        (
            "SUPPORT",
            "Support Engineer",
            "Ticket handling, troubleshooting and user support",
        ),
        (
            "EMPLOYEE",
            "Employee",
            "Create and track tickets and view permitted information",
        ),
        ("VIEWER", "Viewer", "Read-only access to permitted tickets and dashboards"),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO roles (
            role_code,
            role_name,
            description
        )
        VALUES (?, ?, ?)
    """,
        roles,
    )

    connection.commit()
    connection.close()


def seed_master_data():
    seed_departments()
    seed_roles()


if __name__ == "__main__":
    seed_master_data()
    print("Departments and roles seeded successfully.")
