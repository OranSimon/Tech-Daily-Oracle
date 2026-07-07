from __future__ import annotations

from pathlib import Path

from pipeline_policy import DAILY_STEP_POLICIES, StepId


def test_daily_step_policy_classifies_all_major_steps_in_order() -> None:
    assert [policy.name for policy in DAILY_STEP_POLICIES] == [
        "Loading historical context",
        "Collecting sources",
        "Collecting market data (yfinance / FRED)",
        "Collecting trending snapshot (OSSInsight + HuggingFace)",
        "Normalizing and deduplicating events",
        "Analyzing topics",
        "Analyzing companies",
        "Analyzing papers",
        "Analyzing GitHub projects",
        "Loading trending history",
        "Analyzing trending items",
        "Analyzing social signals",
        "Analyzing macro/geopolitical impact",
        "Analyzing market signals (MarketSignalAgent)",
        "Updating predictions",
        "Generating new predictions",
        "Generating daily brief report",
        "Saving outputs",
        "Publishing to Notion",
    ]


def test_daily_step_policy_has_stable_step_ids_in_order() -> None:
    assert [policy.step_id for policy in DAILY_STEP_POLICIES] == [
        StepId.LOAD_HISTORICAL_CONTEXT,
        StepId.COLLECT_SOURCES,
        StepId.COLLECT_MARKET_DATA,
        StepId.COLLECT_TRENDING_SNAPSHOT,
        StepId.NORMALIZE_EVENTS,
        StepId.ANALYZE_TOPICS,
        StepId.ANALYZE_COMPANIES,
        StepId.ANALYZE_PAPERS,
        StepId.ANALYZE_GITHUB_PROJECTS,
        StepId.LOAD_TRENDING_HISTORY,
        StepId.ANALYZE_TRENDING,
        StepId.ANALYZE_SOCIAL_SIGNALS,
        StepId.ANALYZE_MACRO_IMPACT,
        StepId.ANALYZE_MARKET_SIGNALS,
        StepId.UPDATE_PREDICTIONS,
        StepId.GENERATE_NEW_PREDICTIONS,
        StepId.GENERATE_DAILY_REPORT,
        StepId.SAVE_OUTPUTS,
        StepId.PUBLISH_TO_NOTION,
    ]

    assert len({policy.step_id for policy in DAILY_STEP_POLICIES}) == len(DAILY_STEP_POLICIES)


def test_daily_step_policy_makes_failure_policy_explicit_for_every_step() -> None:
    assert all(policy.responsibility for policy in DAILY_STEP_POLICIES)
    assert all(policy.current_failure_behavior for policy in DAILY_STEP_POLICIES)
    assert all(policy.proposed_policy in {"fatal", "non_fatal"} for policy in DAILY_STEP_POLICIES)
    assert all(policy.fallback_behavior for policy in DAILY_STEP_POLICIES)


def test_daily_step_policy_does_not_duplicate_runtime_definition_state() -> None:
    from dataclasses import fields

    from pipeline_policy import DailyStepPolicy

    policy_fields = {field.name for field in fields(DailyStepPolicy)}

    assert "wrapped" not in policy_fields
    assert "safe_to_wrap_now" not in policy_fields


def test_policy_steps_are_present_in_daily_pipeline_definitions() -> None:
    from daily_pipeline import DailyPipelineRuntime, build_daily_step_definitions
    from run_context import AppConfig, RunContext
    from run_logging import RunLogger
    from state import TechDailyState

    raw_config = {
        "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
        "market_signal": {"enabled": False, "live_data": False},
        "notion": {"enabled": False},
        "trending": {"top_n": 5},
    }
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=".",
        config=raw_config,
    )
    runtime = DailyPipelineRuntime(
        state=TechDailyState(context.run_id, context.run_date, context.time_window),
        context=context,
        cfg=raw_config,
        app_config=AppConfig(raw_config),
        logger=RunLogger(context),
    )
    definitions_by_name = {definition.name: definition for definition in build_daily_step_definitions(runtime)}

    for policy in DAILY_STEP_POLICIES:
        assert definitions_by_name[policy.name].policy is policy
        assert definitions_by_name[policy.name].step_id is policy.step_id


def test_daily_pipeline_uses_step_ids_not_display_names_for_policy_lookup() -> None:
    source = Path("src/tech_daily/pipeline/daily.py").read_text(encoding="utf-8")

    assert 'get_daily_step_policy("' not in source
    assert 'definition.name == "' not in source
    assert "StepId." in source
    assert "definition.step_id == StepId.LOAD_TRENDING_HISTORY" in source


def test_run_daily_delegates_step_execution_to_daily_pipeline() -> None:
    source = Path("src/tech_daily/cli/run_daily.py").read_text(encoding="utf-8")

    assert "execute_daily_pipeline(runtime, step_printer=_step)" in source
    assert "PipelineStep(" not in source
    assert "run_recorded_step(" not in source


def test_run_daily_retains_cli_context_state_and_summary_boundaries() -> None:
    source = Path("src/tech_daily/cli/run_daily.py").read_text(encoding="utf-8")

    assert "build_daily_arg_parser" in source
    assert "argparse.ArgumentParser" not in source
    assert "RunContext.from_config" in source
    assert "TechDailyState(" in source
    assert "Report:" in source
