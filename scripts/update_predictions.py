"""Prediction Update Engine — update open predictions with today's evidence."""

from __future__ import annotations

import json
from typing import Any

from llm_schemas import NewPredictionsResponse, PredictionUpdatesResponse
from prompt_runner import PromptRunner
from state import (
    NormalizedEvent,
    Prediction,
    PredictionUpdate,
    TechDailyState,
)


def _determine_signal_level(events: list[NormalizedEvent]) -> str:
    high_importance = sum(1 for e in events if e.importance_score > 0.7)
    if high_importance >= 5:
        return "high"
    if high_importance >= 2:
        return "normal"
    return "low"


def _build_today_summary(state: TechDailyState) -> dict[str, Any]:
    return {
        "run_date": state.run_date,
        "top_events": [
            {
                "event_id": e.event_id,
                "title": e.canonical_title,
                "summary": e.summary,
                "companies": e.companies,
                "topics": e.topics,
                "importance_score": e.importance_score,
            }
            for e in sorted(state.normalized_events, key=lambda x: x.importance_score, reverse=True)[:15]
        ],
        "topic_summaries": {
            k: {
                "trend_status": v.trend_status,
                "key_signal_summary": v.key_signal_summary,
                "signal_classification": v.signal_classification,
            }
            for k, v in state.topic_summaries.items()
            if v.report_worthy
        },
        "company_analyses": {
            k: {
                "significance": v.significance,
                "summary": v.summary,
            }
            for k, v in state.company_analyses.items()
            if v.significance in ("high", "medium")
        },
    }


def _run_prediction_update_batch(
    state: TechDailyState,
    prompt_runner: PromptRunner,
) -> list[PredictionUpdate]:
    if not state.open_predictions:
        return []

    today_summary = _build_today_summary(state)

    pred_payload = [
        {
            "prediction_id": p.prediction_id,
            "prediction": p.prediction,
            "probability": p.probability,
            "time_horizon": p.time_horizon,
            "horizon_date": p.horizon_date,
            "resolution_criteria": p.resolution_criteria,
            "topic_tags": p.topic_tags,
            "companies": p.companies,
        }
        for p in state.open_predictions
    ]

    user_msg = json.dumps(
        {
            "open_predictions": pred_payload,
            "today_events": today_summary["top_events"],
            "topic_summaries": today_summary["topic_summaries"],
            "company_analyses": today_summary["company_analyses"],
        },
        ensure_ascii=False,
    )

    # Returns an ARRAY of N updates (one per open prediction).
    # Each update has ~6 fields + reasoning text → ~300-500 tokens.
    # With 30 open predictions the output can exceed 12K tokens, so we
    # allocate generously here. (Single-object analyzers stay at 4096.)
    results = prompt_runner.run_json(
        prompt_path="prediction_update.md",
        payload=user_msg,
        schema=PredictionUpdatesResponse,
        max_tokens=16384,
    )

    updates = []
    for r in results.root:
        updates.append(
            PredictionUpdate(
                prediction_id=r.prediction_id,
                update_date=state.run_date,
                evidence_summary=r.evidence_summary,
                impact=r.impact,
                probability_before=r.probability_before,
                probability_after=r.probability_after,
                reasoning=r.reasoning,
                source_event_ids=r.source_event_ids,
                resolution=r.resolution,
            )
        )

    print(f"  [Predictions] {len(updates)} prediction updates")
    return updates


def run_prediction_updates(
    state: TechDailyState,
    prompt_runner: PromptRunner | None = None,
) -> list[PredictionUpdate]:
    if not state.open_predictions:
        return []

    try:
        return _run_prediction_update_batch(state, prompt_runner or PromptRunner())
    except Exception as e:
        print(f"  [Predictions] Update failed: {e}")
        return []


def _generate_new_prediction_batch(
    state: TechDailyState,
    prompt_runner: PromptRunner,
) -> list[Prediction]:
    today_summary = _build_today_summary(state)
    signal_level = _determine_signal_level(state.normalized_events)
    state.signal_level = signal_level

    existing_ids = {p.prediction_id for p in state.open_predictions}

    user_msg = json.dumps(
        {
            "run_date": state.run_date,
            "today_summary": today_summary,
            "open_predictions": [
                {"prediction_id": p.prediction_id, "prediction": p.prediction} for p in state.open_predictions
            ],
            "recently_resolved": [],
            "signal_level": signal_level,
        },
        ensure_ascii=False,
    )

    # Returns an ARRAY of 1-6 new predictions (depending on signal_level).
    # Each prediction has 11 fields including long evidence/criteria text
    # → ~700-900 tokens per prediction. 6 predictions × 900 = 5400 tokens
    # plus JSON envelope → 4096 was too tight (failed in production logs).
    results = prompt_runner.run_json(
        prompt_path="new_prediction.md",
        payload=user_msg,
        schema=NewPredictionsResponse,
        max_tokens=8192,
    )

    new_preds = []
    for r in results.root:
        pid = r.prediction_id
        if pid in existing_ids:
            continue
        new_preds.append(
            Prediction(
                prediction_id=pid,
                created_date=r.created_date,
                prediction=r.prediction,
                topic_tags=r.topic_tags,
                companies=r.companies,
                time_horizon=r.time_horizon,
                horizon_date=r.horizon_date,
                probability=r.probability,
                evidence=r.evidence,
                resolution_criteria=r.resolution_criteria,
                falsification_condition=r.falsification_condition,
                signals_to_monitor=r.signals_to_monitor,
                status="open",
                confidence=r.confidence,
            )
        )

    print(f"  [Predictions] Generated {len(new_preds)} new predictions (signal_level={signal_level})")
    return new_preds


def generate_new_predictions(
    state: TechDailyState,
    prompt_runner: PromptRunner | None = None,
) -> list[Prediction]:
    try:
        return _generate_new_prediction_batch(state, prompt_runner or PromptRunner())

    except Exception as e:
        print(f"  [Predictions] Generation failed: {e}")
        return []
