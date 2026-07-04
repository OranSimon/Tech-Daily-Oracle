from __future__ import annotations

import json
from pathlib import Path

import storage
from state import Prediction, PredictionUpdate


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")


def _prediction(pid: str = "P1") -> Prediction:
    return Prediction(
        prediction_id=pid,
        created_date="2026-07-02",
        prediction="A test prediction",
        topic_tags=["ai_models"],
        companies=["OpenAI"],
        time_horizon="30 days",
        horizon_date="2026-08-01",
        probability=0.6,
        evidence="Fixture evidence",
        resolution_criteria="Fixture criteria",
        falsification_condition="Fixture falsification",
        signals_to_monitor=[],
        status="open",
        confidence="medium",
    )


def test_save_and_load_open_predictions_round_trip(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    pred = _prediction()

    storage.save_predictions([pred], [])
    loaded = storage.load_open_predictions()

    assert [p.prediction_id for p in loaded] == ["P1"]
    assert loaded[0].probability == 0.6
    assert Path(storage.PREDICTION_LOG).exists()


def test_save_predictions_applies_updates_and_resolution(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    storage.save_predictions([_prediction()], [])

    update = PredictionUpdate(
        prediction_id="P1",
        update_date="2026-07-03",
        evidence_summary="Resolved evidence",
        impact="strengthens",
        probability_before=0.6,
        probability_after=0.9,
        reasoning="Fixture reasoning",
        source_event_ids=["event-1"],
        resolution={
            "resolved": True,
            "resolved_as": "true",
            "resolution_reasoning": "Criteria met",
        },
    )

    storage.save_predictions([], [update])

    rows = [json.loads(line) for line in Path(storage.PREDICTION_LOG).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["probability"] == 0.9
    assert rows[0]["status"] == "resolved_true"
    assert rows[0]["updates"][0]["source_event_ids"] == ["event-1"]
    assert storage.load_open_predictions() == []


def test_report_storage_uses_existing_directory_contract(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)

    daily_path = Path(storage.save_daily_report("2026-07-02", "# Daily"))
    weekly_path = Path(storage.save_weekly_review("2026-W26", "# Weekly"))
    monthly_path = Path(storage.save_monthly_review("2026-06", "# Monthly"))

    assert daily_path == tmp_path / "reports" / "daily" / "2026-07-02.md"
    assert weekly_path == tmp_path / "reports" / "weekly" / "2026-W26.md"
    assert monthly_path == tmp_path / "reports" / "monthly" / "2026-06.md"
    assert daily_path.read_text(encoding="utf-8") == "# Daily"
