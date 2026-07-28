"""OpenAI-compatible Chat Completions adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, ClassVar, Never

import anthropic
import httpx
import openai

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
    _parse_anthropic_search_response,
    _parse_json_search_results,
)

__all__ = ["DeepSeekAdapter", "OpenAIAdapter"]

_DEEPSEEK_ARRAY_ENVELOPE_KEY = "structured_output"


class _OpenAICompatibleAdapter:
    name: str
    credential_environment_variable: str
    token_limit_field: ClassVar[str]

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: Any | None = None,
        search_client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._search_client = search_client
        self._api_key = api_key or os.environ.get(self.credential_environment_variable)

    def has_credentials(self) -> bool:
        return self._client is not None or self._search_client is not None or bool(self._api_key)

    def model_for(self, role: ModelRole) -> str:
        return self._settings.model_for(role)

    def generate_text(self, request: TextRequest) -> LLMResponse:
        return self._generate(
            request,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        )

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        return self._generate(
            request,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
                {"role": "assistant", "content": partial},
                {"role": "user", "content": CONTINUE_PROMPT},
            ],
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        raise NotImplementedError

    def search_web(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError

    def _generate(
        self,
        request: TextRequest | StructuredRequest,
        *,
        messages: list[dict[str, str]],
        request_options: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        model = self._settings.model_for(request.role)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **self._token_limit_payload(request.max_output_tokens),
        }
        if request_options is not None:
            payload.update(request_options)
        try:
            response = self._get_client().chat.completions.create(**payload)
        except openai.APIResponseValidationError as error:
            raise InvalidProviderResponse(self.name) from error
        except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
            raise AuthenticationFailure(self.name) from error
        except openai.RateLimitError as error:
            if _is_quota_error(error.body):
                raise QuotaExceeded(self.name) from error
            raise RateLimited(self.name) from error
        except openai.APIConnectionError as error:
            raise NetworkFailure(self.name) from error
        except openai.InternalServerError as error:
            raise ProviderUnavailable(self.name) from error
        except openai.APIStatusError as error:
            _raise_status_failure(self.name, error.status_code, error.body, error)
        except httpx.HTTPStatusError as error:
            _raise_status_failure(self.name, error.response.status_code, None, error)
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as error:
            raise NetworkFailure(self.name) from error
        text, finish_reason = _parse_openai_response(response, self.name)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            finish_reason=finish_reason,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        raise NotImplementedError

    def _token_limit_payload(self, max_output_tokens: int) -> dict[str, Any]:
        return {self.token_limit_field: max_output_tokens}


class DeepSeekAdapter(_OpenAICompatibleAdapter):
    """Translate neutral requests to DeepSeek's OpenAI-compatible chat API."""

    name = "deepseek"
    credential_environment_variable = "DEEPSEEK_API_KEY"
    token_limit_field = "max_tokens"

    def search_web(self, request: SearchRequest) -> SearchResponse:
        model = self._settings.model_for(request.role)
        try:
            response = self._get_search_client().messages.create(
                model=model,
                max_tokens=request.max_output_tokens,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": request.max_results,
                    }
                ],
                messages=[{"role": "user", "content": request.query}],
            )
        except anthropic.APIResponseValidationError as error:
            raise InvalidProviderResponse(self.name) from error
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as error:
            raise AuthenticationFailure(self.name) from error
        except anthropic.RateLimitError as error:
            if _is_quota_error(error.body):
                raise QuotaExceeded(self.name) from error
            raise RateLimited(self.name) from error
        except anthropic.APIConnectionError as error:
            raise NetworkFailure(self.name) from error
        except anthropic.InternalServerError as error:
            raise ProviderUnavailable(self.name) from error
        except anthropic.APIStatusError as error:
            _raise_status_failure(self.name, error.status_code, error.body, error)
        except httpx.HTTPStatusError as error:
            _raise_status_failure(self.name, error.response.status_code, None, error)
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as error:
            raise NetworkFailure(self.name) from error
        return SearchResponse(
            results=_parse_anthropic_search_response(response, self.name, request.max_results),
            provider=self.name,
            model=model,
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        schema = _json_schema_payload(request.json_schema)
        array_root = schema.get("type") == "array"
        provider_schema = _deepseek_array_envelope_schema(schema) if array_root else schema
        schema_instructions = (
            f"{request.system}\n\n"
            "Return only one valid JSON object matching this JSON Schema:\n"
            f"{json.dumps(provider_schema, ensure_ascii=False, separators=(',', ':'))}"
        )
        response = self._generate(
            request,
            messages=[
                {"role": "system", "content": schema_instructions},
                {"role": "user", "content": request.user},
            ],
            request_options={"response_format": {"type": "json_object"}},
        )
        if not array_root:
            return response
        return _unwrap_deepseek_array_response(response)

    def _build_client(self) -> Any:
        return openai.OpenAI(api_key=self._api_key, base_url="https://api.deepseek.com")

    def _get_search_client(self) -> Any:
        if self._search_client is None:
            self._search_client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url="https://api.deepseek.com/anthropic",
            )
        return self._search_client


