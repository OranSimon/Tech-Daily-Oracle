from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_append_jsonl_rows_safely_preserves_existing_rows(tmp_path: Path) -> None:
    from storage_io import append_jsonl_rows_safely

    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"id": "existing"}) + "\n", encoding="utf-8")

    append_jsonl_rows_safely(path, [{"id": "new-1"}, {"id": "new-2"}])

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"id": "existing"}, {"id": "new-1"}, {"id": "new-2"}]


def test_append_jsonl_rows_safely_handles_empty_rows(tmp_path: Path) -> None:
    from storage_io import append_jsonl_rows_safely

    path = tmp_path / "events.jsonl"

    append_jsonl_rows_safely(path, [])

    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


def test_append_jsonl_rows_safely_does_not_partially_append_on_serialization_error(tmp_path: Path) -> None:
    from storage_io import append_jsonl_rows_safely

    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"id": "existing"}) + "\n", encoding="utf-8")

    with pytest.raises(TypeError):
        append_jsonl_rows_safely(path, [{"id": "new"}, {"bad": object()}])

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"id": "existing"}]


def test_quarantine_jsonl_row_writes_structured_diagnostic(tmp_path: Path) -> None:
    from storage_io import quarantine_jsonl_row

    artifact_path = tmp_path / "prediction_log.jsonl"
    quarantine_path = quarantine_jsonl_row(
        artifact_path,
        line_number=7,
        raw_value="{bad json",
        message="Invalid JSON row",
        quarantine_root=tmp_path / "quarantine",
    )

    rows = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "artifact": str(artifact_path),
            "line_number": 7,
            "message": "Invalid JSON row",
            "raw_value": "{bad json",
        }
    ]
    assert quarantine_path.name == "prediction_log.quarantine.jsonl"


def test_collector_telemetry_migration_accepts_legacy_duration_field() -> None:
    from storage_validation import migrate_collector_telemetry_row, validate_collector_telemetry_row

    legacy_row = {
        "run_date": "2026-07-02",
        "collector_name": "rss",
        "status": "success",
        "duration": 1.25,
        "record_count": 3,
        "timestamp": "2026-07-02T00:00:00+00:00",
    }

    migrated = migrate_collector_telemetry_row(legacy_row)

    assert migrated == {
        "run_date": "2026-07-02",
        "run_id": "",
        "collector_name": "rss",
        "status": "success",
        "duration_seconds": 1.25,
        "record_count": 3,
        "warnings": [],
        "error_message": None,
        "timestamp": "2026-07-02T00:00:00+00:00",
    }
    assert validate_collector_telemetry_row(migrated) == []


def test_collector_telemetry_loader_migrates_legacy_rows(tmp_path: Path, monkeypatch) -> None:
    import storage

    telemetry_path = tmp_path / "collector_runs.jsonl"
    telemetry_path.write_text(
        json.dumps(
            {
                "run_date": "2026-07-02",
                "collector_name": "rss",
                "status": "success",
                "duration": 1.25,
                "record_count": 3,
                "timestamp": "2026-07-02T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(storage, "COLLECTOR_RUNS_LOG", str(telemetry_path))

    rows = storage.load_collector_telemetry()

    assert len(rows) == 1
    assert rows[0]["duration_seconds"] == 1.25
    assert rows[0]["run_id"] == ""


def test_jsonl_append_writes_are_centralized_in_storage_io() -> None:
    allowed_append_files = {
        Path("scripts/storage_io.py"),
        Path("scripts/score_predictions.py"),  # CSV scorecard append, not JSONL.
    }
    offenders: list[str] = []

    for path in sorted(Path("scripts").rglob("*.py")):
        if path in allowed_append_files:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "open(" in line and '"a"' in line:
                offenders.append(f"{path}:{line_number}:{line.strip()}")

    assert offenders == []
