"""Shared retry/backoff helpers for collector network calls."""

from __future__ import annotations

import asyncio
import inspect
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar, cast, overload

from collectors.telemetry import CollectorWarning

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 2
    initial_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    jitter_seconds: float = 0.0
    retryable: Callable[[BaseException], bool] | None = None


DEFAULT_RETRY_CONFIG = RetryConfig()


def retryable_network_error(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and 400 <= status_code < 500 and status_code not in (408, 429):
        return False
    return isinstance(exc, Exception)


NETWORK_RETRY_CONFIG = RetryConfig(retryable=retryable_network_error)


def _is_retryable(exc: BaseException, config: RetryConfig) -> bool:
    if config.retryable is not None:
        return config.retryable(exc)
    return isinstance(exc, Exception)


def _delay_for_attempt(attempt_index: int, config: RetryConfig) -> float:
    base_delay = config.initial_delay_seconds * (config.backoff_multiplier ** max(0, attempt_index - 1))
    if config.jitter_seconds <= 0:
        return base_delay
    return base_delay + random.uniform(0, config.jitter_seconds)


def _warning_message(operation_name: str, attempt: int, max_attempts: int, exc: BaseException, suffix: str) -> str:
    return f"{operation_name}: attempt {attempt}/{max_attempts} failed: {exc}{suffix}"


def _append_warning(
    warnings: list[CollectorWarning] | None,
    *,
    operation_name: str,
    attempt: int,
    max_attempts: int,
    exc: BaseException,
    suffix: str = "",
) -> None:
    if warnings is None:
        return
    warnings.append(
        CollectorWarning(
            message=_warning_message(operation_name, attempt, max_attempts, exc, suffix),
            exception_type=type(exc).__name__,
        )
    )


@overload
async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    warnings: list[CollectorWarning] | None = None,
    config: RetryConfig | None = None,
) -> T: ...


@overload
async def retry_async(
    func: Callable[[], T],
    *,
    operation_name: str,
    warnings: list[CollectorWarning] | None = None,
    config: RetryConfig | None = None,
) -> T: ...


async def retry_async(
    func: Callable[[], T | Awaitable[T]],
    *,
    operation_name: str,
    warnings: list[CollectorWarning] | None = None,
    config: RetryConfig | None = None,
) -> T:
    config = config or DEFAULT_RETRY_CONFIG
    max_attempts = max(1, config.max_attempts)
    for attempt in range(1, max_attempts + 1):
        try:
            result = func()
            if inspect.isawaitable(result):
                return await cast(Awaitable[T], result)
            return result
        except BaseException as exc:
            retryable = _is_retryable(exc, config)
            final_attempt = attempt >= max_attempts
            if not retryable:
                _append_warning(
                    warnings,
                    operation_name=operation_name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exc=exc,
                    suffix="; non-retryable",
                )
                raise
            if final_attempt:
                _append_warning(
                    warnings,
                    operation_name=operation_name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exc=exc,
                    suffix="; giving up",
                )
                raise
            _append_warning(
                warnings,
                operation_name=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                exc=exc,
            )
            delay = _delay_for_attempt(attempt, config)
            if delay > 0:
                await asyncio.sleep(delay)
    raise RuntimeError("unreachable retry state")


def retry_sync(
    func: Callable[[], T],
    *,
    operation_name: str,
    warnings: list[CollectorWarning] | None = None,
    config: RetryConfig | None = None,
) -> T:
    config = config or DEFAULT_RETRY_CONFIG
    max_attempts = max(1, config.max_attempts)
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except BaseException as exc:
            retryable = _is_retryable(exc, config)
            final_attempt = attempt >= max_attempts
            if not retryable:
                _append_warning(
                    warnings,
                    operation_name=operation_name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exc=exc,
                    suffix="; non-retryable",
                )
                raise
            if final_attempt:
                _append_warning(
                    warnings,
                    operation_name=operation_name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exc=exc,
                    suffix="; giving up",
                )
                raise
            _append_warning(
                warnings,
                operation_name=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                exc=exc,
            )
            delay = _delay_for_attempt(attempt, config)
            if delay > 0:
                time.sleep(delay)
    raise RuntimeError("unreachable retry state")