class OpenAIAdapter(_OpenAICompatibleAdapter):
    """Translate neutral requests to OpenAI Chat Completions."""

    name = "openai"
    credential_environment_variable = "OPENAI_API_KEY"
    token_limit_field = "max_completion_tokens"

    def search_web(self, request: SearchRequest) -> SearchResponse:
        model = self._settings.model_for(request.role)
        try:
            response = self._get_client().responses.create(
                model=model,
                input=request.query,
                tools=[{"type": "web_search"}],
                max_output_tokens=request.max_output_tokens,
            )
        except openai.APIResponseValidationError as error:
            raise InvalidProviderResponse(self.name) from error
        except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
            raise AuthenticationFailure(self.name) from error
        except openai.RateLimitError as error:
            if _is_quota_error(error.body):
                raise QuotaExceeded(self.name) from error
            raise RateLimited(self.name) from error
        except openai.APIConnectionError as error:
            raise NetworkFailure(self.name) from error
        except openai.InternalServerError as error:
            raise ProviderUnavailable(self.name) from error
        except openai.APIStatusError as error:
            _raise_status_failure(self.name, error.status_code, error.body, error)
        except httpx.HTTPStatusError as error:
            _raise_status_failure(self.name, error.response.status_code, None, error)
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as error:
            raise NetworkFailure(self.name) from error
        return SearchResponse(
            results=_parse_openai_search_response(response, self.name, request.max_results),
            provider=self.name,
            model=model,
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        return self._generate(
            request,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            request_options={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "strict": True,
                        "schema": _json_schema_payload(request.json_schema),
                    },
                }
            },
        )

    def _build_client(self) -> Any:
        return openai.OpenAI(api_key=self._api_key)

    def _token_limit_payload(self, max_output_tokens: int) -> dict[str, Any]:
        return {"extra_body": {self.token_limit_field: max_output_tokens}}


def _openai_finish_reason(reason: object) -> FinishReason:
    if reason == "stop":
        return FinishReason.COMPLETE
    if reason == "length":
        return FinishReason.MAX_TOKENS
    if reason == "content_filter":
        return FinishReason.SAFETY
    return FinishReason.UNKNOWN


def _raise_status_failure(
    provider: str,
    status_code: int,
    body: object,
    error: BaseException,
) -> Never:
    if status_code in {401, 403}:
        raise AuthenticationFailure(provider) from error
    if status_code == 408:
        raise NetworkFailure(provider) from error
    if status_code == 402 or _is_quota_error(body):
        raise QuotaExceeded(provider) from error
    if status_code == 429:
        raise RateLimited(provider) from error
    if status_code >= 500:
        raise ProviderUnavailable(provider) from error
    raise error


def _is_quota_error(body: object) -> bool:
    if not isinstance(body, Mapping):
        return False
    details = body.get("error", body)
    if not isinstance(details, Mapping):
        return False
    return details.get("code") in {"billing_error", "insufficient_quota", "quota_exceeded"}


