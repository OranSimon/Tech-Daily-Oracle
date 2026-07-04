from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import analyze_social_signals
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import NormalizedEvent, SocialSignalAnalysis
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-social",
        canonical_title="OpenAI fixture model draws intense HN discussion",
        summary="HN users discuss benchmark results for a fixture model.",
        source_urls=["https://news.ycombinator.com/item?id=123"],
        primary_source_url="https://news.ycombinator.com/item?id=123",
        source_type="social",
        published_at=published,
        companies=["OpenAI"],
        projects=[],
        papers=[],
        people=[],
        topics=["ai_models"],
        geography=[],
        event_type="discussion",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.7,
        raw_event_ids=["raw-social-1"],
        metadata={"score": 250, "comments": 83, "hn_url": "https://news.ycombinator.com/item?id=123"},
    )


def _subject_data() -> dict:
    event = _event()
    return {
        "subject": "OpenAI",
        "subject_type": "ai_model",
        "events": [event],
        "trigger_event": event,
    }


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "social_signal_analysis.md").write_text("Social prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_SOCIAL_SIGNAL_JSON = """{
  "subject": "OpenAI",
  "subject_type": "ai_model",
  "trigger_condition_met": true,
  "trigger_reason": "HN discussion crossed the hot threshold.",
  "platforms_sampled": ["hacker_news"],
  "positive_points": ["Developers reproduced useful benchmark results."],
  "negative_points": ["Some users questioned evaluation quality."],
  "controversies": ["Benchmark methodology debate."],
  "authority_opinions": [
    {"person": "A. Researcher", "opinion": "Useful but early.", "platform": "hacker_news"}
  ],
  "community_consensus": "Strong curiosity with cautious adoption.",
  "hype_risk": "medium",
  "hype_risk_reason": "Discussion is intense but production adoption is unproven.",
  "signal_classification": "tech_curiosity",
  "report_worthy": true,
  "report_snippet": "Fixture social signal snippet."
}"""


def test_analyze_social_signals_accepts_fake_prompt_runner_plain_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_SOCIAL_SIGNAL_JSON)

    analyses = analyze_social_signals.analyze_social_signals([_event()], prompt_runner=runner, max_workers=1)

    assert list(analyses) == ["OpenAI"]
    assert isinstance(analyses["OpenAI"], SocialSignalAnalysis)
    assert analyses["OpenAI"].hype_risk == "medium"
    assert analyses["OpenAI"].authority_opinions[0]["person"] == "A. Researcher"


def test_analyze_one_subject_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_SOCIAL_SIGNAL_JSON}\n```")

    analysis = analyze_social_signals._analyze_one_subject(_subject_data(), runner)

    assert analysis is not None
    assert analysis.subject == "OpenAI"
    assert analysis.platforms_sampled == ["hacker_news"]
    assert analysis.report_snippet == "Fixture social signal snippet."


def test_analyze_one_subject_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_social_signals._analyze_one_subject(_subject_data(), runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_subject_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '{"subject": "OpenAI", "report_worthy": true}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_social_signals._analyze_one_subject(_subject_data(), runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "hype_risk" in exc_info.value.message
