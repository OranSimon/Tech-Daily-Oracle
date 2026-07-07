from __future__ import annotations

import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import daily_step_actions as actions
import storage
from collectors.telemetry import CollectorRunResult, CollectorRunStatus
from state import (
    NormalizedEvent,
    Prediction,
    RawEvent,
    TopicSummary,
)

import tech_daily.cli.run_daily as run_daily


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")
    storage.COLLECTOR_RUNS_LOG = str(tmp_path / "data" / "collector_runs.jsonl")


def test_daily_pipeline_smoke_with_fake_dependencies(monkeypatch, tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    raw = RawEvent(
        source_name="Fixture RSS",
        source_type="rss",
        raw_title="OpenAI releases fixture model",
        raw_url="https://example.com/openai-fixture",
        raw_content="OpenAI releases a fixture model for smoke testing.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={"priority": 1, "feed_source_type": "company"},
    )
    normalized = NormalizedEvent(
        event_id="event-2026-07-02-fixture",
        canonical_title="OpenAI releases fixture model",
        summary="OpenAI releases a fixture model for smoke testing.",
        source_urls=["https://example.com/openai-fixture"],
        primary_source_url="https://example.com/openai-fixture",
        source_type="company",
        published_at=raw.published_at,
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
        raw_event_ids=[raw.raw_id],
        metadata={"source_name": raw.source_name},
    )
    topic = TopicSummary(
        topic_id="ai_models",
        topic_label="AI Models",
        trend_status="accelerating",
        trend_change="up",
        confidence="medium",
        signal_count=1,
        key_signal_summary="Fixture signal",
        key_events=[normalized.event_id],
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
    prediction = Prediction(
        prediction_id="P20260702-1",
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
        status="open",
        confidence="medium",
    )

    monkeypatch.setattr(
        actions,
        "collect_sources_with_telemetry",
        lambda cfg, run_date, persist_telemetry, run_id: (
            [raw],
            [
                CollectorRunResult(
                    collector_name="fixture",
                    status=CollectorRunStatus.SUCCESS,
                    duration_seconds=0.01,
                    record_count=1,
                )
            ],
        ),
        raising=False,
    )
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [normalized])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {"ai_models": topic})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([prediction], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(
        actions,
        "generate_daily_report_from_input",
        lambda state: "# Tech Daily Brief — 2026-07-02\n\n## 1. 今日一句话判断\n\nFixture.\n",
    )

    report = run_daily.run_daily("2026-07-02", force=True)

    assert report.startswith("# Tech Daily Brief — 2026-07-02")
    assert (tmp_path / "reports" / "daily" / "2026-07-02.md").exists()
    assert (tmp_path / "data" / "source_events.jsonl").exists()
    assert (tmp_path / "data" / "topic_trends.jsonl").exists()
    assert (tmp_path / "data" / "prediction_log.jsonl").exists()
    source_rows = [
        json.loads(line)
        for line in (tmp_path / "data" / "source_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert source_rows[0]["event_id"] == "event-2026-07-02-fixture"


def test_daily_collection_path_enables_telemetry_persistence(monkeypatch, tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    raw = RawEvent(
        source_name="Fixture RSS",
        source_type="rss",
        raw_title="Telemetry fixture",
        raw_url="https://example.com/telemetry-fixture",
        raw_content="Telemetry fixture content.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={},
    )
    calls: list[dict[str, object]] = []

    def fake_collect_sources_with_telemetry(
        cfg: dict,
        run_date: str,
        *,
        persist_telemetry: bool,
        run_id: str,
    ):
        calls.append(
            {
                "run_date": run_date,
                "persist_telemetry": persist_telemetry,
                "run_id": run_id,
            }
        )
        return [raw], [
            CollectorRunResult(
                collector_name="fixture",
                status=CollectorRunStatus.SUCCESS,
                duration_seconds=0.01,
                record_count=1,
            )
        ]

    monkeypatch.setattr(
        actions,
        "collect_sources_with_telemetry",
        fake_collect_sources_with_telemetry,
        raising=False,
    )
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda state: "# Tech Daily Brief — 2026-07-02\n")

    run_daily.run_daily("2026-07-02", force=True)

    assert len(calls) == 1
    assert calls[0]["run_date"] == "2026-07-02"
    assert calls[0]["persist_telemetry"] is True
    assert isinstance(calls[0]["run_id"], str)
    assert calls[0]["run_id"]


def test_daily_collection_failure_remains_non_fatal(monkeypatch, tmp_path: Path) -> None:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    def fail_collection(*args, **kwargs):
        raise RuntimeError("collector unavailable")

    captured: dict[str, object] = {}

    def fake_normalize(events, run_date):
        captured["normalized_input"] = events
        return []

    def fake_report(input_state):
        captured["source_warnings"] = list(input_state.diagnostics.source_warnings)
        return "# Tech Daily Brief — 2026-07-02\n"

    monkeypatch.setattr(actions, "collect_sources_with_telemetry", fail_collection, raising=False)
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions, "normalize_events", fake_normalize)
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", fake_report)

    report = run_daily.run_daily("2026-07-02", force=True)

    assert report.startswith("# Tech Daily Brief")
    assert captured["normalized_input"] == []
    assert captured["source_warnings"] == ["Source collection error: collector unavailable"]


def test_daily_trending_snapshot_failure_remains_non_fatal(monkeypatch, tmp_path: Path, capsys) -> None:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    raw = RawEvent(
        source_name="Fixture RSS",
        source_type="rss",
        raw_title="No trending fixture",
        raw_url="https://example.com/no-trending-fixture",
        raw_content="Fixture content.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={},
    )
    calls: dict[str, bool] = {"analyze_trending": False}

    monkeypatch.setattr(
        actions,
        "collect_sources_with_telemetry",
        lambda cfg, run_date, persist_telemetry, run_id: (
            [raw],
            [
                CollectorRunResult(
                    collector_name="fixture",
                    status=CollectorRunStatus.SUCCESS,
                    duration_seconds=0.01,
                    record_count=1,
                )
            ],
        ),
        raising=False,
    )

    def fail_trending_snapshot(*args, **kwargs):
        raise RuntimeError("trending unavailable")

    def unexpected_trending_analysis(*args, **kwargs):
        calls["analyze_trending"] = True
        return None

    monkeypatch.setattr(actions, "collect_trending_snapshot", fail_trending_snapshot)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_trending", unexpected_trending_analysis)
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda state: "# Tech Daily Brief — 2026-07-02\n")

    report = run_daily.run_daily("2026-07-02", force=True)
    output = capsys.readouterr().out

    assert report.startswith("# Tech Daily Brief")
    assert "[ERROR] Trending collection failed (non-fatal): trending unavailable" in output
    assert "message=step_summary" in output
    assert calls["analyze_trending"] is False


def test_daily_trending_history_load_is_wrapped_without_changing_analysis(monkeypatch, tmp_path: Path, capsys) -> None:
    _point_storage_at(tmp_path)
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {"enabled": False, "live_data": False},
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    raw = RawEvent(
        source_name="Fixture RSS",
        source_type="rss",
        raw_title="Trending history fixture",
        raw_url="https://example.com/trending-history-fixture",
        raw_content="Fixture content.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={},
    )
    trending_snapshot = {"period": "daily", "items": [{"name": "fixture"}]}
    trending_history = [{"period": "daily", "items": []}]
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        actions,
        "collect_sources_with_telemetry",
        lambda cfg, run_date, persist_telemetry, run_id: (
            [raw],
            [
                CollectorRunResult(
                    collector_name="fixture",
                    status=CollectorRunStatus.SUCCESS,
                    duration_seconds=0.01,
                    record_count=1,
                )
            ],
        ),
        raising=False,
    )
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: trending_snapshot)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "load_trending_history", lambda days: trending_history)

    def fake_analyze_trending(snapshot, history, top_n):
        captured["snapshot"] = snapshot
        captured["history"] = history
        captured["top_n"] = top_n
        return None

    monkeypatch.setattr(actions, "analyze_trending", fake_analyze_trending)
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda state: "# Tech Daily Brief — 2026-07-02\n")

    run_daily.run_daily("2026-07-02", force=True)
    output = capsys.readouterr().out

    assert captured == {
        "snapshot": trending_snapshot,
        "history": trending_history,
        "top_n": 5,
    }
    assert "step=Loading trending history message=completed" in output
    assert '"name": "Loading trending history"' in output


