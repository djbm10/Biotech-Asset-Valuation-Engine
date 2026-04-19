"""Database engine and session management.

Supports both PostgreSQL (production) and SQLite (development/testing).
Configure via DATABASE_URL environment variable.

  PostgreSQL: DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/bve
  SQLite:     DATABASE_URL=sqlite:///./bve.db   (default for local dev)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "sqlite:///./bve_platform.db"
)

# SQLite pragma for FK enforcement
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # SQLite: check_same_thread=False needed for multi-threaded use
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
    echo=os.environ.get("DB_ECHO", "").lower() == "true",
)

if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for standalone scripts and background jobs."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables (used in tests and local dev; migrations handle prod)."""
    # Import all model modules so Base.metadata is populated
    import bve.persistence.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def drop_all_tables() -> None:
    """Drop all tables (used in tests only)."""
    import bve.persistence.models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
