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
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = BACKEND_DIR / ".env"

APP_VERSION: str = "2.0.0"
API_VERSION: str = "v1"
FAKE_MODEL_NAME: str = "fake-deterministic-v1"

GROQ_KEYS_URL: str = "https://console.groq.com/keys"
GEMINI_KEYS_URL: str = "https://aistudio.google.com/apikey"

AIProviderName = Literal["groq", "gemini", "fake", "ollama", "hosted_open_weight"]
AppEnvironment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

SQLITE_FILE_PREFIX: str = "sqlite:///"
SQLITE_IN_MEMORY_URLS: frozenset[str] = frozenset({"sqlite://", "sqlite:///:memory:"})
LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

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
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str | None = None
    hosted_open_weight_base_url: str | None = None
    hosted_open_weight_api_key: SecretStr | None = None
    hosted_open_weight_model: str | None = None
    ai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    ai_max_retries: int = Field(default=1, ge=0, le=3)

    mock_api_base_url: str = "http://localhost:9000"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: LogLevel = "INFO"

    @field_validator(
        "groq_api_key", "gemini_api_key", "groq_model", "gemini_model",
        "ollama_model", "hosted_open_weight_base_url", "hosted_open_weight_api_key",
        "hosted_open_weight_model", mode="before"
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

    @field_validator("ollama_base_url")
    @classmethod
    def _validate_ollama_url(cls, value: str) -> str:
        """Ollama is a local service: only loopback hosts, so prompts never leave the machine."""
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in LOOPBACK_HOSTS:
            raise ValueError(
                "OLLAMA_BASE_URL must be a loopback URL such as http://127.0.0.1:11434."
            )
        return value

    @field_validator("hosted_open_weight_base_url")
    @classmethod
    def _validate_hosted_url(cls, value: str | None) -> str | None:
        """The hosted provider receives an API key, so require HTTPS."""
        if value is None:
            return None
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(
                "HOSTED_OPEN_WEIGHT_BASE_URL must be an https:// URL without embedded credentials."
            )
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
        if self.ai_provider == "ollama":
            return self.ollama_model
        if self.ai_provider == "hosted_open_weight":
            return self.hosted_open_weight_model
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
        elif self.ai_provider == "ollama":
            if self.ollama_model is None:
                issues.append("AI_PROVIDER=ollama but OLLAMA_MODEL is not set.")
        elif self.ai_provider == "hosted_open_weight":
            if self.hosted_open_weight_base_url is None:
                issues.append("AI_PROVIDER=hosted_open_weight but HOSTED_OPEN_WEIGHT_BASE_URL is not set.")
            if self.hosted_open_weight_api_key is None:
                issues.append("AI_PROVIDER=hosted_open_weight but HOSTED_OPEN_WEIGHT_API_KEY is not set.")
            if self.hosted_open_weight_model is None:
                issues.append("AI_PROVIDER=hosted_open_weight but HOSTED_OPEN_WEIGHT_MODEL is not set.")
        return issues

    @property
    def is_ai_configured(self) -> bool:
        """Return ``True`` when the selected AI provider has everything it needs."""
        return not self.ai_configuration_issues()

@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (usable as a FastAPI dependency)."""
    return Settings()
