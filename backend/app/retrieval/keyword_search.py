
import re
import sqlite3

from app.database.connection import DATABASE_PATH


def keyword_search(query: str, k: int = 5) -> list[dict]:
    """
    Search enterprise tickets using SQLite FTS5.

    Requires the tickets_fts index to be created by the database
    initialization process. Uses tickets.ticket_id as the ticket ID.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Keyword search query cannot be empty.")

    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer.")

    # Treat user input as individual literal search terms, not FTS syntax.
    words = re.findall(r"\w+", query.strip(), flags=re.UNICODE)

    if not words:
        return []

    safe_query = " OR ".join(f'"{word}"' for word in words)

    connection = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA busy_timeout = 30000")

        # Fail with a clear message if schema setup has not happened.
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('tickets', 'tickets_fts')
            """
        ).fetchall()

        available_tables = {row["name"] for row in tables}

        if "tickets" not in available_tables:
            raise RuntimeError(
                "The tickets table is missing. Initialize the BugPilot database first."
            )

        if "tickets_fts" not in available_tables:
            raise RuntimeError(
                "The tickets_fts index is missing. Run database initialization first."
            )

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(tickets)"
            ).fetchall()
        }

        required_columns = {
            "ticket_id",
            "ticket_code",
            "title",
            "description",
            "module",
            "category",
            "severity",
            "status",
            "resolution",
        }

        missing = required_columns - columns

        if missing:
            raise RuntimeError(
                "The tickets table does not match the enterprise schema. "
                f"Missing columns: {', '.join(sorted(missing))}"
            )

        rows = connection.execute(
            """
            SELECT
                t.ticket_id,
                t.ticket_code,
                t.title,
                t.description,
                t.module,
                t.category,
                t.severity,
                t.status,
                t.resolution,
                bm25(tickets_fts) AS search_rank
            FROM tickets_fts
            JOIN tickets AS t
                ON t.ticket_id = tickets_fts.rowid
            WHERE tickets_fts MATCH ?
            ORDER BY search_rank ASC, t.ticket_id DESC
            LIMIT ?
            """,
            (safe_query, k),
        ).fetchall()

        return [dict(row) for row in rows]

    except sqlite3.OperationalError as error:
        if "fts5" in str(error).lower() or "syntax error" in str(error).lower():
            raise RuntimeError(
                "SQLite FTS5 search failed. Verify FTS5 support and "
                "the tickets_fts index definition."
            ) from error
        raise

    finally:
        connection.close()
