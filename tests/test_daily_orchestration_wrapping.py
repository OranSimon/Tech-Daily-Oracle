from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import daily_step_actions as actions
import run_daily
import storage
from collectors.telemetry import CollectorRunResult, CollectorRunStatus
from state import (
    CompanyAnalysis,
    NormalizedEvent,
    PaperAnalysis,
    Prediction,
    PredictionUpdate,
    ProjectAnalysis,
    TechDailyState,
    TopicSummary,
)


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")
    storage.COLLECTOR_RUNS_LOG = str(tmp_path / "data" / "collector_runs.jsonl")


def _normalized_event() -> NormalizedEvent:
    timestamp = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-fixture",
        canonical_title="Fixture event",
        summary="Fixture summary",
        source_urls=["https://example.com/fixture"],
        primary_source_url="https://example.com/fixture",
        source_type="company",
        published_at=timestamp,
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
        raw_event_ids=[],
        metadata={},
    )


def _topic_summary(event_id: str = "event-2026-07-02-fixture") -> TopicSummary:
    return TopicSummary(
        topic_id="ai_models",
        topic_label="AI Models",
        trend_status="accelerating",
        trend_change="up",
        confidence="medium",
        signal_count=1,
        key_signal_summary="Fixture signal",
        key_events=[event_id],
        multi_signal_check={},
        signal_classification="single_signal",
        classification_reasoning="Fixture",
        short_term_signals=[],
        medium_term_signals=[],
        long_term_signals=[],
        contradictions=[],
        report_worthy=True,
        report_snippet="Fixture snippet",
    )


def _company_analysis(event_id: str = "event-2026-07-02-fixture") -> CompanyAnalysis:
    return CompanyAnalysis(
        company="OpenAI",
        category="AI",
        report_worthy=True,
        significance="high",
        event_ids=[event_id],
        summary="Fixture company analysis",
        analysis_by_category={},
        confidence="medium",
        source_quality="high",
        watchlist_action="monitor",
        watchlist_notes=None,
    )


def _paper_analysis() -> PaperAnalysis:
    return PaperAnalysis(
        paper_id="paper-fixture",
        title="Fixture paper",
        authors=["Ada"],
        institution="Fixture Lab",
        source="arxiv",
        categories=["cs.AI"],
        link="https://example.com/paper",
        code_available=False,
        report_worthy=True,
        signal_strength="medium",
        technical_contribution="Fixture contribution",
        engineering_product_impact=None,
        novelty_score=0.5,
        impact_score=0.6,
        overall_score=0.55,
        why_notable="Fixture notable reason",
        caveats="Fixture caveat",
        topic_tags=["ai_models"],
        related_companies=["OpenAI"],
        related_predictions=[],
        hype_risk="medium",
        hype_risk_reason=None,
    )


def _project_analysis() -> ProjectAnalysis:
    return ProjectAnalysis(
        repo="example/repo",
        url="https://github.com/example/repo",
        tagline="Fixture project",
        stars_total=100,
        stars_today=10,
        stars_weekly=20,
        language="Python",
        created_days_ago=5,
        last_commit_days_ago=1,
        contributors=3,
        license="MIT",
        report_worthy=True,
        filter_out_reason=None,
        scores={"momentum": 8},
        what_it_does="Does fixture things",
        why_it_matters="Matters for tests",
        risk_label="medium",
        verdict="monitor",
        topic_tags=["ai_models"],
        hype_risk="medium",
        signals_to_monitor=[],
    )


def _prediction(prediction_id: str = "P20260702-1", status: str = "open") -> Prediction:
    return Prediction(
        prediction_id=prediction_id,
        created_date="2026-07-02",
        prediction="Fixture prediction",
        topic_tags=["ai_models"],
        companies=["OpenAI"],
        time_horizon="30 days",
        horizon_date="2026-08-01",
        probability=0.55,
        evidence="Fixture evidence",
        resolution_criteria="Fixture criteria",
        falsification_condition="Fixture falsification",
        signals_to_monitor=[],
        status=status,
        confidence="medium",
    )


