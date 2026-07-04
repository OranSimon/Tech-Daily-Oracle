"""Structured logging primitives for pipeline runs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TextIO

from run_context import RunContext


@dataclass(frozen=True)
class RunLogEvent:
    run_id: str
    run_date: str
    step: str
    severity: str
    message: str
    duration_seconds: float | None = None
    record_count: int | None = None
    error: str | None = None
    details: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "run_id": self.run_id,
            "run_date": self.run_date,
            "step": self.step,
            "severity": self.severity,
            "message": self.message,
        }
        if self.duration_seconds is not None:
            data["duration_seconds"] = self.duration_seconds
        if self.record_count is not None:
            data["record_count"] = self.record_count
        if self.error is not None:
            data["error"] = self.error
        if self.details is not None:
            data["details"] = self.details
        return data


class RunLogger:
    """Small logger that can print JSON lines or structured plain text."""

    def __init__(self, context: RunContext, *, output: TextIO | None = None, json_lines: bool = False) -> None:
        self.context = context
        self.output = output if output is not None else sys.stdout
        self.json_lines = json_lines

    def emit(
        self,
        *,
        step: str,
        severity: str,
        message: str,
        duration_seconds: float | None = None,
        record_count: int | None = None,
        error: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        event = RunLogEvent(
            run_id=self.context.run_id,
            run_date=self.context.run_date,
            step=step,
            severity=severity,
            message=message,
            duration_seconds=duration_seconds,
            record_count=record_count,
            error=error,
            details=details,
        )
        if self.json_lines:
            print(json.dumps(event.to_dict(), ensure_ascii=False), file=self.output)
        else:
            parts = [
                f"  [RunLog] {severity.upper()}",
                f"step={step}",
                f"message={message}",
                f"run_id={self.context.run_id}",
                f"run_date={self.context.run_date}",
            ]
            if duration_seconds is not None:
                parts.append(f"duration_seconds={duration_seconds:.2f}")
            if record_count is not None:
                parts.append(f"record_count={record_count}")
            if error is not None:
                parts.append(f"error={error}")
            if details is not None:
                parts.append(f"details={json.dumps(details, ensure_ascii=False)}")
            print(" ".join(parts), file=self.output)

    def info(
        self,
        *,
        step: str,
        message: str,
        duration_seconds: float | None = None,
        record_count: int | None = None,
    ) -> None:
        self.emit(
            step=step,
            severity="info",
            message=message,
            duration_seconds=duration_seconds,
            record_count=record_count,
        )

    def error(self, *, step: str, message: str, error: str) -> None:
        self.emit(step=step, severity="error", message=message, error=error)
