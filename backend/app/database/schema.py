
from app.database.connection import get_connection


def create_master_tables() -> None:
    """Create BugPilot enterprise tables and their required indexes."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Departments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                department_id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_code TEXT NOT NULL UNIQUE,
                department_name TEXT NOT NULL UNIQUE,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Roles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_code TEXT NOT NULL UNIQUE,
                role_name TEXT NOT NULL UNIQUE,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                employee_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                department_id INTEGER NOT NULL,
                designation TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_login_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id)
                    REFERENCES departments(department_id)
            )
        """)

        # User-role mapping
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_role_id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                assigned_by TEXT,
                UNIQUE(employee_id, role_id),
                FOREIGN KEY (employee_id)
                    REFERENCES users(employee_id) ON DELETE CASCADE,
                FOREIGN KEY (role_id)
                    REFERENCES roles(role_id) ON DELETE CASCADE
            )
        """)

        # Enterprise tickets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_by TEXT NOT NULL,
                assigned_to TEXT,
                department_id INTEGER NOT NULL,
                module TEXT,
                category TEXT,
                issue_type TEXT,
                severity TEXT NOT NULL DEFAULT 'MEDIUM',
                priority TEXT NOT NULL DEFAULT 'MEDIUM',
                status TEXT NOT NULL DEFAULT 'OPEN',
                resolution TEXT,
                resolution_notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                assigned_at TEXT,
                resolved_at TEXT,
                closed_at TEXT,
                embedding_status TEXT NOT NULL DEFAULT 'PENDING',
                last_embedded_at TEXT,
                embedding_version TEXT,
                created_by_ai INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (created_by)
                    REFERENCES users(employee_id),
                FOREIGN KEY (assigned_to)
                    REFERENCES users(employee_id),
                FOREIGN KEY (department_id)
                    REFERENCES departments(department_id)
            )
        """)

        # Validate the existing tickets table before creating FTS.
        cursor.execute("PRAGMA table_info(tickets)")
        ticket_columns = {
            row["name"] for row in cursor.fetchall()
        }

        required_ticket_columns = {
            "ticket_id",
            "ticket_code",
            "title",
            "description",
            "created_by",
            "assigned_to",
            "department_id",
            "module",
            "category",
            "severity",
            "status",
            "resolution",
        }

        missing_columns = required_ticket_columns - ticket_columns

        if missing_columns:
            raise RuntimeError(
                "The existing tickets table uses an incompatible schema. "
                f"Missing columns: {', '.join(sorted(missing_columns))}. "
                "Back up the database and migrate the legacy table before "
                "initializing the enterprise schema."
            )

        # Ticket history / audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                changed_by TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                old_priority TEXT,
                new_priority TEXT,
                comment TEXT,
                changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id)
                    REFERENCES tickets(ticket_id) ON DELETE RESTRICT,
                FOREIGN KEY (changed_by)
                    REFERENCES users(employee_id)
            )
        """)

        # Financial documents / SOPs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_documents (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                document_type TEXT,
                module TEXT,
                content TEXT NOT NULL,
                source TEXT,
                version TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Links between tickets and financial documents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_documents (
                ticket_document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                relevance_score REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticket_id, document_id),
                FOREIGN KEY (ticket_id)
                    REFERENCES tickets(ticket_id) ON DELETE RESTRICT,
                FOREIGN KEY (document_id)
                    REFERENCES financial_documents(document_id)
                    ON DELETE RESTRICT
            )
        """)

        # Indexes for common filters and joins
        indexes = [
            ("idx_users_department", "users", "department_id"),
            ("idx_user_roles_employee", "user_roles", "employee_id"),
            ("idx_user_roles_role", "user_roles", "role_id"),
            ("idx_tickets_created_by", "tickets", "created_by"),
            ("idx_tickets_assigned_to", "tickets", "assigned_to"),
            ("idx_tickets_department", "tickets", "department_id"),
            ("idx_tickets_status", "tickets", "status"),
            ("idx_tickets_priority", "tickets", "priority"),
            ("idx_tickets_created_at", "tickets", "created_at"),
            ("idx_tickets_embedding_status", "tickets", "embedding_status"),
            ("idx_ticket_history_ticket", "ticket_history", "ticket_id"),
            ("idx_ticket_documents_ticket", "ticket_documents", "ticket_id"),
            ("idx_ticket_documents_document", "ticket_documents", "document_id"),
        ]

        for index_name, table_name, column_name in indexes:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name}({column_name})"
            )

        # Full-text search index for enterprise tickets.
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tickets_fts
            USING fts5(
                title,
                description,
                module,
                category,
                resolution,
                content='tickets',
                content_rowid='ticket_id'
            )
        """)

        # Keep FTS synchronized when a ticket is inserted.
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS tickets_fts_insert
            AFTER INSERT ON tickets
            BEGIN
                INSERT INTO tickets_fts(
                    rowid, title, description, module, category, resolution
                )
                VALUES (
                    new.ticket_id, new.title, new.description,
                    new.module, new.category, new.resolution
                );
            END
        """)

        # Remove the previous FTS entry before a ticket is updated.
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS tickets_fts_delete
            AFTER DELETE ON tickets
            BEGIN
                INSERT INTO tickets_fts(
                    tickets_fts, rowid, title, description,
                    module, category, resolution
                )
                VALUES (
                    'delete', old.ticket_id, old.title, old.description,
                    old.module, old.category, old.resolution
                );
            END
        """)

        # Replace the FTS entry after a ticket is updated.
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS tickets_fts_update
            AFTER UPDATE OF
                title, description, module, category, resolution
            ON tickets
            BEGIN
                INSERT INTO tickets_fts(
                    tickets_fts, rowid, title, description,
                    module, category, resolution
                )
                VALUES (
                    'delete', old.ticket_id, old.title, old.description,
                    old.module, old.category, old.resolution
                );

                INSERT INTO tickets_fts(
                    rowid, title, description, module, category, resolution
                )
                VALUES (
                    new.ticket_id, new.title, new.description,
                    new.module, new.category, new.resolution
                );
            END
        """)

        # Rebuild the index so existing tickets are searchable too.
        cursor.execute("""
            INSERT INTO tickets_fts(tickets_fts) VALUES ('rebuild')
        """)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    create_master_tables()
    print("BugPilot enterprise schema initialized successfully.")
