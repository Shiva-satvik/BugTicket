import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "bugpilot.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    """Create the AI-analysis table and safely add ownership to older databases."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyzed_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket TEXT NOT NULL,
                summary TEXT,
                category TEXT,
                module TEXT,
                problem TEXT,
                keywords TEXT,
                analysis TEXT,
                historical_evidence TEXT,
                severity TEXT,
                priority TEXT,
                likely_cause TEXT,
                suggested_resolution TEXT,
                missing_information TEXT,
                confidence_score REAL,
                confidence_level TEXT,
                confidence_reason TEXT,
                retrieval_diagnostics TEXT,
                llm_status TEXT,
                llm_error TEXT,
                analysis_mode TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Migration for databases created before ownership tracking was added.
        cursor.execute("PRAGMA table_info(analyzed_tickets)")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        if "created_by" not in existing_columns:
            cursor.execute("ALTER TABLE analyzed_tickets ADD COLUMN created_by TEXT")
        for column_name, column_type in (
            ("retrieval_diagnostics", "TEXT"),
            ("llm_status", "TEXT"),
            ("llm_error", "TEXT"),
            ("analysis_mode", "TEXT"),
        ):
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE analyzed_tickets ADD COLUMN {column_name} {column_type}")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyzed_tickets_created_by
            ON analyzed_tickets(created_by)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyzed_tickets_created_at
            ON analyzed_tickets(created_at)
        """)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def save_analyzed_ticket(result: dict, created_by: str | None = None) -> int:
    """Save a completed analysis and, when provided, its authenticated owner."""
    required_fields = [
        "ticket", "summary", "category", "module", "problem", "keywords",
        "analysis", "historical_evidence", "severity", "priority",
        "likely_cause", "suggested_resolution", "missing_information",
        "confidence_score", "confidence_level", "confidence_reason",
    ]
    missing_fields = [field for field in required_fields if field not in result]
    if missing_fields:
        raise ValueError(
            "Cannot save analyzed ticket. Missing fields: " + ", ".join(missing_fields)
        )

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO analyzed_tickets (
                ticket, summary, category, module, problem, keywords, analysis,
                historical_evidence, severity, priority, likely_cause,
                suggested_resolution, missing_information, confidence_score,
                confidence_level, confidence_reason, retrieval_diagnostics,
                llm_status, llm_error, analysis_mode, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(result["ticket"]).strip(),
                str(result["summary"]).strip(),
                str(result["category"]).strip(),
                str(result["module"]).strip(),
                str(result["problem"]).strip(),
                json.dumps(result["keywords"]),
                str(result["analysis"]).strip(),
                str(result["historical_evidence"]).strip(),
                str(result["severity"]).strip(),
                str(result["priority"]).strip(),
                str(result["likely_cause"]).strip(),
                str(result["suggested_resolution"]).strip(),
                json.dumps(result["missing_information"]),
                float(result["confidence_score"]),
                str(result["confidence_level"]).strip(),
                str(result["confidence_reason"]).strip(),
                json.dumps(result.get("retrieval_diagnostics", {})),
                str(result.get("llm_status", "unknown")),
                str(result.get("llm_error", "")),
                str(result.get("analysis_mode", "unknown")),
                created_by,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_all_analyzed_tickets(
    employee_id: str | None = None,
    is_admin: bool = False,
    is_manager: bool = False,
    department_id: int | None = None,
) -> list[dict]:
    """
    List analyses according to the caller's role-based access level:

    - ADMIN      -> every analysis in the system.
    - MANAGER    -> analyses owned by users in the manager's department.
    - everyone   -> only their own analyses.

    Old records with no owner are not exposed to regular users after the
    ownership migration.
    """
    connection = get_connection()
    try:
        cursor = connection.cursor()
        if is_admin:
            cursor.execute("""
                SELECT id, ticket, summary, category, module, severity, priority,
                       confidence_score, confidence_level, llm_status, analysis_mode,
                       created_by, created_at
                FROM analyzed_tickets
                ORDER BY id DESC
            """)
        elif is_manager and department_id is not None:
            cursor.execute("""
                SELECT a.id, a.ticket, a.summary, a.category, a.module, a.severity,
                       a.priority, a.confidence_score, a.confidence_level,
                       a.llm_status, a.analysis_mode, a.created_by, a.created_at
                FROM analyzed_tickets a
                INNER JOIN users u ON a.created_by = u.employee_id
                WHERE u.department_id = ?
                ORDER BY a.id DESC
            """, (department_id,))
        elif employee_id:
            cursor.execute("""
                SELECT id, ticket, summary, category, module, severity, priority,
                       confidence_score, confidence_level, llm_status, analysis_mode,
                       created_by, created_at
                FROM analyzed_tickets
                WHERE created_by = ?
                ORDER BY id DESC
            """, (employee_id,))
        else:
            return []
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def get_analyzed_ticket(
    ticket_id: int,
    employee_id: str | None = None,
    is_admin: bool = False,
    is_manager: bool = False,
    department_id: int | None = None,
) -> dict | None:
    """
    Fetch one analysis only if the caller owns it, is an administrator,
    or is a manager whose department contains the analysis owner.
    """
    if ticket_id <= 0:
        raise ValueError("Ticket ID must be greater than 0.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        row = None
        if is_admin:
            row = cursor.execute(
                "SELECT * FROM analyzed_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
        elif is_manager and department_id is not None:
            row = cursor.execute(
                """
                SELECT a.*
                FROM analyzed_tickets a
                INNER JOIN users u ON a.created_by = u.employee_id
                WHERE a.id = ? AND u.department_id = ?
                """,
                (ticket_id, department_id),
            ).fetchone()
        elif employee_id:
            row = cursor.execute(
                "SELECT * FROM analyzed_tickets WHERE id = ? AND created_by = ?",
                (ticket_id, employee_id),
            ).fetchone()

        if row is None:
            return None

        ticket = dict(row)
        for field in ("keywords", "missing_information"):
            try:
                ticket[field] = json.loads(ticket[field]) if ticket.get(field) else []
            except (json.JSONDecodeError, TypeError):
                ticket[field] = []
        try:
            ticket["retrieval_diagnostics"] = json.loads(ticket["retrieval_diagnostics"]) if ticket.get("retrieval_diagnostics") else {}
        except (json.JSONDecodeError, TypeError):
            ticket["retrieval_diagnostics"] = {}
        return ticket
    finally:
        connection.close()