def _parse_openai_response(response: object, provider: str) -> tuple[str, FinishReason]:
    choices = _response_attribute(response, "choices")
    if not isinstance(choices, list | tuple) or not choices:
        raise InvalidProviderResponse(provider)
    choice = choices[0]
    message = _response_attribute(choice, "message")
    if message is None:
        raise InvalidProviderResponse(provider)

    content = _response_attribute(message, "content")
    refusal = _response_attribute(message, "refusal")
    if refusal:
        return content if isinstance(content, str) else "", FinishReason.REFUSAL
    if not isinstance(content, str):
        raise InvalidProviderResponse(provider)
    return content, _openai_finish_reason(_response_attribute(choice, "finish_reason"))


def _response_attribute(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _json_schema_payload(schema: Mapping[str, Any]) -> dict[str, Any]:
    parsed: object = json.loads(json.dumps(schema, default=dict))
    if not isinstance(parsed, dict):
        raise TypeError("JSON schema must be an object")
    return parsed


def _deepseek_array_envelope_schema(schema: dict[str, Any]) -> dict[str, Any]:
    array_schema = dict(schema)
    definitions = array_schema.pop("$defs", None)
    envelope: dict[str, Any] = {
        "type": "object",
        "properties": {_DEEPSEEK_ARRAY_ENVELOPE_KEY: array_schema},
        "required": [_DEEPSEEK_ARRAY_ENVELOPE_KEY],
        "additionalProperties": False,
    }
    if definitions is not None:
        envelope["$defs"] = definitions
    return envelope


def _unwrap_deepseek_array_response(response: LLMResponse) -> LLMResponse:
    try:
        envelope: object = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise InvalidProviderResponse("deepseek") from error
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {_DEEPSEEK_ARRAY_ENVELOPE_KEY}
        or not isinstance(envelope[_DEEPSEEK_ARRAY_ENVELOPE_KEY], list)
    ):
        raise InvalidProviderResponse("deepseek")
    return LLMResponse(
        text=json.dumps(
            envelope[_DEEPSEEK_ARRAY_ENVELOPE_KEY],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        provider=response.provider,
        model=response.model,
        finish_reason=response.finish_reason,
    )


def _parse_openai_search_response(
    response: object,
    provider: str,
    max_results: int,
) -> list[dict[str, str]]:
    output = _response_attribute(response, "output")
    if not isinstance(output, list | tuple):
        raise InvalidProviderResponse(provider)

    text_blocks: list[str] = []
    results: list[dict[str, str]] = []
    for item in output:
        content = _response_attribute(item, "content")
        if not isinstance(content, list | tuple):
            continue
        for block in content:
            if _response_attribute(block, "type") != "output_text":
                continue
            text = _response_attribute(block, "text")
            if isinstance(text, str) and text.strip():
                text_blocks.append(text)
            annotations = _response_attribute(block, "annotations")
            if not isinstance(annotations, list | tuple):
                continue
            for annotation in annotations:
                if _response_attribute(annotation, "type") != "url_citation":
                    continue
                summary = _response_attribute(annotation, "summary")
                if not isinstance(summary, str):
                    summary = _response_attribute(annotation, "cited_text")
                if not isinstance(summary, str) and isinstance(text, str):
                    summary = text
                results.append(
                    _normalize_search_result(
                        provider=provider,
                        title=_response_attribute(annotation, "title"),
                        url=_response_attribute(annotation, "url"),
                        source=_response_attribute(annotation, "source"),
                        summary=summary,
                        published_at=_response_attribute(annotation, "published_at"),
                    )
                )

    if results:
        return _deduplicate_results(results, max_results)
    output_text = _response_attribute(response, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _parse_json_search_results(output_text, provider, max_results)
    if text_blocks:
        return _parse_json_search_results("\n".join(text_blocks), provider, max_results)
    raise InvalidProviderResponse(provider)
