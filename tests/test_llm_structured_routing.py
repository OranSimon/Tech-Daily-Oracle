from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import BaseModel

from tech_daily.llm.client import ClaudeLLMClient, ProviderLLMClient
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
from tech_daily.llm.errors import InvalidProviderResponse, ProviderExhaustedError
from tech_daily.llm.providers import ClaudeAdapter, DeepSeekAdapter, GeminiAdapter, OpenAIAdapter
from tech_daily.llm.router import AttemptRecord, ProviderRouter
from tech_daily.llm.schemas import TrendingAnalysisResponse


class ExampleSchema(BaseModel):
    name: str
    score: int


@dataclass
class FakeAdapter:
    name: str
    structured_text: str
    calls: list[str] = field(default_factory=list)

    def has_credentials(self) -> bool:
        return True

    def generate_text(self, request: TextRequest) -> LLMResponse:
        raise NotImplementedError

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        self.calls.append("generate_structured")
        return LLMResponse(
            text=self.structured_text,
            provider=self.name,
            model=f"{self.name}-model",
            finish_reason=FinishReason.COMPLETE,
        )

    def search_web(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        raise NotImplementedError


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.last_request: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create)

    def _create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, str]],
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        self.last_request = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "extra_body": extra_body,
        }
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"name":"ok","score":1}')],
            stop_reason="end_turn",
        )


class FakeOpenAICompatibleClient:
    def __init__(self, response_text: str = '{"name":"ok","score":1}') -> None:
        self.last_request: dict[str, Any] = {}
        self.response_text = response_text
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=self.response_text,
                        refusal=None,
                    ),
                )
            ]
        )


class FakeGeminiClient:
    def __init__(self) -> None:
        self.last_request: dict[str, Any] = {}
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        return SimpleNamespace(
            text='{"name":"ok","score":1}',
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )


def _settings(name: str) -> ProviderSettings:
    model = f"{name}-fixture-model"
    return ProviderSettings(name, {role: model for role in ModelRole})


def _request() -> StructuredRequest:
    return StructuredRequest(
        "system",
        "user",
        json_schema=ExampleSchema.model_json_schema(),
        max_output_tokens=321,
    )


def test_malformed_json_falls_back_before_returning() -> None:
    deepseek = FakeAdapter("deepseek", structured_text="not-json")
    claude = FakeAdapter("claude", structured_text='{"name":"ok","score":9}')

    result = ProviderRouter([deepseek, claude]).generate_structured(_request(), ExampleSchema)

    assert result == ExampleSchema(name="ok", score=9)
    assert deepseek.calls == ["generate_structured"]
    assert claude.calls == ["generate_structured"]


def test_schema_mismatch_is_invalid_provider_response() -> None:
    records: list[AttemptRecord] = []
    first = FakeAdapter("deepseek", structured_text='{"name":"missing score"}')
    second = FakeAdapter("claude", structured_text='{"name":"ok","score":2}')

    result = ProviderRouter([first, second], on_attempt=records.append).generate_structured(
        _request(),
        ExampleSchema,
    )

    assert result.score == 2
    assert records[0].error_category == "invalid_provider_response"
    assert records[1].outcome == "success"


def test_deepseek_requests_json_mode_and_includes_schema_in_instructions() -> None:
    client = FakeOpenAICompatibleClient()
    adapter = DeepSeekAdapter(_settings("deepseek"), client=client)

    response = adapter.generate_structured(_request())

    assert response.text == '{"name":"ok","score":1}'
    assert client.last_request["response_format"] == {"type": "json_object"}
    assert '"score"' in client.last_request["messages"][0]["content"]
    assert '"integer"' in client.last_request["messages"][0]["content"]
    assert '"structured_output"' not in client.last_request["messages"][0]["content"]


def test_deepseek_wraps_root_array_schema_and_unwraps_provider_object() -> None:
    items = [
        {
            "item_id": "trend-1",
            "why_trending": "Rapid adoption",
            "what_it_signals": "Growing demand",
            "topics": ["AI"],
            "hype_risk": "medium",
            "report_snippet": "Adoption accelerated.",
        }
    ]
    client = FakeOpenAICompatibleClient(json.dumps({"structured_output": items}))
    adapter = DeepSeekAdapter(_settings("deepseek"), client=client)
    array_schema = TrendingAnalysisResponse.model_json_schema()
    request = StructuredRequest(
        "system",
        "user",
        json_schema=array_schema,
    )

    response = adapter.generate_structured(request)

    provider_schema = json.loads(
        client.last_request["messages"][0]["content"].split(
            "Return only one valid JSON object matching this JSON Schema:\n",
            maxsplit=1,
        )[1]
    )
    assert provider_schema == {
        "$defs": array_schema["$defs"],
        "type": "object",
        "properties": {"structured_output": {key: value for key, value in array_schema.items() if key != "$defs"}},
        "required": ["structured_output"],
        "additionalProperties": False,
    }
    assert json.loads(response.text) == items
    assert response.provider == "deepseek"
    assert response.model == "deepseek-fixture-model"


