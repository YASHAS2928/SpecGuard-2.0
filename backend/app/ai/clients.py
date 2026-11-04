"""HTTP completion clients for Ollama and OpenAI-compatible hosted endpoints.

Safety rules shared by both clients:

* Proxy environment variables are ignored and redirects are not followed, so a
  request only ever reaches the configured host.
* Error messages never include URLs, credentials, prompts or response bodies.
* One short-lived ``httpx.Client`` per call: nothing leaks between requests.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.completion import Completion, CompletionError

TEMPERATURE = 0.1


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class _JsonPoster:
    def __init__(self, timeout_seconds: float, transport: httpx.BaseTransport | None) -> None:
        self._timeout = timeout_seconds
        self._transport = transport

    def post(
        self, url: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=self._timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
            ) as http:
                response = http.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise CompletionError("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise CompletionError("The AI provider could not be reached.") from exc

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise CompletionError("The AI provider rate limit was reached.")
        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise CompletionError("The AI provider rejected the credentials.")
        if response.status_code != httpx.codes.OK:
            raise CompletionError(f"The AI provider returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise CompletionError("The AI provider returned a response that is not JSON.") from exc
        if not isinstance(data, dict):
            raise CompletionError("The AI provider returned an unexpected response shape.")
        return data


class OllamaClient:
    """Local Ollama ``/api/chat`` in JSON mode."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url}/api/chat"
        self._model = model
        self._poster = _JsonPoster(timeout_seconds, transport)

    def complete(self, prompt: str) -> Completion:
        data = self._poster.post(
            self._url,
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": TEMPERATURE},
            },
        )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise CompletionError("The AI provider returned an unexpected response shape.")
        return Completion(
            text=content,
            tokens_in=_int_or_none(data.get("prompt_eval_count")),
            tokens_out=_int_or_none(data.get("eval_count")),
        )


class OpenAICompatibleClient:
    """OpenAI-compatible ``/chat/completions`` in JSON mode, authenticated with a bearer key."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._poster = _JsonPoster(timeout_seconds, transport)

    def complete(self, prompt: str) -> Completion:
        data = self._poster.post(
            self._url,
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
            self._headers,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise CompletionError("The AI provider returned an unexpected response shape.")
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return Completion(
            text=content,
            tokens_in=_int_or_none(usage.get("prompt_tokens")),
            tokens_out=_int_or_none(usage.get("completion_tokens")),
        )
