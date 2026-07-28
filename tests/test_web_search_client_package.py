from __future__ import annotations

from typing import Any

from tech_daily.llm import client as llm_client_module
from tech_daily.web_search import client as client_module


class FakeProviderClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search_web(self, *, prompt: str, max_results: int) -> list[dict[str, Any]]:
        self.calls.append({"prompt": prompt, "max_results": max_results})
        return [{"title": "Fixture", "url": "https://example.com"}]


def test_provider_web_search_client_delegates_to_neutral_default(monkeypatch) -> None:
    fake = FakeProviderClient()
    monkeypatch.setattr(client_module, "get_default_client", lambda: fake)

    result = client_module.ProviderWebSearchClient().search(
        "AI infrastructure news",
        max_results=3,
    )

    assert result == [{"title": "Fixture", "url": "https://example.com"}]
    assert fake.calls == [{"prompt": "AI infrastructure news", "max_results": 3}]


def test_provider_web_search_client_uses_canonical_llm_singleton(monkeypatch) -> None:
    fake = FakeProviderClient()

    def unexpected_local_config_load() -> None:
        raise AssertionError("web-search boundary must not build a second router")

    monkeypatch.setattr(llm_client_module, "get_default_client", lambda: fake)
    monkeypatch.setattr(client_module, "_default_client", None, raising=False)
    monkeypatch.setattr(client_module, "load_llm_settings", unexpected_local_config_load, raising=False)

    result = client_module.ProviderWebSearchClient().search("canonical query", max_results=4)

    assert result == [{"title": "Fixture", "url": "https://example.com"}]
    assert fake.calls == [{"prompt": "canonical query", "max_results": 4}]


def test_provider_web_search_client_preserves_max_uses_default(monkeypatch) -> None:
    fake = FakeProviderClient()
    monkeypatch.setattr(client_module, "get_default_client", lambda: fake)

    client_module.ProviderWebSearchClient().search(prompt="fixture", max_uses=2)

    assert fake.calls == [{"prompt": "fixture", "max_results": 2}]


def test_claude_web_search_client_is_neutral_compatibility_name() -> None:
    assert issubclass(client_module.ClaudeWebSearchClient, client_module.ProviderWebSearchClient)


def test_script_web_search_client_reexports_package_classes() -> None:
    from web_search_client import ClaudeWebSearchClient as ScriptClaudeWebSearchClient
    from web_search_client import ProviderWebSearchClient as ScriptProviderWebSearchClient
    from web_search_client import WebSearchClient as ScriptWebSearchClient

    from tech_daily.web_search.client import (
        ClaudeWebSearchClient,
        ProviderWebSearchClient,
        WebSearchClient,
    )

    assert ScriptClaudeWebSearchClient is ClaudeWebSearchClient
    assert ScriptProviderWebSearchClient is ProviderWebSearchClient
    assert ScriptWebSearchClient is WebSearchClient
