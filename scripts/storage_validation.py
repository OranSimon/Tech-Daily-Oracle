"""Validation diagnostics for persisted storage artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StorageWarning:
    artifact: str
    message: str
    line_number: int | None = None
    raw_value: str | None = None
    exception_type: str | None = None


@dataclass
class StorageDiagnostics:
    warnings: list[StorageWarning] = field(default_factory=list)

    def add(
        self,
        *,
        artifact: str,
        message: str,
        line_number: int | None = None,
        raw_value: str | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.warnings.append(
            StorageWarning(
                artifact=artifact,
                message=message,
                line_number=line_number,
                raw_value=raw_value,
                exception_type=type(exception).__name__ if exception else None,
            )
        )


OPEN_PREDICTION_REQUIRED_FIELDS = {
    "prediction_id",
    "created_date",
    "prediction",
    "time_horizon",
    "probability",
    "status",
    "confidence",
}

OPEN_PREDICTION_LIST_FIELDS = {
    "topic_tags",
    "companies",
    "signals_to_monitor",
    "updates",
}

COLLECTOR_TELEMETRY_REQUIRED_FIELDS = {
    "run_date",
    "run_id",
    "collector_name",
    "status",
    "duration_seconds",
    "record_count",
    "warnings",
    "error_message",
    "timestamp",
}

COLLECTOR_RUN_STATUSES = {"success", "partial", "failed", "skipped"}


def validate_open_prediction_row(row: dict[str, Any]) -> list[str]:
    """Return validation errors for fields consumed when loading open predictions."""
    errors: list[str] = []
    missing = sorted(field for field in OPEN_PREDICTION_REQUIRED_FIELDS if field not in row)
    if missing:
        errors.append(f"Missing required prediction fields: {', '.join(missing)}")

    if "probability" in row and not isinstance(row["probability"], int | float):
        errors.append("Field probability must be numeric")

    for field_name in OPEN_PREDICTION_LIST_FIELDS:
        if field_name in row and not isinstance(row[field_name], list):
            errors.append(f"Field {field_name} must be a list")

    for field_name in OPEN_PREDICTION_REQUIRED_FIELDS - {"probability"}:
        if field_name in row and not isinstance(row[field_name], str):
            errors.append(f"Field {field_name} must be a string")

    return errors


def validate_collector_telemetry_row(row: dict[str, Any]) -> list[str]:
    """Return validation errors for persisted collector telemetry rows."""
    errors: list[str] = []
    missing = sorted(field for field in COLLECTOR_TELEMETRY_REQUIRED_FIELDS if field not in row)
    if missing:
        errors.append(f"Missing required collector telemetry fields: {', '.join(missing)}")

    for field_name in ["run_date", "run_id", "collector_name", "status", "timestamp"]:
        if field_name in row and not isinstance(row[field_name], str):
            errors.append(f"Field {field_name} must be a string")

    if "status" in row and isinstance(row["status"], str) and row["status"] not in COLLECTOR_RUN_STATUSES:
        errors.append("Field status must be one of success, partial, failed, skipped")

    if "duration_seconds" in row and not isinstance(row["duration_seconds"], int | float):
        errors.append("Field duration_seconds must be numeric")

    if "record_count" in row and not isinstance(row["record_count"], int):
        errors.append("Field record_count must be an integer")

    if "warnings" in row:
        if not isinstance(row["warnings"], list):
            errors.append("Field warnings must be a list")
        else:
            for index, warning in enumerate(row["warnings"]):
                if not isinstance(warning, dict):
                    errors.append(f"Warning {index} must be an object")
                    continue
                if not isinstance(warning.get("message"), str):
                    errors.append(f"Warning {index} message must be a string")
                exception_type = warning.get("exception_type")
                if exception_type is not None and not isinstance(exception_type, str):
                    errors.append(f"Warning {index} exception_type must be a string or null")

    if "error_message" in row and row["error_message"] is not None and not isinstance(row["error_message"], str):
        errors.append("Field error_message must be a string or null")

    return errors


def migrate_collector_telemetry_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a backward-compatible collector telemetry row shape.

    This does not rewrite persisted artifacts by itself. It lets readers accept
    earlier local telemetry rows while presenting the current schema to callers.
    """
    migrated = dict(row)
    if "duration_seconds" not in migrated and "duration" in migrated:
        migrated["duration_seconds"] = migrated["duration"]
    migrated.pop("duration", None)
    migrated.setdefault("run_id", "")
    migrated.setdefault("warnings", [])
    migrated.setdefault("error_message", None)
    return migrated
