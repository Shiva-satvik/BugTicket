from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = PROJECT_ROOT / "bugpilot.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


# ============================================================
# SQLALCHEMY ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
)


# ============================================================
# DATABASE SESSION
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================
# SQLALCHEMY BASE
# ============================================================


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy database models.
    """

    pass


# ============================================================
# DATABASE DEPENDENCY
# ============================================================


def get_db():
    """
    Provide a database session and guarantee that it is closed
    after the request or operation is completed.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
