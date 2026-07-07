"""Prediction Update Engine — update open predictions with today's evidence."""

from __future__ import annotations

import json
from typing import Any

from llm_schemas import NewPredictionsResponse, PredictionUpdatesResponse
from pipeline_state import PredictionInputState
from prompt_runner import PromptRunner, PromptRunnerError
from state import (
    NormalizedEvent,
    Prediction,
    PredictionUpdate,
    TechDailyState,
)
from tech_daily.predictions.results import PredictionOperationResult


def _determine_signal_level(events: list[NormalizedEvent]) -> str:
    high_importance = sum(1 for e in events if e.importance_score > 0.7)
    if high_importance >= 5:
        return "high"
    if high_importance >= 2:
        return "normal"
    return "low"


def _build_today_summary_from_input(input_state: PredictionInputState) -> dict[str, Any]:
    return {
        "run_date": input_state.run_metadata.run_date,
        "top_events": [
            {
                "event_id": e.event_id,
                "title": e.canonical_title,
                "summary": e.summary,
                "companies": e.companies,
                "topics": e.topics,
                "importance_score": e.importance_score,
            }
            for e in sorted(input_state.corpus.normalized_events, key=lambda x: x.importance_score, reverse=True)[:15]
        ],
        "topic_summaries": {
            k: {
                "trend_status": v.trend_status,
                "key_signal_summary": v.key_signal_summary,
                "signal_classification": v.signal_classification,
            }
            for k, v in input_state.analysis.topic_summaries.items()
            if v.report_worthy
        },
        "company_analyses": {
            k: {
                "significance": v.significance,
                "summary": v.summary,
            }
            for k, v in input_state.analysis.company_analyses.items()
            if v.significance in ("high", "medium")
        },
    }


def _build_today_summary(state: TechDailyState) -> dict[str, Any]:
    return _build_today_summary_from_input(PredictionInputState.from_tech_daily_state(state))


def _prediction_error_kind(exc: Exception) -> str:
    if isinstance(exc, PromptRunnerError):
        return exc.kind
    return type(exc).__name__


def _run_prediction_update_batch(
    state: TechDailyState,
    prompt_runner: PromptRunner,
) -> list[PredictionUpdate]:
    return _run_prediction_update_batch_from_input(PredictionInputState.from_tech_daily_state(state), prompt_runner)


def _run_prediction_update_batch_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner,
) -> list[PredictionUpdate]:
    if not input_state.prediction.open_predictions:
        return []

    today_summary = _build_today_summary_from_input(input_state)

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
        for p in input_state.prediction.open_predictions
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
                    update_date=input_state.run_metadata.run_date,
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
    return run_prediction_updates_from_input(PredictionInputState.from_tech_daily_state(state), prompt_runner=prompt_runner)


def run_prediction_updates_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner | None = None,
) -> list[PredictionUpdate]:
    return run_prediction_updates_result_from_input(input_state, prompt_runner=prompt_runner).value


def run_prediction_updates_result_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner | None = None,
) -> PredictionOperationResult[list[PredictionUpdate]]:
    if not input_state.prediction.open_predictions:
        return PredictionOperationResult.ok([])
    try:
        updates = _run_prediction_update_batch_from_input(input_state, prompt_runner or PromptRunner())
        return PredictionOperationResult.ok(updates)
    except Exception as exc:
        print(f"  [Predictions] Update failed: {exc}")
        return PredictionOperationResult.failed(
            [],
            error_kind=_prediction_error_kind(exc),
            error_message=str(exc),
        )


def _generate_new_prediction_batch(
    state: TechDailyState,
    prompt_runner: PromptRunner,
) -> list[Prediction]:
    new_predictions, signal_level = _generate_new_prediction_batch_from_input(
        PredictionInputState.from_tech_daily_state(state),
        prompt_runner,
    )
    state.signal_level = signal_level
    return new_predictions


def _generate_new_prediction_batch_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner,
) -> tuple[list[Prediction], str]:
    today_summary = _build_today_summary_from_input(input_state)
    signal_level = _determine_signal_level(input_state.corpus.normalized_events)

    existing_ids = {p.prediction_id for p in input_state.prediction.open_predictions}

    user_msg = json.dumps(
        {
            "run_date": input_state.run_metadata.run_date,
            "today_summary": today_summary,
            "open_predictions": [
                {"prediction_id": p.prediction_id, "prediction": p.prediction}
                for p in input_state.prediction.open_predictions
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
    return new_preds, signal_level


def generate_new_predictions(
    state: TechDailyState,
    prompt_runner: PromptRunner | None = None,
) -> list[Prediction]:
    input_state = PredictionInputState.from_tech_daily_state(state)
    new_predictions, signal_level = generate_new_predictions_from_input(input_state, prompt_runner=prompt_runner)
    state.signal_level = signal_level
    return new_predictions


def generate_new_predictions_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner | None = None,
) -> tuple[list[Prediction], str]:
    return generate_new_predictions_result_from_input(input_state, prompt_runner=prompt_runner).value


def generate_new_predictions_result_from_input(
    input_state: PredictionInputState,
    prompt_runner: PromptRunner | None = None,
) -> PredictionOperationResult[tuple[list[Prediction], str]]:
    fallback = ([], _determine_signal_level(input_state.corpus.normalized_events))
    try:
        new_predictions, signal_level = _generate_new_prediction_batch_from_input(
            input_state,
            prompt_runner or PromptRunner(),
        )
        return PredictionOperationResult.ok((new_predictions, signal_level))
    except Exception as exc:
        print(f"  [Predictions] Generation failed: {exc}")
        return PredictionOperationResult.failed(
            fallback,
            error_kind=_prediction_error_kind(exc),
            error_message=str(exc),
        )
