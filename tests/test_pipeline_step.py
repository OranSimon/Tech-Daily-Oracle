from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from pipeline_step import (
    PipelineStep,
    PipelineStepResult,
    log_step_summary,
    run_recorded_step,
    run_step,
    summarize_step_results,
)
from run_context import RunContext
from run_logging import RunLogger


def _logger(tmp_path: Path) -> tuple[RunLogger, StringIO]:
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config={},
    )
    output = StringIO()
    return RunLogger(context, output=output, json_lines=True), output


def test_pipeline_step_logs_success_with_duration_and_record_count(tmp_path: Path) -> None:
    logger, output = _logger(tmp_path)

    result = run_step(
        PipelineStep(
            name="Collecting sources",
            action=lambda: ["a", "b"],
            record_count=len,
        ),
        logger,
    )

    event = json.loads(output.getvalue())
    assert result.success is True
    assert result.value == ["a", "b"]
    assert result.record_count == 2
    assert result.duration_seconds >= 0
    assert event["step"] == "Collecting sources"
    assert event["severity"] == "info"
    assert event["message"] == "completed"
    assert event["record_count"] == 2
    assert event["duration_seconds"] >= 0


def test_pipeline_step_logs_failure_with_structured_error(tmp_path: Path) -> None:
    logger, output = _logger(tmp_path)

    def fail() -> list[str]:
        raise RuntimeError("network timeout")

    result = run_step(
        PipelineStep(
            name="Collecting sources",
            action=fail,
            fallback=[],
            record_count=len,
            failure_message="source collection failed",
        ),
        logger,
    )

    event = json.loads(output.getvalue())
    assert result.success is False
    assert result.value == []
    assert result.record_count == 0
    assert result.error == "network timeout"
    assert event["severity"] == "error"
    assert event["message"] == "source collection failed"
    assert event["error"] == "network timeout"
    assert event["record_count"] == 0


def test_fatal_pipeline_step_failure_propagates_after_logging(tmp_path: Path) -> None:
    logger, output = _logger(tmp_path)

    def fail() -> None:
        raise ValueError("bad config")

    with pytest.raises(ValueError, match="bad config"):
        run_step(PipelineStep(name="Fatal step", action=fail, fatal=True), logger)

    event = json.loads(output.getvalue())
    assert event["severity"] == "error"
    assert event["error"] == "bad config"


def test_non_fatal_pipeline_step_failure_is_captured(tmp_path: Path) -> None:
    logger, output = _logger(tmp_path)

    result = run_step(
        PipelineStep(
            name="Optional step",
            action=lambda: (_ for _ in ()).throw(RuntimeError("optional failure")),
            fallback={"fallback": True},
            fatal=False,
        ),
        logger,
    )

    assert result.success is False
    assert result.value == {"fallback": True}
    assert result.error == "optional failure"
    assert json.loads(output.getvalue())["severity"] == "error"


def test_step_summary_includes_status_duration_counts_and_errors() -> None:
    summary = summarize_step_results(
        [
            PipelineStepResult(
                name="Collecting sources",
                success=True,
                duration_seconds=1.25,
                record_count=4,
            ),
            PipelineStepResult(
                name="Collecting trending snapshot",
                success=False,
                duration_seconds=0.5,
                record_count=None,
                error="upstream unavailable",
            ),
        ]
    )

    assert summary == {
        "total_steps": 2,
        "successful_steps": 1,
        "failed_steps": 1,
        "total_duration_seconds": 1.75,
        "steps": [
            {
                "name": "Collecting sources",
                "success": True,
                "duration_seconds": 1.25,
                "record_count": 4,
                "error": None,
            },
            {
                "name": "Collecting trending snapshot",
                "success": False,
                "duration_seconds": 0.5,
                "record_count": None,
                "error": "upstream unavailable",
            },
        ],
    }


def test_step_summary_can_be_emitted_through_run_logger(tmp_path: Path) -> None:
    logger, output = _logger(tmp_path)

    log_step_summary(
        [
            PipelineStepResult(
                name="Normalizing and deduplicating events",
                success=True,
                duration_seconds=0.25,
                record_count=3,
            )
        ],
        logger,
    )

    event = json.loads(output.getvalue())
    assert event["step"] == "run"
    assert event["severity"] == "info"
    assert event["message"] == "step_summary"
    assert event["details"]["total_steps"] == 1
    assert event["details"]["steps"][0]["record_count"] == 3


def test_step_summary_includes_only_executed_steps() -> None:
    summary = summarize_step_results(
        [
            PipelineStepResult(
                name="Collecting sources",
                success=True,
                duration_seconds=0.1,
            ),
            PipelineStepResult(
                name="Generating daily brief report",
                success=True,
                duration_seconds=0.2,
            ),
        ]
    )

    assert [step["name"] for step in summary["steps"]] == [
        "Collecting sources",
        "Generating daily brief report",
    ]
    assert "Publishing to Notion" not in {step["name"] for step in summary["steps"]}


def test_step_summary_logging_does_not_mutate_report_text(tmp_path: Path) -> None:
    logger, _output = _logger(tmp_path)
    report = "# Tech Daily Brief\n\nFixture report.\n"

    log_step_summary(
        [
            PipelineStepResult(
                name="Generating daily brief report",
                success=True,
                duration_seconds=0.1,
            )
        ],
        logger,
    )

    assert report == "# Tech Daily Brief\n\nFixture report.\n"


def test_run_recorded_step_appends_result(tmp_path: Path) -> None:
    logger, _output = _logger(tmp_path)
    results: list[PipelineStepResult] = []

    result = run_recorded_step(
        PipelineStep(name="Recorded step", action=lambda: ["fixture"], record_count=len),
        logger,
        results,
    )

    assert result.success is True
    assert result.record_count == 1
    assert results == [result]