@pytest.mark.parametrize(
    "response_text",
    [
        "not-json",
        "[]",
        '{"wrong_key":[]}',
        '{"structured_output":"not-an-array"}',
        '{"structured_output":[],"unexpected":true}',
    ],
)
def test_deepseek_rejects_malformed_root_array_envelopes(response_text: str) -> None:
    client = FakeOpenAICompatibleClient(response_text)
    adapter = DeepSeekAdapter(_settings("deepseek"), client=client)
    request = StructuredRequest(
        "system",
        "user",
        json_schema=TrendingAnalysisResponse.model_json_schema(),
    )

    with pytest.raises(InvalidProviderResponse):
        adapter.generate_structured(request)


def test_provider_client_routes_real_root_model_array_through_deepseek() -> None:
    items = [
        {
            "item_id": "trend-1",
            "why_trending": "Rapid adoption",
            "what_it_signals": "Growing demand",
            "topics": ["AI"],
            "hype_risk": "medium",
            "report_snippet": "Adoption accelerated.",
        }
    ]
    client = FakeOpenAICompatibleClient(json.dumps({"structured_output": items}))
    adapter = DeepSeekAdapter(_settings("deepseek"), client=client)
    provider_client = ProviderLLMClient(router=ProviderRouter([adapter]))

    result = provider_client.generate_structured(
        system="system",
        user="user",
        schema=TrendingAnalysisResponse,
    )

    assert isinstance(result, TrendingAnalysisResponse)
    assert [item.item_id for item in result.root] == ["trend-1"]


def test_claude_uses_minimum_sdk_extra_body_for_json_schema_output() -> None:
    client = FakeAnthropicClient()
    adapter = ClaudeAdapter(_settings("claude"), client=client)

    response = adapter.generate_structured(_request())

    assert response.text == '{"name":"ok","score":1}'
    assert client.last_request["extra_body"] == {
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": ExampleSchema.model_json_schema(),
            }
        }
    }


def test_openai_requests_strict_json_schema_output() -> None:
    client = FakeOpenAICompatibleClient()
    adapter = OpenAIAdapter(_settings("openai"), client=client)

    response = adapter.generate_structured(_request())

    assert response.text == '{"name":"ok","score":1}'
    assert client.last_request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "strict": True,
            "schema": ExampleSchema.model_json_schema(),
        },
    }


def test_gemini_requests_json_schema_output() -> None:
    client = FakeGeminiClient()
    adapter = GeminiAdapter(_settings("gemini"), client=client)

    response = adapter.generate_structured(_request())

    assert response.text == '{"name":"ok","score":1}'
    assert client.last_request["config"]["response_mime_type"] == "application/json"
    assert client.last_request["config"]["response_json_schema"] == ExampleSchema.model_json_schema()


def test_production_client_routes_structured_requests_through_provider_router() -> None:
    class FakeRouter:
        def __init__(self) -> None:
            self.request: StructuredRequest | None = None
            self.schema: type[BaseModel] | None = None

        def generate_structured(
            self,
            request: StructuredRequest,
            schema: type[ExampleSchema],
        ) -> ExampleSchema:
            self.request = request
            self.schema = schema
            return ExampleSchema(name="ok", score=4)

    router = FakeRouter()

    result = ClaudeLLMClient(router=cast(ProviderRouter, router)).generate_structured(
        system="system",
        user="user",
        schema=ExampleSchema,
        model="deep",
        max_tokens=321,
        cache_system=False,
    )

    assert result == ExampleSchema(name="ok", score=4)
    assert router.schema is ExampleSchema
    assert router.request == StructuredRequest(
        "system",
        "user",
        ExampleSchema.model_json_schema(),
        role=ModelRole.DEEP,
        max_output_tokens=321,
        cache_system=False,
    )


@pytest.mark.parametrize("structured_text", ["", "[]", '{"name":"ok","score":"bad"}'])
def test_invalid_structured_responses_exhaust_safely(structured_text: str) -> None:
    adapter = FakeAdapter("deepseek", structured_text=structured_text)

    with pytest.raises(ProviderExhaustedError) as raised:
        ProviderRouter([adapter]).generate_structured(_request(), ExampleSchema)

    assert "invalid_provider_response" in str(raised.value)
    if structured_text:
        assert structured_text not in str(raised.value)
