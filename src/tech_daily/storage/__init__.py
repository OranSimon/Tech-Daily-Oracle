"""Storage package facade."""

from __future__ import annotations

from tech_daily.storage.context import StorageContext
from tech_daily.storage.events import (  # noqa: E402
    append_events,
    load_company_mentions_recent,
    load_last_signal_per_ticker,
    load_market_signals_history,
    load_topic_trends_recent,
    load_trending_history,
    save_market_signals,
    save_trending_snapshot,
)
from tech_daily.storage.io import (
    append_jsonl_rows_safely,
    atomic_replace,
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    quarantine_jsonl_row,
)
from tech_daily.storage.predictions import load_open_predictions, save_predictions  # noqa: E402
from tech_daily.storage.reports import (  # noqa: E402
    load_recent_monthly_reviews,
    load_recent_reports,
    load_recent_weekly_reviews,
    save_daily_report,
    save_monthly_review,
    save_weekly_review,
)
from tech_daily.storage.telemetry import (  # noqa: E402
    compact_collector_telemetry,
    load_collector_telemetry,
    save_collector_telemetry,
)
from tech_daily.storage.validation import (
    StorageDiagnostics,
    StorageWarning,
    migrate_collector_telemetry_row,
    validate_collector_telemetry_row,
    validate_open_prediction_row,
)

__all__ = [
    "StorageDiagnostics",
    "StorageContext",
    "StorageWarning",
    "append_jsonl_rows_safely",
    "atomic_replace",
    "atomic_write_json",
    "atomic_write_jsonl",
    "atomic_write_text",
    "migrate_collector_telemetry_row",
    "quarantine_jsonl_row",
    "validate_collector_telemetry_row",
    "validate_open_prediction_row",
    "append_events",
    "compact_collector_telemetry",
    "load_collector_telemetry",
    "load_company_mentions_recent",
    "load_last_signal_per_ticker",
    "load_market_signals_history",
    "load_open_predictions",
    "load_recent_monthly_reviews",
    "load_recent_reports",
    "load_recent_weekly_reviews",
    "load_topic_trends_recent",
    "load_trending_history",
    "save_collector_telemetry",
    "save_daily_report",
    "save_market_signals",
    "save_monthly_review",
    "save_predictions",
    "save_trending_snapshot",
    "save_weekly_review",
]
