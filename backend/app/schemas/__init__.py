import sqlite3
from pathlib import Path

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DB_PATH = PROJECT_ROOT / "bugpilot.db"


# ============================================================
# INSPECT DATABASE
# ============================================================


def inspect_database():

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    try:

        # ----------------------------------------------------
        # Show all tables
        # ----------------------------------------------------

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name;
            """)

        tables = cursor.fetchall()

        print("\nTables:")

        for table in tables:
            print("-", table[0])

        # ----------------------------------------------------
        # Show columns for every table
        # ----------------------------------------------------

        for table in tables:

            table_name = table[0]

            print(f"\n--- {table_name} ---")

            cursor.execute(f"PRAGMA table_info({table_name});")

            columns = cursor.fetchall()

            for column in columns:
                print(column)

    finally:

        connection.close()


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    inspect_database()
