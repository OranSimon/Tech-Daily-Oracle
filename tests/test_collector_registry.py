from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import collect_sources
import collectors.registry as registry
from state import RawEvent


class FakeAsyncClient:
    pass


class FakeWebSearchClient:
    pass


def _event(source_name: str, source_type: str = "rss") -> RawEvent:
    return RawEvent(
        source_name=source_name,
        source_type=source_type,
        raw_title=f"{source_name} title",
        raw_url=f"https://example.com/{source_name}",
        raw_content=f"{source_name} content",
        published_at="2026-07-03",
        fetched_at=datetime(2026, 7, 3, tzinfo=UTC).isoformat(),
        metadata={},
    )


async def _run_tasks(tasks: list[Any]) -> list[list[RawEvent]]:
    return await asyncio.gather(*tasks)


def test_registry_declares_existing_collectors_in_expected_order() -> None:
    assert [collector.name for collector in registry.ASYNC_COLLECTORS] == [
        "rss",
        "hacker_news",
        "hugging_face",
        "arxiv",
        "github_trending",
    ]
    assert registry.WEB_SEARCH_COLLECTOR.name == "web_search"


def test_registry_builds_async_tasks_from_config_defaults(monkeypatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_collect(name: str, *args: Any) -> list[RawEvent]:
        calls.append((name, args))
        return [_event(name)]

    monkeypatch.setattr(registry, "fetch_rss", lambda *args: fake_collect("rss", *args))
    monkeypatch.setattr(registry, "fetch_hn", lambda *args: fake_collect("hacker_news", *args))
    monkeypatch.setattr(registry, "fetch_hf_daily_papers", lambda *args: fake_collect("hugging_face", *args))
    monkeypatch.setattr(registry, "fetch_arxiv", lambda *args: fake_collect("arxiv", *args))
    monkeypatch.setattr(registry, "fetch_github_trending", lambda *args: fake_collect("github_trending", *args))

    tasks = registry.build_async_collector_tasks(
        source_cfg={},
        source_registry={"rss_feeds": [{"name": "Feed", "url": "https://example.com/feed.xml"}]},
        client=FakeAsyncClient(),
        cutoff=datetime(2026, 7, 2, tzinfo=UTC),
        github_token="gh-token",
        hf_token="hf-token",
    )
    results = asyncio.run(_run_tasks(tasks))

    assert [event.source_name for events in results for event in events] == [
        "rss",
        "hacker_news",
        "hugging_face",
        "arxiv",
        "github_trending",
    ]
    hn_call = next(args for name, args in calls if name == "hacker_news")
    assert hn_call[-3:-1] == (50, 100)
    arxiv_call = next(args for name, args in calls if name == "arxiv")
    assert arxiv_call[-4:-1] == (["cs.AI", "cs.LG", "cs.RO", "cs.CV", "cs.CL"], 20, 2)
    github_call = next(args for name, args in calls if name == "github_trending")
    assert github_call[-3:-1] == ("gh-token", 25)


def test_registry_respects_disabled_and_nested_collector_config(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_collect(name: str, *args: Any) -> list[RawEvent]:
        calls.append(name)
        return [_event(name)]

    monkeypatch.setattr(registry, "fetch_rss", lambda *args: fake_collect("rss", *args))
    monkeypatch.setattr(registry, "fetch_hn", lambda *args: fake_collect("hacker_news", *args))
    monkeypatch.setattr(registry, "fetch_hf_daily_papers", lambda *args: fake_collect("hugging_face", *args))
    monkeypatch.setattr(registry, "fetch_arxiv", lambda *args: fake_collect("arxiv", *args))
    monkeypatch.setattr(registry, "fetch_github_trending", lambda *args: fake_collect("github_trending", *args))

    tasks = registry.build_async_collector_tasks(
        source_cfg={
            "rss": {"enabled": False},
            "hacker_news": {"enabled": False},
            "hugging_face": {"enabled": True, "daily_papers": False},
            "arxiv": {"enabled": False},
            "github_trending": {"enabled": False},
        },
        source_registry={"rss_feeds": [{"name": "Feed", "url": "https://example.com/feed.xml"}]},
        client=FakeAsyncClient(),
        cutoff=datetime(2026, 7, 2, tzinfo=UTC),
        github_token=None,
        hf_token=None,
    )

    assert tasks == []
    assert calls == []


def test_registry_web_search_uses_query_limit_and_fake_client(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_fetch_web_search_sync(queries: list[str], date_str: str, web_search_client: Any) -> list[RawEvent]:
        calls.append({"queries": queries, "date_str": date_str, "web_search_client": web_search_client})
        return [_event("web", source_type="rss")]

    monkeypatch.setattr(registry, "fetch_web_search_sync", fake_fetch_web_search_sync)
    fake_client = FakeWebSearchClient()

    events = registry.run_web_search_collector(
        source_cfg={"web_search": {"enabled": True, "queries_per_run": 2}},
        date_str="2026-07-03",
        web_search_client=fake_client,
    )

    assert [event.source_name for event in events] == ["web"]
    assert len(calls[0]["queries"]) == 2
    assert calls[0]["date_str"] == "2026-07-03"
    assert calls[0]["web_search_client"] is fake_client


def test_collect_all_uses_registry_for_async_and_web_collectors(monkeypatch) -> None:
    async def fake_async_event() -> list[RawEvent]:
        return [_event("async")]

    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [registry.CollectorTaskGroup(name="async", tasks=[fake_async_event()])],
    )
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "run_web_search_collector",
        lambda **kwargs: [_event("web")],
    )

    events = asyncio.run(
        collect_sources.collect_all(
            {"run": {"report_window_hours": 24}, "sources": {"web_search": {"enabled": True}}},
            run_date="2026-07-03",
            web_search_client=FakeWebSearchClient(),
        )
    )

    assert [event.source_name for event in events] == ["async", "web"]
