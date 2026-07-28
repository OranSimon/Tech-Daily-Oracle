from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from llm_client import ClaudeLLMClient, TextLLMClient
from prompt_runner import PromptRunner, PromptRunnerError
from pydantic import BaseModel, ValidationError
from web_search_client import ClaudeWebSearchClient

from tech_daily.llm import client as llm_client_module
from tech_daily.llm.contracts import ModelRole
from tech_daily.llm.errors import ProviderExhaustedError
from tech_daily.web_search import client as web_search_client_module


class ExampleSchema(BaseModel):
    name: str
    score: int


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
        auto_continue: bool = False,
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "max_tokens": max_tokens,
                "cache_system": cache_system,
                "auto_continue": auto_continue,
            }
        )
        return self.response


class FakeStructuredLLMClient(FakeLLMClient):
    def __init__(self, response: ExampleSchema) -> None:
        super().__init__("generate_text must not be used")
        self.structured_response = response
        self.structured_calls: list[dict[str, Any]] = []

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[ExampleSchema],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> ExampleSchema:
        self.structured_calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "model": model,
                "max_tokens": max_tokens,
                "cache_system": cache_system,
            }
        )
        return self.structured_response


class ExhaustedStructuredLLMClient(FakeStructuredLLMClient):
    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[ExampleSchema],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> ExampleSchema:
        raise ProviderExhaustedError(
            "generate_structured",
            ["deepseek: invalid_provider_response", "claude: rate_limited"],
        )


def test_fake_llm_client_satisfies_text_compatibility_protocol() -> None:
    fake: TextLLMClient = FakeLLMClient('{"name": "alpha", "score": 1}')

    assert fake.generate_text(system="s", user="u") == '{"name": "alpha", "score": 1}'


def test_claude_llm_client_delegates_to_neutral_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeProviderClient:
        def generate_text(self, **kwargs: Any) -> str:
            calls.append(kwargs)
            return "adapter response"

    monkeypatch.setattr(llm_client_module, "get_default_client", lambda: FakeProviderClient())

    result = ClaudeLLMClient().generate_text(
        system="system",
        user="user",
        model="model",
        max_tokens=17,
        cache_system=False,
        auto_continue=True,
    )

    assert result == "adapter response"
    assert calls == [
        {
            "system": "system",
            "user": "user",
            "role": ModelRole.DEFAULT,
            "max_output_tokens": 17,
            "cache_system": False,
            "auto_continue": True,
        }
    ]


def test_claude_web_search_compatibility_name_delegates_to_neutral_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    response = [{"title": "result", "url": "https://example.com"}]

    class FakeProviderClient:
        def search_web(self, *, prompt: str, max_results: int) -> list[dict[str, Any]]:
            calls.append({"prompt": prompt, "max_results": max_results})
            return response

    monkeypatch.setattr(
        web_search_client_module,
        "get_default_client",
        lambda: FakeProviderClient(),
    )

    result = ClaudeWebSearchClient().search("search prompt", max_uses=2)

    assert result == response
    assert calls == [{"prompt": "search prompt", "max_results": 2}]


