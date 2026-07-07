"""Compatibility wrapper for package-owned pipeline policy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.pipeline.policy import (  # noqa: E402
    DAILY_STEP_POLICIES,
    DAILY_STEP_POLICY_BY_ID,
    DailyStepPolicy,
    StepId,
    StepPolicy,
    get_daily_step_policy,
)

__all__ = [
    "DAILY_STEP_POLICIES",
    "DAILY_STEP_POLICY_BY_ID",
    "DailyStepPolicy",
    "StepId",
    "StepPolicy",
    "get_daily_step_policy",
]
