"""Shared pytest fixtures.

The environment is configured *before* the application is imported, so the
cached settings and the database engine point at an isolated temporary SQLite
file and the fake AI provider. Real API keys in ``backend/.env`` are overridden.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
import uvicorn
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


@dataclass
class MockServer:
    """The real synthetic Time-to-Pay API running on a free loopback port."""

    base_url: str

    def use(self, version: str) -> None:
        response = httpx.post(f"{self.base_url}/admin/version", json={"version": version}, trust_env=False)
        assert response.status_code == 200, response.text

    def reset(self) -> None:
        """Drop the runtime selection so the MOCK_VERSION environment variable applies again."""
        assert httpx.delete(f"{self.base_url}/admin/version", trust_env=False).status_code == 200


@pytest.fixture(scope="session")
def mock_server() -> Iterator[MockServer]:
    from mock_api.main import app as mock_app

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "mock API did not start"
    mock = MockServer(f"http://127.0.0.1:{port}")
    yield mock
    mock.reset()
    server.should_exit = True
    thread.join(timeout=5)
