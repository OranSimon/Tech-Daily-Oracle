from __future__ import annotations

from pathlib import Path
from typing import Any

import claude_client
import pytest
from llm_client import ClaudeLLMClient, LLMClient
from prompt_runner import PromptRunner, PromptRunnerError
from pydantic import BaseModel
from web_search_client import ClaudeWebSearchClient


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


def test_fake_llm_client_satisfies_protocol() -> None:
    fake: LLMClient = FakeLLMClient('{"name": "alpha", "score": 1}')

    assert fake.generate_text(system="s", user="u") == '{"name": "alpha", "score": 1}'


def test_claude_llm_client_delegates_to_existing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_claude(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "adapter response"

    monkeypatch.setattr(claude_client, "call_claude", fake_call_claude)

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
            "model": "model",
            "max_tokens": 17,
            "cache_system": False,
            "auto_continue": True,
        }
    ]


def test_claude_web_search_client_delegates_to_existing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    response = [{"title": "result", "url": "https://example.com"}]

    def fake_call_claude_web_search(prompt: str, max_uses: int = 3) -> list[dict[str, Any]]:
        calls.append({"prompt": prompt, "max_uses": max_uses})
        return response

    monkeypatch.setattr(claude_client, "call_claude_web_search", fake_call_claude_web_search)

    result = ClaudeWebSearchClient().search("search prompt", max_uses=2)

    assert result == response
    assert calls == [{"prompt": "search prompt", "max_uses": 2}]


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
