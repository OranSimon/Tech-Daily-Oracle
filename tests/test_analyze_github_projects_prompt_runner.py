from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import analyze_github_projects
import pytest
from llm_schemas import GitHubProjectAnalysisResponse
from prompt_runner import PromptRunner, PromptRunnerError
from state import NormalizedEvent, ProjectAnalysis, TrendingItem, TrendingSnapshot
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-github",
        canonical_title="oransimon/fixture-repo trends on GitHub",
        summary="Fixture repo for GitHub analysis.",
        source_urls=["https://github.com/oransimon/fixture-repo"],
        primary_source_url="https://github.com/oransimon/fixture-repo",
        source_type="github",
        published_at=published,
        companies=[],
        projects=["oransimon/fixture-repo"],
        papers=[],
        people=[],
        topics=["developer_tools"],
        geography=[],
        event_type="github_trending",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-github-1"],
        metadata={
            "owner": "oransimon",
            "repo": "fixture-repo",
            "stars": 1200,
            "forks": 42,
            "language": "Python",
            "topics": ["developer-tools"],
            "license": "MIT",
        },
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "github_project_analysis.md").write_text("GitHub prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


def _repo_item() -> dict[str, Any]:
    return {
        "event_id": "event-2026-07-02-github",
        "url": "https://github.com/oransimon/fixture-repo",
        "description": "Fixture repo for GitHub analysis.",
        "meta": _event().metadata,
        "details": {
            "stargazers_count": 1200,
            "forks_count": 42,
            "language": "Python",
            "created_at": "2026-06-01T00:00:00Z",
            "pushed_at": "2026-07-01T00:00:00Z",
            "open_issues_count": 3,
            "license": {"spdx_id": "MIT"},
            "description": "Fixture repo for GitHub analysis.",
            "topics": ["developer-tools"],
            "subscribers_count": 17,
        },
    }


def _trending_item(*, velocity_score: float = 27) -> TrendingItem:
    return TrendingItem(
        item_id="snapshot-owner/snapshot-repo",
        item_type="github_repo",
        source="ossinsight",
        title="snapshot-owner/snapshot-repo",
        url="https://github.com/snapshot-owner/snapshot-repo",
        description="Snapshot repo for GitHub analysis.",
        period="daily",
        rank=1,
        velocity_score=velocity_score,
        language="Rust",
        topics=["developer-tools"],
        snapshot_date="2026-07-02",
        extra={"forks": 9, "total_score": 42},
    )


def _trending_snapshot(*items: TrendingItem) -> TrendingSnapshot:
    return TrendingSnapshot(
        snapshot_date="2026-07-02",
        period="daily",
        github_items=list(items),
        hf_paper_items=[],
        hf_model_items=[],
    )


VALID_GITHUB_PROJECT_JSON = """{
  "repo": "oransimon/fixture-repo",
  "url": "https://github.com/oransimon/fixture-repo",
  "tagline": "Fixture repo for GitHub analysis",
  "stars_total": 1200,
  "stars_today": 20,
  "stars_weekly": 140,
  "language": "Python",
  "created_days_ago": 31,
  "last_commit_days_ago": 1,
  "contributors": 5,
  "license": "MIT",
  "report_worthy": true,
  "filter_out_reason": null,
  "scores": {
    "pain_point": 8,
    "star_velocity": 7,
    "maintenance": 8,
    "documentation": 7,
    "authority_signals": 6,
    "topic_relevance": 8,
    "total": 44
  },
  "what_it_does": "It exercises the GitHub analyzer.",
  "why_it_matters": "Fixture judgment for regression coverage.",
  "risk_label": "strong_signal",
  "verdict": "Watch",
  "topic_tags": ["developer_tools"],
  "hype_risk": "low",
  "signals_to_monitor": ["release cadence"]
}"""


async def _fake_fetch_repo_details(
    client: object,
    owner: str,
    repo: str,
    github_token: str | None,
) -> dict[str, Any]:
    assert owner == "oransimon"
    assert repo == "fixture-repo"
    assert github_token is None
    return _repo_item()["details"]


def test_snapshot_candidates_are_preferred_and_preserve_daily_velocity() -> None:
    candidates, source = analyze_github_projects._select_candidates(
        [_event()],
        _trending_snapshot(_trending_item(velocity_score=27)),
    )

    assert source == "ossinsight"
    assert len(candidates) == 1
    assert candidates[0].full_name == "snapshot-owner/snapshot-repo"
    assert candidates[0].stars_today == 27
    assert candidates[0].stars_weekly == 0
    assert candidates[0].metadata["language"] == "Rust"


def test_normalized_events_are_used_when_snapshot_has_no_github_items() -> None:
    candidates, source = analyze_github_projects._select_candidates([_event()], _trending_snapshot())

    assert source == "normalized_events"
    assert [candidate.full_name for candidate in candidates] == ["oransimon/fixture-repo"]


def test_all_candidate_failures_are_distinct_from_filtered_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRunner:
        def run_json(self, **kwargs: object) -> GitHubProjectAnalysisResponse:
            raise PromptRunnerError(kind="json_parse_error", message="bad JSON")

    monkeypatch.setattr(
        analyze_github_projects,
        "_load_config",
        lambda: {"fetch": {"top_n_in_report": 3, "max_repos_to_analyze": 25}},
    )
    monkeypatch.setattr(analyze_github_projects, "_fetch_repo_details", _fake_fetch_repo_details)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    outcome = analyze_github_projects.analyze_github_projects(
        [_event()],
        prompt_runner=FailingRunner(),
        max_workers=1,
    )

    assert outcome.analyses == {}
    assert outcome.reason == "analysis_failed"
    assert outcome.candidate_count == 1
    assert outcome.analyzed_count == 0
    assert outcome.filtered_count == 0
    assert outcome.failed_count == 1
    assert outcome.failures == ["oransimon/fixture-repo: json_parse_error: bad JSON"]


def test_analyze_github_projects_accepts_fake_prompt_runner_plain_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        analyze_github_projects,
        "_load_config",
        lambda: {"fetch": {"top_n_in_report": 3}},
    )
    monkeypatch.setattr(analyze_github_projects, "_fetch_repo_details", _fake_fetch_repo_details)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    runner = _prompt_runner(tmp_path, VALID_GITHUB_PROJECT_JSON)

    analyses = analyze_github_projects.analyze_github_projects([_event()], prompt_runner=runner, max_workers=1)

    assert list(analyses) == ["oransimon/fixture-repo"]
    assert isinstance(analyses["oransimon/fixture-repo"], ProjectAnalysis)
    assert analyses["oransimon/fixture-repo"].verdict == "Watch"
    assert analyses["oransimon/fixture-repo"].scores["total"] == 44


