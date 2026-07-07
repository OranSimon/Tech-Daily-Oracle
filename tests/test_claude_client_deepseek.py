from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import claude_client


class FakeOpenAICompatibleClient:
    def __init__(self, *, text: str = "deepseek response", finish_reason: str = "stop") -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._text = text
        self._finish_reason = finish_reason

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=self._finish_reason,
                    message=SimpleNamespace(content=self._text),
                )
            ]
        )


def test_default_provider_order_prefers_deepseek() -> None:
    assert claude_client.DEFAULT_PROVIDER_ORDER == ["deepseek", "claude", "openai", "gemini"]


def test_deepseek_direct_uses_openai_compatible_client(monkeypatch) -> None:
    fake_client = FakeOpenAICompatibleClient()
    monkeypatch.setattr(claude_client, "_deepseek_client", fake_client)

    text, stop_reason = claude_client._call_deepseek_direct(
        "system prompt",
        "user prompt",
        "deepseek-v4-flash",
        123,
    )

    assert text == "deepseek response"
    assert stop_reason == "end_turn"
    assert fake_client.calls == [
        {
            "model": "deepseek-v4-flash",
            "max_tokens": 123,
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
        }
    ]


def test_fallback_uses_deepseek_when_key_is_available(monkeypatch) -> None:
    fake_client = FakeOpenAICompatibleClient(text="from deepseek")
    monkeypatch.setattr(claude_client, "_deepseek_client", fake_client)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        claude_client,
        "_load_provider_config",
        lambda: (
            ["deepseek", "claude", "openai", "gemini"],
            {
                "deepseek": {"default": "deepseek-v4-flash", "fast": "deepseek-v4-flash", "deep": "deepseek-v4-pro"},
                "claude": {"default": "claude-sonnet-4-6", "fast": "claude-haiku", "deep": "claude-opus"},
                "openai": {"default": "gpt-4o", "fast": "gpt-4o-mini", "deep": "o1"},
                "gemini": {"default": "gemini-2.5-flash", "fast": "gemini-2.5-flash-lite", "deep": "gemini-pro"},
            },
        ),
    )

    text, provider, stop_reason = claude_client._call_with_fallback(
        "system",
        "user",
        "claude-sonnet-4-6",
        321,
        True,
    )

    assert text == "from deepseek"
    assert provider == "deepseek"
    assert stop_reason == "end_turn"
    assert fake_client.calls[0]["model"] == "deepseek-v4-flash"


def test_openai_provider_name_and_gpt_alias_share_models(monkeypatch) -> None:
    order, models = claude_client._load_provider_config()

    assert "openai" in order
    assert "openai" in models
    assert models["gpt"] == models["openai"]
