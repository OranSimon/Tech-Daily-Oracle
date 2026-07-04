from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import collect_sources
from collectors.registry import CollectorTaskGroup
from collectors.retry import RetryConfig, retry_async, retry_sync
from collectors.telemetry import CollectorRunStatus, CollectorWarning
from state import RawEvent


class TransientCollectorError(RuntimeError):
    pass


class PermanentCollectorError(ValueError):
    pass


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


def test_retry_async_succeeds_after_transient_failure_and_records_warning() -> None:
    attempts = 0
    warnings: list[CollectorWarning] = []

    async def flaky_call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransientCollectorError("temporary outage")
        return "ok"

    result = asyncio.run(
        retry_async(
            flaky_call,
            operation_name="fixture async",
            warnings=warnings,
            config=RetryConfig(max_attempts=2, initial_delay_seconds=0),
        )
    )

    assert result == "ok"
    assert attempts == 2
    assert len(warnings) == 1
    assert "attempt 1/2 failed" in warnings[0].message
    assert warnings[0].exception_type == "TransientCollectorError"


def test_retry_sync_stops_after_max_attempts_and_records_final_warning() -> None:
    attempts = 0
    warnings: list[CollectorWarning] = []

    def failing_call() -> str:
        nonlocal attempts
        attempts += 1
        raise TransientCollectorError("still down")

    try:
        retry_sync(
            failing_call,
            operation_name="fixture sync",
            warnings=warnings,
            config=RetryConfig(max_attempts=2, initial_delay_seconds=0),
        )
    except TransientCollectorError:
        pass
    else:
        raise AssertionError("Expected retry_sync to re-raise final failure")

    assert attempts == 2
    assert len(warnings) == 2
    assert "attempt 2/2 failed" in warnings[-1].message
    assert "giving up" in warnings[-1].message


def test_retry_sync_does_not_retry_non_retryable_errors() -> None:
    attempts = 0
    warnings: list[CollectorWarning] = []

    def invalid_response() -> str:
        nonlocal attempts
        attempts += 1
        raise PermanentCollectorError("bad input")

    try:
        retry_sync(
            invalid_response,
            operation_name="fixture non-retryable",
            warnings=warnings,
            config=RetryConfig(
                max_attempts=3,
                initial_delay_seconds=0,
                retryable=lambda exc: not isinstance(exc, PermanentCollectorError),
            ),
        )
    except PermanentCollectorError:
        pass
    else:
        raise AssertionError("Expected retry_sync to re-raise non-retryable failure")

    assert attempts == 1
    assert len(warnings) == 1
    assert "non-retryable" in warnings[0].message


def test_collector_telemetry_records_successful_retry_warning(monkeypatch) -> None:
    warnings_seen: list[CollectorWarning] = []

    async def retried_collector(warnings: list[CollectorWarning]) -> list[RawEvent]:
        warnings.append(CollectorWarning(message="fixture retry warning", exception_type="TimeoutError"))
        return [_event("retried")]

    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [
            CollectorTaskGroup(
                name="fixture",
                tasks=[retried_collector(warnings_seen)],
                warnings=warnings_seen,
            )
        ],
    )

    events, telemetry = asyncio.run(
        collect_sources.collect_all_with_telemetry(
            {
                "run": {"report_window_hours": 24},
                "sources": {
                    "web_search": {"enabled": False},
                },
            },
            run_date="2026-07-03",
        )
    )

    assert [event.source_name for event in events] == ["retried"]
    result = next(item for item in telemetry if item.collector_name == "fixture")
    assert result.status is CollectorRunStatus.PARTIAL
    assert result.record_count == 1
    assert result.warnings == warnings_seen