def test_daily_market_data_collection_success_is_wrapped_without_changing_downstream_input(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    _point_storage_at(tmp_path)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "market_watchlist.yml").write_text(
        "tickers:\n  - ticker: NVDA\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {
                "enabled": True,
                "live_data": True,
                "watchlist_file": "sources/market_watchlist.yml",
            },
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
        "load_last_signal_per_ticker",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    market_data = {"per_ticker": {"NVDA": {"current_price": 100.0}}, "macro": {}}
    captured: dict[str, object] = {}

    def fake_collect_market_data(tickers, cfg):
        captured["tickers"] = tickers
        return market_data

    def fake_analyze_market_signals_from_input(input_state, *, market_data, prior_signals, config):
        captured["market_data"] = market_data
        captured["prior_signals"] = prior_signals
        return {}

    monkeypatch.setitem(
        sys.modules,
        "collect_market_data",
        types.SimpleNamespace(collect_market_data=fake_collect_market_data),
    )
    monkeypatch.setattr(actions, "analyze_market_signals_from_input", fake_analyze_market_signals_from_input)
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
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda state: "# Tech Daily Brief — 2026-07-02\n")

    run_daily.run_daily("2026-07-02", force=True)
    output = capsys.readouterr().out

    assert captured["tickers"] == ["NVDA"]
    assert captured["market_data"] is market_data
    assert captured["prior_signals"] == []
    assert "step=Collecting market data (yfinance / FRED) message=completed" in output
    assert '"name": "Collecting market data (yfinance / FRED)"' in output


