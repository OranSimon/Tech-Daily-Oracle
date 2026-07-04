from __future__ import annotations

from pathlib import Path

import daily_step_actions as actions
import pytest
import storage
from run_context import RunContext
from state import TechDailyState


def _state() -> TechDailyState:
    return TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
    )


def _context(tmp_path: Path) -> RunContext:
    return RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config={"run": {"report_window_hours": 24}},
    )


def _point_storage_at(tmp_path: Path) -> None:
    storage.DATA_DIR = str(tmp_path / "data")
    storage.REPORTS_DIR = str(tmp_path / "reports")
    storage.PREDICTION_LOG = str(tmp_path / "data" / "prediction_log.jsonl")
    storage.TRENDING_LOG = str(tmp_path / "data" / "trending_snapshots.jsonl")
    storage.MARKET_SIGNALS_LOG = str(tmp_path / "data" / "market_signals.jsonl")
    storage.COLLECTOR_RUNS_LOG = str(tmp_path / "data" / "collector_runs.jsonl")


def test_load_historical_context_action_mutates_state(monkeypatch, tmp_path: Path) -> None:
    state = _state()
    monkeypatch.setattr(actions, "load_recent_reports", lambda days: ["daily"])
    monkeypatch.setattr(actions, "load_recent_weekly_reviews", lambda count: ["weekly"])
    monkeypatch.setattr(actions, "load_recent_monthly_reviews", lambda count: ["monthly"])
    monkeypatch.setattr(actions, "load_topic_trends_recent", lambda days: [{"topic": "ai"}])
    monkeypatch.setattr(actions, "load_company_mentions_recent", lambda days: [{"company": "OpenAI"}])
    monkeypatch.setattr(actions, "load_open_predictions", lambda: ["prediction"])

    result = actions.load_historical_context_action(state)

    assert result == {
        "previous_reports": ["daily"],
        "weekly_reviews": ["weekly"],
        "monthly_reviews": ["monthly"],
        "recent_topic_trends": [{"topic": "ai"}],
        "recent_company_mentions": [{"company": "OpenAI"}],
        "open_predictions": ["prediction"],
    }
    assert state.previous_reports == ["daily"]
    assert state.weekly_reviews == ["weekly"]
    assert state.monthly_reviews == ["monthly"]
    assert state.recent_topic_trends == [{"topic": "ai"}]
    assert state.recent_company_mentions == [{"company": "OpenAI"}]
    assert state.open_predictions == ["prediction"]


def test_collect_sources_action_uses_context_run_identity(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_collect_sources_with_telemetry(cfg, *, run_date, persist_telemetry, run_id):
        captured.update(
            {
                "cfg": cfg,
                "run_date": run_date,
                "persist_telemetry": persist_telemetry,
                "run_id": run_id,
            }
        )
        return ["raw-event"], ["telemetry"]

    monkeypatch.setattr(actions, "collect_sources_with_telemetry", fake_collect_sources_with_telemetry)

    result = actions.collect_sources_action({"sources": {}}, _context(tmp_path))

    assert result == ["raw-event"]
    assert captured == {
        "cfg": {"sources": {}},
        "run_date": "2026-07-02",
        "persist_telemetry": True,
        "run_id": "run-fixture",
    }


def test_save_outputs_action_preserves_core_writes_and_optional_subwrite_failures(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    _point_storage_at(tmp_path)
    state = _state()
    state.final_report = "# Tech Daily Brief\n"
    state.new_predictions = []
    state.prediction_updates = []
    state.market_signal_analyses = {"NVDA": object()}

    monkeypatch.setattr(
        actions, "save_trending_snapshot", lambda snapshot: (_ for _ in ()).throw(RuntimeError("trend"))
    )
    monkeypatch.setattr(actions, "save_market_signals", lambda *args: (_ for _ in ()).throw(RuntimeError("market")))

    report_path = actions.save_outputs_action(
        state,
        run_date="2026-07-02",
        trending_snapshot={"snapshot_date": "2026-07-02"},
    )
    output = capsys.readouterr().out

    assert report_path.endswith("reports/daily/2026-07-02.md")
    assert (tmp_path / "reports" / "daily" / "2026-07-02.md").read_text(encoding="utf-8") == state.final_report
    assert "[Storage] Trending snapshot save failed (non-fatal): trend" in output
    assert "[Storage] Market signals save failed (non-fatal): market" in output


def test_generate_daily_report_action_surfaces_report_errors(monkeypatch) -> None:
    state = _state()

    def fail_report(_state: TechDailyState) -> str:
        raise RuntimeError("report unavailable")

    monkeypatch.setattr(actions, "generate_daily_report", fail_report)

    with pytest.raises(RuntimeError, match="report unavailable"):
        actions.generate_daily_report_action(state)
