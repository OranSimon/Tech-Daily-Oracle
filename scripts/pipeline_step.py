"""Compatibility wrapper for pipeline step package module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.pipeline.step import (  # noqa: E402
    PipelineStep,
    PipelineStepResult,
    log_step_summary,
    run_recorded_step,
    run_step,
    summarize_step_results,
)

__all__ = [
    "PipelineStep",
    "PipelineStepResult",
    "log_step_summary",
    "run_recorded_step",
    "run_step",
    "summarize_step_results",
]