def _prediction_update() -> PredictionUpdate:
    return PredictionUpdate(
        prediction_id="P20260702-1",
        update_date="2026-07-02",
        evidence_summary="Fixture evidence",
        impact="increase",
        probability_before=0.5,
        probability_after=0.6,
        reasoning="Fixture reasoning",
        source_event_ids=["event-2026-07-02-fixture"],
        resolution={"resolved": False},
    )


def _run_daily_with_fakes(
    monkeypatch,
    tmp_path: Path,
    *,
    config: dict | None = None,
    normalized_events: list[NormalizedEvent] | None = None,
    collect_trending_snapshot_impl=None,
    load_trending_history_impl=None,
    analyze_topics_impl=None,
    analyze_companies_impl=None,
    analyze_papers_impl=None,
    analyze_github_projects_impl=None,
    analyze_trending_impl=None,
    analyze_social_signals_impl=None,
    analyze_macro_impact_impl=None,
    analyze_market_signals_impl=None,
    load_last_signal_per_ticker_impl=None,
    run_prediction_updates_impl=None,
    generate_new_predictions_impl=None,
    generate_daily_report_impl=None,
    publish_to_notion_impl=None,
) -> tuple[str, TechDailyState]:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    raw_config = config or {
        "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
        "market_signal": {"enabled": False, "live_data": False},
        "notion": {"enabled": False},
        "trending": {"top_n": 5},
    }
    monkeypatch.setattr(run_daily, "_load_config", lambda: raw_config)
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(actions, "load_trending_history", load_trending_history_impl or (lambda *args, **kwargs: []))
    monkeypatch.setattr(
        actions,
        "load_last_signal_per_ticker",
        load_last_signal_per_ticker_impl or (lambda *args, **kwargs: []),
    )

    events = normalized_events if normalized_events is not None else [_normalized_event()]
    captured: dict[str, TechDailyState] = {}

    monkeypatch.setattr(
        actions,
        "collect_sources_with_telemetry",
        lambda cfg, run_date, persist_telemetry, run_id: (
            [],
            [
                CollectorRunResult(
                    collector_name="fixture",
                    status=CollectorRunStatus.SUCCESS,
                    duration_seconds=0.01,
                    record_count=0,
                )
            ],
        ),
        raising=False,
    )
    monkeypatch.setattr(
        actions,
        "collect_trending_snapshot",
        collect_trending_snapshot_impl or (lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(actions, "normalize_events", lambda raw_events, run_date: events)
    monkeypatch.setattr(actions, "analyze_topics", analyze_topics_impl or (lambda normalized: {}))
    monkeypatch.setattr(actions, "analyze_companies", analyze_companies_impl or (lambda normalized: {}))
    monkeypatch.setattr(actions, "analyze_papers", analyze_papers_impl or (lambda normalized: {}))
    monkeypatch.setattr(
        actions,
        "analyze_github_projects",
        analyze_github_projects_impl or (lambda normalized: {}),
    )
    monkeypatch.setattr(actions, "analyze_trending", analyze_trending_impl or (lambda snapshot, history, top_n: None))
    monkeypatch.setattr(actions, "analyze_social_signals", analyze_social_signals_impl or (lambda normalized: {}))
    monkeypatch.setattr(
        actions,
        "analyze_macro_impact",
        analyze_macro_impact_impl or (lambda normalized, predictions: {}),
    )
    if analyze_market_signals_impl is not None:
        monkeypatch.setitem(
            sys.modules,
            "analyze_market_signals",
            types.SimpleNamespace(analyze_market_signals=analyze_market_signals_impl),
        )
    monkeypatch.setattr(actions, "run_prediction_updates", run_prediction_updates_impl or (lambda state: []))
    monkeypatch.setattr(actions, "generate_new_predictions", generate_new_predictions_impl or (lambda state: []))
    monkeypatch.setattr(actions, "save_market_signals", lambda *args, **kwargs: None)

    def fake_report(state: TechDailyState) -> str:
        captured["state"] = state
        if generate_daily_report_impl is not None:
            return generate_daily_report_impl(state)
        return "# Tech Daily Brief — 2026-07-02\n"

    monkeypatch.setattr(actions, "generate_daily_report", fake_report)
    monkeypatch.setattr(actions, "publish_to_notion", publish_to_notion_impl or (lambda *args, **kwargs: None))

    report = run_daily.run_daily("2026-07-02", force=True)
    return report, captured["state"]


def test_topic_analysis_success_updates_state_and_step_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    topic = _topic_summary()

    def fake_analyze_topics(events: list[NormalizedEvent]) -> dict[str, TopicSummary]:
        assert events == [_normalized_event()]
        return {"ai_models": topic}

    report, state = _run_daily_with_fakes(monkeypatch, tmp_path, analyze_topics_impl=fake_analyze_topics)
    output = capsys.readouterr().out

    assert report.startswith("# Tech Daily Brief")
    assert state.topic_summaries == {"ai_models": topic}
    assert state.confidence_flags == []
    assert "step=Analyzing topics message=completed" in output
    assert '"name": "Analyzing topics"' in output


def test_topic_analysis_failure_preserves_default_state_and_confidence_flag(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    def fail_topics(events: list[NormalizedEvent]) -> dict[str, TopicSummary]:
        raise RuntimeError("topic analyzer unavailable")

    _, state = _run_daily_with_fakes(monkeypatch, tmp_path, analyze_topics_impl=fail_topics)
    output = capsys.readouterr().out

    assert state.topic_summaries == {}
    assert state.confidence_flags == ["Topic analysis error: topic analyzer unavailable"]
    assert "[ERROR] Topic analysis failed: topic analyzer unavailable" in output
    assert "step=Analyzing topics message=topic analysis failed" in output


def test_topic_analysis_empty_normalized_input_uses_analyzer_result(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[NormalizedEvent]] = []

    def fake_analyze_topics(events: list[NormalizedEvent]) -> dict[str, TopicSummary]:
        calls.append(events)
        return {}

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        normalized_events=[],
        analyze_topics_impl=fake_analyze_topics,
    )

    assert calls == [[]]
    assert state.topic_summaries == {}
    assert state.confidence_flags == []


def test_company_paper_and_github_analysis_success_update_state(monkeypatch, tmp_path: Path, capsys) -> None:
    company = _company_analysis()
    paper = _paper_analysis()
    project = _project_analysis()

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        analyze_companies_impl=lambda events: {"OpenAI": company},
        analyze_papers_impl=lambda events: {"paper-fixture": paper},
        analyze_github_projects_impl=lambda events: {"example/repo": project},
    )
    output = capsys.readouterr().out

    assert state.company_analyses == {"OpenAI": company}
    assert state.paper_analyses == {"paper-fixture": paper}
    assert state.github_project_analyses == {"example/repo": project}
    assert state.confidence_flags == []
    assert "step=Analyzing companies message=completed" in output
    assert "step=Analyzing papers message=completed" in output
    assert "step=Analyzing GitHub projects message=completed" in output


def test_company_paper_and_github_analysis_failures_preserve_fallbacks(monkeypatch, tmp_path: Path, capsys) -> None:
    def fail_company(events: list[NormalizedEvent]):
        raise RuntimeError("company unavailable")

    def fail_papers(events: list[NormalizedEvent]):
        raise RuntimeError("paper unavailable")

    def fail_github(events: list[NormalizedEvent]):
        raise RuntimeError("github unavailable")

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        analyze_companies_impl=fail_company,
        analyze_papers_impl=fail_papers,
        analyze_github_projects_impl=fail_github,
    )
    output = capsys.readouterr().out

    assert state.company_analyses == {}
    assert state.paper_analyses == {}
    assert state.github_project_analyses == {}
    assert state.confidence_flags == [
        "Company analysis error: company unavailable",
        "Paper analysis error: paper unavailable",
        "GitHub analysis error: github unavailable",
    ]
    assert "[ERROR] Company analysis failed: company unavailable" in output
    assert "[ERROR] Paper analysis failed: paper unavailable" in output
    assert "[ERROR] GitHub analysis failed: github unavailable" in output
    assert "step=Analyzing companies message=company analysis failed" in output
    assert "step=Analyzing papers message=paper analysis failed" in output
    assert "step=Analyzing GitHub projects message=github analysis failed" in output


