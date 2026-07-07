from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import update_predictions
from pipeline_state import PredictionInputState
from prompt_runner import PromptRunner, PromptRunnerError
from state import NormalizedEvent, Prediction, PredictionUpdate, TechDailyState
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-prediction",
        canonical_title="Fixture AI infrastructure demand increases",
        summary="A fixture event indicates AI infrastructure demand is increasing.",
        source_urls=["https://example.com/prediction"],
        primary_source_url="https://example.com/prediction",
        source_type="company",
        published_at=published,
        companies=["Nvidia"],
        projects=[],
        papers=[],
        people=[],
        topics=["ai_infrastructure"],
        geography=[],
        event_type="product_launch",
        importance_score=0.85,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-prediction-1"],
        metadata={},
    )


def _prediction() -> Prediction:
    return Prediction(
        prediction_id="P20260701-1",
        created_date="2026-07-01",
        prediction="AI infrastructure demand will increase by Q4.",
        topic_tags=["ai_infrastructure"],
        companies=["Nvidia"],
        time_horizon="6 months",
        horizon_date="2026-12-31",
        probability=0.6,
        evidence="Fixture initial evidence.",
        resolution_criteria="Demand indicators increase.",
        falsification_condition="Demand indicators fall.",
        signals_to_monitor=[{"signal": "orders", "threshold": "increase", "meaning": "demand"}],
        status="open",
        confidence="medium",
    )


def _state() -> TechDailyState:
    return TechDailyState(
        run_id="run-2026-07-02",
        run_date="2026-07-02",
        time_window="last_24h",
        normalized_events=[_event()],
        open_predictions=[_prediction()],
    )


