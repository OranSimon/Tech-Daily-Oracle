"""Private shared helpers for storage artifact modules."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from tech_daily.storage.context import StorageContext
from tech_daily.storage.validation import StorageDiagnostics


def storage_context(storage_context: StorageContext | None = None) -> StorageContext:
    if storage_context is not None:
        return storage_context
    return StorageContext.from_globals()


def ensure_dirs(storage_context: StorageContext | None = None) -> None:
    context = storage_context if storage_context is not None else StorageContext.from_globals()
    for directory in [
        context.data_dir,
        context.reports_dir / "daily",
        context.reports_dir / "weekly",
        context.reports_dir / "monthly",
    ]:
        Path(directory).mkdir(parents=True, exist_ok=True)


def safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [safe_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: safe_dict(value) for key, value in obj.items()}
    return obj


def record_storage_warning(
    diagnostics: StorageDiagnostics | None,
    *,
    path: str | Path,
    message: str,
    line_number: int | None = None,
    raw_value: str | None = None,
    exception: Exception | None = None,
) -> None:
    artifact = str(path)
    if diagnostics is not None:
        diagnostics.add(
            artifact=artifact,
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


def read_jsonl_dict_rows(
    path: str | Path,
    *,
    diagnostics: StorageDiagnostics | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return []

    rows: list[tuple[int, dict[str, Any]]] = []
    with artifact_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw_line = line.strip()
            if not raw_line:
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as exception:
                record_storage_warning(
                    diagnostics,
                    path=artifact_path,
                    message="Invalid JSON row",
                    line_number=line_number,
                    raw_value=raw_line,
                    exception=exception,
                )
                continue
            if not isinstance(row, dict):
                record_storage_warning(
                    diagnostics,
                    path=artifact_path,
                    message="JSONL row must be an object",
                    line_number=line_number,
                    raw_value=raw_line,
                )
                continue
            rows.append((line_number, row))
    return rows


def load_jsonl_since(
    path: str | Path,
    days: int,
    *,
    diagnostics: StorageDiagnostics | None = None,
    date_field: str = "run_date",
) -> list[dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows: list[dict[str, Any]] = []
    for _line_number, row in read_jsonl_dict_rows(path, diagnostics=diagnostics):
        if row.get(date_field, "9999") >= cutoff:
            rows.append(row)
    return rows
