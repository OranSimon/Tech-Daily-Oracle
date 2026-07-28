"""Normalized failures used to decide whether provider fallback is safe."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "AuthenticationFailure",
    "InvalidProviderResponse",
    "LLMConfigurationError",
    "MissingCredential",
    "NetworkFailure",
    "ProviderExhaustedError",
    "ProviderFailure",
    "ProviderUnavailable",
    "QuotaExceeded",
    "RateLimited",
    "is_fallback_eligible",
]


class ProviderFailure(RuntimeError):
    """A normalized provider error with a source provider name."""

    fallback_eligible = False

    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        super().__init__(message or self.__class__.__name__)


class MissingCredential(ProviderFailure):
    fallback_eligible = True


class AuthenticationFailure(ProviderFailure):
    fallback_eligible = True


class RateLimited(ProviderFailure):
    fallback_eligible = True


class QuotaExceeded(ProviderFailure):
    fallback_eligible = True


class NetworkFailure(ProviderFailure):
    fallback_eligible = True


class ProviderUnavailable(ProviderFailure):
    fallback_eligible = True


class InvalidProviderResponse(ProviderFailure):
    fallback_eligible = True


_FALLBACK_ELIGIBLE_TYPES = (
    MissingCredential,
    AuthenticationFailure,
    RateLimited,
    QuotaExceeded,
    NetworkFailure,
    ProviderUnavailable,
    InvalidProviderResponse,
)
_SAFE_CAPABILITIES = frozenset({"generate_text", "generate_json", "generate_structured", "search_web", "continue_text"})
_SAFE_PROVIDERS = frozenset({"deepseek", "claude", "openai", "gemini"})
_SAFE_FAILURE_CATEGORIES = frozenset(
    {
        "missing_credential",
        "authentication_failure",
        "rate_limited",
        "quota_exceeded",
        "network_failure",
        "provider_unavailable",
        "invalid_provider_response",
    }
)


def is_fallback_eligible(error: BaseException) -> bool:
    """Return whether an error is one of the approved fallback categories."""

    return isinstance(error, _FALLBACK_ELIGIBLE_TYPES)


class ProviderExhaustedError(RuntimeError):
    """Raised after every configured provider fails an eligible attempt."""

    def __init__(self, capability: str, attempts: Iterable[str]) -> None:
        self.capability = capability if capability in _SAFE_CAPABILITIES else "requested capability"
        self.attempts = tuple(_sanitize_attempt(attempt) for attempt in attempts)
        summary = "; ".join(self.attempts) or "no provider attempts"
        super().__init__(f"Providers exhausted for {self.capability}: {summary}")


class LLMConfigurationError(RuntimeError):
    """Raised when LLM configuration cannot be read or validated."""


def _sanitize_attempt(attempt: str) -> str:
    """Preserve only a recognized provider name and normalized failure category."""

    provider, separator, category = attempt.partition(": ")
    if separator and provider in _SAFE_PROVIDERS and category in _SAFE_FAILURE_CATEGORIES:
        return f"{provider}: {category}"
    return "provider_failure"
