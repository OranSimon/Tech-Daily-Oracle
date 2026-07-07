from __future__ import annotations

import sys
from types import ModuleType


class FakeClaudeClientModule(ModuleType):
    call_claude_web_search: object


def test_package_claude_web_search_client_delegates_to_legacy_function(monkeypatch) -> None:
    from tech_daily.web_search.client import ClaudeWebSearchClient

    fake_legacy = FakeClaudeClientModule("claude_client")

    def fake_call_claude_web_search(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
        assert query == "AI infrastructure news"
        assert max_results == 3
        return [{"title": "Fixture", "url": "https://example.com", "snippet": "Result"}]

    fake_legacy.call_claude_web_search = fake_call_claude_web_search
    monkeypatch.setitem(sys.modules, "claude_client", fake_legacy)

    result = ClaudeWebSearchClient().search("AI infrastructure news", max_results=3)

    assert result == [{"title": "Fixture", "url": "https://example.com", "snippet": "Result"}]


def test_package_claude_web_search_client_uses_legacy_default_max_uses(monkeypatch) -> None:
    from tech_daily.web_search.client import ClaudeWebSearchClient

    fake_legacy = FakeClaudeClientModule("claude_client")
    calls: list[dict[str, int | str]] = []

    def fake_call_claude_web_search(prompt: str, max_uses: int = 3) -> list[dict[str, str]]:
        calls.append({"prompt": prompt, "max_uses": max_uses})
        return [{"title": "Fixture"}]

    fake_legacy.call_claude_web_search = fake_call_claude_web_search
    monkeypatch.setitem(sys.modules, "claude_client", fake_legacy)

    result = ClaudeWebSearchClient().search("fixture")

    assert result == [{"title": "Fixture"}]
    assert calls == [{"prompt": "fixture", "max_uses": 3}]


def test_package_claude_web_search_client_accepts_legacy_prompt_keyword(monkeypatch) -> None:
    from tech_daily.web_search.client import ClaudeWebSearchClient

    fake_legacy = FakeClaudeClientModule("claude_client")
    calls: list[dict[str, int | str]] = []

    def fake_call_claude_web_search(prompt: str, max_uses: int = 3) -> list[dict[str, str]]:
        calls.append({"prompt": prompt, "max_uses": max_uses})
        return [{"title": "Fixture"}]

    fake_legacy.call_claude_web_search = fake_call_claude_web_search
    monkeypatch.setitem(sys.modules, "claude_client", fake_legacy)

    result = ClaudeWebSearchClient().search(prompt="fixture", max_uses=3)

    assert result == [{"title": "Fixture"}]
    assert calls == [{"prompt": "fixture", "max_uses": 3}]


def test_script_web_search_client_reexports_package_classes() -> None:
    from web_search_client import ClaudeWebSearchClient as ScriptClaudeWebSearchClient
    from web_search_client import WebSearchClient as ScriptWebSearchClient

    from tech_daily.web_search.client import ClaudeWebSearchClient, WebSearchClient

    assert ScriptClaudeWebSearchClient is ClaudeWebSearchClient
    assert ScriptWebSearchClient is WebSearchClient
