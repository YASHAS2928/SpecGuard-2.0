"""Factory that returns the configured AI provider.

* A selected provider with missing credentials raises a clear configuration
  error. The factory never silently switches to the fake provider.
* Provider modules are loaded lazily so none is required to run another. Ollama, the hosted
  open-weight provider and Groq live in this package (Groq is a thin configuration of the shared
  OpenAI-compatible client). Gemini has no implementation yet and answers 503 saying so, before any
  key or model is asked for. A provider value without an entry here is a configuration error
  (HTTP 503), never an unhandled exception.
"""

from __future__ import annotations

import importlib
import importlib.util

from app.ai.fake_provider import FakeProvider
from app.ai.integration_interface import RequirementAI
from app.core.config import Settings
from app.core.contracts import AIProvider
from app.core.errors import AIProviderNotConfiguredError

SUPPORTED = "fake, ollama, hosted_open_weight, groq"

_PROVIDER_CLASSES: dict[AIProvider, tuple[str, str]] = {
    AIProvider.GROQ: ("app.ai.groq_provider", "GroqProvider"),
    AIProvider.GEMINI: ("app.ai.gemini_provider", "GeminiProvider"),
    AIProvider.OLLAMA: ("app.ai.ollama_provider", "OllamaProvider"),
    AIProvider.HOSTED_OPEN_WEIGHT: ("app.ai.hosted_provider", "HostedOpenWeightProvider"),
}

_PIP_PACKAGES: dict[str, str] = {"groq": "groq", "google": "google-genai"}


def get_ai_provider(settings: Settings) -> RequirementAI:
    """Return the provider selected by ``AI_PROVIDER`` or raise a configuration error."""
    provider_name = AIProvider(settings.ai_provider)
    if provider_name is not AIProvider.FAKE and provider_name in _PROVIDER_CLASSES:
        module_name = _PROVIDER_CLASSES[provider_name][0]
        if importlib.util.find_spec(module_name) is None:
            # No amount of configuration helps: say so before asking for keys.
            raise AIProviderNotConfiguredError(
                f"The {provider_name.value} provider is not implemented in this build. "
                f"Set AI_PROVIDER to one of: {SUPPORTED}.",
                details={"provider": provider_name.value, "module": module_name, "supported": SUPPORTED},
            )

    issues = settings.ai_configuration_issues()
    if issues:
        raise AIProviderNotConfiguredError(
            f"AI provider '{settings.ai_provider}' is not configured.",
            details={"provider": settings.ai_provider, "issues": issues},
        )

    if provider_name is AIProvider.FAKE:
        return FakeProvider()

    module_name, class_name = _PROVIDER_CLASSES.get(provider_name, ("", ""))
    if not module_name:
        raise AIProviderNotConfiguredError(
            f"No implementation is registered for AI provider '{provider_name.value}'.",
            details={"provider": provider_name.value},
        )
    details = {"provider": provider_name.value, "module": module_name}
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise AIProviderNotConfiguredError(
                f"The {provider_name.value} provider is not implemented in this build ({module_name}). "
                f"Set AI_PROVIDER to one of: {SUPPORTED}.",
                details=details,
            ) from exc
        missing = (exc.name or "").split(".")[0]
        package = _PIP_PACKAGES.get(missing, missing)
        raise AIProviderNotConfiguredError(
            f"Python package '{package}' is required by the {provider_name.value} provider. "
            f"Install it with: pip install {package}",
            details={**details, "missing_package": package},
        ) from exc

    provider_class = getattr(module, class_name, None)
    if provider_class is None:
        raise AIProviderNotConfiguredError(
            f"{module_name} does not define {class_name}.", details=details
        )
    provider = provider_class(settings)
    if not isinstance(provider, RequirementAI):
        raise AIProviderNotConfiguredError(
            f"{class_name} does not implement the RequirementAI interface.", details=details
        )
    return provider
