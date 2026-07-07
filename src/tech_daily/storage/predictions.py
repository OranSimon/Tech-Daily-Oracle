"""Prediction artifact storage helpers."""

from __future__ import annotations

import json
from typing import Any

from tech_daily.pipeline.state import Prediction, PredictionUpdate
from tech_daily.storage._shared import (
    ensure_dirs,
    read_jsonl_dict_rows,
    record_storage_warning,
    safe_dict,
)
from tech_daily.storage._shared import (
    storage_context as resolve_storage_context,
)
from tech_daily.storage.context import StorageContext
from tech_daily.storage.io import atomic_write_jsonl
from tech_daily.storage.validation import StorageDiagnostics, validate_open_prediction_row


def load_open_predictions(
    diagnostics: StorageDiagnostics | None = None,
    *,
    storage_context: StorageContext | None = None,
) -> list[Prediction]:
    prediction_log = str(resolve_storage_context(storage_context).prediction_log_path())
    predictions: list[Prediction] = []
    for line_number, row in read_jsonl_dict_rows(prediction_log, diagnostics=diagnostics):
        if row.get("status") != "open":
            continue

        validation_errors = validate_open_prediction_row(row)
        if validation_errors:
            record_storage_warning(
                diagnostics,
                path=prediction_log,
                message="; ".join(validation_errors),
                line_number=line_number,
                raw_value=json.dumps(row, ensure_ascii=False),
            )
            continue

        try:
            predictions.append(
                Prediction(
                    prediction_id=row["prediction_id"],
                    created_date=row["created_date"],
                    prediction=row["prediction"],
                    topic_tags=row.get("topic_tags", []),
                    companies=row.get("companies", []),
                    time_horizon=row["time_horizon"],
                    horizon_date=row.get("horizon_date", ""),
                    probability=row["probability"],
                    evidence=row.get("evidence", ""),
                    resolution_criteria=row.get("resolution_criteria", ""),
                    falsification_condition=row.get("falsification_condition", ""),
                    signals_to_monitor=row.get("signals_to_monitor", []),
                    status=row["status"],
                    confidence=row.get("confidence", "medium"),
                    updates=row.get("updates", []),
                )
            )
        except Exception as exception:
            record_storage_warning(
                diagnostics,
                path=prediction_log,
                message="Failed to load prediction",
                line_number=line_number,
                raw_value=json.dumps(row, ensure_ascii=False),
                exception=exception,
            )
    return predictions


def save_predictions(
    new_predictions: list[Prediction],
    updates: list[PredictionUpdate],
    *,
    storage_context: StorageContext | None = None,
) -> None:
    """Append new predictions and apply updates to the log."""
    context = resolve_storage_context(storage_context)
    prediction_log = str(context.prediction_log_path())
    ensure_dirs(context)

    all_predictions: dict[str, dict[str, Any]] = {}
    diagnostics = StorageDiagnostics()
    for line_number, row in read_jsonl_dict_rows(prediction_log, diagnostics=diagnostics):
        prediction_id = row.get("prediction_id")
        if isinstance(prediction_id, str) and prediction_id:
            all_predictions[prediction_id] = row
        else:
            record_storage_warning(
                diagnostics,
                path=prediction_log,
                message="Prediction row missing prediction_id",
                line_number=line_number,
                raw_value=json.dumps(row, ensure_ascii=False),
            )

    for update in updates:
        prediction_id = update.prediction_id
        if prediction_id not in all_predictions:
            continue

        prediction = all_predictions[prediction_id]
        prediction["probability"] = update.probability_after
        prediction.setdefault("updates", []).append(safe_dict(update))
        if update.resolution.get("resolved"):
            outcome = update.resolution.get("resolved_as")
            prediction["status"] = f"resolved_{outcome}" if outcome else "resolved_unknown"
            prediction["resolution_reasoning"] = update.resolution.get("resolution_reasoning", "")

    for new_prediction in new_predictions:
        all_predictions[new_prediction.prediction_id] = safe_dict(new_prediction)

    atomic_write_jsonl(prediction_log, all_predictions.values(), ensure_ascii=False)
    print(f"  [Storage] Prediction log updated: {len(new_predictions)} new, {len(updates)} updated")
