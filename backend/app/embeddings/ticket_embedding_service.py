
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.vectorstore.chroma_store import (
    delete_ticket,
    upsert_ticket,
)


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "bugpilot.db"

EMBEDDING_VERSION = "all-MiniLM-L6-v2:v1"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    """Open a connection to the BugPilot SQLite database."""

    connection = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


# ============================================================
# EMBEDDING TRACKING COLUMNS
# ============================================================

def ensure_tracking_columns(
    connection: sqlite3.Connection,
) -> None:
    """Ensure tickets has all required embedding tracking columns."""

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(tickets)"
        ).fetchall()
    }

    if not columns:
        raise RuntimeError(
            "The tickets table does not exist in the BugPilot database."
        )

    additions = {
        "embedding_status": "TEXT NOT NULL DEFAULT 'pending'",
        "last_embedded_at": "TEXT",
        "embedding_version": "TEXT",
        "embedding_error": "TEXT",
    }

    for column_name, column_type in additions.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE tickets ADD COLUMN "
                f"{column_name} {column_type}"
            )

    connection.commit()


# ============================================================
# BUILD SEARCHABLE TICKET DOCUMENT
# ============================================================

def build_ticket_document(
    ticket: sqlite3.Row,
) -> str:
    """Convert enterprise ticket fields into searchable text."""

    fields = [
        ("Ticket Code", ticket["ticket_code"]),
        ("Title", ticket["title"]),
        ("Description", ticket["description"]),
        ("Module", ticket["module"]),
        ("Category", ticket["category"]),
        ("Severity", ticket["severity"]),
        ("Status", ticket["status"]),
        ("Resolution", ticket["resolution"]),
    ]

    return "\n\n".join(
        f"{label}: {str(value or '').strip()}"
        for label, value in fields
    )


# ============================================================
# BUILD CHROMA METADATA
# ============================================================

def build_ticket_metadata(
    ticket: sqlite3.Row,
) -> dict[str, Any]:
    """Build metadata used for filtering and retrieval in ChromaDB."""

    metadata: dict[str, Any] = {
        "ticket_id": str(ticket["ticket_id"]),
    }

    fields = [
        "ticket_code",
        "module",
        "category",
        "severity",
        "status",
    ]

    for field in fields:
        value = ticket[field]

        if value is not None and str(value).strip():
            metadata[field] = str(value).strip()

    return metadata


# ============================================================
# SYNCHRONIZE ONE TICKET
# ============================================================

def sync_ticket_embedding(
    ticket_id: int | str,
) -> dict[str, Any]:
    """
    Create or refresh a ticket's vector embedding.

    Uses tickets.ticket_id as the primary key.
    Updates SQLite tracking information after synchronization.
    """

    normalized_ticket_id = int(ticket_id)

    if normalized_ticket_id <= 0:
        raise ValueError("Ticket ID must be greater than zero.")

    connection = get_connection()

    try:
        ensure_tracking_columns(connection)

        # IMPORTANT: The enterprise schema uses ticket_id, not id.
        ticket = connection.execute(
            """
            SELECT
                ticket_id,
                ticket_code,
                title,
                description,
                module,
                category,
                severity,
                status,
                resolution
            FROM tickets
            WHERE ticket_id = ?
            """,
            (normalized_ticket_id,),
        ).fetchone()

        if ticket is None:
            # Remove any stale vector if the source ticket no longer exists.
            delete_ticket(normalized_ticket_id)

            return {
                "ticket_id": normalized_ticket_id,
                "status": "source_ticket_not_found",
            }

        document = build_ticket_document(ticket)
        metadata = build_ticket_metadata(ticket)

        connection.execute(
            """
            UPDATE tickets
            SET embedding_status = 'processing',
                embedding_error = NULL
            WHERE ticket_id = ?
            """,
            (normalized_ticket_id,),
        )
        connection.commit()

        try:
            # Upsert creates a new vector or replaces the existing vector.
            upsert_ticket(
                ticket_id=normalized_ticket_id,
                document=document,
                metadata=metadata,
            )

        except Exception as exc:
            connection.execute(
                """
                UPDATE tickets
                SET embedding_status = 'failed',
                    embedding_error = ?
                WHERE ticket_id = ?
                """,
                (
                    str(exc)[:1000],
                    normalized_ticket_id,
                ),
            )
            connection.commit()
            raise

        embedded_at = datetime.now(timezone.utc).isoformat()

        connection.execute(
            """
            UPDATE tickets
            SET embedding_status = 'embedded',
                last_embedded_at = ?,
                embedding_version = ?,
                embedding_error = NULL
            WHERE ticket_id = ?
            """,
            (
                embedded_at,
                EMBEDDING_VERSION,
                normalized_ticket_id,
            ),
        )
        connection.commit()

        return {
            "ticket_id": normalized_ticket_id,
            "status": "embedded",
            "last_embedded_at": embedded_at,
            "embedding_version": EMBEDDING_VERSION,
        }

    finally:
        connection.close()


# ============================================================
# RECONCILE PENDING OR OUTDATED EMBEDDINGS
# ============================================================

def sync_pending_ticket_embeddings(
    limit: int = 100,
    retry_failed: bool = True,
) -> dict[str, Any]:
    """
    Process tickets that are pending, failed, interrupted, or outdated.

    Intended for initial indexing and scheduled reconciliation.
    """

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    connection = get_connection()

    try:
        ensure_tracking_columns(connection)

        rows = connection.execute(
            """
            SELECT ticket_id
            FROM tickets
            WHERE LOWER(COALESCE(embedding_status, '')) IN ('', 'pending', 'processing')
               OR (
                    LOWER(COALESCE(embedding_status, '')) = 'embedded'
                    AND (embedding_version IS NULL OR embedding_version != ?)
               )
               OR (? = 1 AND LOWER(COALESCE(embedding_status, '')) = 'failed')
            ORDER BY ticket_id ASC
            LIMIT ?
            """,
            (
                EMBEDDING_VERSION,
                1 if retry_failed else 0,
                limit,
            ),
        ).fetchall()

        ticket_ids = [
            row["ticket_id"]
            for row in rows
        ]

    finally:
        connection.close()

    succeeded = 0
    failed = []

    for current_ticket_id in ticket_ids:
        try:
            result = sync_ticket_embedding(current_ticket_id)

            if result["status"] == "embedded":
                succeeded += 1
            else:
                failed.append({
                    "ticket_id": current_ticket_id,
                    "error": result["status"],
                })

        except Exception as exc:
            failed.append({
                "ticket_id": current_ticket_id,
                "error": str(exc)[:500],
            })

    return {
        "selected": len(ticket_ids),
        "succeeded": succeeded,
        "failed": failed,
        "embedding_version": EMBEDDING_VERSION,
    }


# ============================================================
# MARK TICKET FOR RE-EMBEDDING
# ============================================================

def mark_ticket_embedding_pending(
    ticket_id: int | str,
) -> None:
    """Mark a ticket so the next reconciliation run re-embeds it."""

    normalized_ticket_id = int(ticket_id)

    if normalized_ticket_id <= 0:
        raise ValueError("Ticket ID must be greater than zero.")

    connection = get_connection()

    try:
        ensure_tracking_columns(connection)

        cursor = connection.execute(
            """
            UPDATE tickets
            SET embedding_status = 'pending',
                embedding_error = NULL
            WHERE ticket_id = ?
            """,
            (normalized_ticket_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Ticket {normalized_ticket_id} was not found."
            )

        connection.commit()

    finally:
        connection.close()
