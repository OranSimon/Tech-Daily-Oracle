"""Google Gen AI adapter for Gemini."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from importlib import import_module
from typing import Any

import httpx

from tech_daily.llm.config import ProviderSettings
from tech_daily.llm.contracts import (
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
    NetworkFailure,
    ProviderUnavailable,
    QuotaExceeded,
    RateLimited,
)
from tech_daily.llm.providers.anthropic import (
    CONTINUE_PROMPT,
    _deduplicate_results,
    _normalize_search_result,
    _parse_json_search_results,
)

__all__ = ["GeminiAdapter"]

_GOOGLE_GENAI_API_ERRORS: tuple[type[BaseException], ...] | None = None


def _load_google_genai_api_errors() -> tuple[type[BaseException], ...]:
    global _GOOGLE_GENAI_API_ERRORS
    if _GOOGLE_GENAI_API_ERRORS is not None:
        return _GOOGLE_GENAI_API_ERRORS
    try:
        errors: Any = import_module("google.genai.errors")
    except ModuleNotFoundError as error:
        if error.name in {"google.genai", "google.genai.errors"}:
            _GOOGLE_GENAI_API_ERRORS = ()
            return _GOOGLE_GENAI_API_ERRORS
        raise
    _GOOGLE_GENAI_API_ERRORS = (errors.APIError,)
    return _GOOGLE_GENAI_API_ERRORS


class GeminiAdapter:
    """Translate provider-neutral requests to Google Gen AI calls."""

    name = "gemini"

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def has_credentials(self) -> bool:
        return self._client is not None or bool(self._api_key)

    def model_for(self, role: ModelRole) -> str:
        return self._settings.model_for(role)

    def generate_text(self, request: TextRequest) -> LLMResponse:
        return self._generate(
            request,
            contents=[{"role": "user", "parts": [{"text": request.user}]}],
        )

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        return self._generate(
            request,
            contents=[
                {"role": "user", "parts": [{"text": request.user}]},
                {"role": "model", "parts": [{"text": partial}]},
                {"role": "user", "parts": [{"text": CONTINUE_PROMPT}]},
            ],
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        return self._generate(
            request,
            contents=[{"role": "user", "parts": [{"text": request.user}]}],
            config_options={
                "response_mime_type": "application/json",
                "response_json_schema": _json_schema_payload(request.json_schema),
            },
        )

    def search_web(self, request: SearchRequest) -> SearchResponse:
        model = self._settings.model_for(request.role)
        try:
            response = self._get_client().models.generate_content(
                model=model,
                contents=request.query,
                config={
                    "tools": [{"google_search": {}}],
                    "max_output_tokens": request.max_output_tokens,
                },
            )
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code in {401, 403}:
                raise AuthenticationFailure(self.name) from error
            if status_code == 408:
                raise NetworkFailure(self.name) from error
            if status_code == 402:
                raise QuotaExceeded(self.name) from error
            if status_code == 429:
                raise RateLimited(self.name) from error
            if status_code >= 500:
                raise ProviderUnavailable(self.name) from error
            raise
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as error:
            raise NetworkFailure(self.name) from error
        except BaseException as error:
            if _is_google_genai_api_error(error):
                _raise_google_genai_failure(self.name, error)
            raise
        return SearchResponse(
            results=_parse_gemini_search_response(response, self.name, request.max_results),
            provider=self.name,
            model=model,
        )

    def _generate(
        self,
        request: TextRequest | StructuredRequest,
        *,
        contents: list[dict[str, Any]],
        config_options: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        model = self._settings.model_for(request.role)
        config: dict[str, Any] = {
            "system_instruction": request.system,
            "max_output_tokens": request.max_output_tokens,
        }
        if config_options is not None:
            config.update(config_options)
        try:
            response = self._get_client().models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code in {401, 403}:
                raise AuthenticationFailure(self.name) from error
            if status_code == 408:
                raise NetworkFailure(self.name) from error
            if status_code == 402:
                raise QuotaExceeded(self.name) from error
            if status_code == 429:
                raise RateLimited(self.name) from error
            if status_code >= 500:
                raise ProviderUnavailable(self.name) from error
            raise
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as error:
            raise NetworkFailure(self.name) from error
        except BaseException as error:
            if _is_google_genai_api_error(error):
                _raise_google_genai_failure(self.name, error)
            raise
        text, finish_reason = _parse_gemini_response(response, self.name)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            finish_reason=finish_reason,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            genai: Any = import_module("google.genai")
            self._client = genai.Client(api_key=self._api_key)
        return self._client


def _gemini_finish_reason(reason: object) -> FinishReason:
    normalized = str(reason).rsplit(".", maxsplit=1)[-1].upper()
    if normalized == "STOP":
        return FinishReason.COMPLETE
    if normalized == "MAX_TOKENS":
        return FinishReason.MAX_TOKENS
    if normalized in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}:
        return FinishReason.SAFETY
    return FinishReason.UNKNOWN


def _is_google_genai_api_error(error: BaseException) -> bool:
    if _GOOGLE_GENAI_API_ERRORS is None:
        errors = sys.modules.get("google.genai.errors")
        api_error = getattr(errors, "APIError", None)
        if not isinstance(api_error, type) or not isinstance(error, api_error):
            return False
    return isinstance(error, _load_google_genai_api_errors())


def _raise_google_genai_failure(provider: str, error: BaseException) -> None:
    typed_error: Any = error
    status_code = typed_error.code
    body = typed_error.details
    if status_code in {401, 403}:
        raise AuthenticationFailure(provider) from error
    if status_code in {408, 504}:
        raise NetworkFailure(provider) from error
    if status_code == 402 or _is_quota_error(body):
        raise QuotaExceeded(provider) from error
    if status_code == 429:
        raise RateLimited(provider) from error
    if isinstance(status_code, int) and status_code >= 500:
        raise ProviderUnavailable(provider) from error
    raise error


def _is_quota_error(body: object) -> bool:
    if not isinstance(body, Mapping):
        return False
    details = body.get("error", body)
    if not isinstance(details, Mapping):
        return False
    return details.get("status") in {"RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"}


def _parse_gemini_response(response: object, provider: str) -> tuple[str, FinishReason]:
    candidates = _response_attribute(response, "candidates")
    if not isinstance(candidates, list | tuple) or not candidates:
        raise InvalidProviderResponse(provider)
    finish_reason = _response_attribute(candidates[0], "finish_reason")
    try:
        text = _response_attribute(response, "text")
    except ValueError as error:
        raise InvalidProviderResponse(provider) from error
    if not isinstance(text, str):
        raise InvalidProviderResponse(provider)
    return text, _gemini_finish_reason(finish_reason)


def _response_attribute(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _json_schema_payload(schema: Mapping[str, Any]) -> dict[str, Any]:
    parsed: object = json.loads(json.dumps(schema, default=dict))
    if not isinstance(parsed, dict):
        raise TypeError("JSON schema must be an object")
    return parsed


def _parse_gemini_search_response(
    response: object,
    provider: str,
    max_results: int,
) -> list[dict[str, str]]:
    candidates = _response_attribute(response, "candidates")
    if not isinstance(candidates, list | tuple) or not candidates:
        raise InvalidProviderResponse(provider)
    metadata = _response_attribute(candidates[0], "grounding_metadata")
    chunks = _response_attribute(metadata, "grounding_chunks")
    supports = _response_attribute(metadata, "grounding_supports")

    summaries: dict[int, list[str]] = {}
    if isinstance(supports, list | tuple):
        for support in supports:
            segment = _response_attribute(support, "segment")
            summary = _response_attribute(segment, "text")
            indices = _response_attribute(support, "grounding_chunk_indices")
            if not isinstance(summary, str) or not isinstance(indices, list | tuple):
                continue
            for index in indices:
                if isinstance(index, int):
                    summaries.setdefault(index, []).append(summary)

    results: list[dict[str, str]] = []
    if isinstance(chunks, list | tuple):
        for index, chunk in enumerate(chunks):
            web = _response_attribute(chunk, "web")
            if web is None:
                continue
            results.append(
                _normalize_search_result(
                    provider=provider,
                    title=_response_attribute(web, "title"),
                    url=_response_attribute(web, "uri") or _response_attribute(web, "url"),
                    source=_response_attribute(web, "source"),
                    summary=" ".join(summaries.get(index, [])),
                    published_at=_response_attribute(web, "published_at"),
                )
            )

    if results:
        return _deduplicate_results(results, max_results)
    try:
        text = _response_attribute(response, "text")
    except ValueError as error:
        raise InvalidProviderResponse(provider) from error
    if isinstance(text, str) and text.strip():
        return _parse_json_search_results(text, provider, max_results)
    raise InvalidProviderResponse(provider)