def test_company_paper_and_github_empty_input_passes_through(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, list[NormalizedEvent]] = {}

    def companies(events: list[NormalizedEvent]):
        calls["companies"] = events
        return {}

    def papers(events: list[NormalizedEvent]):
        calls["papers"] = events
        return {}

    def github(events: list[NormalizedEvent]):
        calls["github"] = events
        return {}

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        normalized_events=[],
        analyze_companies_impl=companies,
        analyze_papers_impl=papers,
        analyze_github_projects_impl=github,
    )

    assert calls == {"companies": [], "papers": [], "github": []}
    assert state.company_analyses == {}
    assert state.paper_analyses == {}
    assert state.github_project_analyses == {}


def test_social_macro_trending_and_market_analysis_success_update_state(monkeypatch, tmp_path: Path, capsys) -> None:
    trending_snapshot = {"period": "daily", "items": [{"name": "fixture"}]}
    trending_history = [{"period": "daily", "items": []}]
    captured: dict[str, object] = {}

    def fake_trending(snapshot, history, top_n):
        captured["trending_args"] = (snapshot, history, top_n)
        return "trending-analysis"

    def fake_social(events: list[NormalizedEvent]):
        captured["social_events"] = events
        return {"social": "analysis"}

    def fake_macro(events: list[NormalizedEvent], predictions: list):
        captured["macro_args"] = (events, predictions)
        return {"macro": "analysis"}

    def fake_market(state, market_data, prior_signals, config):
        captured["market_args"] = (market_data, prior_signals)
        return {"NVDA": "market-analysis"}

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        config={
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": True, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
        collect_trending_snapshot_impl=lambda *args, **kwargs: trending_snapshot,
        load_trending_history_impl=lambda *args, **kwargs: trending_history,
        analyze_trending_impl=fake_trending,
        analyze_social_signals_impl=fake_social,
        analyze_macro_impact_impl=fake_macro,
        analyze_market_signals_impl=fake_market,
        load_last_signal_per_ticker_impl=lambda: [],
    )
    output = capsys.readouterr().out

    assert state.trending_analysis == "trending-analysis"
    assert state.social_signal_analyses == {"social": "analysis"}
    assert state.macro_impact_analyses == {"macro": "analysis"}
    assert state.market_signal_analyses == {"NVDA": "market-analysis"}
    assert captured["trending_args"] == (trending_snapshot, trending_history, 5)
    assert captured["social_events"] == [_normalized_event()]
    assert captured["macro_args"] == ([_normalized_event()], [])
    assert captured["market_args"] == (None, [])
    assert "step=Analyzing trending items message=completed" in output
    assert "step=Analyzing social signals message=completed" in output
    assert "step=Analyzing macro/geopolitical impact message=completed" in output
    assert "step=Analyzing market signals (MarketSignalAgent) message=completed" in output


