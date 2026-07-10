from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import generate_report
from pipeline_state import (
    AnalysisState,
    CorpusState,
    DiagnosticsState,
    HistoricalContextState,
    PredictionState,
    ReportInputState,
    RunMetadataState,
)
from prompt_runner import PromptRunner
from state import ProjectAnalysis, TechDailyState
from test_prompt_runner import FakeLLMClient

from tech_daily.reports import daily as daily_report


def _project_analysis(*, verdict: str) -> ProjectAnalysis:
    return ProjectAnalysis(
        repo="owner/repo",
        url="https://github.com/owner/repo",
        tagline="Fixture repository",
        stars_total=1200,
        stars_today=25,
        stars_weekly=100,
        language="Python",
        created_days_ago=30,
        last_commit_days_ago=1,
        contributors=8,
        license="MIT",
        report_worthy=True,
        filter_out_reason=None,
        scores={"total": 40},
        what_it_does="Exercises report rendering.",
        why_it_matters="Fixture judgment.",
        risk_label="promising",
        verdict=verdict,
        topic_tags=["developer_tools"],
        hype_risk="low",
        signals_to_monitor=["releases"],
    )


def test_build_report_payload_contains_existing_report_generation_contract() -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")

    payload = daily_report._build_report_payload(state)

    assert payload["run_date"] == "2026-07-02"
    assert payload["normalized_events"] == []
    assert payload["topic_summaries"] == {}
    assert payload["open_predictions"] == []
    assert payload["history_context"] == {
        "weekly_reviews": [],
        "monthly_reviews": [],
        "topic_trend_30d": [],
        "company_mentions_90d": [],
    }
    assert payload["signal_level"] == "normal"


def test_report_payload_distinguishes_no_watch_from_source_empty() -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    state.github_project_analyses = {"owner/repo": _project_analysis(verdict="Track")}
    state.github_project_analysis_status = {
        "reason": "accepted_projects_available",
        "source": "ossinsight",
        "candidate_count": 3,
        "analyzed_count": 3,
        "filtered_count": 2,
        "failed_count": 0,
        "failures": [],
    }

    payload = daily_report._build_report_payload(state)

    assert payload["github_project_analyses"] == []
    assert payload["github_project_analysis_status"]["reason"] == "no_watch_verdict"
    assert payload["github_project_analysis_status"]["candidate_count"] == 3


def test_empty_github_section_is_replaced_without_internal_prompt_text(monkeypatch, tmp_path: Path) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    response = (
        "# Tech Daily Brief — 2026-07-02\n\n"
        "## 5. GitHub Trending: Top 3 High-Signal Repos\n\n"
        "**CRITICAL DATA-INTEGRITY RULE:** leaked\n\n"
        "## 6. Papers & Research Frontiers\n"
    )
    runner = PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)
    monkeypatch.setattr(daily_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100}})
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {})

    report = daily_report.generate_daily_report(state, prompt_runner=runner)

    assert "CRITICAL DATA-INTEGRITY RULE" not in report
    assert "未获取到可分析的 GitHub 趋势候选" in report
    assert report.count("## 5. GitHub Trending: Top 3 High-Signal Repos") == 1
    assert "## 6. Papers & Research Frontiers" in report


def test_daily_prompt_does_not_contain_displayable_internal_rule_label() -> None:
    prompt = Path("prompts/daily_brief.md").read_text(encoding="utf-8")

    assert "CRITICAL DATA-INTEGRITY RULE" not in prompt


def test_report_input_from_typed_states_matches_tech_daily_state_payload(monkeypatch) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    state.source_warnings = ["source warning"]
    state.confidence_flags = ["confidence flag"]
    state.signal_level = "high"
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {"timezone": "UTC"})

    typed_input = ReportInputState.from_typed_states(
        run_metadata=RunMetadataState.from_tech_daily_state(state),
        corpus=CorpusState.from_tech_daily_state(state),
        historical_context=HistoricalContextState.from_tech_daily_state(state),
        analysis=AnalysisState.from_tech_daily_state(state),
        prediction=PredictionState.from_tech_daily_state(state),
        diagnostics=DiagnosticsState.from_tech_daily_state(state),
    )

    assert daily_report.build_daily_report_payload_from_input(typed_input) == daily_report._build_report_payload(state)


def test_generate_daily_report_from_typed_input_uses_fake_prompt_runner(monkeypatch, tmp_path: Path) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    typed_input = ReportInputState.from_tech_daily_state(state)
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    fake = FakeLLMClient("# Tech Daily Brief — 2026-07-02\n\n## 1. 今日一句话判断\n")
    runner = PromptRunner(fake, prompt_root=tmp_path)

    monkeypatch.setattr(daily_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100, "default": "model"}})
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {})

    report = generate_report.generate_daily_report_from_input(typed_input, prompt_runner=runner)

    assert report.startswith("# Tech Daily Brief — 2026-07-02")
    assert fake.calls[0]["system"] == "Daily prompt"
    assert fake.calls[0]["model"] == "model"
    assert fake.calls[0]["max_tokens"] == 100


def test_generate_report_wrapper_monkeypatches_loader_for_typed_input(monkeypatch, tmp_path: Path) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    typed_input = ReportInputState.from_tech_daily_state(state)
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    fake = FakeLLMClient("# Tech Daily Brief — 2026-07-02\n\n## 1. 今日一句话判断\n")
    runner = PromptRunner(fake, prompt_root=tmp_path)

    monkeypatch.setattr(
        generate_report,
        "_load_config",
        lambda: {"model": {"max_tokens_daily": 123, "default": "wrapper-model"}},
    )
    monkeypatch.setattr(generate_report, "_load_preferences", lambda: {})

    report = generate_report.generate_daily_report_from_input(typed_input, prompt_runner=runner)

    assert report.startswith("# Tech Daily Brief — 2026-07-02")
    assert fake.calls[0]["system"] == "Daily prompt"
    assert fake.calls[0]["model"] == "wrapper-model"
    assert fake.calls[0]["max_tokens"] == 123


def test_generate_daily_report_uses_fake_prompt_runner_and_appends_trending_section(
    monkeypatch, tmp_path: Path
) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    state.trending_analysis = SimpleNamespace(report_section="## 🔥 趋势榜单 — 今日 (2026-07-02)")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    fake = FakeLLMClient("# Tech Daily Brief — 2026-07-02\n\n## 1. 今日一句话判断\n")
    runner = PromptRunner(fake, prompt_root=tmp_path)

    monkeypatch.setattr(daily_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100, "default": "model"}})
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {})

    report = generate_report.generate_daily_report(state, prompt_runner=runner)

    assert report.startswith("# Tech Daily Brief — 2026-07-02")
    assert "---\n## 🔥 趋势榜单 — 今日 (2026-07-02)" in report
    assert fake.calls[0]["system"] == "Daily prompt"
    assert fake.calls[0]["model"] == "model"
    assert fake.calls[0]["max_tokens"] == 100


def test_generate_daily_report_surfaces_fake_llm_failure(monkeypatch, tmp_path: Path) -> None:
    class FailingLLMClient:
        def generate_text(self, **kwargs):
            raise RuntimeError("fake LLM failure")

    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    runner = PromptRunner(FailingLLMClient(), prompt_root=tmp_path)
    monkeypatch.setattr(daily_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100}})
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {})

    try:
        generate_report.generate_daily_report(state, prompt_runner=runner)
    except RuntimeError as exc:
        assert "fake LLM failure" in str(exc)
    else:
        raise AssertionError("Expected fake LLM failure to surface")
