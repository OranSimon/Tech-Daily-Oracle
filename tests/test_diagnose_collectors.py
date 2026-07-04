from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import diagnose_collectors
import storage


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.COLLECTOR_RUNS_LOG = str(tmp_path / "data" / "collector_runs.jsonl")


def _row(
    *,
    run_date: str,
    collector_name: str,
    status: str,
    record_count: int,
    duration_seconds: float = 1.0,
    warning: str | None = None,
    error_message: str | None = None,
) -> dict[str, object]:
    return {
        "run_date": run_date,
        "run_id": f"{run_date}-{collector_name}",
        "collector_name": collector_name,
        "status": status,
        "duration_seconds": duration_seconds,
        "record_count": record_count,
        "warnings": ([{"message": warning, "exception_type": "RuntimeError"}] if warning else []),
        "error_message": error_message,
        "timestamp": f"{run_date}T01:02:03+00:00",
    }


def _write_rows(tmp_path: Path, rows: list[dict[str, object]], extra_lines: list[str] | None = None) -> None:
    _point_storage_at(tmp_path)
    path = Path(storage.COLLECTOR_RUNS_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    if extra_lines:
        lines.extend(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(args: list[str], *, as_of_date: date = date(2026, 7, 5)) -> str:
    output = io.StringIO()
    exit_code = diagnose_collectors.main(args, output=output, as_of_date=as_of_date)
    assert exit_code == 0
    return output.getvalue()


def _run_with_exit(args: list[str], *, as_of_date: date = date(2026, 7, 5)) -> tuple[int, str]:
    output = io.StringIO()
    exit_code = diagnose_collectors.main(args, output=output, as_of_date=as_of_date)
    return exit_code, output.getvalue()


def test_diagnostics_summarizes_healthy_collector_rows(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-04", collector_name="rss", status="success", record_count=3, duration_seconds=1.0),
            _row(run_date="2026-07-05", collector_name="rss", status="success", record_count=5, duration_seconds=3.0),
        ],
    )

    output = _run(["--days", "7"])

    assert "Collector Health (last 7 days)" in output
    assert "| rss | 2 | 0 | 0 | 0 | success | 5 | 2.00s |" in output
    assert "No recent warnings or errors." in output


def test_diagnostics_summarizes_failed_and_partial_collectors(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(
                run_date="2026-07-04",
                collector_name="github",
                status="partial",
                record_count=2,
                warning="retry succeeded",
            ),
            _row(
                run_date="2026-07-05",
                collector_name="github",
                status="failed",
                record_count=0,
                error_message="api unavailable",
            ),
        ],
    )

    output = _run(["--days", "7"])

    assert "| github | 0 | 1 | 1 | 0 | failed | 0 | 1.00s |" in output
    assert "- 2026-07-05 github [failed] api unavailable" in output
    assert "- 2026-07-04 github [partial] retry succeeded" in output


def test_diagnostics_filters_by_days_collector_status_and_limit(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-06-20", collector_name="rss", status="failed", record_count=0),
            _row(run_date="2026-07-04", collector_name="rss", status="failed", record_count=0),
            _row(run_date="2026-07-05", collector_name="github", status="failed", record_count=0),
        ],
    )

    output = _run(["--days", "2", "--collector", "rss", "--status", "failed", "--limit", "1"])

    assert "| rss | 0 | 0 | 1 | 0 | failed | 0 | 1.00s |" in output
    assert "github" not in output
    assert "2026-06-20" not in output


def test_diagnostics_reports_malformed_rows_without_crashing(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [_row(run_date="2026-07-05", collector_name="rss", status="success", record_count=1)],
        extra_lines=["{not json}"],
    )

    output = _run(["--days", "7"])

    assert "Malformed telemetry rows skipped: 1" in output
    assert "| rss | 1 | 0 | 0 | 0 | success | 1 | 1.00s |" in output


def test_diagnostics_empty_telemetry_file_prints_clear_message(tmp_path: Path) -> None:
    _write_rows(tmp_path, [])

    output = _run(["--days", "7"])

    assert "No collector telemetry found for the selected filters." in output


def test_health_check_passes_for_healthy_telemetry(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-04", collector_name="rss", status="success", record_count=2),
            _row(run_date="2026-07-05", collector_name="rss", status="success", record_count=3),
        ],
    )

    exit_code, output = _run_with_exit(
        ["--health-check", "--max-failed-rate", "0.1", "--min-record-count", "1", "--require-recent-success"]
    )

    assert exit_code == 0
    assert "Health check passed." in output


def test_health_check_fails_when_failed_rate_threshold_is_exceeded(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-04", collector_name="github", status="success", record_count=2),
            _row(run_date="2026-07-05", collector_name="github", status="failed", record_count=0),
        ],
    )

    exit_code, output = _run_with_exit(["--health-check", "--max-failed-rate", "0.25"])

    assert exit_code == 1
    assert "Health check failed." in output
    assert "github failed rate 0.50 exceeds 0.25" in output


def test_health_check_fails_when_consecutive_failures_exceed_threshold(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-03", collector_name="arxiv", status="success", record_count=4),
            _row(run_date="2026-07-04", collector_name="arxiv", status="failed", record_count=0),
            _row(run_date="2026-07-05", collector_name="arxiv", status="failed", record_count=0),
        ],
    )

    exit_code, output = _run_with_exit(["--health-check", "--max-consecutive-failures", "1"])

    assert exit_code == 1
    assert "arxiv consecutive failures 2 exceeds 1" in output


def test_health_check_fails_when_recent_success_is_required(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-04", collector_name="web_search", status="success", record_count=2),
            _row(run_date="2026-07-05", collector_name="web_search", status="partial", record_count=1),
        ],
    )

    exit_code, output = _run_with_exit(["--health-check", "--require-recent-success"])

    assert exit_code == 1
    assert "web_search latest status partial is not success" in output


def test_health_check_respects_collector_filter(tmp_path: Path) -> None:
    _write_rows(
        tmp_path,
        [
            _row(run_date="2026-07-05", collector_name="rss", status="success", record_count=3),
            _row(run_date="2026-07-05", collector_name="github", status="failed", record_count=0),
        ],
    )

    exit_code, output = _run_with_exit(["--health-check", "--collector", "rss", "--max-failed-rate", "0"])

    assert exit_code == 0
    assert "Health check passed." in output
    assert "github" not in output


def test_normal_summary_mode_still_exits_successfully_with_bad_health(tmp_path: Path) -> None:
    _write_rows(tmp_path, [_row(run_date="2026-07-05", collector_name="github", status="failed", record_count=0)])

    exit_code, output = _run_with_exit(["--max-failed-rate", "0"])

    assert exit_code == 0
    assert "| github | 0 | 0 | 1 | 0 | failed | 0 | 1.00s |" in output


def test_health_check_empty_or_malformed_telemetry_does_not_crash(tmp_path: Path) -> None:
    _write_rows(tmp_path, [], extra_lines=["{not json}"])

    exit_code, output = _run_with_exit(["--health-check", "--require-recent-success"])

    assert exit_code == 1
    assert "Malformed telemetry rows skipped: 1" in output
    assert "No collector telemetry found for the selected filters." in output
