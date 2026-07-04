"""Publishing & Storage Layer — save reports and update data files."""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

from collectors.telemetry import CollectorRunResult
from state import MarketSignalAnalysis, Prediction, PredictionUpdate, Report, TechDailyState, TrendingSnapshot
from storage_io import append_jsonl_rows_safely, atomic_write_jsonl, atomic_write_text
from storage_validation import (
    StorageDiagnostics,
    migrate_collector_telemetry_row,
    validate_collector_telemetry_row,
    validate_open_prediction_row,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(ROOT, "reports")


def _ensure_dirs() -> None:
    for d in [
        DATA_DIR,
        os.path.join(REPORTS_DIR, "daily"),
        os.path.join(REPORTS_DIR, "weekly"),
        os.path.join(REPORTS_DIR, "monthly"),
    ]:
        os.makedirs(d, exist_ok=True)


def _safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_safe_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Report storage
# ---------------------------------------------------------------------------


def save_daily_report(run_date: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "daily", f"{run_date}.md")
    atomic_write_text(path, content)
    print(f"  [Storage] Saved daily report: {path}")
    return path


def save_weekly_review(week: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "weekly", f"{week}.md")
    atomic_write_text(path, content)
    print(f"  [Storage] Saved weekly review: {path}")
    return path


def save_monthly_review(month: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "monthly", f"{month}.md")
    atomic_write_text(path, content)
    print(f"  [Storage] Saved monthly review: {path}")
    return path


# ---------------------------------------------------------------------------
# Prediction log
# ---------------------------------------------------------------------------

PREDICTION_LOG = os.path.join(DATA_DIR, "prediction_log.jsonl")


def _record_storage_warning(
    diagnostics: StorageDiagnostics | None,
    *,
    path: str,
    message: str,
    line_number: int | None = None,
    raw_value: str | None = None,
    exception: Exception | None = None,
) -> None:
    if diagnostics is not None:
        diagnostics.add(
            artifact=path,
            message=message,
            line_number=line_number,
            raw_value=raw_value,
            exception=exception,
        )
    detail = f" line {line_number}" if line_number is not None else ""
    if exception is not None:
        print(f"  [Storage] {message}{detail}: {exception}")
    else:
        print(f"  [Storage] {message}{detail}")


def _read_jsonl_dict_rows(
    path: str,
    *,
    diagnostics: StorageDiagnostics | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    if not os.path.exists(path):
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as e:
                _record_storage_warning(
                    diagnostics,
                    path=path,
                    message="Invalid JSON row",
                    line_number=line_number,
                    raw_value=raw_line,
                    exception=e,
                )
                continue
            if not isinstance(row, dict):
                _record_storage_warning(
                    diagnostics,
                    path=path,
                    message="JSONL row must be an object",
                    line_number=line_number,
                    raw_value=raw_line,
                )
                continue
            rows.append((line_number, row))
    return rows


def load_open_predictions(diagnostics: StorageDiagnostics | None = None) -> list[Prediction]:
    predictions = []
    for line_number, d in _read_jsonl_dict_rows(PREDICTION_LOG, diagnostics=diagnostics):
        if d.get("status") == "open":
            validation_errors = validate_open_prediction_row(d)
            if validation_errors:
                _record_storage_warning(
                    diagnostics,
                    path=PREDICTION_LOG,
                    message="; ".join(validation_errors),
                    line_number=line_number,
                    raw_value=json.dumps(d, ensure_ascii=False),
                )
                continue
            try:
                predictions.append(
                    Prediction(
                        prediction_id=d["prediction_id"],
                        created_date=d["created_date"],
                        prediction=d["prediction"],
                        topic_tags=d.get("topic_tags", []),
                        companies=d.get("companies", []),
                        time_horizon=d["time_horizon"],
                        horizon_date=d.get("horizon_date", ""),
                        probability=d["probability"],
                        evidence=d.get("evidence", ""),
                        resolution_criteria=d.get("resolution_criteria", ""),
                        falsification_condition=d.get("falsification_condition", ""),
                        signals_to_monitor=d.get("signals_to_monitor", []),
                        status=d["status"],
                        confidence=d.get("confidence", "medium"),
                        updates=d.get("updates", []),
                    )
                )
            except Exception as e:
                _record_storage_warning(
                    diagnostics,
                    path=PREDICTION_LOG,
                    message="Failed to load prediction",
                    line_number=line_number,
                    raw_value=json.dumps(d, ensure_ascii=False),
                    exception=e,
                )
    return predictions


def save_predictions(new_predictions: list[Prediction], updates: list[PredictionUpdate]) -> None:
    """Append new predictions and apply updates to the log."""
    _ensure_dirs()

    # Load all existing predictions
    all_predictions: dict[str, dict[str, Any]] = {}
    diagnostics = StorageDiagnostics()
    for line_number, d in _read_jsonl_dict_rows(PREDICTION_LOG, diagnostics=diagnostics):
        prediction_id = d.get("prediction_id")
        if isinstance(prediction_id, str) and prediction_id:
            all_predictions[prediction_id] = d
        else:
            _record_storage_warning(
                diagnostics,
                path=PREDICTION_LOG,
                message="Prediction row missing prediction_id",
                line_number=line_number,
                raw_value=json.dumps(d, ensure_ascii=False),
            )

    # Apply updates
    for update in updates:
        pid = update.prediction_id
        if pid in all_predictions:
            p = all_predictions[pid]
            p["probability"] = update.probability_after
            p.setdefault("updates", []).append(_safe_dict(update))
            if update.resolution.get("resolved"):
                outcome = update.resolution.get("resolved_as")
                p["status"] = f"resolved_{outcome}" if outcome else "resolved_unknown"
                p["resolution_reasoning"] = update.resolution.get("resolution_reasoning", "")

    # Add new predictions
    for pred in new_predictions:
        d = _safe_dict(pred)
        all_predictions[pred.prediction_id] = d

    # Rewrite log
    atomic_write_jsonl(PREDICTION_LOG, all_predictions.values(), ensure_ascii=False)

    print(f"  [Storage] Prediction log updated: {len(new_predictions)} new, {len(updates)} updated")


# ---------------------------------------------------------------------------
# Event data files (append-only)
# ---------------------------------------------------------------------------


def append_events(state: TechDailyState) -> None:
    """Append today's events to data log files."""
    _ensure_dirs()

    # source_events.jsonl
    events_payload = [
        {
            "run_date": state.run_date,
            "run_id": state.run_id,
            **_safe_dict(e),
        }
        for e in state.normalized_events
    ]
    append_jsonl_rows_safely(os.path.join(DATA_DIR, "source_events.jsonl"), events_payload, ensure_ascii=False)

    # topic_trends.jsonl
    topic_payload = [
        {
            "run_date": state.run_date,
            "topic_id": ts.topic_id,
            "trend_status": ts.trend_status,
            "signal_count": ts.signal_count,
            "signal_classification": ts.signal_classification,
        }
        for ts in state.topic_summaries.values()
    ]
    append_jsonl_rows_safely(os.path.join(DATA_DIR, "topic_trends.jsonl"), topic_payload, ensure_ascii=False)

    # company_mentions.jsonl
    company_payload = [
        {
            "run_date": state.run_date,
            "company": name,
            "significance": a.significance,
            "summary": a.summary,
        }
        for name, a in state.company_analyses.items()
    ]
    if company_payload:
        append_jsonl_rows_safely(os.path.join(DATA_DIR, "company_mentions.jsonl"), company_payload, ensure_ascii=False)

    # paper_mentions.jsonl
    paper_payload = [
        {
            "run_date": state.run_date,
            "title": p.title,
            "link": p.link,
            "signal_strength": p.signal_strength,
            "overall_score": p.overall_score,
        }
        for p in state.paper_analyses.values()
        if p.report_worthy
    ]
    if paper_payload:
        append_jsonl_rows_safely(os.path.join(DATA_DIR, "paper_mentions.jsonl"), paper_payload, ensure_ascii=False)

    # project_mentions.jsonl
    project_payload = [
        {
            "run_date": state.run_date,
            "repo": p.repo,
            "url": p.url,
            "verdict": p.verdict,
            "stars_total": p.stars_total,
        }
        for p in state.github_project_analyses.values()
    ]
    if project_payload:
        append_jsonl_rows_safely(os.path.join(DATA_DIR, "project_mentions.jsonl"), project_payload, ensure_ascii=False)

    print("  [Storage] Appended events to data logs")


# ---------------------------------------------------------------------------
# Historical context loading
# ---------------------------------------------------------------------------


def load_recent_reports(n: int = 7) -> list[Report]:
    daily_dir = os.path.join(REPORTS_DIR, "daily")
    if not os.path.exists(daily_dir):
        return []

    report_files = sorted([f for f in os.listdir(daily_dir) if f.endswith(".md")], reverse=True)[:n]

    reports = []
    for fname in report_files:
        path = os.path.join(daily_dir, fname)
        report_date = fname.replace(".md", "")
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            reports.append(
                Report(
                    report_type="daily",
                    report_date=report_date,
                    content=content,
                )
            )
        except Exception as e:
            print(f"  [Storage] Failed to load report {fname}: {e}")

    return reports


def load_recent_weekly_reviews(n: int = 4) -> list[Report]:
    weekly_dir = os.path.join(REPORTS_DIR, "weekly")
    if not os.path.exists(weekly_dir):
        return []
    files = sorted([f for f in os.listdir(weekly_dir) if f.endswith(".md")], reverse=True)[:n]
    reviews = []
    for fname in files:
        try:
            with open(os.path.join(weekly_dir, fname), encoding="utf-8") as f:
                content = f.read()
            reviews.append(Report(report_type="weekly", report_date=fname.replace(".md", ""), content=content))
        except Exception as e:
            print(f"  [Storage] Failed to load weekly review {fname}: {e}")
    return reviews


def load_recent_monthly_reviews(n: int = 3) -> list[Report]:
    monthly_dir = os.path.join(REPORTS_DIR, "monthly")
    if not os.path.exists(monthly_dir):
        return []
    files = sorted([f for f in os.listdir(monthly_dir) if f.endswith(".md")], reverse=True)[:n]
    reviews = []
    for fname in files:
        try:
            with open(os.path.join(monthly_dir, fname), encoding="utf-8") as f:
                content = f.read()
            reviews.append(Report(report_type="monthly", report_date=fname.replace(".md", ""), content=content))
        except Exception as e:
            print(f"  [Storage] Failed to load monthly review {fname}: {e}")
    return reviews


def _load_jsonl_since(
    path: str,
    days: int,
    *,
    diagnostics: StorageDiagnostics | None = None,
    date_field: str = "run_date",
) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    records = []
    for _line_number, d in _read_jsonl_dict_rows(path, diagnostics=diagnostics):
        if d.get(date_field, "9999") >= cutoff:
            records.append(d)
    return records


def load_topic_trends_recent(days: int = 30, diagnostics: StorageDiagnostics | None = None) -> list[dict]:
    return _load_jsonl_since(os.path.join(DATA_DIR, "topic_trends.jsonl"), days, diagnostics=diagnostics)


def load_company_mentions_recent(days: int = 90, diagnostics: StorageDiagnostics | None = None) -> list[dict]:
    return _load_jsonl_since(os.path.join(DATA_DIR, "company_mentions.jsonl"), days, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Trending snapshots
# ---------------------------------------------------------------------------

TRENDING_LOG = os.path.join(DATA_DIR, "trending_snapshots.jsonl")


def save_trending_snapshot(snapshot: TrendingSnapshot) -> None:
    """Append one row per trending item to trending_snapshots.jsonl."""
    _ensure_dirs()
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
    append_jsonl_rows_safely(TRENDING_LOG, rows, ensure_ascii=False)
    print(f"  [Storage] Appended {len(all_items)} trending items to snapshot log")


def load_trending_history(days: int = 30, diagnostics: StorageDiagnostics | None = None) -> list[dict]:
    """Load trending snapshot rows from the past N days."""
    return _load_jsonl_since(TRENDING_LOG, days, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Market signals log (Phase 4+)
# ---------------------------------------------------------------------------

MARKET_SIGNALS_LOG = os.path.join(DATA_DIR, "market_signals.jsonl")
COLLECTOR_RUNS_LOG = os.path.join(DATA_DIR, "collector_runs.jsonl")
COLLECTOR_TELEMETRY_RETENTION_DAYS = 90
COLLECTOR_TELEMETRY_MAX_ROWS = 5000


def save_market_signals(run_date: str, analyses: dict[str, MarketSignalAnalysis]) -> None:
    """Append one row per ticker to market_signals.jsonl."""
    _ensure_dirs()
    if not analyses:
        return
    rows = []
    for _ticker, analysis in analyses.items():
        row = _safe_dict(analysis)
        row["run_date"] = run_date
        # Omit the verbose report_snippet from the log to keep file lean;
        # it can always be regenerated from the other fields.
        row.pop("report_snippet", None)
        rows.append(row)
    append_jsonl_rows_safely(MARKET_SIGNALS_LOG, rows, ensure_ascii=False)
    print(f"  [Storage] Saved {len(analyses)} market signals to log")


def load_market_signals_history(days: int = 90, diagnostics: StorageDiagnostics | None = None) -> list[dict]:
    """Load market signal rows from the past N days (for accuracy tracking)."""
    return _load_jsonl_since(MARKET_SIGNALS_LOG, days, diagnostics=diagnostics)


def load_last_signal_per_ticker(diagnostics: StorageDiagnostics | None = None) -> dict[str, dict]:
    """Return the most recent signal dict keyed by ticker.

    Used to pass `previous_signal` context to the MarketSignalAgent so it can
    compare today's thesis against its own prior output.
    """
    latest: dict[str, dict] = {}
    for _line_number, d in _read_jsonl_dict_rows(MARKET_SIGNALS_LOG, diagnostics=diagnostics):
        ticker = d.get("ticker", "")
        if ticker:
            latest[ticker] = d  # last line wins (file is append-only, date-ordered)
    return latest


# ---------------------------------------------------------------------------
# Collector telemetry log
# ---------------------------------------------------------------------------


def _collector_telemetry_row(
    *,
    run_date: str,
    result: CollectorRunResult,
    run_id: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "run_date": run_date,
        "run_id": run_id,
        "collector_name": result.collector_name,
        "status": result.status.value,
        "duration_seconds": result.duration_seconds,
        "record_count": result.record_count,
        "warnings": [
            {
                "message": warning.message,
                "exception_type": warning.exception_type,
            }
            for warning in result.warnings
        ],
        "error_message": result.error_message,
        "timestamp": timestamp,
    }


def save_collector_telemetry(
    *,
    run_date: str,
    results: list[CollectorRunResult],
    run_id: str = "",
    timestamp: str | None = None,
) -> None:
    """Persist collector run telemetry as JSONL using atomic full-file replacement."""
    _ensure_dirs()
    timestamp = timestamp or datetime.now(UTC).isoformat()
    existing_rows = load_collector_telemetry()
    new_rows = [
        _collector_telemetry_row(
            run_date=run_date,
            result=result,
            run_id=run_id,
            timestamp=timestamp,
        )
        for result in results
    ]
    retained_rows = _retain_collector_telemetry_rows(
        [*existing_rows, *new_rows],
        retention_days=COLLECTOR_TELEMETRY_RETENTION_DAYS,
        max_rows=COLLECTOR_TELEMETRY_MAX_ROWS,
    )
    atomic_write_jsonl(COLLECTOR_RUNS_LOG, retained_rows, ensure_ascii=False)
    print(f"  [Storage] Saved collector telemetry: {len(new_rows)} rows")


def load_collector_telemetry(
    *,
    diagnostics: StorageDiagnostics | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load valid collector telemetry rows, reporting malformed rows through diagnostics."""
    rows: list[dict[str, Any]] = []
    for line_number, row in _read_jsonl_dict_rows(COLLECTOR_RUNS_LOG, diagnostics=diagnostics):
        migrated_row = migrate_collector_telemetry_row(row)
        validation_errors = validate_collector_telemetry_row(migrated_row)
        if validation_errors:
            _record_storage_warning(
                diagnostics,
                path=COLLECTOR_RUNS_LOG,
                message="; ".join(validation_errors),
                line_number=line_number,
                raw_value=json.dumps(row, ensure_ascii=False),
            )
            continue
        rows.append(migrated_row)

    if limit is not None:
        return rows[-limit:]
    return rows


def _retention_cutoff(retention_days: int, as_of_date: str | date | None = None) -> str:
    if as_of_date is None:
        anchor = date.today()
    elif isinstance(as_of_date, date):
        anchor = as_of_date
    else:
        anchor = date.fromisoformat(as_of_date)
    return (anchor - timedelta(days=retention_days)).isoformat()


def _retain_collector_telemetry_rows(
    rows: list[dict[str, Any]],
    *,
    retention_days: int,
    max_rows: int,
    as_of_date: str | date | None = None,
) -> list[dict[str, Any]]:
    cutoff = _retention_cutoff(retention_days, as_of_date)
    retained = [row for row in rows if row.get("run_date", "") >= cutoff]
    if max_rows > 0:
        return retained[-max_rows:]
    return retained


def compact_collector_telemetry(
    *,
    retention_days: int = COLLECTOR_TELEMETRY_RETENTION_DAYS,
    max_rows: int = COLLECTOR_TELEMETRY_MAX_ROWS,
    as_of_date: str | date | None = None,
    diagnostics: StorageDiagnostics | None = None,
) -> int:
    """Compact collector telemetry by keeping recent valid rows and atomically rewriting."""
    if not os.path.exists(COLLECTOR_RUNS_LOG):
        return 0
    rows = load_collector_telemetry(diagnostics=diagnostics)
    retained_rows = _retain_collector_telemetry_rows(
        rows,
        retention_days=retention_days,
        max_rows=max_rows,
        as_of_date=as_of_date,
    )
    atomic_write_jsonl(COLLECTOR_RUNS_LOG, retained_rows, ensure_ascii=False)
    print(f"  [Storage] Compacted collector telemetry: {len(retained_rows)} rows retained")
    return len(retained_rows)
