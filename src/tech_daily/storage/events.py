"""Event, trending, and market-signal artifact storage helpers."""

from __future__ import annotations

from typing import Any, Protocol

from tech_daily.pipeline.state import MarketSignalAnalysis, TechDailyState
from tech_daily.storage._shared import (
    ensure_dirs,
    load_jsonl_since,
    read_jsonl_dict_rows,
    safe_dict,
)
from tech_daily.storage._shared import (
    storage_context as resolve_storage_context,
)
from tech_daily.storage.context import StorageContext
from tech_daily.storage.event_payloads import EventStoragePayload
from tech_daily.storage.io import append_jsonl_rows_safely
from tech_daily.storage.validation import StorageDiagnostics


class TrendingItemLike(Protocol):
    item_id: str
    item_type: str
    source: str
    title: str
    rank: int
    velocity_score: float
    language: str | None


class TrendingSnapshotLike(Protocol):
    snapshot_date: str
    period: str
    github_items: list[TrendingItemLike]
    hf_paper_items: list[TrendingItemLike]
    hf_model_items: list[TrendingItemLike]


def append_event_payload(
    payload: EventStoragePayload,
    *,
    storage_context: StorageContext | None = None,
) -> None:
    """Append today's event payload to data log files."""
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)

    events_payload = [
        {
            "run_date": payload.run_date,
            "run_id": payload.run_id,
            **safe_dict(event),
        }
        for event in payload.normalized_events
    ]
    append_jsonl_rows_safely(context.data_dir / "source_events.jsonl", events_payload, ensure_ascii=False)

    topic_payload = [
        {
            "run_date": payload.run_date,
            "topic_id": summary.topic_id,
            "trend_status": summary.trend_status,
            "signal_count": summary.signal_count,
            "signal_classification": summary.signal_classification,
        }
        for summary in payload.topic_summaries.values()
    ]
    append_jsonl_rows_safely(context.data_dir / "topic_trends.jsonl", topic_payload, ensure_ascii=False)

    company_payload = [
        {
            "run_date": payload.run_date,
            "company": name,
            "significance": analysis.significance,
            "summary": analysis.summary,
        }
        for name, analysis in payload.company_analyses.items()
    ]
    if company_payload:
        append_jsonl_rows_safely(context.data_dir / "company_mentions.jsonl", company_payload, ensure_ascii=False)

    paper_payload = [
        {
            "run_date": payload.run_date,
            "title": analysis.title,
            "link": analysis.link,
            "signal_strength": analysis.signal_strength,
            "overall_score": analysis.overall_score,
        }
        for analysis in payload.paper_analyses.values()
        if analysis.report_worthy
    ]
    if paper_payload:
        append_jsonl_rows_safely(context.data_dir / "paper_mentions.jsonl", paper_payload, ensure_ascii=False)

    project_payload = [
        {
            "run_date": payload.run_date,
            "repo": analysis.repo,
            "url": analysis.url,
            "verdict": analysis.verdict,
            "stars_total": analysis.stars_total,
        }
        for analysis in payload.github_project_analyses.values()
    ]
    if project_payload:
        append_jsonl_rows_safely(context.data_dir / "project_mentions.jsonl", project_payload, ensure_ascii=False)

    print("  [Storage] Appended events to data logs")


def append_events(state: TechDailyState, *, storage_context: StorageContext | None = None) -> None:
    """Append today's events to data log files."""
    append_event_payload(EventStoragePayload.from_state(state), storage_context=storage_context)


def load_topic_trends_recent(
    days: int = 30,
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> list[dict[str, Any]]:
    context = resolve_storage_context(storage_context)
    return load_jsonl_since(context.data_dir / "topic_trends.jsonl", days, diagnostics=diagnostics)


def load_company_mentions_recent(
    days: int = 90,
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> list[dict[str, Any]]:
    context = resolve_storage_context(storage_context)
    return load_jsonl_since(context.data_dir / "company_mentions.jsonl", days, diagnostics=diagnostics)


def save_trending_snapshot(
    snapshot: TrendingSnapshotLike,
    *,
    storage_context: StorageContext | None = None,
) -> None:
    """Append one row per trending item to trending_snapshots.jsonl."""
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)
    all_items = (
        getattr(snapshot, "github_items", [])
        + getattr(snapshot, "hf_paper_items", [])
        + getattr(snapshot, "hf_model_items", [])
    )
    if not all_items:
        return

    rows = [
        {
            "snapshot_date": snapshot.snapshot_date,
            "period": snapshot.period,
            "item_id": item.item_id,
            "item_type": item.item_type,
            "source": item.source,
            "title": item.title,
            "rank": item.rank,
            "velocity_score": item.velocity_score,
            "language": item.language,
        }
        for item in all_items
    ]
    append_jsonl_rows_safely(context.trending_log_path(), rows, ensure_ascii=False)
    print(f"  [Storage] Appended {len(all_items)} trending items to snapshot log")


def load_trending_history(
    days: int = 30,
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> list[dict[str, Any]]:
    """Load trending snapshot rows from the past N days."""
    return load_jsonl_since(
        resolve_storage_context(storage_context).trending_log_path(),
        days,
        diagnostics=diagnostics,
    )


def save_market_signals(
    run_date: str,
    analyses: dict[str, MarketSignalAnalysis],
    *,
    storage_context: StorageContext | None = None,
) -> None:
    """Append one row per ticker to market_signals.jsonl."""
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)
    if not analyses:
        return

    rows = []
    for analysis in analyses.values():
        row = safe_dict(analysis)
        row["run_date"] = run_date
        row.pop("report_snippet", None)
        rows.append(row)
    append_jsonl_rows_safely(context.market_signals_log_path(), rows, ensure_ascii=False)
    print(f"  [Storage] Saved {len(analyses)} market signals to log")


def load_market_signals_history(
    days: int = 90,
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> list[dict[str, Any]]:
    """Load market signal rows from the past N days (for accuracy tracking)."""
    return load_jsonl_since(
        resolve_storage_context(storage_context).market_signals_log_path(),
        days,
        diagnostics=diagnostics,
    )


def load_last_signal_per_ticker(
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the most recent signal dict keyed by ticker."""
    latest: dict[str, dict[str, Any]] = {}
    market_signals_log = resolve_storage_context(storage_context).market_signals_log_path()
    for _line_number, row in read_jsonl_dict_rows(market_signals_log, diagnostics=diagnostics):
        ticker = row.get("ticker", "")
        if ticker:
            latest[ticker] = row
    return latest
