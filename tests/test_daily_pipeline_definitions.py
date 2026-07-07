from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
from state import TechDailyState

from tech_daily.pipeline import daily as daily_pipeline
from tech_daily.pipeline.daily import DailyPipelineRuntime, DailyStepDefinition, build_daily_step_definitions
from tech_daily.pipeline.policy import DAILY_STEP_POLICIES, DailyStepPolicy, StepId
from tech_daily.runtime.run_context import AppConfig, RunContext
from tech_daily.runtime.run_logging import RunLogger


@pytest.fixture
def fake_daily_runtime(tmp_path: Path) -> DailyPipelineRuntime:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-test",
        root_dir=tmp_path,
        config={},
    )
    return DailyPipelineRuntime(
        state=state,
        context=context,
        cfg={},
        app_config=AppConfig({}),
        logger=RunLogger(context),
        root_dir=str(tmp_path),
    )


def _runtime(tmp_path: Path, config: dict | None = None) -> DailyPipelineRuntime:
    raw_config = config or {
        "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
        "market_signal": {"enabled": False, "live_data": False},
        "notion": {"enabled": False},
        "trending": {"top_n": 5},
    }
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config=raw_config,
    )
    state = TechDailyState(
        run_id=context.run_id,
        run_date=context.run_date,
        time_window=context.time_window,
    )
    return DailyPipelineRuntime(
        state=state,
        context=context,
        cfg=raw_config,
        app_config=AppConfig(raw_config),
        logger=RunLogger(context),
    )


def test_daily_step_definitions_match_policy_order(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    assert [definition.name for definition in build_daily_step_definitions(runtime)] == [
        policy.name for policy in DAILY_STEP_POLICIES
    ]


def test_daily_step_definitions_match_policy_step_id_order(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    assert [definition.step_id for definition in build_daily_step_definitions(runtime)] == [
        policy.step_id for policy in DAILY_STEP_POLICIES
    ]


def test_every_step_policy_has_one_executable_definition(fake_daily_runtime: DailyPipelineRuntime) -> None:
    definitions = build_daily_step_definitions(fake_daily_runtime)
    policy_ids = [policy.step_id for policy in DAILY_STEP_POLICIES]
    definition_ids = [definition.step_id for definition in definitions]

    assert definition_ids == policy_ids
    assert len(definition_ids) == len(set(definition_ids))


def test_executable_definition_fatal_flag_matches_policy(fake_daily_runtime: DailyPipelineRuntime) -> None:
    for definition in build_daily_step_definitions(fake_daily_runtime):
        assert definition.fatal == (definition.policy.proposed_policy == "fatal")


def test_daily_step_definitions_have_policy_entries(tmp_path: Path) -> None:
    policy_names = {policy.name for policy in DAILY_STEP_POLICIES}

    assert {definition.name for definition in build_daily_step_definitions(_runtime(tmp_path))} == policy_names


def test_daily_step_definitions_reference_policy_objects(tmp_path: Path) -> None:
    policies_by_name = {policy.name: policy for policy in DAILY_STEP_POLICIES}

    for definition in build_daily_step_definitions(_runtime(tmp_path)):
        assert definition.policy is policies_by_name[definition.name]
        assert definition.step_id is definition.policy.step_id
        assert definition.fatal is (definition.policy.proposed_policy == "fatal")


def test_daily_step_definition_does_not_store_duplicated_policy_fields() -> None:
    definition_fields = {field.name for field in fields(DailyStepDefinition)}

    assert "policy" in definition_fields
    assert "name" not in definition_fields
    assert "fatal" not in definition_fields


def test_conditional_steps_are_explicit(tmp_path: Path) -> None:
    disabled_runtime = _runtime(tmp_path)
    disabled = {
        definition.name: definition.enabled(disabled_runtime)
        for definition in build_daily_step_definitions(disabled_runtime)
    }

    assert disabled["Collecting market data (yfinance / FRED)"] is False
    assert disabled["Analyzing market signals (MarketSignalAgent)"] is False
    assert disabled["Publishing to Notion"] is False

    enabled_runtime = _runtime(
        tmp_path,
        {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": True, "live_data": True},
            "notion": {"enabled": True},
            "trending": {"top_n": 5},
        },
    )
    enabled = {
        definition.name: definition.enabled(enabled_runtime)
        for definition in build_daily_step_definitions(enabled_runtime)
    }

    assert enabled["Collecting market data (yfinance / FRED)"] is True
    assert enabled["Analyzing market signals (MarketSignalAgent)"] is True
    assert enabled["Publishing to Notion"] is True


def test_trending_analysis_steps_depend_on_snapshot(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    definitions = {definition.name: definition for definition in build_daily_step_definitions(runtime)}

    assert definitions["Loading trending history"].enabled(runtime) is False
    assert definitions["Analyzing trending items"].enabled(runtime) is False

    runtime.trending_snapshot = {"snapshot_date": "2026-07-02"}

    assert definitions["Loading trending history"].enabled(runtime) is True
    assert definitions["Analyzing trending items"].enabled(runtime) is False

    runtime.trending_history = []

    assert definitions["Analyzing trending items"].enabled(runtime) is True


def test_trending_history_special_case_uses_step_id_not_display_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    renamed_policy = DailyStepPolicy(
        step_id=StepId.LOAD_TRENDING_HISTORY,
        name="Renamed history loader",
        responsibility="Fixture",
        current_failure_behavior="Fixture",
        proposed_policy="fatal",
        fallback_behavior="Fixture",
    )

    def fail_history(_: DailyPipelineRuntime) -> list[object]:
        raise RuntimeError("fixture history failure")

    monkeypatch.setattr(
        daily_pipeline,
        "build_daily_step_definitions",
        lambda _: [
            DailyStepDefinition(
                policy=renamed_policy,
                action=fail_history,
                record_count=len,
                failure_message="trending history loading failed",
            )
        ],
    )

    daily_pipeline.execute_daily_pipeline(runtime, step_printer=lambda _: None)

    assert runtime.trending_history is None
