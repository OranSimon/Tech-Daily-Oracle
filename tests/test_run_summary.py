from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from state import TechDailyState

from tech_daily.pipeline.daily import DailyPipelineRuntime, DailyStepDefinition, execute_daily_pipeline
from tech_daily.pipeline.policy import StepId, get_daily_step_policy
from tech_daily.pipeline.step import PipelineStepResult
from tech_daily.runtime.run_context import AppConfig, RunContext
from tech_daily.runtime.run_logging import RunLogger
from tech_daily.storage.context import StorageContext


def test_run_summary_row_is_small_and_stable() -> None:
    from tech_daily.pipeline.run_summary import RunStepSummary, RunSummary, run_summary_row

    summary = RunSummary(
        run_date="2026-07-02",
        run_id="run-test",
        steps=[
            RunStepSummary(
                step_name="Collecting sources",
                success=True,
                duration_seconds=0.1,
                record_count=2,
                error=None,
            )
        ],
    )

    assert run_summary_row(summary) == {
        "run_date": "2026-07-02",
        "run_id": "run-test",
        "steps": [
            {
                "step_name": "Collecting sources",
                "success": True,
                "duration_seconds": 0.1,
                "record_count": 2,
                "error": None,
            }
        ],
    }


def test_save_run_summary_writes_jsonl_without_changing_reports(tmp_path: Path) -> None:
    from tech_daily.pipeline.run_summary import RunSummary
    from tech_daily.storage.run_summary import save_run_summary

    context = StorageContext.from_root(tmp_path)
    summary = RunSummary(run_date="2026-07-02", run_id="run-test", steps=[])

    save_run_summary(summary, storage_context=context)

    path = context.data_dir / "run_summaries.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"run_date": "2026-07-02", "run_id": "run-test", "steps": []}]
    assert context.data_dir.exists() is True
    assert context.reports_dir.exists() is False
    assert context.reports_dir / "daily" == context.daily_report_path("2026-07-02").parent
    assert context.daily_report_path("2026-07-02").exists() is False
    assert context.weekly_report_path("2026-W27").exists() is False
    assert context.monthly_report_path("2026-07").exists() is False


def test_execute_daily_pipeline_saves_run_summary_in_runtime_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_root = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    workspace_root.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=workspace_root,
        config={},
    )
    runtime = DailyPipelineRuntime(
        state=TechDailyState(run_id=context.run_id, run_date=context.run_date, time_window=context.time_window),
        context=context,
        cfg={},
        app_config=AppConfig({}),
        logger=RunLogger(context, output=StringIO(), json_lines=True),
    )
    policy = get_daily_step_policy(StepId.COLLECT_SOURCES)

    monkeypatch.setattr(
        "tech_daily.pipeline.daily.build_daily_step_definitions",
        lambda _runtime: [
            DailyStepDefinition(
                policy=policy,
                action=lambda _: ["fixture"],
                record_count=len,
            )
        ],
    )

    result = execute_daily_pipeline(runtime, step_printer=lambda _: None)

    summary_path = workspace_root / "data" / "run_summaries.jsonl"
    rows = [json.loads(line) for line in summary_path.read_text(encoding="utf-8").splitlines()]

    assert result.step_results == [
        PipelineStepResult(
            name=policy.name,
            success=True,
            duration_seconds=runtime.step_results[0].duration_seconds,
            value=["fixture"],
            record_count=1,
            error=None,
            exception=None,
        )
    ]
    assert rows == [
        {
            "run_date": "2026-07-02",
            "run_id": "run-fixture",
            "steps": [
                {
                    "step_name": policy.name,
                    "success": True,
                    "duration_seconds": runtime.step_results[0].duration_seconds,
                    "record_count": 1,
                    "error": None,
                }
            ],
        }
    ]
    assert (elsewhere / "data" / "run_summaries.jsonl").exists() is False


def test_execute_daily_pipeline_treats_run_summary_persistence_failure_as_non_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config={},
    )
    runtime = DailyPipelineRuntime(
        state=TechDailyState(run_id=context.run_id, run_date=context.run_date, time_window=context.time_window),
        context=context,
        cfg={},
        app_config=AppConfig({}),
        logger=RunLogger(context, output=StringIO(), json_lines=True),
    )
    policy = get_daily_step_policy(StepId.COLLECT_SOURCES)

    monkeypatch.setattr(
        "tech_daily.pipeline.daily.build_daily_step_definitions",
        lambda _runtime: [
            DailyStepDefinition(
                policy=policy,
                action=lambda _: ["fixture"],
                record_count=len,
            )
        ],
    )
    monkeypatch.setattr(
        "tech_daily.storage.run_summary.save_run_summary",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )

    result = execute_daily_pipeline(runtime, step_printer=lambda _: None)

    assert len(result.step_results) == 1
    assert result.step_results[0].success is True
    assert "Failed to save run summary (non-fatal): disk full" in capsys.readouterr().out
