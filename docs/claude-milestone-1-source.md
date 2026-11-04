## Milestone 1 — Foundation

**Goal:** a runnable FastAPI backend with typed configuration, a SQLite database layer, health and version endpoints, a trace-ID middleware, and passing tests. No AI calls or business logic yet.

**Two compliance notes before you start:**

- **Groq** hosts open-weight models (for example the Llama, Qwen and GPT-OSS families). If you choose one of those for `GROQ_MODEL`, you stay close to the brief’s open-weight guidance. Record the model’s licence in the README.
- **Gemini** models are proprietary. Keep Gemini optional and off by default, as your plan already does.

### Files in this milestone

PathPurpose`backend/requirements.txt`Milestone 1 dependencies (the Groq and Gemini SDKs are added in Milestone 5)`backend/.env.example`Configuration template`backend/.gitignore`Keeps `.env`, databases and caches out of Git`backend/pytest.ini`**Added:** lets pytest import `app` from `backend/` without installing it as a package`backend/app/__init__.py`**Added:** package marker`backend/app/core/__init__.py`**Added:** package marker`backend/app/database/__init__.py`**Added:** package marker`backend/app/core/config.py`Typed settings, secret masking, AI configuration checks`backend/app/database/base.py`Declarative base, naming conventions, timestamp mixin`backend/app/database/session.py`Engine, SQLite pragmas, session dependency, transaction helper`backend/app/database/init_db.py`Table creation (CLI and startup)`backend/app/main.py`App factory, lifespan, CORS, trace IDs, `/health`, `/version`, error handler`backend/tests/conftest.py`Isolated test environment (fake provider, temporary database)`backend/tests/test_health.py`Endpoint and configuration tests

I also added `CORS_ORIGINS` to `.env.example` so the React dev server (`http://localhost:5173`) can call the API.

---

#### File: backend/requirements.txt

text

```
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
pydantic>=2.7,<3.0
pydantic-settings>=2.4,<3.0
SQLAlchemy>=2.0.30,<2.1
httpx>=0.27,<1.0
python-dotenv>=1.0,<2.0
pytest>=8.2,<9.0
```

#### File: backend/.env.example

env

```
APP_NAME=SpecGuard 2.0
APP_ENV=development
DEBUG=true

DATABASE_URL=sqlite:///./specguard.db

AI_PROVIDER=groq

GROQ_API_KEY=
GROQ_MODEL=

GEMINI_API_KEY=
GEMINI_MODEL=

AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=1

MOCK_API_BASE_URL=http://localhost:9000

CORS_ORIGINS=http://localhost:5173

LOG_LEVEL=INFO
```

#### File: backend/.gitignore

gitignore

```
# Environment and secrets
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Test and tool caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# SQLite databases (including WAL side files)
*.db
*.db-wal
*.db-shm
*.sqlite3

# Editors and OS
.vscode/
.idea/
.DS_Store
Thumbs.db
```

#### File: backend/pytest.ini

ini

```
[pytest]
pythonpath = .
testpaths = tests
addopts = -q
```

#### File: backend/app/**init**.py

python

```
"""SpecGuard 2.0 backend application package."""
```

#### File: backend/app/core/**init**.py

python

```
"""Core configuration, contracts, state machine and audit utilities."""
```

#### File: backend/app/database/**init**.py

python

```
"""Database base classes, engine and session management."""
```

#### File: backend/app/core/config.py

python

