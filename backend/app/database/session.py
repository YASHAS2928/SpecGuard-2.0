"""SQLite engine, session factory and FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import SQLITE_FILE_PREFIX, SQLITE_IN_MEMORY_URLS, get_settings

def _ensure_sqlite_directory(database_url: str) -> None:
    """Create the parent directory of a file-based SQLite database if needed."""
    if database_url in SQLITE_IN_MEMORY_URLS or not database_url.startswith(SQLITE_FILE_PREFIX):
        return
    Path(database_url[len(SQLITE_FILE_PREFIX):]).parent.mkdir(parents=True, exist_ok=True)

def create_db_engine(database_url: str, echo: bool = False) -> Engine:
    """Create a SQLite engine with foreign keys enforced.

    File databases use WAL mode and a busy timeout so the API and test runs do
    not block each other. In-memory databases share one connection so every
    session sees the same data.
    """
    is_memory = database_url in SQLITE_IN_MEMORY_URLS
    _ensure_sqlite_directory(database_url)

    engine_kwargs: dict[str, Any] = {
        "echo": echo,
        "connect_args": {"check_same_thread": False},
    }
    if is_memory:
        engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **engine_kwargs)

    @event.listens_for(engine, "connect")
    def _apply_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            if not is_memory:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    return engine

_settings = get_settings()

engine: Engine = create_db_engine(_settings.resolved_database_url)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)

def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it.

    Services commit explicitly. Any exception rolls back uncommitted work.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

@contextmanager
def session_scope() -> Iterator[Session]:
    """Run a block in one transaction: commit on success, roll back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def check_database(session: Session) -> bool:
    """Return ``True`` if the database answers a trivial query."""
    return session.execute(text("SELECT 1")).scalar_one() == 1
