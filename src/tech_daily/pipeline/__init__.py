"""Pipeline foundation helpers."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from tech_daily.pipeline.policy import DailyStepPolicy, StepId, get_daily_step_policy
from tech_daily.pipeline.step import (
    PipelineStep,
    PipelineStepResult,
    log_step_summary,
    run_recorded_step,
    run_step,
    summarize_step_results,
)

if TYPE_CHECKING:
    from tech_daily.pipeline.state import CollectionState, CorpusState, PredictionState, ReportInputState

_STATE_EXPORTS = {
    "CollectionState",
    "CorpusState",
    "PredictionState",
    "ReportInputState",
}


def __getattr__(name: str) -> object:
    if name in _STATE_EXPORTS:
        return getattr(import_module("tech_daily.pipeline.state"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CollectionState",
    "CorpusState",
    "DailyStepPolicy",
    "PipelineStep",
    "PipelineStepResult",
    "PredictionState",
    "ReportInputState",
    "StepId",
    "get_daily_step_policy",
    "log_step_summary",
    "run_recorded_step",
    "run_step",
    "summarize_step_results",
]
