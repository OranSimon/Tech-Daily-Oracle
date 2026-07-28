from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

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
from tech_daily.llm.errors import InvalidProviderResponse, ProviderUnavailable, RateLimited
from tech_daily.llm.providers import ClaudeAdapter, DeepSeekAdapter, GeminiAdapter, OpenAIAdapter
from tech_daily.llm.providers import openai_compatible as openai_provider
from tech_daily.llm.router import AttemptRecord, ProviderRouter

VALID_RESULT = {
    "title": "Result",
    "url": "https://example.com/result",
    "source": "Example",
    "summary": "Summary",
    "published_at": "2026-07-27",
}


class FakeAnthropicSearchClient:
    def __init__(self, *, malformed: bool = False) -> None:
        self.last_request: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create)
        if malformed:
            self.response = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not-json")],
                stop_reason="end_turn",
            )
        else:
            citation = SimpleNamespace(
                type="web_search_result_location",
                title="Result",
                url="https://example.com/result",
                cited_text="Summary",
            )
            self.response = SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="web_search_tool_result",
                        content=[
                            SimpleNamespace(
                                type="web_search_result",
                                title="Result",
                                url="https://example.com/result",
                                page_age="2026-07-27",
                            )
                        ],
                    ),
                    SimpleNamespace(type="text", text="Summary", citations=[citation]),
                ],
                stop_reason="end_turn",
            )

    def _create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        return self.response


class FakeOpenAISearchClient:
    def __init__(self, *, malformed: bool = False) -> None:
        self.last_request: dict[str, Any] = {}
        self.responses = SimpleNamespace(create=self._create)
        if malformed:
            self.response = SimpleNamespace(output=[], output_text="not-json")
        else:
            annotation = SimpleNamespace(
                type="url_citation",
                title="Result",
                url="https://example.com/result",
                published_at="2026-07-27",
            )
            self.response = SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="Summary",
                                annotations=[annotation],
                            )
                        ],
                    )
                ],
                output_text="Summary",
            )

    def _create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        return self.response


