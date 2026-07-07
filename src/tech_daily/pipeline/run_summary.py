"""Small run summary models for local diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunStepSummary:
    step_name: str
    success: bool
    duration_seconds: float
    record_count: int | None
    error: str | None


@dataclass(frozen=True)
class RunSummary:
    run_date: str
    run_id: str
    steps: list[RunStepSummary]


def run_summary_row(summary: RunSummary) -> dict[str, Any]:
    return {
        "run_date": summary.run_date,
        "run_id": summary.run_id,
        "steps": [
            {
                "step_name": step.step_name,
                "success": step.success,
                "duration_seconds": step.duration_seconds,
                "record_count": step.record_count,
                "error": step.error,
            }
            for step in summary.steps
        ],
    }
