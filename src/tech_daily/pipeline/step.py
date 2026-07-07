"""Tiny execution wrapper for daily pipeline steps."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tech_daily.runtime.run_logging import RunLogger


@dataclass(frozen=True)
class PipelineStepResult:
    name: str
    success: bool
    duration_seconds: float
    value: Any = None
    record_count: int | None = None
    error: str | None = None
    exception: Exception | None = None


@dataclass(frozen=True)
class PipelineStep:
    """Small wrapper for step timing, logging, and fatal/non-fatal policy."""

    name: str
    action: Callable[[], Any]
    fatal: bool = False
    fallback: Any = None
    record_count: Callable[[Any], int] | None = None
    success_message: str = "completed"
    failure_message: str = "failed"

    def run(self, logger: RunLogger) -> PipelineStepResult:
        started_at = time.perf_counter()
        try:
            value = self.action()
        except Exception as exc:
            duration_seconds = time.perf_counter() - started_at
            fallback_count = _count_records(self.record_count, self.fallback)
            error = str(exc)
            logger.emit(
                step=self.name,
                severity="error",
                message=self.failure_message,
                duration_seconds=duration_seconds,
                record_count=fallback_count,
                error=error,
            )
            if self.fatal:
                raise
            return PipelineStepResult(
                name=self.name,
                success=False,
                duration_seconds=duration_seconds,
                value=self.fallback,
                record_count=fallback_count,
                error=error,
                exception=exc,
            )

        duration_seconds = time.perf_counter() - started_at
        count = _count_records(self.record_count, value)
        logger.emit(
            step=self.name,
            severity="info",
            message=self.success_message,
            duration_seconds=duration_seconds,
            record_count=count,
        )
        return PipelineStepResult(
            name=self.name,
            success=True,
            duration_seconds=duration_seconds,
            value=value,
            record_count=count,
        )


def run_step(step: PipelineStep, logger: RunLogger) -> PipelineStepResult:
    return step.run(logger)


def run_recorded_step(
    step: PipelineStep,
    logger: RunLogger,
    results: list[PipelineStepResult],
) -> PipelineStepResult:
    result = step.run(logger)
    results.append(result)
    return result


def summarize_step_results(results: list[PipelineStepResult]) -> dict[str, object]:
    steps: list[dict[str, object]] = [
        {
            "name": result.name,
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "record_count": result.record_count,
            "error": result.error,
        }
        for result in results
    ]
    return {
        "total_steps": len(results),
        "successful_steps": sum(1 for result in results if result.success),
        "failed_steps": sum(1 for result in results if not result.success),
        "total_duration_seconds": sum(result.duration_seconds for result in results),
        "steps": steps,
    }


def log_step_summary(results: list[PipelineStepResult], logger: RunLogger) -> None:
    logger.emit(
        step="run",
        severity="info",
        message="step_summary",
        details=summarize_step_results(results),
    )


def _count_records(counter: Callable[[Any], int] | None, value: Any) -> int | None:
    if counter is None:
        return None
    return counter(value)