def test_analyze_github_projects_preserves_positional_prompt_runner_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        analyze_github_projects,
        "_load_config",
        lambda: {"fetch": {"top_n_in_report": 3, "max_repos_to_analyze": 25}},
    )
    monkeypatch.setattr(analyze_github_projects, "_fetch_repo_details", _fake_fetch_repo_details)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    runner = _prompt_runner(tmp_path, VALID_GITHUB_PROJECT_JSON)

    outcome = analyze_github_projects.analyze_github_projects([_event()], runner, 1)

    assert list(outcome) == ["oransimon/fixture-repo"]


def test_analyze_one_repo_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_GITHUB_PROJECT_JSON}\n```")

    result = analyze_github_projects._analyze_one_repo(_repo_item(), runner, repo_count=1, top_n=3)

    assert result is not None
    score, name, analysis = result
    assert score == 44
    assert name == "oransimon/fixture-repo"
    assert analysis.repo == "oransimon/fixture-repo"
    assert analysis.topic_tags == ["developer_tools"]


def test_analyze_one_repo_defaults_unknown_velocity_and_language(tmp_path: Path) -> None:
    response = (
        VALID_GITHUB_PROJECT_JSON.replace('"stars_today": 20', '"stars_today": null')
        .replace('"stars_weekly": 140', '"stars_weekly": null')
        .replace('"language": "Python"', '"language": null')
    )
    runner = _prompt_runner(tmp_path, response)

    result = analyze_github_projects._analyze_one_repo(_repo_item(), runner, repo_count=1, top_n=3)

    assert result is not None
    _, _, analysis = result
    assert analysis.language == "Unknown"
    assert analysis.stars_today == 0
    assert analysis.stars_weekly == 0


def test_analyze_one_repo_payload_includes_prompt_contract_fields() -> None:
    class CapturingRunner:
        payload: dict[str, Any] | None = None

        def run_json(self, **kwargs: object) -> GitHubProjectAnalysisResponse:
            assert isinstance(kwargs["payload"], str)
            self.payload = __import__("json").loads(kwargs["payload"])
            return GitHubProjectAnalysisResponse.model_validate(__import__("json").loads(VALID_GITHUB_PROJECT_JSON))

    runner = CapturingRunner()

    analyze_github_projects._analyze_one_repo(_repo_item(), runner, repo_count=1, top_n=3)

    assert runner.payload is not None
    assert "star_history" in runner.payload
    assert "contributors_count" in runner.payload
    assert "open_issues" in runner.payload
    assert "topics" in runner.payload


def test_analyze_one_repo_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_github_projects._analyze_one_repo(_repo_item(), runner, repo_count=1, top_n=3)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_repo_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '{"repo": "oransimon/fixture-repo", "report_worthy": true}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_github_projects._analyze_one_repo(_repo_item(), runner, repo_count=1, top_n=3)

    assert exc_info.value.kind == "schema_validation_error"
    assert "scores" in exc_info.value.message