def test_prompt_runner_parses_and_validates_plain_json(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    fake = FakeLLMClient('{"name": "alpha", "score": 7}')
    runner = PromptRunner(fake, prompt_root=tmp_path)

    result = runner.run_json(
        prompt_path="example.md",
        payload={"subject": "fixture"},
        schema=ExampleSchema,
        max_tokens=123,
    )

    assert result == ExampleSchema(name="alpha", score=7)
    assert fake.calls[0]["system"] == "System prompt"
    assert fake.calls[0]["user"] == '{"subject": "fixture"}'
    assert fake.calls[0]["max_tokens"] == 123
    assert fake.calls[0]["auto_continue"] is False


def test_prompt_runner_prefers_structured_client_boundary(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    fake = FakeStructuredLLMClient(ExampleSchema(name="alpha", score=7))
    runner = PromptRunner(fake, prompt_root=tmp_path)

    result = runner.run_json(
        prompt_path="example.md",
        payload={"subject": "fixture"},
        schema=ExampleSchema,
        model="deep",
        max_tokens=123,
        cache_system=False,
    )

    assert result == ExampleSchema(name="alpha", score=7)
    assert fake.calls == []
    assert "auto_continue" not in fake.structured_calls[0]
    assert fake.structured_calls == [
        {
            "system": "System prompt",
            "user": '{"subject": "fixture"}',
            "schema": ExampleSchema,
            "model": "deep",
            "max_tokens": 123,
            "cache_system": False,
        }
    ]


def test_prompt_runner_wraps_structured_provider_exhaustion(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    runner = PromptRunner(
        ExhaustedStructuredLLMClient(ExampleSchema(name="unused", score=0)),
        prompt_root=tmp_path,
    )

    with pytest.raises(PromptRunnerError) as raised:
        runner.run_json(prompt_path="example.md", payload={}, schema=ExampleSchema)

    assert raised.value.kind == "provider_exhausted"
    assert "deepseek: invalid_provider_response" in raised.value.message


def test_prompt_runner_generates_text(tmp_path: Path) -> None:
    prompt_path = tmp_path / "daily.md"
    prompt_path.write_text("Daily prompt", encoding="utf-8")
    fake = FakeLLMClient("# Tech Daily Brief\n\n## 1. 今日一句话判断\n")
    runner = PromptRunner(fake, prompt_root=tmp_path)

    result = runner.run_text(
        prompt_path="daily.md",
        payload={"run_date": "2026-07-02"},
        model="fixture-model",
        max_tokens=321,
    )

    assert result.startswith("# Tech Daily Brief")
    assert fake.calls[0]["system"] == "Daily prompt"
    assert fake.calls[0]["user"] == '{"run_date": "2026-07-02"}'
    assert fake.calls[0]["model"] == "fixture-model"
    assert fake.calls[0]["max_tokens"] == 321
    assert fake.calls[0]["auto_continue"] is True


def test_prompt_runner_parses_fenced_json(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    runner = PromptRunner(FakeLLMClient('```json\n{"name": "beta", "score": 8}\n```'), prompt_root=tmp_path)

    result = runner.run_json(prompt_path="example.md", payload={}, schema=ExampleSchema)

    assert result == ExampleSchema(name="beta", score=8)


def test_prompt_runner_returns_structured_error_for_invalid_json(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    runner = PromptRunner(FakeLLMClient("not-json"), prompt_root=tmp_path)

    with pytest.raises(PromptRunnerError) as exc_info:
        runner.run_json(prompt_path="example.md", payload={}, schema=ExampleSchema)

    assert exc_info.value.kind == "json_parse_error"
    assert exc_info.value.raw_response == "not-json"


def test_prompt_runner_returns_structured_error_for_schema_validation(tmp_path: Path) -> None:
    prompt_path = tmp_path / "example.md"
    prompt_path.write_text("System prompt", encoding="utf-8")
    runner = PromptRunner(FakeLLMClient('{"name": "missing score"}'), prompt_root=tmp_path)

    with pytest.raises(PromptRunnerError) as exc_info:
        runner.run_json(prompt_path="example.md", payload={}, schema=ExampleSchema)

    assert exc_info.value.kind == "schema_validation_error"
    assert "score" in exc_info.value.message


def test_prediction_schema_rejects_out_of_range_probability() -> None:
    from llm_schemas import NewPredictionResponse

    with pytest.raises(ValidationError):
        NewPredictionResponse.model_validate(
            {
                "prediction_id": "P20260702-1",
                "created_date": "2026-07-02",
                "prediction": "Fixture",
                "topic_tags": ["ai_models"],
                "companies": ["OpenAI"],
                "time_horizon": "30 days",
                "horizon_date": "2026-08-01",
                "probability": 1.5,
                "evidence": "Fixture",
                "resolution_criteria": "Fixture",
                "falsification_condition": "Fixture",
                "signals_to_monitor": [],
                "confidence": "medium",
            }
        )


def test_market_signal_schema_rejects_invalid_confidence() -> None:
    from llm_schemas import MarketSignalAnalysisResponse

    payload = {
        "date": "2026-07-02",
        "ticker": "NVDA",
        "company": "NVIDIA",
        "time_horizon": "30 days",
        "event_context": [],
        "conclusion": "neutral",
        "conclusion_zh": "中性",
        "reasoning_zh": "fixture",
        "base_case": "fixture",
        "bull_case": "fixture",
        "bear_case": "fixture",
        "buy_observation_point": "fixture",
        "sell_reduce_observation_point": "fixture",
        "invalidation_condition": "fixture",
        "risk_level": "medium",
        "confidence": "certain",
        "signals_to_monitor": [],
        "source_events": [],
    }

    with pytest.raises(ValidationError):
        MarketSignalAnalysisResponse.model_validate(payload)


def test_prediction_update_schema_accepts_prompt_contract_impacts() -> None:
    from llm_schemas import PredictionUpdateResponse

    base_payload = {
        "prediction_id": "P20260702-1",
        "update_date": "2026-07-02",
        "evidence_summary": "Fixture evidence.",
        "probability_before": 0.4,
        "probability_after": 0.5,
        "reasoning": "Fixture reasoning.",
        "source_event_ids": ["event-1"],
        "resolution": {"resolved": False, "resolved_as": None, "resolution_reasoning": None},
    }

    for impact in (
        "strengthens",
        "weakens",
        "neutral",
        "contradicts",
        "resolves_true",
        "resolves_false",
        "needs_more_data",
    ):
        result = PredictionUpdateResponse.model_validate({**base_payload, "impact": impact})
        assert result.impact == impact


def test_prediction_update_schema_rejects_out_of_contract_impact() -> None:
    from llm_schemas import PredictionUpdateResponse

    payload = {
        "prediction_id": "P20260702-1",
        "update_date": "2026-07-02",
        "evidence_summary": "Fixture evidence.",
        "impact": "resolves",
        "probability_before": 0.4,
        "probability_after": 0.5,
        "reasoning": "Fixture reasoning.",
        "source_event_ids": ["event-1"],
        "resolution": {"resolved": False, "resolved_as": None, "resolution_reasoning": None},
    }

    with pytest.raises(ValidationError):
        PredictionUpdateResponse.model_validate(payload)


def test_new_prediction_schema_rejects_medium_high_confidence() -> None:
    from llm_schemas import NewPredictionResponse

    payload = {
        "prediction_id": "P20260702-1",
        "created_date": "2026-07-02",
        "prediction": "Fixture",
        "topic_tags": ["ai_models"],
        "companies": ["OpenAI"],
        "time_horizon": "30 days",
        "horizon_date": "2026-08-01",
        "probability": 0.55,
        "evidence": "Fixture",
        "resolution_criteria": "Fixture",
        "falsification_condition": "Fixture",
        "signals_to_monitor": [],
        "confidence": "medium-high",
    }

    with pytest.raises(ValidationError):
        NewPredictionResponse.model_validate(payload)