def test_social_macro_trending_and_market_analysis_failures_preserve_fallbacks(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    def fail_trending(snapshot, history, top_n):
        raise RuntimeError("trending analysis unavailable")

    def fail_social(events: list[NormalizedEvent]):
        raise RuntimeError("social unavailable")

    def fail_macro(events: list[NormalizedEvent], predictions: list):
        raise RuntimeError("macro unavailable")

    def fail_market(state, market_data, prior_signals, config):
        raise RuntimeError("market unavailable")

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        config={
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": True, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
        collect_trending_snapshot_impl=lambda *args, **kwargs: {"period": "daily"},
        load_trending_history_impl=lambda *args, **kwargs: [],
        analyze_trending_impl=fail_trending,
        analyze_social_signals_impl=fail_social,
        analyze_macro_impact_impl=fail_macro,
        analyze_market_signals_impl=fail_market,
        load_last_signal_per_ticker_impl=lambda: [],
    )
    output = capsys.readouterr().out

    assert state.trending_analysis is None
    assert state.social_signal_analyses == {}
    assert state.macro_impact_analyses == {}
    assert state.market_signal_analyses == {}
    assert state.confidence_flags == []
    assert "[ERROR] Trending analysis failed (non-fatal): trending analysis unavailable" in output
    assert "[ERROR] Social analysis failed: social unavailable" in output
    assert "[ERROR] Macro analysis failed: macro unavailable" in output
    assert "[MarketSignal] Analysis failed (non-fatal): market unavailable" in output
    assert "step=Analyzing trending items message=trending analysis failed" in output
    assert "step=Analyzing social signals message=social analysis failed" in output
    assert "step=Analyzing macro/geopolitical impact message=macro analysis failed" in output
    assert "step=Analyzing market signals (MarketSignalAgent) message=market signal analysis failed" in output


def test_prediction_steps_success_preserve_returned_updates_and_new_predictions(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    update = _prediction_update()
    duplicate_predictions = [
        _prediction("P20260702-DUP", status="open"),
        _prediction("P20260702-DUP", status="open"),
    ]

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        run_prediction_updates_impl=lambda state: [update],
        generate_new_predictions_impl=lambda state: duplicate_predictions,
    )
    output = capsys.readouterr().out

    assert state.prediction_updates == [update]
    assert state.new_predictions == duplicate_predictions
    assert [prediction.status for prediction in state.new_predictions] == ["open", "open"]
    assert "step=Updating predictions message=completed" in output
    assert "step=Generating new predictions message=completed" in output


def test_prediction_step_failures_preserve_empty_fallbacks(monkeypatch, tmp_path: Path, capsys) -> None:
    def fail_updates(state: TechDailyState):
        raise RuntimeError("prediction updates unavailable")

    def fail_new_predictions(state: TechDailyState):
        raise RuntimeError("new predictions unavailable")

    _, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        run_prediction_updates_impl=fail_updates,
        generate_new_predictions_impl=fail_new_predictions,
    )
    output = capsys.readouterr().out

    assert state.prediction_updates == []
    assert state.new_predictions == []
    assert "[ERROR] Prediction updates failed: prediction updates unavailable" in output
    assert "[ERROR] New predictions failed: new predictions unavailable" in output
    assert "step=Updating predictions message=prediction updates failed" in output
    assert "step=Generating new predictions message=new predictions failed" in output


