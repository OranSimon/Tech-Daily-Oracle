"""Explicit daily pipeline step classification.

This table documents current behavior. It does not drive orchestration yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

StepPolicy = Literal["fatal", "non_fatal"]


class StepId(StrEnum):
    LOAD_HISTORICAL_CONTEXT = "load_historical_context"
    COLLECT_SOURCES = "collect_sources"
    COLLECT_MARKET_DATA = "collect_market_data"
    COLLECT_TRENDING_SNAPSHOT = "collect_trending_snapshot"
    NORMALIZE_EVENTS = "normalize_events"
    ANALYZE_TOPICS = "analyze_topics"
    ANALYZE_COMPANIES = "analyze_companies"
    ANALYZE_PAPERS = "analyze_papers"
    ANALYZE_GITHUB_PROJECTS = "analyze_github_projects"
    LOAD_TRENDING_HISTORY = "load_trending_history"
    ANALYZE_TRENDING = "analyze_trending"
    ANALYZE_SOCIAL_SIGNALS = "analyze_social_signals"
    ANALYZE_MACRO_IMPACT = "analyze_macro_impact"
    ANALYZE_MARKET_SIGNALS = "analyze_market_signals"
    UPDATE_PREDICTIONS = "update_predictions"
    GENERATE_NEW_PREDICTIONS = "generate_new_predictions"
    GENERATE_DAILY_REPORT = "generate_daily_report"
    SAVE_OUTPUTS = "save_outputs"
    PUBLISH_TO_NOTION = "publish_to_notion"


@dataclass(frozen=True)
class DailyStepPolicy:
    step_id: StepId
    name: str
    responsibility: str
    current_failure_behavior: str
    proposed_policy: StepPolicy
    fallback_behavior: str


DAILY_STEP_POLICIES: list[DailyStepPolicy] = [
    DailyStepPolicy(
        step_id=StepId.LOAD_HISTORICAL_CONTEXT,
        name="Loading historical context",
        responsibility="Load recent reports, reviews, trends, company mentions, and open predictions.",
        current_failure_behavior="Uncaught loader failures abort the run.",
        proposed_policy="fatal",
        fallback_behavior="No fallback; abort before downstream analysis.",
    ),
    DailyStepPolicy(
        step_id=StepId.COLLECT_SOURCES,
        name="Collecting sources",
        responsibility="Collect raw source events and persist collector telemetry.",
        current_failure_behavior="Logs an error, records a source warning, and continues with no raw events.",
        proposed_policy="non_fatal",
        fallback_behavior="Use an empty raw-event list.",
    ),
    DailyStepPolicy(
        step_id=StepId.COLLECT_MARKET_DATA,
        name="Collecting market data (yfinance / FRED)",
        responsibility="Optionally collect live market data for market signal analysis.",
        current_failure_behavior="Logs a non-fatal market-data error and continues without market data.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no market data.",
    ),
    DailyStepPolicy(
        step_id=StepId.COLLECT_TRENDING_SNAPSHOT,
        name="Collecting trending snapshot (OSSInsight + HuggingFace)",
        responsibility="Collect the daily trending snapshot used by trending analysis and optional storage.",
        current_failure_behavior="Logs a non-fatal trending collection error and continues without a snapshot.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no trending snapshot.",
    ),
    DailyStepPolicy(
        step_id=StepId.NORMALIZE_EVENTS,
        name="Normalizing and deduplicating events",
        responsibility="Normalize raw source events into canonical events.",
        current_failure_behavior="Logs an error and continues with no normalized events.",
        proposed_policy="non_fatal",
        fallback_behavior="Use an empty normalized-event list.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_TOPICS,
        name="Analyzing topics",
        responsibility="Generate topic summaries from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave topic summaries at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_COMPANIES,
        name="Analyzing companies",
        responsibility="Generate company analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave company analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_PAPERS,
        name="Analyzing papers",
        responsibility="Generate paper analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave paper analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_GITHUB_PROJECTS,
        name="Analyzing GitHub projects",
        responsibility="Generate GitHub project analyses from normalized events.",
        current_failure_behavior="Logs an error, adds a confidence flag, and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave GitHub project analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.LOAD_TRENDING_HISTORY,
        name="Loading trending history",
        responsibility="Load recent trending snapshots for the trending analysis step.",
        current_failure_behavior="Failure is caught by the existing trending analysis handler and skips analysis.",
        proposed_policy="fatal",
        fallback_behavior="No local fallback; raise to the non-fatal trending analysis handler.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_TRENDING,
        name="Analyzing trending items",
        responsibility="Analyze the collected trending snapshot against recent trending history.",
        current_failure_behavior="Logs a non-fatal trending analysis error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave trending analysis at its default value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_SOCIAL_SIGNALS,
        name="Analyzing social signals",
        responsibility="Generate social signal analyses from normalized events.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave social signal analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_MACRO_IMPACT,
        name="Analyzing macro/geopolitical impact",
        responsibility="Generate macro impact analyses using normalized events and open predictions.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave macro impact analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.ANALYZE_MARKET_SIGNALS,
        name="Analyzing market signals (MarketSignalAgent)",
        responsibility="Generate market signal analyses from state, market data, and prior signals.",
        current_failure_behavior="Logs a non-fatal market-signal error with traceback and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave market signal analyses at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.UPDATE_PREDICTIONS,
        name="Updating predictions",
        responsibility="Resolve or update existing open predictions.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave prediction updates at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.GENERATE_NEW_PREDICTIONS,
        name="Generating new predictions",
        responsibility="Generate new predictions from the day's state.",
        current_failure_behavior="Logs an error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Leave new predictions at their default empty value.",
    ),
    DailyStepPolicy(
        step_id=StepId.GENERATE_DAILY_REPORT,
        name="Generating daily brief report",
        responsibility="Render the daily Markdown report.",
        current_failure_behavior="Logs an error, prints a traceback, and writes an error report body.",
        proposed_policy="non_fatal",
        fallback_behavior="Use the existing Markdown error-report fallback.",
    ),
    DailyStepPolicy(
        step_id=StepId.SAVE_OUTPUTS,
        name="Saving outputs",
        responsibility="Persist report, predictions, events, snapshots, market signals, and optional Notion output.",
        current_failure_behavior="Core report/prediction/event writes are fatal; optional snapshot, market, and Notion writes are non-fatal.",
        proposed_policy="fatal",
        fallback_behavior="No fallback for core writes; optional sub-writes keep their local non-fatal handling.",
    ),
    DailyStepPolicy(
        step_id=StepId.PUBLISH_TO_NOTION,
        name="Publishing to Notion",
        responsibility="Optionally publish the generated report to Notion.",
        current_failure_behavior="Runs only when enabled; logs a non-fatal publish error and continues.",
        proposed_policy="non_fatal",
        fallback_behavior="Use no Notion URL.",
    ),
]

DAILY_STEP_POLICY_BY_ID: dict[StepId, DailyStepPolicy] = {policy.step_id: policy for policy in DAILY_STEP_POLICIES}


def get_daily_step_policy(step_id: StepId) -> DailyStepPolicy:
    return DAILY_STEP_POLICY_BY_ID[step_id]


__all__ = [
    "DAILY_STEP_POLICIES",
    "DAILY_STEP_POLICY_BY_ID",
    "DailyStepPolicy",
    "StepId",
    "StepPolicy",
    "get_daily_step_policy",
]
