from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


EXPECTED_JSONL_KEYS = {
    "source_events.jsonl": {
        "run_date",
        "run_id",
        "event_id",
        "canonical_title",
        "summary",
        "source_urls",
        "primary_source_url",
        "source_type",
        "published_at",
        "companies",
        "topics",
        "event_type",
        "importance_score",
        "raw_event_ids",
        "metadata",
    },
    "topic_trends.jsonl": {
        "run_date",
        "topic_id",
        "trend_status",
        "signal_count",
        "signal_classification",
    },
    "company_mentions.jsonl": {"run_date", "company", "significance", "summary"},
    "paper_mentions.jsonl": {
        "run_date",
        "title",
        "link",
        "signal_strength",
        "overall_score",
    },
    "project_mentions.jsonl": {"run_date", "repo", "url", "verdict", "stars_total"},
    "trending_snapshots.jsonl": {
        "snapshot_date",
        "period",
        "item_id",
        "item_type",
        "source",
        "title",
        "rank",
        "velocity_score",
        "language",
    },
    "market_signals.jsonl": {
        "run_date",
        "ticker",
        "company",
        "date",
        "time_horizon",
        "conclusion",
        "conclusion_zh",
        "risk_level",
        "confidence",
        "signals_to_monitor",
        "source_events",
    },
    "prediction_log.jsonl": {
        "prediction_id",
        "created_date",
        "prediction",
        "topic_tags",
        "companies",
        "time_horizon",
        "horizon_date",
        "probability",
        "resolution_criteria",
        "status",
        "confidence",
        "updates",
    },
}


def _sample_jsonl(path: Path, limit: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
        if len(rows) >= limit:
            break
    return rows


def test_existing_jsonl_artifacts_match_implicit_historical_schemas() -> None:
    for filename, required_keys in EXPECTED_JSONL_KEYS.items():
        path = DATA / filename
        rows = _sample_jsonl(path)
        assert rows, f"{filename} should contain historical sample rows"
        for row in rows:
            assert required_keys <= row.keys(), f"{filename} missing keys in {row}"


def test_known_empty_jsonl_artifacts_are_valid_empty_files() -> None:
    for filename in ["macro_events.jsonl", "market_signal_log.jsonl", "social_signals.jsonl"]:
        path = DATA / filename
        assert path.exists()
        assert path.read_text(encoding="utf-8") == ""


def test_scorecard_csv_headers_match_existing_contract() -> None:
    expected_headers = {
        "prediction_scorecard.csv": [
            "date",
            "prediction_id",
            "horizon",
            "probability",
            "outcome",
            "brier_score",
            "notes",
        ],
        "market_signal_scorecard.csv": [
            "date",
            "ticker",
            "horizon",
            "conclusion_type",
            "entry_quality",
            "outcome",
            "score",
            "notes",
        ],
    }

    for filename, header in expected_headers.items():
        with (DATA / filename).open(encoding="utf-8", newline="") as f:
            assert next(csv.reader(f)) == header
