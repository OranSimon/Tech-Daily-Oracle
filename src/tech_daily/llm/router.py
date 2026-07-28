"""Strict capability router for provider-neutral LLM requests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, TypeVar, cast

from pydantic import BaseModel, ValidationError

from tech_daily.llm.contracts import (
    Capability,
    FinishReason,
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.errors import (
    AuthenticationFailure,
    InvalidProviderResponse,
    LLMConfigurationError,
    MissingCredential,
    NetworkFailure,
    ProviderExhaustedError,
    ProviderFailure,
    ProviderUnavailable,
    QuotaExceeded,
    RateLimited,
    is_fallback_eligible,
)
from tech_daily.llm.providers.base import ProviderAdapter

__all__ = ["AttemptRecord", "JSONValue", "ProviderRouter"]

_SAFE_PROVIDER_NAMES = frozenset({"deepseek", "claude", "openai", "gemini"})
_SAFE_MODEL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")
_MAX_CONTINUATIONS = 4
T = TypeVar("T", bound=BaseModel)
JSONValue: TypeAlias = dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None


@dataclass(frozen=True)
class AttemptRecord:
    """Content-free telemetry for one provider routing attempt."""

    capability: Capability
    provider: str
    model: str | None
    attempt_number: int
    outcome: Literal["success", "failure"]
    error_category: str | None
    fallback_reason: str | None


class ProviderRouter:
    """Try provider adapters in configured order for each capability."""

    def __init__(
        self,
        adapters: Iterable[ProviderAdapter],
        *,
        on_attempt: Callable[[AttemptRecord], None] | None = None,
    ) -> None:
        self._adapters = tuple(adapters)
        if any(adapter.name not in _SAFE_PROVIDER_NAMES for adapter in self._adapters):
            raise LLMConfigurationError("Unknown LLM provider configured")
        self._on_attempt = on_attempt

    def generate_text(self, request: TextRequest, *, auto_continue: bool = False) -> LLMResponse:
        """Return the first valid text response from the configured adapters."""

        return self._attempt_text(request, auto_continue=auto_continue)

    def generate_structured(self, request: StructuredRequest, schema_type: type[T]) -> T:
        """Return the first response that parses and validates against ``schema_type``."""

        failures: list[str] = []
        for attempt_number, adapter in enumerate(self._adapters, start=1):
            model = _configured_model(adapter, request.role)
            try:
                if not adapter.has_credentials():
                    raise MissingCredential(adapter.name)
                response = adapter.generate_structured(request)
                self._validate_text_response(adapter, response, allow_max_tokens=False)
                try:
                    parsed = json.loads(response.text)
                    result = schema_type.model_validate(parsed)
                except (json.JSONDecodeError, ValidationError) as error:
                    raise InvalidProviderResponse(adapter.name) from error
            except ProviderFailure as error:
                if not is_fallback_eligible(error):
                    raise
                category = _failure_category(error)
                failures.append(f"{_safe_provider(adapter.name)}: {category}")
                self._record_failure(Capability.STRUCTURED, adapter, model, attempt_number, category)
                continue

            self._record_success(Capability.STRUCTURED, adapter, model, attempt_number)
            return result

        raise ProviderExhaustedError(Capability.STRUCTURED.value, failures)

    def generate_json(self, request: TextRequest) -> JSONValue:
        """Return the first provider response containing a valid JSON value."""

        failures: list[str] = []
        for attempt_number, adapter in enumerate(self._adapters, start=1):
            model = _configured_model(adapter, request.role)
            try:
                if not adapter.has_credentials():
                    raise MissingCredential(adapter.name)
                response = adapter.generate_text(request)
                self._validate_text_response(adapter, response, allow_max_tokens=False)
                result = _parse_json_value(response.text, adapter.name)
            except ProviderFailure as error:
                if not is_fallback_eligible(error):
                    raise
                category = _failure_category(error)
                failures.append(f"{_safe_provider(adapter.name)}: {category}")
                self._record_failure(Capability.JSON, adapter, model, attempt_number, category)
                continue

            self._record_success(Capability.JSON, adapter, model, attempt_number)
            return result

        raise ProviderExhaustedError(Capability.JSON.value, failures)

    def search_web(self, request: SearchRequest) -> SearchResponse:
        """Return the first non-empty provider-native search response."""

        return cast(SearchResponse, self._attempt(Capability.SEARCH, request))

    def _attempt_text(self, request: TextRequest, *, auto_continue: bool) -> LLMResponse:
        failures: list[str] = []
        for attempt_number, adapter in enumerate(self._adapters, start=1):
            model = _configured_model(adapter, request.role)
            try:
                if not adapter.has_credentials():
                    raise MissingCredential(adapter.name)
                response = adapter.generate_text(request)
                self._validate_text_response(adapter, response, allow_max_tokens=auto_continue)
                if response.finish_reason is FinishReason.MAX_TOKENS:
                    response = self._continue_text(adapter, request, response)
            except ProviderFailure as error:
                if not is_fallback_eligible(error):
                    raise
                category = _failure_category(error)
                failures.append(f"{_safe_provider(adapter.name)}: {category}")
                self._record_failure(Capability.TEXT, adapter, model, attempt_number, category)
                continue

            self._record_success(Capability.TEXT, adapter, model, attempt_number)
            return response

        raise ProviderExhaustedError(Capability.TEXT.value, failures)

    def _continue_text(
        self,
        adapter: ProviderAdapter,
        request: TextRequest,
        initial: LLMResponse,
    ) -> LLMResponse:
        accumulated = initial.text
        model = _configured_model(adapter, request.role)
        for attempt_number in range(1, _MAX_CONTINUATIONS + 1):
            try:
                continuation = adapter.continue_text(request, accumulated)
                self._validate_text_response(adapter, continuation, allow_max_tokens=True)
            except ProviderFailure as error:
                if is_fallback_eligible(error):
                    category = _failure_category(error)
                    self._record_failure(
                        Capability.CONTINUATION,
                        adapter,
                        model,
                        attempt_number,
                        category,
                    )
                raise

            self._record_success(
                Capability.CONTINUATION,
                adapter,
                model,
                attempt_number,
            )
            accumulated += continuation.text
            if continuation.finish_reason is FinishReason.COMPLETE:
                return LLMResponse(
                    text=accumulated,
                    provider=initial.provider,
                    model=initial.model,
                    finish_reason=FinishReason.COMPLETE,
                )
        raise InvalidProviderResponse(adapter.name)

    def _attempt(
        self,
        capability: Capability,
        request: TextRequest | StructuredRequest | SearchRequest,
    ) -> LLMResponse | SearchResponse:
        failures: list[str] = []
        for attempt_number, adapter in enumerate(self._adapters, start=1):
            model = _configured_model(adapter, request.role)
            try:
                if not adapter.has_credentials():
                    raise MissingCredential(adapter.name)
                response = self._dispatch(adapter, capability, request)
                self._validate_response(adapter, capability, response)
            except ProviderFailure as error:
                if not is_fallback_eligible(error):
                    raise
                category = _failure_category(error)
                failures.append(f"{_safe_provider(adapter.name)}: {category}")
                self._record_failure(capability, adapter, model, attempt_number, category)
                continue

            self._record_success(capability, adapter, model, attempt_number)
            return response

        raise ProviderExhaustedError(capability.value, failures)

    def _dispatch(
        self,
        adapter: ProviderAdapter,
        capability: Capability,
        request: TextRequest | StructuredRequest | SearchRequest,
    ) -> LLMResponse | SearchResponse:
        if capability is Capability.TEXT:
            return adapter.generate_text(cast(TextRequest, request))
        if capability is Capability.STRUCTURED:
            return adapter.generate_structured(cast(StructuredRequest, request))
        if capability is Capability.SEARCH:
            return adapter.search_web(cast(SearchRequest, request))
        raise ValueError(f"Unsupported router capability: {capability}")

    def _validate_response(
        self,
        adapter: ProviderAdapter,
        capability: Capability,
        response: LLMResponse | SearchResponse,
    ) -> None:
        if capability is Capability.SEARCH:
            if not isinstance(response, SearchResponse) or not response.results:
                raise InvalidProviderResponse(adapter.name)
            for result in response.results:
                if not isinstance(result, Mapping):
                    raise InvalidProviderResponse(adapter.name)
                title = result.get("title")
                url = result.get("url")
                if not isinstance(title, str) or not title.strip() or not isinstance(url, str) or not url.strip():
                    raise InvalidProviderResponse(adapter.name)
            return

        if not isinstance(response, LLMResponse):
            raise InvalidProviderResponse(adapter.name)
        self._validate_text_response(adapter, response, allow_max_tokens=False)

    def _validate_text_response(
        self,
        adapter: ProviderAdapter,
        response: object,
        *,
        allow_max_tokens: bool,
    ) -> None:
        allowed_reasons = {FinishReason.COMPLETE}
        if allow_max_tokens:
            allowed_reasons.add(FinishReason.MAX_TOKENS)
        if (
            not isinstance(response, LLMResponse)
            or not isinstance(response.text, str)
            or not response.text.strip()
            or response.finish_reason not in allowed_reasons
        ):
            raise InvalidProviderResponse(adapter.name)

    def _record_success(
        self,
        capability: Capability,
        adapter: ProviderAdapter,
        model: str | None,
        attempt_number: int,
    ) -> None:
        self._emit(
            AttemptRecord(
                capability=capability,
                provider=_safe_provider(adapter.name),
                model=model,
                attempt_number=attempt_number,
                outcome="success",
                error_category=None,
                fallback_reason=None,
            )
        )

    def _record_failure(
        self,
        capability: Capability,
        adapter: ProviderAdapter,
        model: str | None,
        attempt_number: int,
        category: str,
    ) -> None:
        self._emit(
            AttemptRecord(
                capability=capability,
                provider=_safe_provider(adapter.name),
                model=model,
                attempt_number=attempt_number,
                outcome="failure",
                error_category=category,
                fallback_reason=category,
            )
        )

    def _emit(self, record: AttemptRecord) -> None:
        if self._on_attempt is not None:
            self._on_attempt(record)


def _safe_provider(provider: str) -> str:
    """Keep provider-controlled telemetry to the approved provider names."""

    return provider if provider in _SAFE_PROVIDER_NAMES else "unknown_provider"


def _configured_model(adapter: ProviderAdapter, role: ModelRole) -> str | None:
    """Read model telemetry from adapter-owned configuration, never responses."""

    model_for = getattr(adapter, "model_for", None)
    if not callable(model_for):
        return None
    model = model_for(role)
    if not isinstance(model, str) or _SAFE_MODEL_IDENTIFIER.fullmatch(model) is None:
        return None
    return model


def _parse_json_value(text: str, provider: str) -> JSONValue:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        parsed: object = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise InvalidProviderResponse(provider) from error
    return cast(JSONValue, parsed)


def _failure_category(error: ProviderFailure) -> str:
    """Map normalized errors to their non-sensitive telemetry category."""

    categories: tuple[tuple[type[ProviderFailure], str], ...] = (
        (MissingCredential, "missing_credential"),
        (AuthenticationFailure, "authentication_failure"),
        (RateLimited, "rate_limited"),
        (QuotaExceeded, "quota_exceeded"),
        (NetworkFailure, "network_failure"),
        (ProviderUnavailable, "provider_unavailable"),
        (InvalidProviderResponse, "invalid_provider_response"),
    )
    for error_type, category in categories:
        if isinstance(error, error_type):
            return category
    raise TypeError(f"Unsupported fallback error: {type(error).__name__}")
