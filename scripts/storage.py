"""Compatibility wrapper for package-owned storage modules."""

# ruff: noqa: E402, I001

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.storage.context import StorageContext  # noqa: E402
from tech_daily.storage.events import (  # noqa: E402
    append_events as _append_events,
)
from tech_daily.storage.events import (
    load_company_mentions_recent as _load_company_mentions_recent,
)
from tech_daily.storage.events import (
    load_last_signal_per_ticker as _load_last_signal_per_ticker,
)
from tech_daily.storage.events import (
    load_market_signals_history as _load_market_signals_history,
)
from tech_daily.storage.events import (
    load_topic_trends_recent as _load_topic_trends_recent,
)
from tech_daily.storage.events import (
    load_trending_history as _load_trending_history,
)
from tech_daily.storage.events import (
    save_market_signals as _save_market_signals,
)
from tech_daily.storage.events import (
    save_trending_snapshot as _save_trending_snapshot,
)
from tech_daily.storage.io import append_jsonl_rows_safely, atomic_write_jsonl, atomic_write_text  # noqa: E402,F401
from tech_daily.storage.predictions import load_open_predictions as _load_open_predictions  # noqa: E402
from tech_daily.storage.predictions import save_predictions as _save_predictions  # noqa: E402
from tech_daily.storage.reports import (  # noqa: E402
    load_recent_monthly_reviews as _load_recent_monthly_reviews,
)
from tech_daily.storage.reports import (
    load_recent_reports as _load_recent_reports,
)
from tech_daily.storage.reports import (
    load_recent_weekly_reviews as _load_recent_weekly_reviews,
)
from tech_daily.storage.reports import (
    save_daily_report as _save_daily_report,
)
from tech_daily.storage.reports import (
    save_monthly_review as _save_monthly_review,
)
from tech_daily.storage.reports import (
    save_weekly_review as _save_weekly_review,
)
from tech_daily.storage.telemetry import (  # noqa: E402
    compact_collector_telemetry as _compact_collector_telemetry,
)
from tech_daily.storage.telemetry import (
    load_collector_telemetry as _load_collector_telemetry,
)
from tech_daily.storage.telemetry import (
    save_collector_telemetry as _save_collector_telemetry,
)
from tech_daily.storage.validation import (  # noqa: E402,F401
    StorageDiagnostics,
    migrate_collector_telemetry_row,
    validate_collector_telemetry_row,
    validate_open_prediction_row,
)

ROOT = str(ROOT_DIR)
DATA_DIR = str(ROOT_DIR / "data")
REPORTS_DIR = str(ROOT_DIR / "reports")
PREDICTION_LOG = str(ROOT_DIR / "data" / "prediction_log.jsonl")
TRENDING_LOG = str(ROOT_DIR / "data" / "trending_snapshots.jsonl")
MARKET_SIGNALS_LOG = str(ROOT_DIR / "data" / "market_signals.jsonl")
COLLECTOR_RUNS_LOG = str(ROOT_DIR / "data" / "collector_runs.jsonl")
COLLECTOR_TELEMETRY_RETENTION_DAYS = 90
COLLECTOR_TELEMETRY_MAX_ROWS = 5000


def _script_storage_context(storage_context: StorageContext | None = None) -> StorageContext:
    if storage_context is not None:
        return storage_context
    return StorageContext.from_globals(
        root_dir=ROOT,
        data_dir=DATA_DIR,
        reports_dir=REPORTS_DIR,
        prediction_log=PREDICTION_LOG,
        trending_log=TRENDING_LOG,
        market_signals_log=MARKET_SIGNALS_LOG,
        collector_runs_log=COLLECTOR_RUNS_LOG,
    )


def append_events(state, *, storage_context: StorageContext | None = None):
    return _append_events(state, storage_context=_script_storage_context(storage_context))


def load_company_mentions_recent(days: int = 90, *, storage_context: StorageContext | None = None):
    return _load_company_mentions_recent(days=days, storage_context=_script_storage_context(storage_context))


def load_last_signal_per_ticker(*, storage_context: StorageContext | None = None):
    return _load_last_signal_per_ticker(storage_context=_script_storage_context(storage_context))


