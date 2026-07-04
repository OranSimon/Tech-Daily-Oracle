from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import collect_sources
import pytest
from collectors import arxiv, github, hackernews, huggingface, rss, web_search
from collectors.telemetry import CollectorWarning


class FakeResponse:
    def __init__(self, *, text: str = "", data: Any = None) -> None:
        self.text = text
        self._data = data

    def json(self) -> Any:
        return self._data

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeWebSearchClient:
    def search(self, prompt: str, max_uses: int = 3) -> list[dict[str, Any]]:
        return [
            {
                "title": "Web fixture",
                "url": "https://example.com/web",
                "source": "Example Web",
                "summary": "Web summary",
                "published_at": "2026-07-03",
            }
        ]


def test_rss_collector_builds_raw_events_from_rss_item() -> None:
    xml = """<?xml version="1.0"?>
    <rss><channel><item>
      <title>RSS fixture</title>
      <link>https://example.com/rss</link>
      <pubDate>Fri, 03 Jul 2026 10:00:00 GMT</pubDate>
      <description>RSS summary</description>
    </item></channel></rss>
    """
    client = FakeAsyncClient([FakeResponse(text=xml)])
    feed = {
        "name": "Fixture Feed",
        "url": "https://example.com/feed.xml",
        "source_type": "media",
        "priority": 2,
        "topics": ["ai"],
    }

    events = asyncio.run(rss.fetch_rss(client, feed, datetime(2026, 7, 2, tzinfo=UTC)))

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Fixture Feed"
    assert event.source_type == "rss"
    assert event.raw_title == "RSS fixture"
    assert event.raw_url == "https://example.com/rss"
    assert event.raw_content == "RSS summary"
    assert event.metadata == {"feed_source_type": "media", "priority": 2, "topics": ["ai"]}


def test_rss_collector_retries_transient_fetch_failure() -> None:
    xml = """<?xml version="1.0"?>
    <rss><channel><item>
      <title>RSS retry fixture</title>
      <link>https://example.com/rss-retry</link>
      <pubDate>Fri, 03 Jul 2026 10:00:00 GMT</pubDate>
      <description>RSS retry summary</description>
    </item></channel></rss>
    """
    client = FakeAsyncClient([TimeoutError("temporary timeout"), FakeResponse(text=xml)])
    feed = {"name": "Retry Feed", "url": "https://example.com/feed.xml"}
    warnings: list[CollectorWarning] = []

    events = asyncio.run(rss.fetch_rss(client, feed, datetime(2026, 7, 2, tzinfo=UTC), warnings))

    assert [event.raw_title for event in events] == ["RSS retry fixture"]
    assert len(client.calls) == 2
    assert len(warnings) == 1
    assert "attempt 1/2 failed" in warnings[0].message


def test_hackernews_collector_filters_by_score_and_builds_raw_event() -> None:
    client = FakeAsyncClient(
        [
            FakeResponse(data=[101]),
            FakeResponse(
                data={
                    "type": "story",
                    "score": 150,
                    "title": "HN fixture",
                    "url": "https://example.com/hn",
                    "text": "HN text",
                    "time": 1783072800,
                    "descendants": 12,
                }
            ),
        ]
    )

    events = asyncio.run(hackernews.fetch_hn(client, top_n=1, min_score=100))

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Hacker News"
    assert event.source_type == "hacker_news"
    assert event.raw_title == "HN fixture"
    assert event.raw_url == "https://example.com/hn"
    assert event.metadata["hn_id"] == 101
    assert event.metadata["score"] == 150
    assert event.metadata["comments"] == 12


def test_huggingface_collector_builds_daily_paper_events() -> None:
    client = FakeAsyncClient(
        [
            FakeResponse(
                data=[
                    {
                        "publishedAt": "2026-07-03T10:00:00Z",
                        "upvotes": 42,
                        "paper": {
                            "title": "HF paper fixture",
                            "id": "2607.00001",
                            "summary": "HF summary",
                            "authors": [{"name": "Ada"}],
                        },
                    }
                ]
            )
        ]
    )

    events = asyncio.run(huggingface.fetch_hf_daily_papers(client, hf_token="token"))

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Hugging Face Daily Papers"
    assert event.source_type == "huggingface"
    assert event.raw_title == "HF paper fixture"
    assert event.raw_url == "https://arxiv.org/abs/2607.00001"
    assert event.metadata["authors"] == ["Ada"]
    assert event.metadata["upvotes"] == 42


def test_arxiv_collector_builds_raw_events(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(arxiv.asyncio, "sleep", fake_sleep)
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>arXiv fixture</title>
        <id>https://arxiv.org/abs/2607.00001</id>
        <published>2026-07-03T10:00:00Z</published>
        <summary>arXiv summary</summary>
        <author><name>Ada</name></author>
      </entry>
    </feed>
    """
    client = FakeAsyncClient([FakeResponse(text=xml)])

    events = asyncio.run(arxiv.fetch_arxiv(client, ["cs.AI"], max_per_cat=1, days_back=7))

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "arXiv cs.AI"
    assert event.source_type == "arxiv"
    assert event.raw_title == "arXiv fixture"
    assert event.raw_url == "https://arxiv.org/abs/2607.00001"
    assert event.metadata["category"] == "cs.AI"
    assert event.metadata["arxiv_id"] == "2607.00001"


def test_github_collector_builds_daily_and_weekly_events() -> None:
    repo = {
        "full_name": "example/repo",
        "html_url": "https://github.com/example/repo",
        "description": "GitHub summary",
        "created_at": "2026-07-03T10:00:00Z",
        "owner": {"login": "example"},
        "name": "repo",
        "stargazers_count": 1000,
        "forks_count": 50,
        "language": "Python",
        "topics": ["ai"],
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-07-03T11:00:00Z",
        "open_issues_count": 3,
    }
    weekly_repo = {**repo, "full_name": "example/weekly", "html_url": "https://github.com/example/weekly"}
    client = FakeAsyncClient([FakeResponse(data={"items": [repo]}), FakeResponse(data={"items": [weekly_repo]})])

    events = asyncio.run(github.fetch_github_trending(client, github_token="token", top_n=1))

    assert [event.source_name for event in events] == ["GitHub Trending", "GitHub Weekly Trending"]
    assert events[0].source_type == "github"
    assert events[0].raw_title == "example/repo"
    assert events[0].metadata["stars"] == 1000
    assert events[1].raw_url == "https://github.com/example/weekly"


def test_web_search_collector_builds_events_and_deduplicates_urls() -> None:
    events = web_search.fetch_web_search_sync(
        ["query one", "query two"],
        "2026-07-03",
        FakeWebSearchClient(),
    )

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Example Web"
    assert event.source_type == "rss"
    assert event.raw_title == "Web fixture"
    assert event.metadata["via"] == "web_search"


def test_collect_sources_facade_can_run_with_all_sources_disabled() -> None:
    events = collect_sources.collect_sources(
        {
            "run": {"report_window_hours": 24},
            "sources": {
                "rss": {"enabled": False},
                "hacker_news": {"enabled": False},
                "hugging_face": {"enabled": False},
                "arxiv": {"enabled": False},
                "github_trending": {"enabled": False},
                "web_search": {"enabled": False},
            },
        },
        run_date="2026-07-03",
    )

    assert events == []
