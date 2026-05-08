"""Prediction Scorecard — Brier score computation and calibration review."""

from __future__ import annotations

import csv
import json
import math
import os
from datetime import date
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTION_LOG = os.path.join(ROOT, "data", "prediction_log.jsonl")
SCORECARD = os.path.join(ROOT, "data", "prediction_scorecard.csv")


def brier_score(probability: float, outcome: bool) -> float:
    """Brier score for a single prediction: (p - outcome)^2."""
    return (probability - (1.0 if outcome else 0.0)) ** 2


def load_predictions() -> list[dict[str, Any]]:
    predictions = []
    if os.path.exists(PREDICTION_LOG):
        with open(PREDICTION_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        predictions.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return predictions


def compute_scorecard() -> dict[str, Any]:
    predictions = load_predictions()
    resolved = [p for p in predictions if p.get("status") in ("resolved_true", "resolved_false")]

    if not resolved:
        return {"total": 0, "resolved": 0, "brier_score": None, "calibration": "insufficient_data"}

    scores = []
    for p in resolved:
        outcome = p.get("status") == "resolved_true"
        # Use final probability before resolution
        updates = p.get("updates", [])
        if updates:
            prob = updates[-1].get("probability_after", p.get("probability", 0.5))
        else:
            prob = p.get("probability", 0.5)
        scores.append(brier_score(prob, outcome))

    avg_brier = sum(scores) / len(scores)

    # Simple calibration check
    if avg_brier < 0.1:
        calibration = "well-calibrated"
    elif avg_brier < 0.2:
        calibration = "slightly-over-confident"
    else:
        calibration = "poorly-calibrated"

    return {
        "computed_at": date.today().isoformat(),
        "total": len(predictions),
        "open": len([p for p in predictions if p.get("status") == "open"]),
        "resolved": len(resolved),
        "resolved_true": len([p for p in resolved if p.get("status") == "resolved_true"]),
        "resolved_false": len([p for p in resolved if p.get("status") == "resolved_false"]),
        "brier_score": round(avg_brier, 4),
        "calibration": calibration,
    }


def append_to_scorecard(row: dict[str, Any]) -> None:
    fieldnames = ["date", "prediction_id", "horizon", "probability",
                  "outcome", "brier_score", "notes"]
    file_exists = os.path.exists(SCORECARD)
    with open(SCORECARD, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def update_scorecard_for_resolved(prediction: dict[str, Any]) -> None:
    """Write resolved prediction to scorecard."""
    outcome = prediction.get("status") == "resolved_true"
    updates = prediction.get("updates", [])
    if updates:
        prob = updates[-1].get("probability_after", prediction.get("probability", 0.5))
    else:
        prob = prediction.get("probability", 0.5)
    bs = brier_score(prob, outcome)
    append_to_scorecard({
        "date": date.today().isoformat(),
        "prediction_id": prediction.get("prediction_id", ""),
        "horizon": prediction.get("time_horizon", ""),
        "probability": prob,
        "outcome": "true" if outcome else "false",
        "brier_score": round(bs, 4),
        "notes": prediction.get("resolution_reasoning", ""),
    })


if __name__ == "__main__":
    scorecard = compute_scorecard()
    print(json.dumps(scorecard, indent=2))
