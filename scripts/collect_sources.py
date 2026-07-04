"""Source Collector facade — orchestrate configured per-source collectors."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from collectors import registry as collector_registry
from collectors.base import cutoff_dt
from collectors.registry import CollectorTaskGroup
from collectors.telemetry import CollectorRunResult, CollectorRunStatus, CollectorWarning
from state import RawEvent
from storage import save_collector_telemetry
from web_search_client import WebSearchClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict[str, Any]:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _load_source_registry() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "source_registry.yml")) as f:
        return yaml.safe_load(f)


def _warning_from_exception(exc: BaseException) -> CollectorWarning:
    return CollectorWarning(message=str(exc), exception_type=type(exc).__name__)


def _result_status(record_count: int, warnings: list[CollectorWarning]) -> CollectorRunStatus:
    if not warnings:
        return CollectorRunStatus.SUCCESS
    if record_count > 0:
        return CollectorRunStatus.PARTIAL
    return CollectorRunStatus.FAILED


async def _run_async_collector_group(group: CollectorTaskGroup) -> tuple[list[RawEvent], CollectorRunResult]:
    start = time.perf_counter()
    if group.skipped_reason is not None:
        return [], CollectorRunResult(
            collector_name=group.name,
            status=CollectorRunStatus.SKIPPED,
            duration_seconds=0.0,
            record_count=0,
            warnings=[CollectorWarning(message=group.skipped_reason)],
        )

    results = await asyncio.gather(*group.tasks, return_exceptions=True)
    events: list[RawEvent] = []
    warnings: list[CollectorWarning] = group.warnings if group.warnings is not None else []
    for result in results:
        if isinstance(result, list):
            events.extend(result)
        elif isinstance(result, Exception):
            warning = _warning_from_exception(result)
            warnings.append(warning)
            print(f"  [Collector] Task error: {warning.message}")

    duration = time.perf_counter() - start
    error_message = warnings[0].message if warnings and not events else None
    return events, CollectorRunResult(
        collector_name=group.name,
        status=_result_status(len(events), warnings),
        duration_seconds=duration,
        record_count=len(events),
        warnings=warnings,
        error_message=error_message,
    )


async def _run_web_search_with_telemetry(
    source_cfg: dict[str, Any],
    date_str: str,
    web_search_client: WebSearchClient | None,
) -> tuple[list[RawEvent], CollectorRunResult]:
    if not collector_registry.is_web_search_enabled(source_cfg):
        return [], CollectorRunResult(
            collector_name=collector_registry.WEB_SEARCH_COLLECTOR.name,
            status=CollectorRunStatus.SKIPPED,
            duration_seconds=0.0,
            record_count=0,
            warnings=[CollectorWarning(message="disabled")],
        )

    start = time.perf_counter()
    warnings: list[CollectorWarning] = []
    try:
        events = await asyncio.to_thread(
            collector_registry.run_web_search_collector,
            source_cfg=source_cfg,
            date_str=date_str,
            web_search_client=web_search_client,
            warnings=warnings,
        )
    except Exception as exc:
        warning = _warning_from_exception(exc)
        warnings.append(warning)
        events = []
        print(f"  [Collector] Task error: {warning.message}")

    duration = time.perf_counter() - start
    error_message = warnings[0].message if warnings and not events else None
    return events, CollectorRunResult(
        collector_name=collector_registry.WEB_SEARCH_COLLECTOR.name,
        status=_result_status(len(events), warnings),
        duration_seconds=duration,
        record_count=len(events),
        warnings=warnings,
        error_message=error_message,
    )


async def collect_all(
    config: dict[str, Any],
    run_date: str = "",
    web_search_client: WebSearchClient | None = None,
) -> list[RawEvent]:
    events, _telemetry = await collect_all_with_telemetry(config, run_date, web_search_client)
    return events


async def collect_all_with_telemetry(
    config: dict[str, Any],
    run_date: str = "",
    web_search_client: WebSearchClient | None = None,
    *,
    persist_telemetry: bool = False,
    run_id: str = "",
) -> tuple[list[RawEvent], list[CollectorRunResult]]:
    source_cfg = config.get("sources", {})
    window_hours = config.get("run", {}).get("report_window_hours", 24)
    cutoff = cutoff_dt(window_hours)
    date_str = run_date or datetime.now(UTC).strftime("%Y-%m-%d")

    github_token = os.environ.get("GITHUB_TOKEN")
    hf_token = os.environ.get("HF_TOKEN")

    registry = _load_source_registry()
    all_events: list[RawEvent] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": f"TechDailyAgent/1.0 ({os.environ.get('SEC_USER_EMAIL', '')})"},
        follow_redirects=True,
    ) as client:
        task_groups = collector_registry.build_async_collector_task_groups(
            source_cfg=source_cfg,
            source_registry=registry,
            client=client,
            cutoff=cutoff,
            github_token=github_token,
            hf_token=hf_token,
        )
        async_results = await asyncio.gather(*[_run_async_collector_group(group) for group in task_groups])

    telemetry: list[CollectorRunResult] = []
    for events, result in async_results:
        all_events.extend(events)
        telemetry.append(result)

    # Web search runs after async tasks (synchronous, uses the WebSearchClient boundary)
    web_events, web_result = await _run_web_search_with_telemetry(source_cfg, date_str, web_search_client)
    all_events.extend(web_events)
    telemetry.append(web_result)

    print(f"  [Collector] Fetched {len(all_events)} raw events total")
    if persist_telemetry:
        try:
            save_collector_telemetry(run_date=date_str, results=telemetry, run_id=run_id)
        except Exception as exc:
            print(f"  [Collector] Failed to save collector telemetry (non-fatal): {exc}")
    return all_events, telemetry


def collect_sources(
    config: dict[str, Any],
    run_date: str = "",
    web_search_client: WebSearchClient | None = None,
) -> list[RawEvent]:
    """Synchronous entry point."""
    return asyncio.run(collect_all(config, run_date, web_search_client))


def collect_sources_with_telemetry(
    config: dict[str, Any],
    run_date: str = "",
    web_search_client: WebSearchClient | None = None,
    *,
    persist_telemetry: bool = False,
    run_id: str = "",
) -> tuple[list[RawEvent], list[CollectorRunResult]]:
    """Synchronous entry point that also returns per-collector telemetry."""
    return asyncio.run(
        collect_all_with_telemetry(
            config,
            run_date,
            web_search_client,
            persist_telemetry=persist_telemetry,
            run_id=run_id,
        )
    )


if __name__ == "__main__":
    cfg = _load_config()
    events = collect_sources(cfg)
    print(
        json.dumps(
            [{"title": e.raw_title, "source": e.source_name, "url": e.raw_url} for e in events],
            indent=2,
            ensure_ascii=False,
        )
    )
