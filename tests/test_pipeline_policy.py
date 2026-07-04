from __future__ import annotations

from pathlib import Path

from pipeline_policy import DAILY_STEP_POLICIES


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


def test_daily_step_policy_makes_failure_policy_explicit_for_every_step() -> None:
    assert all(policy.responsibility for policy in DAILY_STEP_POLICIES)
    assert all(policy.current_failure_behavior for policy in DAILY_STEP_POLICIES)
    assert all(policy.proposed_policy in {"fatal", "non_fatal"} for policy in DAILY_STEP_POLICIES)
    assert all(policy.fallback_behavior for policy in DAILY_STEP_POLICIES)
    assert all(isinstance(policy.wrapped, bool) for policy in DAILY_STEP_POLICIES)
    assert all(isinstance(policy.safe_to_wrap_now, bool) for policy in DAILY_STEP_POLICIES)


def test_daily_step_policy_marks_wrapped_steps_accurately() -> None:
    wrapped = {policy.name for policy in DAILY_STEP_POLICIES if policy.wrapped}

    assert wrapped == {
        "Loading historical context",
        "Collecting sources",
        "Collecting market data (yfinance / FRED)",
        "Collecting trending snapshot (OSSInsight + HuggingFace)",
        "Normalizing and deduplicating events",
        "Analyzing topics",
        "Analyzing companies",
        "Analyzing papers",
        "Analyzing GitHub projects",
        "Analyzing trending items",
        "Loading trending history",
        "Analyzing social signals",
        "Analyzing macro/geopolitical impact",
        "Analyzing market signals (MarketSignalAgent)",
        "Updating predictions",
        "Generating new predictions",
        "Generating daily brief report",
        "Saving outputs",
        "Publishing to Notion",
    }


def test_no_steps_are_deferred_after_orchestration_wrapping() -> None:
    assert {policy.name for policy in DAILY_STEP_POLICIES if not policy.safe_to_wrap_now} == set()


def test_wrapped_policy_steps_are_present_in_daily_pipeline_definitions() -> None:
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
        if policy.wrapped:
            assert definitions_by_name[policy.name].policy is policy


def test_run_daily_delegates_step_execution_to_daily_pipeline() -> None:
    source = Path("scripts/run_daily.py").read_text(encoding="utf-8")

    assert "execute_daily_pipeline(runtime, step_printer=_step)" in source
    assert "PipelineStep(" not in source
    assert "run_recorded_step(" not in source


def test_run_daily_retains_cli_context_state_and_summary_boundaries() -> None:
    source = Path("scripts/run_daily.py").read_text(encoding="utf-8")

    assert "argparse.ArgumentParser" in source
    assert "RunContext.from_config" in source
    assert "TechDailyState(" in source
    assert "Report:" in source