```
"""Application configuration for SpecGuard 2.0.

Settings are read from environment variables first, then from ``backend/.env``.
API keys are stored as ``SecretStr`` so they never appear in logs, reprs or API
responses. A selected AI provider with missing credentials is reported as a
clear configuration issue; the application never silently switches to the
fake provider.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = BACKEND_DIR / ".env"

APP_VERSION: str = "2.0.0"
API_VERSION: str = "v1"
FAKE_MODEL_NAME: str = "fake-deterministic-v1"

GROQ_KEYS_URL: str = "https://console.groq.com/keys"
GEMINI_KEYS_URL: str = "https://aistudio.google.com/apikey"

AIProviderName = Literal["groq", "gemini", "fake"]
AppEnvironment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

SQLITE_FILE_PREFIX: str = "sqlite:///"
SQLITE_IN_MEMORY_URLS: frozenset[str] = frozenset({"sqlite://", "sqlite:///:memory:"})

class Settings(BaseSettings):
    """Typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "SpecGuard 2.0"
    app_env: AppEnvironment = "development"
    debug: bool = False

    database_url: str = "sqlite:///./specguard.db"

    ai_provider: AIProviderName = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    ai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    ai_max_retries: int = Field(default=1, ge=0, le=3)

    mock_api_base_url: str = "http://localhost:9000"
    cors_origins: str = "http://localhost:5173"
    log_level: LogLevel = "INFO"

    @field_validator(
        "groq_api_key", "gemini_api_key", "groq_model", "gemini_model", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        """Treat empty or whitespace-only values (e.g. ``GROQ_API_KEY=``) as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("ai_provider", "app_env", mode="before")
    @classmethod
    def _normalise_lowercase(cls, value: Any) -> Any:
        """Accept values such as ``Groq`` or ``DEVELOPMENT``."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: Any) -> Any:
        """Accept lowercase log levels such as ``info``."""
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def _require_sqlite(cls, value: str) -> str:
        """SpecGuard 2.0 uses SQLite only; reject other database URLs early."""
        value = value.strip()
        if not value.startswith("sqlite:"):
            raise ValueError(
                "SpecGuard 2.0 supports SQLite only; DATABASE_URL must start with 'sqlite:'."
            )
        return value

    @field_validator("mock_api_base_url")
    @classmethod
    def _validate_mock_api_url(cls, value: str) -> str:
        """Require an http(s) base URL and remove any trailing slash."""
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("MOCK_API_BASE_URL must start with http:// or https://")
        return value

    @property
    def resolved_database_url(self) -> str:
        """Return the database URL with relative SQLite paths anchored to ``backend/``.

        This keeps the database in the same place whichever directory the
        server or tests are started from.
        """
        if self.database_url in SQLITE_IN_MEMORY_URLS:
            return self.database_url
        if not self.database_url.startswith(SQLITE_FILE_PREFIX):
            return self.database_url
        path = Path(self.database_url[len(SQLITE_FILE_PREFIX):])
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return f"{SQLITE_FILE_PREFIX}{path.as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the comma-separated ``CORS_ORIGINS`` value as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def active_ai_model(self) -> str | None:
        """Return the model identifier configured for the selected provider."""
        if self.ai_provider == "groq":
            return self.groq_model
        if self.ai_provider == "gemini":
            return self.gemini_model
        return FAKE_MODEL_NAME

    def ai_configuration_issues(self) -> list[str]:
        """List human-readable problems with the selected AI provider configuration."""
        issues: list[str] = []
        if self.ai_provider == "groq":
            if self.groq_api_key is None:
                issues.append(
                    "AI_PROVIDER=groq but GROQ_API_KEY is not set. "
                    f"Create a key at {GROQ_KEYS_URL} and add it to backend/.env."
                )
            if self.groq_model is None:
                issues.append(
                    "AI_PROVIDER=groq but GROQ_MODEL is not set. Choose a current Groq "
                    "model that supports JSON or structured output and add it to backend/.env."
                )
        elif self.ai_provider == "gemini":
            if self.gemini_api_key is None:
                issues.append(
                    "AI_PROVIDER=gemini but GEMINI_API_KEY is not set. "
                    f"Create a key at {GEMINI_KEYS_URL} and add it to backend/.env."
                )
            if self.gemini_model is None:
                issues.append(
                    "AI_PROVIDER=gemini but GEMINI_MODEL is not set. Choose a current Gemini "
                    "model that supports structured JSON output and add it to backend/.env."
                )
        return issues

    @property
    def is_ai_configured(self) -> bool:
        """Return ``True`` when the selected AI provider has everything it needs."""
        return not self.ai_configuration_issues()

@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (usable as a FastAPI dependency)."""
    return Settings()
```

