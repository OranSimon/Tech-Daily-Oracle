"""Shared collector execution telemetry types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CollectorRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CollectorWarning:
    message: str
    exception_type: str | None = None


@dataclass(frozen=True)
class CollectorRunResult:
    collector_name: str
    status: CollectorRunStatus
    duration_seconds: float
    record_count: int
    warnings: list[CollectorWarning] = field(default_factory=list)
    error_message: str | None = None
