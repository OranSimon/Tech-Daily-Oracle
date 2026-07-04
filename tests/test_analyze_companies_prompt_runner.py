from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import analyze_companies
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import NormalizedEvent
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-company",
        canonical_title="OpenAI releases fixture model",
        summary="OpenAI releases a fixture model for company analysis.",
        source_urls=["https://example.com/company"],
        primary_source_url="https://example.com/company",
        source_type="company",
        published_at=published,
        companies=["OpenAI"],
        projects=[],
        papers=[],
        people=[],
        topics=["ai_models"],
        geography=[],
        event_type="product_launch",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-1"],
        metadata={},
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "company_analysis.md").write_text("Company prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


def _company_config() -> dict:
    return {"name": "OpenAI", "category": "ai_lab", "ticker": None, "domains": ["ChatGPT"]}


VALID_COMPANY_JSON = """{
  "category": "ai_lab",
  "report_worthy": true,
  "significance": "high",
  "event_ids": ["event-2026-07-02-company"],
  "summary": "Fixture company summary",
  "analysis_by_category": {"product": "fixture"},
  "confidence": "medium",
  "source_quality": "official",
  "watchlist_action": "none",
  "watchlist_notes": null
}"""


def test_analyze_companies_accepts_fake_prompt_runner_plain_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        analyze_companies,
        "_load_watchlist",
        lambda: {"ai_labs": [_company_config()]},
    )
    runner = _prompt_runner(tmp_path, VALID_COMPANY_JSON)

    analyses = analyze_companies.analyze_companies([_event()], prompt_runner=runner, max_workers=1)

    assert list(analyses) == ["OpenAI"]
    assert analyses["OpenAI"].company == "OpenAI"
    assert analyses["OpenAI"].category == "ai_lab"
    assert analyses["OpenAI"].significance == "high"
    assert analyses["OpenAI"].summary == "Fixture company summary"


def test_analyze_one_company_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_COMPANY_JSON}\n```")

    analysis = analyze_companies._analyze_one_company(_company_config(), [_event()], runner)

    assert analysis is not None
    assert analysis.company == "OpenAI"
    assert analysis.source_quality == "official"


def test_analyze_one_company_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_companies._analyze_one_company(_company_config(), [_event()], runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_company_raises_prompt_runner_error_for_missing_required_fields(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, '{"category": "ai_lab", "report_worthy": true}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_companies._analyze_one_company(_company_config(), [_event()], runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "significance" in exc_info.value.message
