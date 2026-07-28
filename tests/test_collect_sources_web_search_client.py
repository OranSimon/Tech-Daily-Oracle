from __future__ import annotations

from typing import Any

import collect_sources
import pytest
from collectors import web_search

from tech_daily.llm.errors import ProviderExhaustedError


class FakeWebSearchClient:
    def __init__(self, response: list[dict[str, Any]] | BaseException) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        prompt: str,
        max_uses: int = 3,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"prompt": prompt, "max_uses": max_uses})
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def _web_search_only_config() -> dict[str, Any]:
    return {
        "run": {"report_window_hours": 24},
        "sources": {
            "rss": {"enabled": False},
            "hacker_news": {"enabled": False},
            "hugging_face": {"enabled": False},
            "arxiv": {"enabled": False},
            "github_trending": {"enabled": False},
            "web_search": {"enabled": True, "queries_per_run": 1},
        },
    }


def test_collect_sources_uses_fake_web_search_client_for_source_events() -> None:
    fake = FakeWebSearchClient(
        [
            {
                "title": "Example AI release",
                "url": "https://example.com/ai-release",
                "source": "Example News",
                "summary": "A concise fixture summary.",
                "published_at": "2026-07-03",
            },
            {
                "title": "",
                "url": "https://example.com/ignored",
                "source": "Example News",
                "summary": "Missing title should be ignored.",
                "published_at": "2026-07-03",
            },
        ]
    )

    events = collect_sources.collect_sources(
        _web_search_only_config(),
        run_date="2026-07-03",
        web_search_client=fake,
    )

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Example News"
    assert event.source_type == "rss"
    assert event.raw_title == "Example AI release"
    assert event.raw_url == "https://example.com/ai-release"
    assert event.raw_content == "A concise fixture summary."
    assert event.published_at == "2026-07-03"
    assert event.metadata == {
        "priority": 3,
        "feed_source_type": "media",
        "via": "web_search",
        "query": "major AI model releases or announcements in the last 24 hours",
    }
    assert fake.calls[0]["max_uses"] == 3
    assert "Date: 2026-07-03" in fake.calls[0]["prompt"]


def test_collect_sources_continues_when_web_search_client_fails() -> None:
    fake = FakeWebSearchClient(
        ProviderExhaustedError(
            "search_web",
            ["deepseek: provider_unavailable"],
        )
    )

    events = collect_sources.collect_sources(
        _web_search_only_config(),
        run_date="2026-07-03",
        web_search_client=fake,
    )

    assert events == []
    assert len(fake.calls) == 2


def test_web_search_collector_propagates_type_error_without_retry() -> None:
    fake = FakeWebSearchClient(TypeError("collector programming defect"))

    with pytest.raises(TypeError, match="collector programming defect"):
        web_search.web_search_query_to_events(
            "query",
            "2026-07-27",
            fake,
        )

    assert len(fake.calls) == 1


def test_collector_defaults_to_neutral_web_search_client(monkeypatch) -> None:
    response = [
        {
            "title": "Neutral result",
            "url": "https://example.com/neutral",
            "source": "Example",
            "summary": "Summary",
            "published_at": "2026-07-27",
        }
    ]

    class DefaultFakeWebSearchClient(FakeWebSearchClient):
        def __init__(self) -> None:
            super().__init__(response)

    monkeypatch.setattr(web_search, "ProviderWebSearchClient", DefaultFakeWebSearchClient)

    events = web_search.fetch_web_search_sync(["q"], "2026-07-27")

    assert [event.raw_url for event in events] == ["https://example.com/neutral"]
