"""Transport-level contract between text-completion backends and the AI layer.

A ``CompletionClient`` only turns a prompt into text. Parsing, validation,
retries and error mapping live in ``app.ai.structured`` so every backend
behaves the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CompletionError(Exception):
    """The backend could not return a completion (network, timeout, rate limit, 4xx/5xx).

    Messages must be safe to show to users: no URLs, credentials, prompts or
    response bodies.
    """


@dataclass(frozen=True)
class Completion:
    """Raw text returned by a backend, with optional token counts."""

    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class CompletionClient(Protocol):
    """Anything that can complete a prompt. Raise ``CompletionError`` on failure."""

    def complete(self, prompt: str) -> Completion: ...