class FakeGeminiSearchClient:
    def __init__(self, *, malformed: bool = False) -> None:
        self.last_request: dict[str, Any] = {}
        self.models = SimpleNamespace(generate_content=self._generate_content)
        if malformed:
            metadata = SimpleNamespace(grounding_chunks=[], grounding_supports=[])
            text = "not-json"
        else:
            web = SimpleNamespace(
                title="Result",
                uri="https://example.com/result",
                published_at="2026-07-27",
            )
            metadata = SimpleNamespace(
                grounding_chunks=[SimpleNamespace(web=web)],
                grounding_supports=[
                    SimpleNamespace(
                        segment=SimpleNamespace(text="Summary"),
                        grounding_chunk_indices=[0],
                    )
                ],
            )
            text = "Summary"
        self.response: object = SimpleNamespace(
            text=text,
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    grounding_metadata=metadata,
                )
            ],
        )

    def _generate_content(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        return self.response


def _settings(name: str) -> ProviderSettings:
    model = f"{name}-fixture-model"
    return ProviderSettings(name, {role: model for role in ModelRole})


def make_search_adapter(
    provider: str,
    *,
    malformed: bool = False,
) -> tuple[Any, Any]:
    client: Any
    if provider == "deepseek":
        client = FakeAnthropicSearchClient(malformed=malformed)
        return (
            DeepSeekAdapter(_settings(provider), client=object(), search_client=client),
            client,
        )
    if provider == "claude":
        client = FakeAnthropicSearchClient(malformed=malformed)
        return ClaudeAdapter(_settings(provider), client=client), client
    if provider == "openai":
        client = FakeOpenAISearchClient(malformed=malformed)
        return OpenAIAdapter(_settings(provider), client=client), client
    if provider == "gemini":
        client = FakeGeminiSearchClient(malformed=malformed)
        return GeminiAdapter(_settings(provider), client=client), client
    raise AssertionError(f"unsupported fixture provider: {provider}")


@pytest.mark.parametrize("provider", ["deepseek", "claude", "openai", "gemini"])
def test_each_provider_normalizes_native_search_results(provider: str) -> None:
    adapter, _ = make_search_adapter(provider)

    response = adapter.search_web(SearchRequest("recent AI news", max_results=3))

    assert response.results == (VALID_RESULT,)
    assert response.provider == provider
    assert response.model == f"{provider}-fixture-model"


@pytest.mark.parametrize("provider", ["deepseek", "claude"])
def test_anthropic_compatible_search_uses_server_web_search_tool(provider: str) -> None:
    adapter, client = make_search_adapter(provider)

    adapter.search_web(SearchRequest("recent AI news", max_results=3, max_output_tokens=321))

    assert client.last_request["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
    assert client.last_request["messages"] == [{"role": "user", "content": "recent AI news"}]
    assert client.last_request["max_tokens"] == 321


def test_deepseek_search_builds_anthropic_client_for_supported_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAnthropicSearchClient()
    calls: list[dict[str, Any]] = []

    def fake_anthropic(**kwargs: Any) -> FakeAnthropicSearchClient:
        calls.append(kwargs)
        return client

    monkeypatch.setattr(openai_provider.anthropic, "Anthropic", fake_anthropic)
    adapter = DeepSeekAdapter(_settings("deepseek"), api_key="fixture-key")

    adapter.search_web(SearchRequest("recent AI news"))

    assert calls == [
        {
            "api_key": "fixture-key",
            "base_url": "https://api.deepseek.com/anthropic",
        }
    ]


def test_openai_search_uses_responses_web_search_tool() -> None:
    adapter, client = make_search_adapter("openai")

    adapter.search_web(SearchRequest("recent AI news", max_results=3, max_output_tokens=321))

    assert client.last_request == {
        "model": "openai-fixture-model",
        "input": "recent AI news",
        "tools": [{"type": "web_search"}],
        "max_output_tokens": 321,
    }


def test_gemini_search_uses_google_search_grounding() -> None:
    adapter, client = make_search_adapter("gemini")

    adapter.search_web(SearchRequest("recent AI news", max_results=3, max_output_tokens=321))

    assert client.last_request["contents"] == "recent AI news"
    assert client.last_request["config"] == {
        "tools": [{"google_search": {}}],
        "max_output_tokens": 321,
    }


@dataclass
class FakeAdapter:
    name: str
    search_results: list[dict[str, str]] = field(default_factory=lambda: [VALID_RESULT])
    search_error: BaseException | None = None
    calls: list[str] = field(default_factory=list)

    def has_credentials(self) -> bool:
        return True

    def generate_text(self, request: TextRequest) -> LLMResponse:
        raise NotImplementedError

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        raise NotImplementedError

    def search_web(self, request: SearchRequest) -> SearchResponse:
        self.calls.append("search_web")
        if self.search_error is not None:
            raise self.search_error
        return SearchResponse(self.search_results, self.name, f"{self.name}-model")

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        return LLMResponse("", self.name, f"{self.name}-model", FinishReason.COMPLETE)


def test_search_uses_configured_fallback_order() -> None:
    first = FakeAdapter("deepseek", search_error=RateLimited("deepseek"))
    second = FakeAdapter("claude")

    result = ProviderRouter([first, second]).search_web(SearchRequest("query"))

    assert result.provider == "claude"
    assert first.calls == ["search_web"]
    assert second.calls == ["search_web"]


def test_router_rejects_missing_url_before_accepting_search_attempt() -> None:
    records: list[AttemptRecord] = []
    first = FakeAdapter("deepseek", search_results=[{"title": "missing URL"}])
    second = FakeAdapter("claude")

    result = ProviderRouter([first, second], on_attempt=records.append).search_web(SearchRequest("query"))

    assert result.provider == "claude"
    assert records[0].error_category == "invalid_provider_response"


@pytest.mark.parametrize("provider", ["deepseek", "claude", "openai", "gemini"])
def test_malformed_native_search_output_falls_back(provider: str) -> None:
    malformed, _ = make_search_adapter(provider, malformed=True)
    replacement = FakeAdapter("claude")

    result = ProviderRouter([malformed, replacement]).search_web(SearchRequest("query"))

    assert result.provider == "claude"


def test_gemini_search_text_property_failure_is_invalid_provider_response() -> None:
    class BlockedGeminiResponse:
        candidates = [SimpleNamespace(grounding_metadata=None)]

        @property
        def text(self) -> str:
            raise ValueError("blocked provider response")

    client = FakeGeminiSearchClient()
    client.response = BlockedGeminiResponse()
    adapter = GeminiAdapter(_settings("gemini"), client=client)

    with pytest.raises(InvalidProviderResponse):
        adapter.search_web(SearchRequest("query"))


@pytest.mark.parametrize(
    ("error_code", "expected_error"),
    [
        ("too_many_requests", RateLimited),
        ("unavailable", ProviderUnavailable),
    ],
)
def test_anthropic_sdk_search_error_object_is_normalized(
    error_code: str,
    expected_error: type[BaseException],
) -> None:
    client = FakeAnthropicSearchClient()
    client.response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="web_search_tool_result",
                content=SimpleNamespace(
                    type="web_search_tool_result_error",
                    error_code=error_code,
                ),
            )
        ],
        stop_reason="end_turn",
    )
    adapter = ClaudeAdapter(_settings("claude"), client=client)

    with pytest.raises(expected_error):
        adapter.search_web(SearchRequest("query"))


@pytest.mark.parametrize("text", ["not-json", "{}", "[]", '[{"title":"missing URL"}]'])
def test_malformed_json_search_output_is_invalid_provider_response(text: str) -> None:
    client = FakeAnthropicSearchClient()
    client.response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
    )
    adapter = ClaudeAdapter(_settings("claude"), client=client)

    with pytest.raises(InvalidProviderResponse):
        adapter.search_web(SearchRequest("query"))
