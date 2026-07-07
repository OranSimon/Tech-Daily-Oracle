from __future__ import annotations

import json
from pathlib import Path

import storage
from state import (
    CompanyAnalysis,
    MarketSignalAnalysis,
    NormalizedEvent,
    PaperAnalysis,
    Prediction,
    PredictionUpdate,
    ProjectAnalysis,
    TechDailyState,
    TopicSummary,
    TrendingItem,
    TrendingSnapshot,
)


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")


def _prediction(pid: str = "P1") -> Prediction:
    return Prediction(
        prediction_id=pid,
        created_date="2026-07-02",
        prediction="A test prediction",
        topic_tags=["ai_models"],
        companies=["OpenAI"],
        time_horizon="30 days",
        horizon_date="2026-08-01",
        probability=0.6,
        evidence="Fixture evidence",
        resolution_criteria="Fixture criteria",
        falsification_condition="Fixture falsification",
        signals_to_monitor=[],
        status="open",
        confidence="medium",
    )


def test_save_and_load_open_predictions_round_trip(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    pred = _prediction()

    storage.save_predictions([pred], [])
    loaded = storage.load_open_predictions()

    assert [p.prediction_id for p in loaded] == ["P1"]
    assert loaded[0].probability == 0.6
    assert Path(storage.PREDICTION_LOG).exists()


def test_save_predictions_applies_updates_and_resolution(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    storage.save_predictions([_prediction()], [])

    update = PredictionUpdate(
        prediction_id="P1",
        update_date="2026-07-03",
        evidence_summary="Resolved evidence",
        impact="strengthens",
        probability_before=0.6,
        probability_after=0.9,
        reasoning="Fixture reasoning",
        source_event_ids=["event-1"],
        resolution={
            "resolved": True,
            "resolved_as": "true",
            "resolution_reasoning": "Criteria met",
        },
    )

    storage.save_predictions([], [update])

    rows = [json.loads(line) for line in Path(storage.PREDICTION_LOG).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["probability"] == 0.9
    assert rows[0]["status"] == "resolved_true"
    assert rows[0]["updates"][0]["source_event_ids"] == ["event-1"]
    assert storage.load_open_predictions() == []


def test_report_storage_uses_existing_directory_contract(tmp_path: Path) -> None:
    _point_storage_at(tmp_path)

    daily_path = Path(storage.save_daily_report("2026-07-02", "# Daily"))
    weekly_path = Path(storage.save_weekly_review("2026-W26", "# Weekly"))
    monthly_path = Path(storage.save_monthly_review("2026-06", "# Monthly"))

    assert daily_path == tmp_path / "reports" / "daily" / "2026-07-02.md"
    assert weekly_path == tmp_path / "reports" / "weekly" / "2026-W26.md"
    assert monthly_path == tmp_path / "reports" / "monthly" / "2026-06.md"
    assert daily_path.read_text(encoding="utf-8") == "# Daily"


def test_storage_context_builds_expected_default_paths(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)

    assert context.root_dir == tmp_path
    assert context.data_dir == tmp_path / "data"
    assert context.reports_dir == tmp_path / "reports"
    assert context.daily_report_path("2026-07-02") == tmp_path / "reports" / "daily" / "2026-07-02.md"
    assert context.weekly_report_path("2026-W26") == tmp_path / "reports" / "weekly" / "2026-W26.md"
    assert context.monthly_report_path("2026-06") == tmp_path / "reports" / "monthly" / "2026-06.md"
    assert context.prediction_log_path() == tmp_path / "data" / "prediction_log.jsonl"
    assert context.collector_telemetry_path() == tmp_path / "data" / "collector_runs.jsonl"


def test_report_storage_accepts_storage_context_without_changing_paths(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)

    daily_path = Path(storage.save_daily_report("2026-07-02", "# Daily", storage_context=context))
    weekly_path = Path(storage.save_weekly_review("2026-W26", "# Weekly", storage_context=context))
    monthly_path = Path(storage.save_monthly_review("2026-06", "# Monthly", storage_context=context))

    assert daily_path == context.daily_report_path("2026-07-02")
    assert weekly_path == context.weekly_report_path("2026-W26")
    assert monthly_path == context.monthly_report_path("2026-06")


def test_prediction_storage_accepts_storage_context(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    pred = _prediction()

    storage.save_predictions([pred], [], storage_context=context)
    loaded = storage.load_open_predictions(storage_context=context)

    assert context.prediction_log_path().exists()
    assert [p.prediction_id for p in loaded] == ["P1"]


def test_append_events_accepts_storage_context(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    state.normalized_events = [
        NormalizedEvent(
            event_id="event-1",
            canonical_title="Context-aware storage event",
            summary="A fixture event",
            source_urls=["https://example.com/event-1"],
            primary_source_url="https://example.com/event-1",
            source_type="media",
            published_at="2026-07-02T00:00:00+00:00",
            companies=[],
            projects=[],
            papers=[],
            people=[],
            topics=["ai_models"],
            geography=[],
            event_type="news",
            raw_event_ids=["raw-1"],
        )
    ]

    storage.append_events(state, storage_context=context)

    source_events_path = context.data_dir / "source_events.jsonl"
    rows = [json.loads(line) for line in source_events_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["run_date"] == "2026-07-02"
    assert rows[0]["event_id"] == "event-1"


def test_append_event_payload_writes_same_artifacts_as_state_append(tmp_path: Path) -> None:
    from tech_daily.storage.context import StorageContext
    from tech_daily.storage.event_payloads import EventStoragePayload
    from tech_daily.storage.events import append_event_payload

    state = TechDailyState(run_id="run-1", run_date="2026-07-02", time_window="last_24h")
    state.normalized_events = [
        NormalizedEvent(
            event_id="event-1",
            canonical_title="Fixture",
            summary="Fixture summary",
            source_urls=["https://example.com"],
            primary_source_url="https://example.com",
            source_type="company",
            published_at="2026-07-02T00:00:00+00:00",
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
    ]
    state.topic_summaries = {
        "ai_models": TopicSummary(
            topic_id="ai_models",
            topic_label="AI Models",
            trend_status="accelerating",
            trend_change="up",
            confidence="medium",
            signal_count=1,
            key_signal_summary="Fixture",
            key_events=["event-1"],
            multi_signal_check={},
            signal_classification="single_signal",
            classification_reasoning="Fixture",
            short_term_signals=[],
            medium_term_signals=[],
            long_term_signals=[],
            contradictions=[],
            report_worthy=True,
            report_snippet="Fixture",
        )
    }
    state.company_analyses = {
        "OpenAI": CompanyAnalysis(
            company="OpenAI",
            category="product",
            report_worthy=True,
            significance="high",
            event_ids=["event-1"],
            summary="OpenAI shipped the fixture launch.",
            analysis_by_category={"product": "Launch expands model access."},
            confidence="high",
            source_quality="high",
            watchlist_action="monitor",
            watchlist_notes="Track adoption.",
        )
    }
    state.paper_analyses = {
        "paper-1": PaperAnalysis(
            paper_id="paper-1",
            title="Fixture Paper",
            authors=["Ada Lovelace"],
            institution="Fixture Lab",
            source="arxiv",
            categories=["ai_models"],
            link="https://example.com/paper-1",
            code_available=True,
            report_worthy=True,
            signal_strength="strong",
            technical_contribution="Demonstrates fixture method.",
            engineering_product_impact="Useful for production evaluation.",
            novelty_score=0.7,
            impact_score=0.8,
            overall_score=0.9,
            why_notable="Strong benchmark gains.",
            caveats="Synthetic example.",
            topic_tags=["ai_models"],
            related_companies=["OpenAI"],
            related_predictions=[],
            hype_risk="low",
            hype_risk_reason="Backed by reproducible details.",
        )
    }
    state.github_project_analyses = {
        "openai/fixture-project": ProjectAnalysis(
            repo="openai/fixture-project",
            url="https://github.com/openai/fixture-project",
            tagline="Fixture project",
            stars_total=1234,
            stars_today=45,
            stars_weekly=120,
            language="Python",
            created_days_ago=30,
            last_commit_days_ago=1,
            contributors=12,
            license="MIT",
            report_worthy=True,
            filter_out_reason=None,
            scores={"novelty": 8, "traction": 9},
            what_it_does="Packages the fixture workflow.",
            why_it_matters="Shows project artifact persistence.",
            risk_label="low",
            verdict="worth_tracking",
            topic_tags=["ai_models"],
            hype_risk="low",
            signals_to_monitor=["stars", "contributors"],
        )
    }

    payload_context = StorageContext.from_root(tmp_path / "payload")
    legacy_context = StorageContext.from_root(tmp_path / "legacy")

    payload = EventStoragePayload.from_state(state)
    append_event_payload(payload, storage_context=payload_context)
    storage.append_events(state, storage_context=legacy_context)

    artifact_names = [
        "source_events.jsonl",
        "topic_trends.jsonl",
        "company_mentions.jsonl",
        "paper_mentions.jsonl",
        "project_mentions.jsonl",
    ]
    expected_artifacts = {
        "source_events.jsonl": json.dumps(
            {
                "run_date": "2026-07-02",
                "run_id": "run-1",
                "event_id": "event-1",
                "canonical_title": "Fixture",
                "summary": "Fixture summary",
                "source_urls": ["https://example.com"],
                "primary_source_url": "https://example.com",
                "source_type": "company",
                "published_at": "2026-07-02T00:00:00+00:00",
                "companies": ["OpenAI"],
                "projects": [],
                "papers": [],
                "people": [],
                "topics": ["ai_models"],
                "geography": [],
                "event_type": "product_launch",
                "importance_score": 0.9,
                "novelty_score": 0.8,
                "reliability_score": 0.95,
                "social_heat_score": 0.0,
                "raw_event_ids": ["raw-1"],
                "metadata": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        "topic_trends.jsonl": json.dumps(
            {
                "run_date": "2026-07-02",
                "topic_id": "ai_models",
                "trend_status": "accelerating",
                "signal_count": 1,
                "signal_classification": "single_signal",
            },
            ensure_ascii=False,
        )
        + "\n",
        "company_mentions.jsonl": json.dumps(
            {
                "run_date": "2026-07-02",
                "company": "OpenAI",
                "significance": "high",
                "summary": "OpenAI shipped the fixture launch.",
            },
            ensure_ascii=False,
        )
        + "\n",
        "paper_mentions.jsonl": json.dumps(
            {
                "run_date": "2026-07-02",
                "title": "Fixture Paper",
                "link": "https://example.com/paper-1",
                "signal_strength": "strong",
                "overall_score": 0.9,
            },
            ensure_ascii=False,
        )
        + "\n",
        "project_mentions.jsonl": json.dumps(
            {
                "run_date": "2026-07-02",
                "repo": "openai/fixture-project",
                "url": "https://github.com/openai/fixture-project",
                "verdict": "worth_tracking",
                "stars_total": 1234,
            },
            ensure_ascii=False,
        )
        + "\n",
    }

    for artifact_name in artifact_names:
        payload_path = payload_context.data_dir / artifact_name
        legacy_path = legacy_context.data_dir / artifact_name

        assert payload_path.exists(), artifact_name
        assert legacy_path.exists(), artifact_name
        payload_raw = payload_path.read_text(encoding="utf-8")
        legacy_raw = legacy_path.read_text(encoding="utf-8")

        assert payload_raw == expected_artifacts[artifact_name]
        assert legacy_raw == expected_artifacts[artifact_name]
        assert payload_raw == legacy_raw


def test_historical_loaders_accept_storage_context(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    context.daily_report_path("2026-07-02").parent.mkdir(parents=True)
    context.weekly_report_path("2026-W26").parent.mkdir(parents=True)
    context.monthly_report_path("2026-06").parent.mkdir(parents=True)
    context.daily_report_path("2026-07-02").write_text("# Daily", encoding="utf-8")
    context.weekly_report_path("2026-W26").write_text("# Weekly", encoding="utf-8")
    context.monthly_report_path("2026-06").write_text("# Monthly", encoding="utf-8")
    context.data_dir.mkdir(parents=True)
    (context.data_dir / "topic_trends.jsonl").write_text(
        json.dumps({"run_date": "2026-07-02", "topic_id": "ai_models"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (context.data_dir / "company_mentions.jsonl").write_text(
        json.dumps({"run_date": "2026-07-02", "company": "OpenAI"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert [report.report_date for report in storage.load_recent_reports(storage_context=context)] == ["2026-07-02"]
    assert [report.report_date for report in storage.load_recent_weekly_reviews(storage_context=context)] == [
        "2026-W26"
    ]
    assert [report.report_date for report in storage.load_recent_monthly_reviews(storage_context=context)] == [
        "2026-06"
    ]
    assert storage.load_topic_trends_recent(storage_context=context)[0]["topic_id"] == "ai_models"
    assert storage.load_company_mentions_recent(storage_context=context)[0]["company"] == "OpenAI"


def test_recent_report_loaders_return_empty_for_zero_limit_when_files_exist(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    context.daily_report_path("2026-07-02").parent.mkdir(parents=True)
    context.weekly_report_path("2026-W26").parent.mkdir(parents=True)
    context.monthly_report_path("2026-06").parent.mkdir(parents=True)
    context.daily_report_path("2026-07-02").write_text("# Daily", encoding="utf-8")
    context.weekly_report_path("2026-W26").write_text("# Weekly", encoding="utf-8")
    context.monthly_report_path("2026-06").write_text("# Monthly", encoding="utf-8")

    assert storage.load_recent_reports(0, storage_context=context) == []
    assert storage.load_recent_weekly_reviews(0, storage_context=context) == []
    assert storage.load_recent_monthly_reviews(0, storage_context=context) == []


def test_trending_snapshot_storage_accepts_storage_context(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    snapshot = TrendingSnapshot(
        snapshot_date="2026-07-02",
        period="daily",
        github_items=[
            TrendingItem(
                item_id="owner/repo",
                item_type="github_repo",
                source="ossinsight",
                title="owner/repo",
                url="https://github.com/owner/repo",
                description="Fixture repo",
                period="daily",
                rank=1,
                velocity_score=42.0,
                language="Python",
                topics=["ai_models"],
                snapshot_date="2026-07-02",
                extra={},
            )
        ],
        hf_paper_items=[],
        hf_model_items=[],
    )

    storage.save_trending_snapshot(snapshot, storage_context=context)
    rows = storage.load_trending_history(storage_context=context)

    assert context.trending_log_path().exists()
    assert rows[0]["item_id"] == "owner/repo"


def test_market_signal_storage_accepts_storage_context(tmp_path: Path) -> None:
    context = storage.StorageContext.from_root(tmp_path)
    analysis = MarketSignalAnalysis(
        ticker="NVDA",
        company="NVIDIA",
        date="2026-07-02",
        time_horizon="30 days",
        event_context=["event-1"],
        conclusion="watch",
        conclusion_zh="观察",
        reasoning_zh="测试",
        base_case="Base",
        bull_case="Bull",
        bear_case="Bear",
        buy_observation_point="Buy",
        sell_reduce_observation_point="Sell",
        invalidation_condition="Invalidation",
        risk_level="medium",
        confidence="medium",
        signals_to_monitor=[],
        source_events=["event-1"],
        report_snippet="omitted from log",
    )

    storage.save_market_signals("2026-07-02", {"NVDA": analysis}, storage_context=context)
    history = storage.load_market_signals_history(storage_context=context)
    latest = storage.load_last_signal_per_ticker(storage_context=context)

    assert context.market_signals_log_path().exists()
    assert history[0]["ticker"] == "NVDA"
    assert "report_snippet" not in history[0]
    assert latest["NVDA"]["company"] == "NVIDIA"
