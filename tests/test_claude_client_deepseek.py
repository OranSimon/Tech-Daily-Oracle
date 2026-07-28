from __future__ import annotations

import claude_client

from tech_daily.llm.contracts import ModelRole, TextRequest


class FakeProviderLLMClient:
    def __init__(self) -> None:
        self.last_request: TextRequest | None = None

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        role: ModelRole,
        max_output_tokens: int,
        cache_system: bool,
        auto_continue: bool,
    ) -> str:
        self.last_request = TextRequest(
            system,
            user,
            role=role,
            max_output_tokens=max_output_tokens,
            cache_system=cache_system,
        )
        return "from neutral client"


def test_default_provider_order_prefers_deepseek() -> None:
    assert claude_client.DEFAULT_PROVIDER_ORDER == ["deepseek", "claude", "openai", "gemini"]


def test_legacy_module_has_no_provider_direct_call_helpers(monkeypatch) -> None:
    fake = FakeProviderLLMClient()
    monkeypatch.setattr(claude_client, "get_default_client", lambda: fake)

    result = claude_client.call_claude("system", "user", max_tokens=123)

    assert result == "from neutral client"
    assert fake.last_request == TextRequest("system", "user", max_output_tokens=123)
    assert not hasattr(claude_client, "_call_deepseek_direct")
    assert not hasattr(claude_client, "_call_with_fallback")
