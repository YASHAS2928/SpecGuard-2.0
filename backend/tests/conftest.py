"""Shared pytest fixtures.

The environment is configured *before* the application is imported, so the
cached settings and the database engine point at an isolated temporary SQLite
file and the fake AI provider. Real API keys in ``backend/.env`` are overridden.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "false"
os.environ["AI_PROVIDER"] = "fake"
os.environ["GROQ_API_KEY"] = ""
os.environ["GROQ_MODEL"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = ""
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["DATABASE_URL"] = "sqlite://"

import app.models  # noqa: E402,F401  (register models before any create_all)
from app.database.base import Base  # noqa: E402
from app.database.session import create_db_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Return a test client with the application lifespan (startup/shutdown) running."""
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Return a session on a fresh in-memory database with all tables created.

    Foreign keys are enforced (``PRAGMA foreign_keys=ON``) exactly as in the app.
    """
    engine = create_db_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
