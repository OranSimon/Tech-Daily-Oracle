from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import collect_sources
import storage
from collectors.registry import CollectorTaskGroup
from collectors.telemetry import CollectorRunResult, CollectorRunStatus, CollectorWarning
from state import RawEvent
from storage_validation import StorageDiagnostics


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")
    storage.COLLECTOR_RUNS_LOG = str(tmp_path / "data" / "collector_runs.jsonl")


def _event(source_name: str) -> RawEvent:
    return RawEvent(
        source_name=source_name,
        source_type="rss",
        raw_title=f"{source_name} title",
        raw_url=f"https://example.com/{source_name}",
        raw_content=f"{source_name} content",
        published_at="2026-07-03",
        fetched_at=datetime(2026, 7, 3, tzinfo=UTC).isoformat(),
        metadata={},
    )


async def _successful_events(*events: RawEvent) -> list[RawEvent]:
    return list(events)


def _result() -> CollectorRunResult:
    return CollectorRunResult(
        collector_name="rss",
        status=CollectorRunStatus.PARTIAL,
        duration_seconds=0.125,
        record_count=2,
        warnings=[CollectorWarning(message="retry succeeded", exception_type="ReadTimeout")],
        error_message=None,
    )


def test_save_collector_telemetry_writes_jsonl_artifact(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)

    storage.save_collector_telemetry(
        run_date="2026-07-03",
        results=[_result()],
        run_id="run-123",
        timestamp="2026-07-03T01:02:03+00:00",
    )

    path = Path(storage.COLLECTOR_RUNS_LOG)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "run_date": "2026-07-03",
            "run_id": "run-123",
            "collector_name": "rss",
            "status": "partial",
            "duration_seconds": 0.125,
            "record_count": 2,
            "warnings": [{"message": "retry succeeded", "exception_type": "ReadTimeout"}],
            "error_message": None,
            "timestamp": "2026-07-03T01:02:03+00:00",
        }
    ]


def test_load_collector_telemetry_validates_expected_rows(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    storage.save_collector_telemetry(
        run_date="2026-07-03",
        results=[_result()],
        timestamp="2026-07-03T01:02:03+00:00",
    )
    diagnostics = StorageDiagnostics()

    rows = storage.load_collector_telemetry(diagnostics=diagnostics)

    assert [row["collector_name"] for row in rows] == ["rss"]
    assert rows[0]["status"] == "partial"
    assert diagnostics.warnings == []


def test_load_collector_telemetry_reports_malformed_rows(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.COLLECTOR_RUNS_LOG).parent.mkdir(parents=True)
    Path(storage.COLLECTOR_RUNS_LOG).write_text(
        "{not json}\n"
        + json.dumps(
            {
                "run_date": "2026-07-03",
                "run_id": "",
                "collector_name": "rss",
                "status": "success",
                "duration_seconds": 0.1,
                "record_count": 1,
                "warnings": [],
                "error_message": None,
                "timestamp": "2026-07-03T01:02:03+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    rows = storage.load_collector_telemetry(diagnostics=diagnostics)

    assert [row["collector_name"] for row in rows] == ["rss"]
    assert len(diagnostics.warnings) == 1
    assert diagnostics.warnings[0].line_number == 1
    assert "Invalid JSON" in diagnostics.warnings[0].message


def test_load_collector_telemetry_reports_rows_missing_required_fields(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.COLLECTOR_RUNS_LOG).parent.mkdir(parents=True)
    Path(storage.COLLECTOR_RUNS_LOG).write_text(
        json.dumps(
            {
                "run_date": "2026-07-03",
                "collector_name": "rss",
                "status": "success",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    rows = storage.load_collector_telemetry(diagnostics=diagnostics)

    assert rows == []
    assert len(diagnostics.warnings) == 1
    assert "Missing required collector telemetry fields" in diagnostics.warnings[0].message


def test_compact_collector_telemetry_keeps_recent_rows_and_reports_malformed_rows(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.COLLECTOR_RUNS_LOG).parent.mkdir(parents=True)
    rows: list[dict[str, object]] = [
        {
            "run_date": "2026-06-01",
            "run_id": "old-run",
            "collector_name": "rss",
            "status": "success",
            "duration_seconds": 0.1,
            "record_count": 1,
            "warnings": [],
            "error_message": None,
            "timestamp": "2026-06-01T00:00:00+00:00",
        },
        {
            "run_date": "2026-07-02",
            "run_id": "recent-run",
            "collector_name": "github",
            "status": "success",
            "duration_seconds": 0.2,
            "record_count": 3,
            "warnings": [],
            "error_message": None,
            "timestamp": "2026-07-02T00:00:00+00:00",
        },
    ]
    Path(storage.COLLECTOR_RUNS_LOG).write_text(
        "\n".join(
            [
                json.dumps(rows[0], ensure_ascii=False),
                "{not json}",
                json.dumps(rows[1], ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    kept = storage.compact_collector_telemetry(
        retention_days=7,
        max_rows=10,
        as_of_date="2026-07-04",
        diagnostics=diagnostics,
    )

    compacted_rows = storage.load_collector_telemetry()
    assert kept == 1
    assert [row["run_id"] for row in compacted_rows] == ["recent-run"]
    assert len(diagnostics.warnings) == 1
    assert "Invalid JSON" in diagnostics.warnings[0].message


def test_compact_collector_telemetry_applies_max_rows_after_date_retention(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.COLLECTOR_RUNS_LOG).parent.mkdir(parents=True)
    rows: list[dict[str, object]] = [
        {
            "run_date": "2026-07-02",
            "run_id": f"run-{index}",
            "collector_name": "rss",
            "status": "success",
            "duration_seconds": 0.1,
            "record_count": index,
            "warnings": [],
            "error_message": None,
            "timestamp": f"2026-07-02T00:00:0{index}+00:00",
        }
        for index in range(3)
    ]
    Path(storage.COLLECTOR_RUNS_LOG).write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    kept = storage.compact_collector_telemetry(
        retention_days=30,
        max_rows=2,
        as_of_date="2026-07-04",
    )

    compacted_rows = storage.load_collector_telemetry()
    assert kept == 2
    assert [row["run_id"] for row in compacted_rows] == ["run-1", "run-2"]


def test_collect_all_telemetry_persistence_failure_is_non_fatal(monkeypatch) -> None:
    monkeypatch.setattr(collect_sources, "_load_source_registry", lambda: {"rss_feeds": []})
    monkeypatch.setattr(
        collect_sources.collector_registry,
        "build_async_collector_task_groups",
        lambda **kwargs: [
            CollectorTaskGroup(
                name="fixture",
                tasks=[_successful_events(_event("one"))],
            )
        ],
    )

    def fail_save(*args, **kwargs) -> None:
        raise OSError("telemetry disk full")

    monkeypatch.setattr(collect_sources, "save_collector_telemetry", fail_save)

    events, telemetry = asyncio.run(
        collect_sources.collect_all_with_telemetry(
            {"run": {"report_window_hours": 24}, "sources": {"web_search": {"enabled": False}}},
            run_date="2026-07-03",
            persist_telemetry=True,
            run_id="run-123",
        )
    )

    assert [event.source_name for event in events] == ["one"]
    assert [result.collector_name for result in telemetry] == ["fixture", "web_search"]
