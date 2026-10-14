
import sqlite3
from pathlib import Path


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "bugpilot.db"

CONNECTION_TIMEOUT = 30


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    """
    Create a connection to the BugPilot SQLite database.

    Features:
    - Uses one consistent database path.
    - Returns rows accessible by column name.
    - Enables foreign-key enforcement.
    - Waits for database locks instead of failing immediately.
    """

    connection = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=CONNECTION_TIMEOUT,
    )

    try:
        connection.row_factory = sqlite3.Row

        connection.execute(
            f"PRAGMA busy_timeout = {CONNECTION_TIMEOUT * 1000}"
        )

        connection.execute("PRAGMA foreign_keys = ON")

        return connection

    except Exception:
        connection.close()
        raise
