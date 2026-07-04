from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import analyze_macro_impact
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import MacroImpactAnalysis, NormalizedEvent, Prediction
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-macro",
        canonical_title="New chip export controls target AI accelerators",
        summary="Policy update restricts advanced AI accelerator exports.",
        source_urls=["https://example.com/macro"],
        primary_source_url="https://example.com/macro",
        source_type="policy",
        published_at=published,
        companies=["Nvidia", "TSMC"],
        projects=[],
        papers=[],
        people=[],
        topics=["macro_geopolitical", "semiconductors"],
        geography=["US", "China"],
        event_type="policy",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-macro-1"],
        metadata={},
    )


def _prediction() -> Prediction:
    return Prediction(
        prediction_id="pred-macro-1",
        created_date="2026-07-01",
        prediction="AI accelerator export controls will tighten.",
        topic_tags=["macro_geopolitical", "semiconductors"],
        companies=["Nvidia"],
        time_horizon="medium",
        horizon_date="2026-12-31",
        probability=0.65,
        evidence="Fixture evidence.",
        resolution_criteria="Policy change occurs.",
        falsification_condition="Controls are relaxed.",
        signals_to_monitor=[],
        status="open",
        confidence="medium",
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "macro_impact_analysis.md").write_text("Macro prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_MACRO_IMPACT_JSON = """{
  "event_id": "event-2026-07-02-macro",
  "event_title": "New chip export controls target AI accelerators",
  "event_type": "export_control",
  "report_worthy": true,
  "exclusion_reason": null,
  "transmission_path": "Export controls constrain accelerator supply.",
  "affected_companies": ["Nvidia", "TSMC"],
  "affected_sectors": ["semiconductors", "ai_infrastructure"],
  "affected_directions": ["AI accelerator supply"],
  "time_dimension": "medium",
  "time_reasoning": "Supply effects compound over several quarters.",
  "severity": "high",
  "confidence": "medium",
  "prediction_impacts": [
    {"prediction_id": "pred-macro-1", "impact": "strengthens"}
  ],
  "report_snippet": "Fixture macro impact snippet."
}"""


def test_analyze_macro_impact_accepts_fake_prompt_runner_plain_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        analyze_macro_impact,
        "_load_macro_watchlist",
        lambda: {"key_policy_domains": {"Nvidia": {}, "TSMC": {}}},
    )
    runner = _prompt_runner(tmp_path, VALID_MACRO_IMPACT_JSON)

    analyses = analyze_macro_impact.analyze_macro_impact(
        [_event()],
        [_prediction()],
        prompt_runner=runner,
    )

    assert list(analyses) == ["event-2026-07-02-macro"]
    assert isinstance(analyses["event-2026-07-02-macro"], MacroImpactAnalysis)
    assert analyses["event-2026-07-02-macro"].severity == "high"
    assert analyses["event-2026-07-02-macro"].prediction_impacts[0]["prediction_id"] == "pred-macro-1"


def test_analyze_one_macro_event_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_MACRO_IMPACT_JSON}\n```")

    analysis = analyze_macro_impact._analyze_one_macro_event(
        _event(),
        ["Nvidia", "TSMC"],
        [{"id": "pred-macro-1", "prediction": "Fixture", "topics": ["macro_geopolitical"]}],
        runner,
    )

    assert analysis is not None
    assert analysis.event_id == "event-2026-07-02-macro"
    assert analysis.affected_companies == ["Nvidia", "TSMC"]
    assert analysis.report_snippet == "Fixture macro impact snippet."


def test_analyze_one_macro_event_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_macro_impact._analyze_one_macro_event(_event(), ["Nvidia"], [], runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_macro_event_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '{"event_id": "event-2026-07-02-macro", "report_worthy": true}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_macro_impact._analyze_one_macro_event(_event(), ["Nvidia"], [], runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "severity" in exc_info.value.message
