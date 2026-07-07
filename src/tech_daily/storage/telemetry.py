"""Collector telemetry artifact storage helpers."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from tech_daily.storage._shared import (
    ensure_dirs,
    read_jsonl_dict_rows,
    record_storage_warning,
)
from tech_daily.storage._shared import (
    storage_context as resolve_storage_context,
)
from tech_daily.storage.context import StorageContext
from tech_daily.storage.io import atomic_write_jsonl
from tech_daily.storage.validation import (
    StorageDiagnostics,
    migrate_collector_telemetry_row,
    validate_collector_telemetry_row,
)

if TYPE_CHECKING:
    from collectors.telemetry import CollectorRunResult


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
    storage_context: StorageContext | None = None,
    retention_days: int = 90,
    max_rows: int = 5000,
) -> None:
    """Persist collector run telemetry as JSONL using atomic full-file replacement."""
    context = resolve_storage_context(storage_context)
    collector_runs_log = str(context.collector_telemetry_path())
    ensure_dirs(context)
    timestamp = timestamp or datetime.now(UTC).isoformat()
    existing_rows = load_collector_telemetry(storage_context=context)
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
        retention_days=retention_days,
        max_rows=max_rows,
    )
    atomic_write_jsonl(collector_runs_log, retained_rows, ensure_ascii=False)
    print(f"  [Storage] Saved collector telemetry: {len(new_rows)} rows")


def load_collector_telemetry(
    *,
    diagnostics: StorageDiagnostics | None = None,
    limit: int | None = None,
    storage_context: StorageContext | None = None,
) -> list[dict[str, Any]]:
    """Load valid collector telemetry rows, reporting malformed rows through diagnostics."""
    collector_runs_log = str(resolve_storage_context(storage_context).collector_telemetry_path())
    rows: list[dict[str, Any]] = []
    for line_number, row in read_jsonl_dict_rows(collector_runs_log, diagnostics=diagnostics):
        migrated_row = migrate_collector_telemetry_row(row)
        validation_errors = validate_collector_telemetry_row(migrated_row)
        if validation_errors:
            record_storage_warning(
                diagnostics,
                path=collector_runs_log,
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
    retention_days: int = 90,
    max_rows: int = 5000,
    as_of_date: str | date | None = None,
    diagnostics: StorageDiagnostics | None = None,
    storage_context: StorageContext | None = None,
) -> int:
    """Compact collector telemetry by keeping recent valid rows and atomically rewriting."""
    context = resolve_storage_context(storage_context)
    collector_runs_log = context.collector_telemetry_path()
    if not collector_runs_log.exists():
        return 0

    rows = load_collector_telemetry(diagnostics=diagnostics, storage_context=context)
    retained_rows = _retain_collector_telemetry_rows(
        rows,
        retention_days=retention_days,
        max_rows=max_rows,
        as_of_date=as_of_date,
    )
    atomic_write_jsonl(collector_runs_log, retained_rows, ensure_ascii=False)
    print(f"  [Storage] Compacted collector telemetry: {len(retained_rows)} rows retained")
    return len(retained_rows)
