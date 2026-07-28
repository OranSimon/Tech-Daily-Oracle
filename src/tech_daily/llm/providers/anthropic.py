"""Anthropic Messages adapter for Claude."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Never
from urllib.parse import urlparse

import anthropic
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

__all__ = ["CONTINUE_PROMPT", "ClaudeAdapter"]

CONTINUE_PROMPT = "上一轮回复因输出上限被截断。请从停止位置继续，不重复已输出内容，不要添加引言或元说明。"


class ClaudeAdapter:
    """Translate provider-neutral requests to Anthropic Messages calls."""

    name = "claude"

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def has_credentials(self) -> bool:
        return self._client is not None or bool(self._api_key)

    def model_for(self, role: ModelRole) -> str:
        return self._settings.model_for(role)

    def generate_text(self, request: TextRequest) -> LLMResponse:
        return self._generate(
            request,
            messages=[{"role": "user", "content": request.user}],
        )

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        return self._generate(
            request,
            messages=[
                {"role": "user", "content": request.user},
                {"role": "assistant", "content": partial},
                {"role": "user", "content": CONTINUE_PROMPT},
            ],
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        return self._generate(
            request,
            messages=[{"role": "user", "content": request.user}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _json_schema_payload(request.json_schema),
                }
            },
        )

    def search_web(self, request: SearchRequest) -> SearchResponse:
        model = self._settings.model_for(request.role)
        try:
            response = self._get_client().messages.create(
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

    def _generate(
        self,
        request: TextRequest | StructuredRequest,
        *,
        messages: list[dict[str, str]],
        output_config: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        system: list[dict[str, Any]] = [{"type": "text", "text": request.system}]
        if request.cache_system:
            system[0]["cache_control"] = {"type": "ephemeral"}
        model = self._settings.model_for(request.role)
        request_options: dict[str, Any] = {}
        if output_config is not None:
            request_options["extra_body"] = {"output_config": output_config}
        try:
            response = self._get_client().messages.create(
                model=model,
                max_tokens=request.max_output_tokens,
                system=system,
                messages=messages,
                **request_options,
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
        text, finish_reason = _parse_anthropic_response(response, self.name)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            finish_reason=finish_reason,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client


def _anthropic_finish_reason(reason: object) -> FinishReason:
    if reason in {"end_turn", "stop_sequence"}:
        return FinishReason.COMPLETE
    if reason == "max_tokens":
        return FinishReason.MAX_TOKENS
    if reason == "refusal":
        return FinishReason.REFUSAL
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


def _parse_anthropic_response(response: object, provider: str) -> tuple[str, FinishReason]:
    content = _response_attribute(response, "content")
    if not isinstance(content, list | tuple):
        raise InvalidProviderResponse(provider)
    for block in content:
        if _response_attribute(block, "type") != "text":
            continue
        text = _response_attribute(block, "text")
        if isinstance(text, str):
            return text, _anthropic_finish_reason(_response_attribute(response, "stop_reason"))
    raise InvalidProviderResponse(provider)


def _response_attribute(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _json_schema_payload(schema: Mapping[str, Any]) -> dict[str, Any]:
    parsed: object = json.loads(json.dumps(schema, default=dict))
    if not isinstance(parsed, dict):
        raise TypeError("JSON schema must be an object")
    return parsed


def _parse_anthropic_search_response(
    response: object,
    provider: str,
    max_results: int,
) -> list[dict[str, str]]:
    content = _response_attribute(response, "content")
    if not isinstance(content, list | tuple):
        raise InvalidProviderResponse(provider)

    text_blocks: list[str] = []
    citation_summaries: dict[str, str] = {}
    for block in content:
        if _response_attribute(block, "type") != "text":
            continue
        text = _response_attribute(block, "text")
        if isinstance(text, str) and text.strip():
            text_blocks.append(text)
        citations = _response_attribute(block, "citations")
        if not isinstance(citations, list | tuple):
            continue
        for citation in citations:
            url = _response_attribute(citation, "url")
            cited_text = _response_attribute(citation, "cited_text")
            if isinstance(url, str) and isinstance(cited_text, str):
                citation_summaries[url] = cited_text

    results: list[dict[str, str]] = []
    for block in content:
        if _response_attribute(block, "type") != "web_search_tool_result":
            continue
        tool_content = _response_attribute(block, "content")
        if _response_attribute(tool_content, "type") == "web_search_tool_result_error":
            _raise_search_tool_result_error(provider, tool_content)
        if not isinstance(tool_content, list | tuple):
            raise InvalidProviderResponse(provider)
        for item in tool_content:
            if _response_attribute(item, "type") != "web_search_result":
                continue
            url = _response_attribute(item, "url")
            summary = _response_attribute(item, "summary")
            if not isinstance(summary, str) and isinstance(url, str):
                summary = citation_summaries.get(url, "")
            results.append(
                _normalize_search_result(
                    provider=provider,
                    title=_response_attribute(item, "title"),
                    url=url,
                    source=_response_attribute(item, "source"),
                    summary=summary,
                    published_at=_response_attribute(item, "published_at") or _response_attribute(item, "page_age"),
                )
            )

    if results:
        return _deduplicate_results(results, max_results)
    if not text_blocks:
        raise InvalidProviderResponse(provider)
    return _parse_json_search_results("\n".join(text_blocks), provider, max_results)


def _parse_json_search_results(
    raw_text: str,
    provider: str,
    max_results: int,
) -> list[dict[str, str]]:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidProviderResponse(provider) from error
    if not isinstance(parsed, list) or not parsed:
        raise InvalidProviderResponse(provider)

    results: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, Mapping):
            raise InvalidProviderResponse(provider)
        results.append(
            _normalize_search_result(
                provider=provider,
                title=item.get("title"),
                url=item.get("url"),
                source=item.get("source"),
                summary=item.get("summary", item.get("snippet")),
                published_at=item.get("published_at"),
            )
        )
    return _deduplicate_results(results, max_results)


def _normalize_search_result(
    *,
    provider: str,
    title: object,
    url: object,
    source: object = None,
    summary: object = None,
    published_at: object = None,
) -> dict[str, str]:
    if not isinstance(title, str) or not title.strip():
        raise InvalidProviderResponse(provider)
    if not isinstance(url, str) or not url.strip():
        raise InvalidProviderResponse(provider)
    optional_values = (source, summary, published_at)
    if any(value is not None and not isinstance(value, str) for value in optional_values):
        raise InvalidProviderResponse(provider)

    normalized_url = url.strip()
    normalized_source = source.strip() if isinstance(source, str) else ""
    return {
        "title": title.strip(),
        "url": normalized_url,
        "source": normalized_source or _source_from_url(normalized_url),
        "summary": summary.strip() if isinstance(summary, str) else "",
        "published_at": published_at.strip() if isinstance(published_at, str) else "",
    }


def _deduplicate_results(
    results: list[dict[str, str]],
    max_results: int,
) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for result in results:
        if result["url"] in seen_urls:
            continue
        seen_urls.add(result["url"])
        unique.append(result)
        if len(unique) == max_results:
            break
    if not unique:
        raise InvalidProviderResponse("unknown_provider")
    return unique


def _source_from_url(url: str) -> str:
    hostname = (urlparse(url).hostname or "").removeprefix("www.")
    if not hostname:
        return ""
    label = hostname.split(".", maxsplit=1)[0].replace("-", " ").replace("_", " ")
    return label.title()


def _raise_search_tool_result_error(provider: str, content: object) -> Never:
    if _response_attribute(content, "type") != "web_search_tool_result_error":
        raise InvalidProviderResponse(provider)
    error_code = _response_attribute(content, "error_code")
    if error_code == "too_many_requests":
        raise RateLimited(provider)
    if error_code == "unavailable":
        raise ProviderUnavailable(provider)
    raise InvalidProviderResponse(provider)
