"""Shared pipeline error taxonomy and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorDiagnostic:
    category: str
    severity: str
    message: str
    exception_type: str
    step: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "exception_type": self.exception_type,
        }
        if self.step is not None:
            data["step"] = self.step
        if self.details:
            data["details"] = self.details
        return data


class TechDailyError(Exception):
    """Base class for expected Tech Daily pipeline failures."""

    category = "pipeline"
    severity = "error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_diagnostic(self, *, step: str | None = None, severity: str | None = None) -> ErrorDiagnostic:
        return ErrorDiagnostic(
            category=self.category,
            severity=severity or self.severity,
            message=str(self),
            exception_type=type(self).__name__,
            step=step,
            details=dict(self.details),
        )


class ConfigError(TechDailyError):
    category = "config"


class StorageError(TechDailyError):
    category = "storage"


class ValidationError(TechDailyError):
    category = "validation"


class ProviderError(TechDailyError):
    category = "provider"


class AnalyzerError(TechDailyError):
    category = "analyzer"


class ReportGenerationError(TechDailyError):
    category = "report_generation"


class NonFatalStepError(TechDailyError):
    category = "non_fatal_step"
    severity = "warning"


def diagnostic_from_exception(
    exc: Exception,
    *,
    step: str | None = None,
    category: str = "unexpected",
    severity: str = "error",
    details: dict[str, Any] | None = None,
) -> ErrorDiagnostic:
    """Normalize any exception into a structured diagnostic."""
    if isinstance(exc, TechDailyError):
        return exc.to_diagnostic(step=step, severity=severity)
    return ErrorDiagnostic(
        category=category,
        severity=severity,
        message=str(exc),
        exception_type=type(exc).__name__,
        step=step,
        details=details or {},
    )