def test_daily_market_data_collection_failure_remains_non_fatal(monkeypatch, tmp_path: Path, capsys) -> None:
    _point_storage_at(tmp_path)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "market_watchlist.yml").write_text(
        "tickers:\n  - ticker: NVDA\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
            "market_signal": {
                "enabled": True,
                "live_data": True,
                "watchlist_file": "sources/market_watchlist.yml",
            },
            "notion": {"enabled": False},
            "trending": {"top_n": 5},
        },
    )
    for name in [
        "load_recent_reports",
        "load_recent_weekly_reviews",
        "load_recent_monthly_reviews",
        "load_topic_trends_recent",
        "load_company_mentions_recent",
        "load_open_predictions",
        "load_trending_history",
        "load_last_signal_per_ticker",
    ]:
        monkeypatch.setattr(actions, name, lambda *args, **kwargs: [])

    captured: dict[str, object] = {}

    def fail_collect_market_data(tickers, cfg):
        raise RuntimeError("market data unavailable")

    def fake_analyze_market_signals_from_input(input_state, *, market_data, prior_signals, config):
        captured["market_data"] = market_data
        return {}

    monkeypatch.setitem(
        sys.modules,
        "collect_market_data",
        types.SimpleNamespace(collect_market_data=fail_collect_market_data),
    )
    monkeypatch.setattr(actions, "analyze_market_signals_from_input", fake_analyze_market_signals_from_input)
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
    monkeypatch.setattr(actions, "collect_trending_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: [])
    monkeypatch.setattr(actions, "analyze_topics", lambda events: {})
    monkeypatch.setattr(actions, "analyze_companies", lambda events: {})
    monkeypatch.setattr(actions, "analyze_papers", lambda events: {})
    monkeypatch.setattr(actions, "analyze_github_projects", lambda events: {})
    monkeypatch.setattr(actions, "analyze_social_signals", lambda events: {})
    monkeypatch.setattr(actions, "analyze_macro_impact", lambda events, predictions: {})
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: [])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: ([], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda state: "# Tech Daily Brief — 2026-07-02\n")

    run_daily.run_daily("2026-07-02", force=True)
    output = capsys.readouterr().out

    assert captured["market_data"] is None
    assert "[MarketData] Collection failed (non-fatal): market data unavailable" in output
    assert "step=Collecting market data (yfinance / FRED) message=failed" in output
