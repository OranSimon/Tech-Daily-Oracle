from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import collect_sources
from collectors.registry import CollectorTaskGroup
from collectors.telemetry import CollectorRunStatus
from state import RawEvent


def _event(source_name: str) -> RawEvent:
    return RawEvent(
        source_name=source_name,
        source_type="rss",
        raw_title=f"{source_name} title",
        raw_url=f"https://example.com/{source_name}",
        raw_content=f"{source_name} content",
        published_at="2026-07-03",
        fetched_at=datetime(2026, 7, 3, tzinfo=UTC).isoformat(),
        metadata={},
    )


async def _successful_events(*events: RawEvent) -> list[RawEvent]:
    return list(events)


async def _failing_events() -> list[RawEvent]:
    raise RuntimeError("collector exploded")


class FailingWebSearchClient:
    def search(self, prompt: str, max_uses: int = 3) -> list[dict]:
        raise RuntimeError("search unavailable")


def _config_with_only_web_search(enabled: bool) -> dict:
    return {
        "run": {"report_window_hours": 24},
        "sources": {
            "rss": {"enabled": False},
            "hacker_news": {"enabled": False},
            "hugging_face": {"enabled": False},
            "arxiv": {"enabled": False},
            "github_trending": {"enabled": False},
            "web_search": {"enabled": enabled, "queries_per_run": 1},
        },
    }


def test_collect_all_with_telemetry_records_success_and_skipped(monkeypatch) -> None:
    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [
            CollectorTaskGroup(
                name="fixture",
                tasks=[_successful_events(_event("one"), _event("two"))],
            )
        ],
    )

    events, telemetry = asyncio.run(
        collect_sources.collect_all_with_telemetry(
            _config_with_only_web_search(enabled=False),
            run_date="2026-07-03",
        )
    )

    assert [event.source_name for event in events] == ["one", "two"]
    fixture = next(result for result in telemetry if result.collector_name == "fixture")
    assert fixture.status is CollectorRunStatus.SUCCESS
    assert fixture.record_count == 2
    assert fixture.duration_seconds >= 0
    assert fixture.warnings == []
    web = next(result for result in telemetry if result.collector_name == "web_search")
    assert web.status is CollectorRunStatus.SKIPPED
    assert web.record_count == 0


def test_collect_all_with_telemetry_records_failed_collector_without_breaking_others(monkeypatch) -> None:
    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [
            CollectorTaskGroup(name="bad", tasks=[_failing_events()]),
            CollectorTaskGroup(name="good", tasks=[_successful_events(_event("good"))]),
        ],
    )

    events, telemetry = asyncio.run(
        collect_sources.collect_all_with_telemetry(
            _config_with_only_web_search(enabled=False),
            run_date="2026-07-03",
        )
    )

    assert [event.source_name for event in events] == ["good"]
    bad = next(result for result in telemetry if result.collector_name == "bad")
    assert bad.status is CollectorRunStatus.FAILED
    assert bad.record_count == 0
    assert "collector exploded" in (bad.error_message or "")
    good = next(result for result in telemetry if result.collector_name == "good")
    assert good.status is CollectorRunStatus.SUCCESS


def test_collect_all_with_telemetry_captures_web_search_failure() -> None:
    events, telemetry = asyncio.run(
        collect_sources.collect_all_with_telemetry(
            _config_with_only_web_search(enabled=True),
            run_date="2026-07-03",
            web_search_client=FailingWebSearchClient(),
        )
    )

    assert events == []
    web = next(result for result in telemetry if result.collector_name == "web_search")
    assert web.status is CollectorRunStatus.FAILED
    assert web.record_count == 0
    assert web.warnings
    assert "search unavailable" in (web.error_message or "")


def test_existing_collect_all_return_value_remains_events_only(monkeypatch) -> None:
    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [CollectorTaskGroup(name="fixture", tasks=[_successful_events(_event("only"))])],
    )

    events = asyncio.run(
        collect_sources.collect_all(
            _config_with_only_web_search(enabled=False),
            run_date="2026-07-03",
        )
    )

    assert [event.source_name for event in events] == ["only"]