#### File: backend/app/database/base.py

python

```
"""Declarative base and shared column mixins for SpecGuard models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    """Declarative base with deterministic constraint names."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns maintained by the ORM.

    SQLite does not store timezone offsets; values are written in UTC and read
    back as naive datetimes that should be treated as UTC.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
```

#### File: backend/app/database/session.py

python

```
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
```

#### File: backend/app/database/init_db.py

python

```
"""Database initialisation for SpecGuard 2.0.

Run from the ``backend`` directory:

    python -m app.database.init_db

Model modules are registered with ``Base.metadata`` in Milestone 3, which adds
the model import to this file. Until then no tables are created.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect

from app.core.config import get_settings
from app.database.base import Base
from app.database.session import engine as default_engine

logger = logging.getLogger("specguard.database")

def init_db(bind: Engine | None = None) -> list[str]:
    """Create all registered tables (idempotent) and return the table names."""
    target = bind if bind is not None else default_engine
    Base.metadata.create_all(bind=target)
    tables = sorted(inspect(target).get_table_names())
    logger.info("Database initialised with %d table(s)", len(tables))
    return tables

def main() -> None:
    """Command-line entry point that initialises the configured database."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    tables = init_db()
    print(f"Database initialised at {get_settings().resolved_database_url}")
    if tables:
        print(f"Tables ({len(tables)}): {', '.join(tables)}")
    else:
        print("Tables: none yet (models are added in Milestone 3)")

if __name__ == "__main__":
    main()
```

#### File: backend/app/main.py

python

```
"""SpecGuard 2.0 FastAPI application entry point.

Start the server from the ``backend`` directory:

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import API_VERSION, APP_VERSION, Settings, get_settings
from app.database.init_db import init_db
from app.database.session import check_database, get_db

logger = logging.getLogger("specguard")

TRACE_HEADER = "X-Trace-ID"
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

class AIStatus(BaseModel):
    """Configuration status of the selected AI provider (no secrets)."""

    provider: str
    model: str | None
    configured: bool
    issues: list[str] = Field(default_factory=list)

class HealthResponse(BaseModel):
    """Response body of ``GET /health``."""

    status: Literal["ok", "degraded"]
    app: str
    environment: str
    database: Literal["ok", "unavailable"]
    ai: AIStatus

class VersionResponse(BaseModel):
    """Response body of ``GET /version``."""

    name: str
    version: str
    api_version: str
    environment: str
    ai_provider: str
    ai_model: str | None

def configure_logging(level: str) -> None:
    """Configure root logging once and set the SpecGuard logger level."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("specguard").setLevel(level)

def resolve_trace_id(candidate: str | None) -> str:
    """Reuse a safe incoming trace ID, otherwise generate a new one."""
    if candidate and _SAFE_TRACE_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex

def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        tables = init_db()
        logger.info(
            "Database ready at %s (%d tables)", settings.resolved_database_url, len(tables)
        )
        logger.info(
            "AI provider: %s, model: %s",
            settings.ai_provider,
            settings.active_ai_model or "<not set>",
        )
        for issue in settings.ai_configuration_issues():
            logger.warning("AI configuration issue: %s", issue)
        yield
        logger.info("SpecGuard shutting down")

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        description=(
            "Requirements Intelligence and Executable Quality platform for workforce "
            "software. The AI drafts specifications; deterministic code computes expected "
            "results, validates and executes tests; humans approve."
        ),
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TRACE_HEADER],
    )

    @app.middleware("http")
    async def trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a trace ID to every request, response and log line."""
        trace_id = resolve_trace_id(request.headers.get(TRACE_HEADER))
        request.state.trace_id = trace_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[TRACE_HEADER] = trace_id
        logger.info(
            "%s %s -> %d (%.1f ms) trace=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            trace_id,
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a standard error body without leaking internal details."""
        trace_id = getattr(request.state, "trace_id", None) or uuid.uuid4().hex
        logger.error(
            "Unhandled error trace=%s: %s", trace_id, type(exc).__name__, exc_info=exc
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Quote the trace ID when reporting it.",
                    "details": None,
                    "trace_id": trace_id,
                }
            },
            headers={TRACE_HEADER: trace_id},
        )

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Service health",
        responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
    )
    def health(
        response: Response,
        db: Session = Depends(get_db),
        current: Settings = Depends(get_settings),
    ) -> HealthResponse:
        """Report database reachability and AI provider configuration status."""
        try:
            database_ok = check_database(db)
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            database_ok = False

        issues = current.ai_configuration_issues()
        ai_status = AIStatus(
            provider=current.ai_provider,
            model=current.active_ai_model,
            configured=not issues,
            issues=issues,
        )
        if not database_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return HealthResponse(
            status="ok" if database_ok and not issues else "degraded",
            app=current.app_name,
            environment=current.app_env,
            database="ok" if database_ok else "unavailable",
            ai=ai_status,
        )

    @app.get(
        "/version",
        response_model=VersionResponse,
        tags=["system"],
        summary="Application and API version",
    )
    def version(current: Settings = Depends(get_settings)) -> VersionResponse:
        """Return version information and the active AI provider (never credentials)."""
        return VersionResponse(
            name=current.app_name,
            version=APP_VERSION,
            api_version=API_VERSION,
            environment=current.app_env,
            ai_provider=current.ai_provider,
            ai_model=current.active_ai_model,
        )

    return app

app = create_app()
```

