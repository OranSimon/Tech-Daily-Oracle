from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import analyze_papers
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import NormalizedEvent, PaperAnalysis
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-paper",
        canonical_title="Fixture paper improves retrieval",
        summary="A fixture paper introduces a retrieval benchmark.",
        source_urls=["https://arxiv.org/abs/2607.00001"],
        primary_source_url="https://arxiv.org/abs/2607.00001",
        source_type="paper",
        published_at=published,
        companies=[],
        projects=[],
        papers=["Fixture paper improves retrieval"],
        people=[],
        topics=["papers_research", "ai_models"],
        geography=[],
        event_type="paper",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-paper-1"],
        metadata={
            "authors": ["A. Researcher"],
            "arxiv_id": "2607.00001",
            "source_name": "arXiv",
        },
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "paper_analysis.md").write_text("Paper prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_PAPER_JSON = """{
  "paper_id": "paper-fixture",
  "title": "Fixture paper improves retrieval",
  "authors": ["A. Researcher"],
  "institution": "Fixture Lab",
  "source": "arXiv",
  "categories": ["papers_research", "ai_models"],
  "link": "https://arxiv.org/abs/2607.00001",
  "code_available": true,
  "report_worthy": true,
  "signal_strength": "high",
  "technical_contribution": "Introduces a fixture benchmark.",
  "engineering_product_impact": "Could improve retrieval evals.",
  "novelty_score": 0.8,
  "impact_score": 0.7,
  "overall_score": 0.75,
  "why_notable": "It is useful as a regression fixture.",
  "caveats": "Synthetic example.",
  "topic_tags": ["ai_models"],
  "related_companies": ["OpenAI"],
  "related_predictions": [],
  "hype_risk": "low",
  "hype_risk_reason": null
}"""


def test_analyze_papers_accepts_fake_prompt_runner_plain_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_PAPER_JSON)

    analyses = analyze_papers.analyze_papers([_event()], prompt_runner=runner, max_workers=1)

    assert list(analyses) == ["paper-fixture"]
    assert isinstance(analyses["paper-fixture"], PaperAnalysis)
    assert analyses["paper-fixture"].title == "Fixture paper improves retrieval"
    assert analyses["paper-fixture"].signal_strength == "high"
    assert analyses["paper-fixture"].topic_tags == ["ai_models"]


def test_analyze_one_paper_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_PAPER_JSON}\n```")

    analysis = analyze_papers._analyze_one_paper(_event(), runner)

    assert analysis is not None
    assert analysis.paper_id == "paper-fixture"
    assert analysis.source == "arXiv"
    assert analysis.related_companies == ["OpenAI"]


def test_analyze_one_paper_defaults_null_technical_contribution(tmp_path: Path) -> None:
    runner = _prompt_runner(
        tmp_path,
        VALID_PAPER_JSON.replace(
            '"technical_contribution": "Introduces a fixture benchmark."',
            '"technical_contribution": null',
        ),
    )

    analysis = analyze_papers._analyze_one_paper(_event(), runner)

    assert analysis is not None
    assert analysis.technical_contribution == "Unspecified technical contribution."


def test_analyze_one_paper_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_papers._analyze_one_paper(_event(), runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_paper_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '{"paper_id": "paper-fixture", "report_worthy": true}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_papers._analyze_one_paper(_event(), runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "title" in exc_info.value.message


def test_analyze_one_paper_preserves_legacy_paper_id_fallback(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_PAPER_JSON.replace('"paper_id": "paper-fixture",\n  ', ""))

    analysis = analyze_papers._analyze_one_paper(_event(), runner)

    assert analysis is not None
    assert analysis.paper_id == "event-2026-07-02-paper"
