from __future__ import annotations

import json
from pathlib import Path

import pytest
import storage
import storage_io
from storage_validation import StorageDiagnostics


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")


def _prediction_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "prediction_id": "P-storage-1",
        "created_date": "2026-07-02",
        "prediction": "A storage validation fixture",
        "topic_tags": ["ai_models"],
        "companies": ["OpenAI"],
        "time_horizon": "30 days",
        "horizon_date": "2026-08-01",
        "probability": 0.62,
        "evidence": "Historical-style evidence",
        "resolution_criteria": "Historical-style criteria",
        "falsification_condition": "Historical-style falsification",
        "signals_to_monitor": [],
        "status": "open",
        "confidence": "medium",
        "updates": [],
    }
    row.update(overrides)
    return row


def test_atomic_write_text_replaces_target(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("old", encoding="utf-8")

    storage_io.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_text_preserves_target_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "report.md"
    target.write_text("old", encoding="utf-8")

    def fail_replace(source: str, destination: str) -> None:
        raise OSError(f"simulated replace failure: {source} -> {destination}")

    monkeypatch.setattr(storage_io.os, "replace", fail_replace)

    with pytest.raises(OSError):
        storage_io.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".report.md.*.tmp"))


def test_load_open_predictions_validates_historical_style_rows(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.PREDICTION_LOG).parent.mkdir(parents=True)
    Path(storage.PREDICTION_LOG).write_text(
        json.dumps(_prediction_row(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    loaded = storage.load_open_predictions(diagnostics=diagnostics)

    assert [prediction.prediction_id for prediction in loaded] == ["P-storage-1"]
    assert diagnostics.warnings == []


def test_load_open_predictions_reports_malformed_jsonl_rows(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    Path(storage.PREDICTION_LOG).parent.mkdir(parents=True)
    Path(storage.PREDICTION_LOG).write_text(
        "{not json}\n" + json.dumps(_prediction_row(prediction_id="P-storage-2"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    loaded = storage.load_open_predictions(diagnostics=diagnostics)

    assert [prediction.prediction_id for prediction in loaded] == ["P-storage-2"]
    assert len(diagnostics.warnings) == 1
    assert diagnostics.warnings[0].line_number == 1
    assert "Invalid JSON" in diagnostics.warnings[0].message


def test_load_open_predictions_reports_rows_missing_required_fields(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    invalid = _prediction_row()
    invalid.pop("probability")
    Path(storage.PREDICTION_LOG).parent.mkdir(parents=True)
    Path(storage.PREDICTION_LOG).write_text(
        json.dumps(invalid, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    diagnostics = StorageDiagnostics()

    loaded = storage.load_open_predictions(diagnostics=diagnostics)

    assert loaded == []
    assert len(diagnostics.warnings) == 1
    assert "Missing required prediction fields" in diagnostics.warnings[0].message
