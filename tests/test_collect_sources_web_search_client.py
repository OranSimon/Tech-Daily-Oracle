from __future__ import annotations

from typing import Any

import collect_sources


class FakeWebSearchClient:
    def __init__(self, response: list[dict[str, Any]] | BaseException) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def search(self, prompt: str, max_uses: int = 3) -> list[dict[str, Any]]:
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
    fake = FakeWebSearchClient(RuntimeError("search unavailable"))

    events = collect_sources.collect_sources(
        _web_search_only_config(),
        run_date="2026-07-03",
        web_search_client=fake,
    )

    assert events == []
