#!/usr/bin/env python3
"""Inspect recent collector telemetry from data/collector_runs.jsonl."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, TextIO

from storage import load_collector_telemetry
from tech_daily.storage.validation import StorageDiagnostics

STATUSES = ("success", "partial", "failed", "skipped")


@dataclass
class CollectorSummary:
    collector_name: str
    counts: dict[str, int]
    latest_status: str
    latest_record_count: int
    average_duration_seconds: float


@dataclass
class HealthThresholds:
    max_failed_rate: float | None
    max_partial_rate: float | None
    max_consecutive_failures: int | None
    min_record_count: int | None
    max_avg_duration: float | None
    require_recent_success: bool


def _parse_args(args: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize recent collector health from local telemetry.",
    )
    parser.add_argument("--days", type=int, default=7, help="Show telemetry from the last N days.")
    parser.add_argument("--collector", default="", help="Filter to one collector name.")
    parser.add_argument("--status", choices=STATUSES, default="", help="Filter to one collector status.")
    parser.add_argument("--limit", type=int, default=50, help="Limit rows considered after filtering.")
    parser.add_argument("--health-check", action="store_true", help="Return nonzero when thresholds are violated.")
    parser.add_argument(
        "--max-failed-rate", type=float, default=None, help="Fail when failed / total exceeds this rate."
    )
    parser.add_argument(
        "--max-partial-rate", type=float, default=None, help="Fail when partial / total exceeds this rate."
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=None,
        help="Fail when latest consecutive failed runs exceed this count.",
    )
    parser.add_argument(
        "--min-record-count", type=int, default=None, help="Fail when latest record count is below this."
    )
    parser.add_argument(
        "--max-avg-duration",
        type=float,
        default=None,
        help="Fail when average duration in seconds exceeds this value.",
    )
    parser.add_argument("--require-recent-success", action="store_true", help="Fail unless latest status is success.")
    return parser.parse_args(args)


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    timestamp = row.get("timestamp", "")
    run_date = row.get("run_date", "")
    return (str(timestamp), str(run_date))


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    days: int,
    collector: str,
    status: str,
    limit: int,
    as_of_date: date,
) -> list[dict[str, Any]]:
    cutoff = (as_of_date - timedelta(days=days)).isoformat()
    filtered = [row for row in rows if str(row.get("run_date", "")) >= cutoff]
    if collector:
        filtered = [row for row in filtered if row.get("collector_name") == collector]
    if status:
        filtered = [row for row in filtered if row.get("status") == status]

    filtered = sorted(filtered, key=_row_sort_key)
    if limit > 0:
        return filtered[-limit:]
    return filtered


def _summarize(rows: list[dict[str, Any]]) -> list[CollectorSummary]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["collector_name"])].append(row)

    summaries: list[CollectorSummary] = []
    for collector_name, collector_rows in sorted(grouped.items()):
        ordered = sorted(collector_rows, key=_row_sort_key)
        counts = {status: 0 for status in STATUSES}
        total_duration = 0.0
        for row in ordered:
            row_status = str(row["status"])
            counts[row_status] += 1
            total_duration += float(row["duration_seconds"])
        latest = ordered[-1]
        summaries.append(
            CollectorSummary(
                collector_name=collector_name,
                counts=counts,
                latest_status=str(latest["status"]),
                latest_record_count=int(latest["record_count"]),
                average_duration_seconds=total_duration / len(ordered),
            )
        )
    return summaries


def _latest_consecutive_failures(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in sorted(rows, key=_row_sort_key, reverse=True):
        if row["status"] != "failed":
            break
        count += 1
    return count


def evaluate_health(
    rows: list[dict[str, Any]],
    *,
    thresholds: HealthThresholds,
) -> list[str]:
    violations: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["collector_name"])].append(row)

    for collector_name, collector_rows in sorted(grouped.items()):
        ordered = sorted(collector_rows, key=_row_sort_key)
        total = len(ordered)
        summary = _summarize(ordered)[0]
        failed_rate = summary.counts["failed"] / total
        partial_rate = summary.counts["partial"] / total

        if thresholds.max_failed_rate is not None and failed_rate > thresholds.max_failed_rate:
            violations.append(
                f"{collector_name} failed rate {failed_rate:.2f} exceeds {thresholds.max_failed_rate:.2f}"
            )

        if thresholds.max_partial_rate is not None and partial_rate > thresholds.max_partial_rate:
            violations.append(
                f"{collector_name} partial rate {partial_rate:.2f} exceeds {thresholds.max_partial_rate:.2f}"
            )

        consecutive_failures = _latest_consecutive_failures(ordered)
        if (
            thresholds.max_consecutive_failures is not None
            and consecutive_failures > thresholds.max_consecutive_failures
        ):
            violations.append(
                f"{collector_name} consecutive failures {consecutive_failures} "
                f"exceeds {thresholds.max_consecutive_failures}"
            )

        if thresholds.min_record_count is not None and summary.latest_record_count < thresholds.min_record_count:
            violations.append(
                f"{collector_name} latest record count {summary.latest_record_count} "
                f"is below {thresholds.min_record_count}"
            )

        if thresholds.max_avg_duration is not None and summary.average_duration_seconds > thresholds.max_avg_duration:
            violations.append(
                f"{collector_name} average duration {summary.average_duration_seconds:.2f}s "
                f"exceeds {thresholds.max_avg_duration:.2f}s"
            )

        if thresholds.require_recent_success and summary.latest_status != "success":
            violations.append(f"{collector_name} latest status {summary.latest_status} is not success")

    return violations


def _warning_lines(rows: list[dict[str, Any]], *, limit: int = 10) -> list[str]:
    lines: list[str] = []
    for row in sorted(rows, key=_row_sort_key, reverse=True):
        messages: list[str] = []
        error_message = row.get("error_message")
        if error_message:
            messages.append(str(error_message))
        for warning in row.get("warnings", []):
            if isinstance(warning, dict) and warning.get("message"):
                messages.append(str(warning["message"]))
        for message in messages:
            lines.append(f"- {row['run_date']} {row['collector_name']} [{row['status']}] {message}")
            if len(lines) >= limit:
                return lines
    return lines


def render_summary(
    rows: list[dict[str, Any]],
    *,
    days: int,
    malformed_count: int,
    output: TextIO,
) -> None:
    print(f"Collector Health (last {days} days)", file=output)
    print(f"Rows analyzed: {len(rows)}", file=output)
    if malformed_count:
        print(f"Malformed telemetry rows skipped: {malformed_count}", file=output)
    print("", file=output)

    if not rows:
        print("No collector telemetry found for the selected filters.", file=output)
        return

    print(
        "| Collector | Success | Partial | Failed | Skipped | Latest Status | Latest Records | Avg Duration |",
        file=output,
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |", file=output)
    for summary in _summarize(rows):
        print(
            f"| {summary.collector_name} | "
            f"{summary.counts['success']} | "
            f"{summary.counts['partial']} | "
            f"{summary.counts['failed']} | "
            f"{summary.counts['skipped']} | "
            f"{summary.latest_status} | "
            f"{summary.latest_record_count} | "
            f"{summary.average_duration_seconds:.2f}s |",
            file=output,
        )

    print("", file=output)
    print("Recent warnings/errors:", file=output)
    warning_lines = _warning_lines(rows)
    if warning_lines:
        for line in warning_lines:
            print(line, file=output)
    else:
        print("No recent warnings or errors.", file=output)


def render_health_check(
    rows: list[dict[str, Any]],
    *,
    thresholds: HealthThresholds,
    malformed_count: int,
    output: TextIO,
) -> int:
    if malformed_count:
        print(f"Malformed telemetry rows skipped: {malformed_count}", file=output)

    if not rows:
        print("No collector telemetry found for the selected filters.", file=output)
        return 1

    violations = evaluate_health(rows, thresholds=thresholds)
    if violations:
        print("Health check failed.", file=output)
        for violation in violations:
            print(f"- {violation}", file=output)
        return 1

    print("Health check passed.", file=output)
    return 0


def main(
    args: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
    as_of_date: date | None = None,
) -> int:
    parsed = _parse_args(args)
    diagnostics = StorageDiagnostics()
    rows = load_collector_telemetry(diagnostics=diagnostics)
    filtered = _filter_rows(
        rows,
        days=parsed.days,
        collector=parsed.collector,
        status=parsed.status,
        limit=parsed.limit,
        as_of_date=as_of_date or date.today(),
    )
    thresholds = HealthThresholds(
        max_failed_rate=parsed.max_failed_rate,
        max_partial_rate=parsed.max_partial_rate,
        max_consecutive_failures=parsed.max_consecutive_failures,
        min_record_count=parsed.min_record_count,
        max_avg_duration=parsed.max_avg_duration,
        require_recent_success=parsed.require_recent_success,
    )
    if parsed.health_check:
        return render_health_check(
            filtered,
            thresholds=thresholds,
            malformed_count=len(diagnostics.warnings),
            output=output,
        )

    render_summary(
        filtered,
        days=parsed.days,
        malformed_count=len(diagnostics.warnings),
        output=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
