"""Explicit daily pipeline step classification.

This table documents current behavior. It does not drive orchestration yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StepPolicy = Literal["fatal", "non_fatal"]


@dataclass(frozen=True)
class DailyStepPolicy:
    name: str
    responsibility: str
    current_failure_behavior: str
    proposed_policy: StepPolicy
    fallback_behavior: str
    wrapped: bool
    safe_to_wrap_now: bool


DAILY_STEP_POLICIES: list[DailyStepPolicy] = [
    DailyStepPolicy(
        name="Loading historical context",
        responsibility="Load recent reports, reviews, trends, company mentions, and open predictions.",
        current_failure_behavior="Uncaught loader failures abort the run.",
        proposed_policy="fatal",
        fallback_behavior="No fallback; abort before downstream analysis.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Collecting sources",
        responsibility="Collect raw source events and persist collector telemetry.",
        current_failure_behavior="Logs an error, records a source warning, and continues with no raw events.",
        proposed_policy="non_fatal",
        fallback_behavior="Use an empty raw-event list.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Collecting market data (yfinance / FRED)",
        responsibility="Optionally collect live market data for market signal analysis.",
        current_failure_behavior="Logs a non-fatal market-data error and continues without market data.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no market data.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Collecting trending snapshot (OSSInsight + HuggingFace)",
        responsibility="Collect the daily trending snapshot used by trending analysis and optional storage.",
        current_failure_behavior="Logs a non-fatal trending collection error and continues without a snapshot.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no trending snapshot.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Normalizing and deduplicating events",
        responsibility="Normalize raw source events into canonical events.",
        current_failure_behavior="Logs an error and continues with no normalized events.",
        proposed_policy="non_fatal",
        fallback_behavior="Use an empty normalized-event list.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing topics",
        responsibility="Generate topic summaries from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave topic summaries at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing companies",
        responsibility="Generate company analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave company analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing papers",
        responsibility="Generate paper analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave paper analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing GitHub projects",
        responsibility="Generate GitHub project analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave GitHub project analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Loading trending history",
        responsibility="Load recent trending snapshots for the trending analysis step.",
        current_failure_behavior="Failure is caught by the existing trending analysis handler and skips analysis.",
        proposed_policy="fatal",
        fallback_behavior="No local fallback; raise to the non-fatal trending analysis handler.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing trending items",
        responsibility="Analyze the collected trending snapshot against recent trending history.",
        current_failure_behavior="Logs a non-fatal trending analysis error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave trending analysis at its default value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing social signals",
        responsibility="Generate social signal analyses from normalized events.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave social signal analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing macro/geopolitical impact",
        responsibility="Generate macro impact analyses using normalized events and open predictions.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave macro impact analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Analyzing market signals (MarketSignalAgent)",
        responsibility="Generate market signal analyses from state, market data, and prior signals.",
        current_failure_behavior="Logs a non-fatal market-signal error with traceback and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave market signal analyses at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Updating predictions",
        responsibility="Resolve or update existing open predictions.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave prediction updates at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Generating new predictions",
        responsibility="Generate new predictions from the day's state.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave new predictions at their default empty value.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Generating daily brief report",
        responsibility="Render the daily Markdown report.",
        current_failure_behavior="Logs an error, prints a traceback, and writes an error report body.",
        proposed_policy="non_fatal",
        fallback_behavior="Use the existing Markdown error-report fallback.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Saving outputs",
        responsibility="Persist report, predictions, events, snapshots, market signals, and optional Notion output.",
        current_failure_behavior="Core report/prediction/event writes are fatal; optional snapshot, market, and Notion writes are non-fatal.",
        proposed_policy="fatal",
        fallback_behavior="No fallback for core writes; optional sub-writes keep their local non-fatal handling.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
    DailyStepPolicy(
        name="Publishing to Notion",
        responsibility="Optionally publish the generated report to Notion.",
        current_failure_behavior="Runs only when enabled; logs a non-fatal publish error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no Notion URL.",
        wrapped=True,
        safe_to_wrap_now=True,
    ),
]

DAILY_STEP_POLICY_BY_NAME: dict[str, DailyStepPolicy] = {policy.name: policy for policy in DAILY_STEP_POLICIES}


def get_daily_step_policy(name: str) -> DailyStepPolicy:
    return DAILY_STEP_POLICY_BY_NAME[name]