#### File: backend/tests/conftest.py

python

```
"""Shared pytest fixtures.

The environment is configured *before* the application is imported, so the
cached settings and the database engine point at an isolated temporary SQLite
file and the fake AI provider. Real API keys in ``backend/.env`` are overridden.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TEST_DIR = Path(tempfile.mkdtemp(prefix="specguard-tests-"))

os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "false"
os.environ["AI_PROVIDER"] = "fake"
os.environ["GROQ_API_KEY"] = ""
os.environ["GROQ_MODEL"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = ""
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DIR / 'test_specguard.db').as_posix()}"

from app.main import create_app  # noqa: E402

@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Return a test client with the application lifespan (startup/shutdown) running."""
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client

@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_database() -> Iterator[None]:
    """Dispose the engine and delete the temporary database after the test session."""
    yield
    from app.database.session import engine

    engine.dispose()
    shutil.rmtree(_TEST_DIR, ignore_errors=True)
```

#### File: backend/tests/test_health.py

python

```
"""Tests for system endpoints and configuration behaviour."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import API_VERSION, APP_VERSION, BACKEND_DIR, FAKE_MODEL_NAME, Settings

# --- Endpoints -----------------------------------------------------------------

def test_health_returns_ok_with_fake_provider(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"
    assert body["ai"] == {
        "provider": "fake",
        "model": FAKE_MODEL_NAME,
        "configured": True,
        "issues": [],
    }

def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SpecGuard 2.0"
    assert body["version"] == APP_VERSION
    assert body["api_version"] == API_VERSION
    assert body["ai_provider"] == "fake"
    assert body["ai_model"] == FAKE_MODEL_NAME

def test_trace_id_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health")
    trace_id = response.headers.get("X-Trace-ID")
    assert trace_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", trace_id)

def test_trace_id_echoed_when_safe(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Trace-ID": "demo-trace-001"})
    assert response.headers["X-Trace-ID"] == "demo-trace-001"

def test_unsafe_trace_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Trace-ID": "bad id <script>"})
    assert response.headers["X-Trace-ID"] != "bad id <script>"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Trace-ID"])

def test_openapi_schema_lists_system_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "SpecGuard 2.0"
    assert "/health" in schema["paths"]
    assert "/version" in schema["paths"]

# --- Configuration -------------------------------------------------------------

def test_groq_selected_without_key_reports_clear_issue() -> None:
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key=None, groq_model=None)
    issues = settings.ai_configuration_issues()
    assert not settings.is_ai_configured
    assert any("GROQ_API_KEY" in issue and "console.groq.com/keys" in issue for issue in issues)
    assert any("GROQ_MODEL" in issue for issue in issues)

def test_gemini_selected_without_key_reports_clear_issue() -> None:
    settings = Settings(
        _env_file=None, ai_provider="gemini", gemini_api_key=None, gemini_model=None
    )
    issues = settings.ai_configuration_issues()
    assert not settings.is_ai_configured
    assert any(
        "GEMINI_API_KEY" in issue and "aistudio.google.com/apikey" in issue for issue in issues
    )
    assert any("GEMINI_MODEL" in issue for issue in issues)

def test_fake_provider_needs_no_credentials() -> None:
    settings = Settings(_env_file=None, ai_provider="fake")
    assert settings.is_ai_configured
    assert settings.active_ai_model == FAKE_MODEL_NAME

def test_invalid_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="openai")

def test_blank_values_become_none() -> None:
    settings = Settings(_env_file=None, ai_provider="groq", groq_api_key="   ", groq_model="")
    assert settings.groq_api_key is None
    assert settings.groq_model is None

def test_relative_sqlite_path_resolves_to_backend_dir() -> None:
    settings = Settings(_env_file=None, database_url="sqlite:///./specguard.db")
    expected = f"sqlite:///{(BACKEND_DIR / 'specguard.db').resolve().as_posix()}"
    assert settings.resolved_database_url == expected

def test_non_sqlite_database_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/specguard")

def test_secrets_are_masked() -> None:
    placeholder = "placeholder-not-a-real-key"
    settings = Settings(
        _env_file=None, ai_provider="groq", groq_api_key=placeholder, groq_model="any-model"
    )
    assert placeholder not in repr(settings)
    assert placeholder not in str(settings.model_dump())
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == placeholder
    assert settings.is_ai_configured
```

