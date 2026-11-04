"""Factory that returns the configured AI provider.

* A selected provider with missing credentials raises a clear configuration
  error. The factory never silently switches to the fake provider.
* Groq and Gemini providers are loaded lazily so neither is required to run
  the other. Their modules are delivered by Member 3:
  ``app/ai/groq_provider.py`` (class ``GroqProvider``) and
  ``app/ai/gemini_provider.py`` (class ``GeminiProvider``). Each class takes
  ``Settings`` as its only constructor argument.
"""

from __future__ import annotations

import importlib

from app.ai.fake_provider import FakeProvider
from app.ai.integration_interface import RequirementAI
from app.core.config import Settings
from app.core.contracts import AIProvider
from app.core.errors import AIProviderNotConfiguredError

_PROVIDER_CLASSES: dict[AIProvider, tuple[str, str]] = {
    AIProvider.GROQ: ("app.ai.groq_provider", "GroqProvider"),
    AIProvider.GEMINI: ("app.ai.gemini_provider", "GeminiProvider"),
}

_PIP_PACKAGES: dict[str, str] = {"groq": "groq", "google": "google-genai"}


def get_ai_provider(settings: Settings) -> RequirementAI:
    """Return the provider selected by ``AI_PROVIDER`` or raise a configuration error."""
    issues = settings.ai_configuration_issues()
    if issues:
        raise AIProviderNotConfiguredError(
            f"AI provider '{settings.ai_provider}' is not configured.",
            details={"provider": settings.ai_provider, "issues": issues},
        )

    provider_name = AIProvider(settings.ai_provider)
    if provider_name is AIProvider.FAKE:
        return FakeProvider()

    module_name, class_name = _PROVIDER_CLASSES[provider_name]
    details = {"provider": provider_name.value, "module": module_name}
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise AIProviderNotConfiguredError(
                f"The {provider_name.value} provider is not implemented yet ({module_name}).",
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