def load_market_signals_history(days: int = 90, *, storage_context: StorageContext | None = None):
    return _load_market_signals_history(days=days, storage_context=_script_storage_context(storage_context))


def load_topic_trends_recent(days: int = 30, *, storage_context: StorageContext | None = None):
    return _load_topic_trends_recent(days=days, storage_context=_script_storage_context(storage_context))


def load_trending_history(*, days: int = 14, storage_context: StorageContext | None = None):
    return _load_trending_history(days=days, storage_context=_script_storage_context(storage_context))


def save_market_signals(run_date: str, market_signal_analyses, *, storage_context: StorageContext | None = None):
    return _save_market_signals(
        run_date,
        market_signal_analyses,
        storage_context=_script_storage_context(storage_context),
    )


def save_trending_snapshot(snapshot, *, storage_context: StorageContext | None = None):
    return _save_trending_snapshot(snapshot, storage_context=_script_storage_context(storage_context))


def load_open_predictions(diagnostics=None, *, storage_context: StorageContext | None = None):
    return _load_open_predictions(diagnostics, storage_context=_script_storage_context(storage_context))


def save_predictions(new_predictions, updates, *, storage_context: StorageContext | None = None):
    return _save_predictions(new_predictions, updates, storage_context=_script_storage_context(storage_context))


def load_recent_monthly_reviews(n: int = 3, *, storage_context: StorageContext | None = None):
    return _load_recent_monthly_reviews(n, storage_context=_script_storage_context(storage_context))


def load_recent_reports(n: int = 7, *, storage_context: StorageContext | None = None):
    return _load_recent_reports(n, storage_context=_script_storage_context(storage_context))


def load_recent_weekly_reviews(n: int = 4, *, storage_context: StorageContext | None = None):
    return _load_recent_weekly_reviews(n, storage_context=_script_storage_context(storage_context))


def save_daily_report(run_date: str, content: str, *, storage_context: StorageContext | None = None):
    return _save_daily_report(run_date, content, storage_context=_script_storage_context(storage_context))


def save_monthly_review(month: str, content: str, *, storage_context: StorageContext | None = None):
    return _save_monthly_review(month, content, storage_context=_script_storage_context(storage_context))


def save_weekly_review(week: str, content: str, *, storage_context: StorageContext | None = None):
    return _save_weekly_review(week, content, storage_context=_script_storage_context(storage_context))


def compact_collector_telemetry(
    *,
    retention_days: int = COLLECTOR_TELEMETRY_RETENTION_DAYS,
    max_rows: int = COLLECTOR_TELEMETRY_MAX_ROWS,
    as_of_date=None,
    diagnostics=None,
    storage_context: StorageContext | None = None,
):
    return _compact_collector_telemetry(
        retention_days=retention_days,
        max_rows=max_rows,
        as_of_date=as_of_date,
        diagnostics=diagnostics,
        storage_context=_script_storage_context(storage_context),
    )


def load_collector_telemetry(
    *,
    diagnostics=None,
    limit: int | None = None,
    storage_context: StorageContext | None = None,
):
    return _load_collector_telemetry(
        diagnostics=diagnostics,
        limit=limit,
        storage_context=_script_storage_context(storage_context),
    )


def save_collector_telemetry(
    *,
    run_date: str,
    results,
    run_id: str = "",
    timestamp: str | None = None,
    storage_context: StorageContext | None = None,
):
    return _save_collector_telemetry(
        run_date=run_date,
        results=results,
        run_id=run_id,
        timestamp=timestamp,
        storage_context=_script_storage_context(storage_context),
        retention_days=COLLECTOR_TELEMETRY_RETENTION_DAYS,
        max_rows=COLLECTOR_TELEMETRY_MAX_ROWS,
    )


__all__ = [
    "COLLECTOR_RUNS_LOG",
    "COLLECTOR_TELEMETRY_MAX_ROWS",
    "COLLECTOR_TELEMETRY_RETENTION_DAYS",
    "DATA_DIR",
    "MARKET_SIGNALS_LOG",
    "PREDICTION_LOG",
    "REPORTS_DIR",
    "ROOT",
    "TRENDING_LOG",
    "StorageContext",
    "append_events",
    "append_jsonl_rows_safely",
    "atomic_write_jsonl",
    "atomic_write_text",
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