---

### Install and run (PowerShell)

powershell

```
cd backend

python -m venv .venv
# If activation is blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
# Until you have a Groq key, use the fake provider:
(Get-Content .env) -replace '^AI_PROVIDER=.*', 'AI_PROVIDER=fake' | Set-Content .env

python -m app.database.init_db
uvicorn app.main:app --reload --port 8000
```

In a second PowerShell window:

powershell

```
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:8000/version | ConvertTo-Json
Start-Process http://localhost:8000/docs
```

Run the tests (from `backend`, with the virtual environment active):

powershell

```
pytest
```

### Expected output

`python -m app.database.init_db`:

text

```
INFO specguard.database: Database initialised with 0 table(s)
Database initialised at sqlite:///C:/.../specguard/backend/specguard.db
Tables: none yet (models are added in Milestone 3)
```

`GET /health` with `AI_PROVIDER=fake`:

json

```
{
  "status": "ok",
  "app": "SpecGuard 2.0",
  "environment": "development",
  "database": "ok",
  "ai": { "provider": "fake", "model": "fake-deterministic-v1", "configured": true, "issues": [] }
}
```

`GET /health` with `AI_PROVIDER=groq` and no key (still HTTP 200, but clearly flagged):

json

```
{
  "status": "degraded",
  "database": "ok",
  "ai": {
    "provider": "groq", "model": null, "configured": false,
    "issues": [
      "AI_PROVIDER=groq but GROQ_API_KEY is not set. Create a key at https://console.groq.com/keys and add it to backend/.env.",
      "AI_PROVIDER=groq but GROQ_MODEL is not set. Choose a current Groq model that supports JSON or structured output and add it to backend/.env."
    ]
  }
}
```

`pytest`:

text

```
..............                                                           [100%]
14 passed in 1.2s
```

### Verification checklist

- `/health` returns `"status": "ok"` with the fake provider
- Switching `AI_PROVIDER=groq` without a key shows `"degraded"` and both issues (restart uvicorn after editing `.env`)
- Every response has an `X-Trace-ID` header (check with `curl.exe -i http://localhost:8000/health`)
- `/docs` shows the **system** endpoints
- `specguard.db` is created in `backend/` and doesn’t appear in `git status`
- `pytest` shows 14 passed