def test_report_generation_and_saving_steps_are_wrapped(monkeypatch, tmp_path: Path, capsys) -> None:
    report, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        generate_daily_report_impl=lambda state: "# Tech Daily Brief — 2026-07-02\n\nFixture report.\n",
    )
    output = capsys.readouterr().out

    assert report == "# Tech Daily Brief — 2026-07-02\n\nFixture report.\n"
    assert state.final_report == report
    assert (tmp_path / "reports" / "daily" / "2026-07-02.md").read_text(encoding="utf-8") == report
    assert "step=Generating daily brief report message=completed" in output
    assert "step=Saving outputs message=completed" in output


def test_report_generation_failure_preserves_error_report_fallback(monkeypatch, tmp_path: Path, capsys) -> None:
    def fail_report(state: TechDailyState) -> str:
        raise RuntimeError("report unavailable")

    report, state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        generate_daily_report_impl=fail_report,
    )
    output = capsys.readouterr().out

    assert report == "# Tech Daily Brief — 2026-07-02\n\n[Report generation failed: report unavailable]"
    assert (tmp_path / "reports" / "daily" / "2026-07-02.md").read_text(encoding="utf-8") == report
    assert "[ERROR] Report generation failed: report unavailable" in output
    assert "step=Generating daily brief report message=report generation failed" in output


def test_notion_publish_failure_remains_non_fatal(monkeypatch, tmp_path: Path, capsys) -> None:
    def fail_notion(run_date: str, final_report: str, cfg: dict) -> str | None:
        raise RuntimeError("notion unavailable")

    report, _state = _run_daily_with_fakes(
        monkeypatch,
        tmp_path,
        config={
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": True},
            "trending": {"top_n": 5},
        },
        publish_to_notion_impl=fail_notion,
    )
    output = capsys.readouterr().out

    assert report.startswith("# Tech Daily Brief")
    assert "[Notion] Publish failed (non-fatal): notion unavailable" in output
    assert "step=Publishing to Notion message=notion publish failed" in output
