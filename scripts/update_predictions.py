"""Prediction Update Engine — update open predictions with today's evidence."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from claude_client import call_claude_json
from state import (
    NormalizedEvent, TopicSummary, CompanyAnalysis,
    Prediction, PredictionUpdate, TechDailyState
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "prediction_update.md")) as f:
        return f.read()


def _load_new_prediction_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "new_prediction.md")) as f:
        return f.read()


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
            for e in sorted(state.normalized_events,
                            key=lambda x: x.importance_score, reverse=True)[:15]
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


def run_prediction_updates(state: TechDailyState) -> list[PredictionUpdate]:
    if not state.open_predictions:
        return []

    prompt_system = _load_prompt()
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

    try:
        user_msg = json.dumps({
            "open_predictions": pred_payload,
            "today_events": today_summary["top_events"],
            "topic_summaries": today_summary["topic_summaries"],
            "company_analyses": today_summary["company_analyses"],
        }, ensure_ascii=False)

        results = call_claude_json(
            system=prompt_system,
            user=user_msg,
            max_tokens=4096,
        )

        if not isinstance(results, list):
            return []

        updates = []
        for r in results:
            updates.append(PredictionUpdate(
                prediction_id=r.get("prediction_id", ""),
                update_date=state.run_date,
                evidence_summary=r.get("evidence_summary", ""),
                impact=r.get("impact", "neutral"),
                probability_before=r.get("probability_before", 0.5),
                probability_after=r.get("probability_after", 0.5),
                reasoning=r.get("reasoning", ""),
                source_event_ids=r.get("source_event_ids", []),
                resolution=r.get("resolution", {"resolved": False, "resolved_as": None,
                                                 "resolution_reasoning": None}),
            ))

        print(f"  [Predictions] {len(updates)} prediction updates")
        return updates

    except Exception as e:
        print(f"  [Predictions] Update failed: {e}")
        return []


def generate_new_predictions(state: TechDailyState) -> list[Prediction]:
    prompt_system = _load_new_prediction_prompt()
    today_summary = _build_today_summary(state)
    signal_level = _determine_signal_level(state.normalized_events)
    state.signal_level = signal_level

    existing_ids = {p.prediction_id for p in state.open_predictions}

    try:
        user_msg = json.dumps({
            "run_date": state.run_date,
            "today_summary": today_summary,
            "open_predictions": [
                {"prediction_id": p.prediction_id, "prediction": p.prediction}
                for p in state.open_predictions
            ],
            "recently_resolved": [],
            "signal_level": signal_level,
        }, ensure_ascii=False)

        results = call_claude_json(
            system=prompt_system,
            user=user_msg,
            max_tokens=4096,
        )

        if not isinstance(results, list):
            return []

        new_preds = []
        for r in results:
            pid = r.get("prediction_id", "")
            if pid in existing_ids:
                continue
            new_preds.append(Prediction(
                prediction_id=pid,
                created_date=r.get("created_date", state.run_date),
                prediction=r.get("prediction", ""),
                topic_tags=r.get("topic_tags", []),
                companies=r.get("companies", []),
                time_horizon=r.get("time_horizon", ""),
                horizon_date=r.get("horizon_date", ""),
                probability=r.get("probability", 0.5),
                evidence=r.get("evidence", ""),
                resolution_criteria=r.get("resolution_criteria", ""),
                falsification_condition=r.get("falsification_condition", ""),
                signals_to_monitor=r.get("signals_to_monitor", []),
                status="open",
                confidence=r.get("confidence", "medium"),
            ))

        print(f"  [Predictions] Generated {len(new_preds)} new predictions "
              f"(signal_level={signal_level})")
        return new_preds

    except Exception as e:
        print(f"  [Predictions] Generation failed: {e}")
        return []
