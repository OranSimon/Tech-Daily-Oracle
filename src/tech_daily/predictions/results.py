"""Typed result wrappers for prediction operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PredictionOperationResult(Generic[T]):
    value: T
    success: bool
    warnings: list[str] = field(default_factory=list)
    error_kind: str | None = None
    error_message: str | None = None

    @classmethod
    def ok(
        cls,
        value: T,
        warnings: list[str] | None = None,
    ) -> PredictionOperationResult[T]:
        return cls(value=value, success=True, warnings=list(warnings or []))

    @classmethod
    def failed(
        cls,
        value: T,
        *,
        error_kind: str,
        error_message: str,
    ) -> PredictionOperationResult[T]:
        return cls(
            value=value,
            success=False,
            error_kind=error_kind,
            error_message=error_message,
        )