def _prompt_runner(tmp_path: Path, response: str, prompt_name: str) -> PromptRunner:
    (tmp_path / prompt_name).write_text("Prediction prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_UPDATE_JSON = """[
  {
    "prediction_id": "P20260701-1",
    "update_date": "2026-07-02",
    "evidence_summary": "Fixture evidence strengthened the thesis.",
    "impact": "strengthens",
    "probability_before": 0.6,
    "probability_after": 0.68,
    "reasoning": "The event supports infrastructure demand.",
    "source_event_ids": ["event-2026-07-02-prediction"],
    "resolution": {
      "resolved": false,
      "resolved_as": null,
      "resolution_reasoning": null
    }
  }
]"""


VALID_NEW_PREDICTION_JSON = """[
  {
    "prediction_id": "P20260702-1",
    "created_date": "2026-07-02",
    "prediction": "A fixture infrastructure project will gain adoption by year-end.",
    "topic_tags": ["ai_infrastructure"],
    "companies": ["Nvidia"],
    "time_horizon": "6 months",
    "horizon_date": "2026-12-31",
    "probability": 0.55,
    "evidence": "Fixture evidence supports the forecast.",
    "resolution_criteria": "Adoption metrics increase.",
    "falsification_condition": "Adoption metrics decline.",
    "signals_to_monitor": [
      {"signal": "usage", "threshold": "increase", "meaning": "adoption"}
    ],
    "status": "open",
    "confidence": "medium"
  }
]"""


def test_run_prediction_updates_accepts_fake_prompt_runner_plain_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_UPDATE_JSON, "prediction_update.md")

    updates = update_predictions.run_prediction_updates(_state(), prompt_runner=runner)

    assert len(updates) == 1
    assert isinstance(updates[0], PredictionUpdate)
    assert updates[0].prediction_id == "P20260701-1"
    assert updates[0].update_date == "2026-07-02"
    assert updates[0].probability_after == 0.68


def test_run_prediction_updates_from_input_matches_legacy_path(tmp_path: Path) -> None:
    legacy_runner = _prompt_runner(tmp_path, VALID_UPDATE_JSON, "prediction_update.md")
    typed_runner = _prompt_runner(tmp_path, VALID_UPDATE_JSON, "prediction_update.md")
    state = _state()
    input_state = PredictionInputState.from_tech_daily_state(state)

    legacy_updates = update_predictions.run_prediction_updates(state, prompt_runner=legacy_runner)
    typed_updates = update_predictions.run_prediction_updates_from_input(input_state, prompt_runner=typed_runner)

    assert typed_updates == legacy_updates


def test_prediction_update_result_captures_llm_failure_without_changing_legacy_return() -> None:
    input_state = PredictionInputState.from_tech_daily_state(_state())

    class FailingRunner:
        def run_json(self, **kwargs: object) -> object:
            raise PromptRunnerError(kind="json_parse_error", message="bad json", raw_response="not-json")

    result = update_predictions.run_prediction_updates_result_from_input(
        input_state,
        prompt_runner=FailingRunner(),
    )
    legacy = update_predictions.run_prediction_updates_from_input(
        input_state,
        prompt_runner=FailingRunner(),
    )

    assert result.value == []
    assert result.success is False
    assert result.error_kind == "json_parse_error"
    assert result.error_message is not None
    assert "bad json" in result.error_message
    assert legacy == []


def test_prediction_updates_accept_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_UPDATE_JSON}\n```", "prediction_update.md")

    updates = update_predictions._run_prediction_update_batch(_state(), runner)

    assert updates[0].impact == "strengthens"
    assert updates[0].source_event_ids == ["event-2026-07-02-prediction"]


def test_prediction_updates_raise_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json", "prediction_update.md")

    with pytest.raises(PromptRunnerError) as exc_info:
        update_predictions._run_prediction_update_batch(_state(), runner)

    assert exc_info.value.kind == "json_parse_error"


def test_prediction_updates_raise_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '[{"prediction_id": "P20260701-1"}]', "prediction_update.md")

    with pytest.raises(PromptRunnerError) as exc_info:
        update_predictions._run_prediction_update_batch(_state(), runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "probability_after" in exc_info.value.message


def test_generate_new_predictions_accepts_fake_prompt_runner_plain_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_NEW_PREDICTION_JSON, "new_prediction.md")
    state = _state()

    predictions = update_predictions.generate_new_predictions(state, prompt_runner=runner)

    assert len(predictions) == 1
    assert predictions[0].prediction_id == "P20260702-1"
    assert predictions[0].status == "open"
    assert state.signal_level == "low"


def test_generate_new_predictions_from_input_matches_legacy_path_and_signal_level(tmp_path: Path) -> None:
    legacy_runner = _prompt_runner(tmp_path, VALID_NEW_PREDICTION_JSON, "new_prediction.md")
    typed_runner = _prompt_runner(tmp_path, VALID_NEW_PREDICTION_JSON, "new_prediction.md")
    state = _state()
    input_state = PredictionInputState.from_tech_daily_state(state)

    legacy_predictions = update_predictions.generate_new_predictions(state, prompt_runner=legacy_runner)
    typed_predictions, signal_level = update_predictions.generate_new_predictions_from_input(
        input_state,
        prompt_runner=typed_runner,
    )

    assert typed_predictions == legacy_predictions
    assert signal_level == state.signal_level == "low"


def test_generate_new_predictions_result_captures_llm_failure_without_changing_legacy_return() -> None:
    input_state = PredictionInputState.from_tech_daily_state(_state())

    class FailingRunner:
        def run_json(self, **kwargs: object) -> object:
            raise PromptRunnerError(kind="schema_validation_error", message="missing fields", raw_response="[]")

    result = update_predictions.generate_new_predictions_result_from_input(
        input_state,
        prompt_runner=FailingRunner(),
    )
    legacy = update_predictions.generate_new_predictions_from_input(
        input_state,
        prompt_runner=FailingRunner(),
    )

    assert result.value == ([], "low")
    assert result.success is False
    assert result.error_kind == "schema_validation_error"
    assert result.error_message is not None
    assert "missing fields" in result.error_message
    assert legacy == ([], "low")


def test_generate_new_predictions_from_input_preserves_duplicate_id_skip(tmp_path: Path) -> None:
    duplicate_json = VALID_NEW_PREDICTION_JSON.replace("P20260702-1", "P20260701-1")
    runner = _prompt_runner(tmp_path, duplicate_json, "new_prediction.md")

    predictions, signal_level = update_predictions.generate_new_predictions_from_input(
        PredictionInputState.from_tech_daily_state(_state()),
        prompt_runner=runner,
    )

    assert predictions == []
    assert signal_level == "low"


def test_generate_new_predictions_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_NEW_PREDICTION_JSON}\n```", "new_prediction.md")

    predictions = update_predictions._generate_new_prediction_batch(_state(), runner)

    assert predictions[0].prediction_id == "P20260702-1"
    assert predictions[0].signals_to_monitor[0]["signal"] == "usage"


def test_generate_new_predictions_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json", "new_prediction.md")

    with pytest.raises(PromptRunnerError) as exc_info:
        update_predictions._generate_new_prediction_batch(_state(), runner)

    assert exc_info.value.kind == "json_parse_error"


def test_generate_new_predictions_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '[{"prediction_id": "P20260702-1"}]', "new_prediction.md")

    with pytest.raises(PromptRunnerError) as exc_info:
        update_predictions._generate_new_prediction_batch(_state(), runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "resolution_criteria" in exc_info.value.message
