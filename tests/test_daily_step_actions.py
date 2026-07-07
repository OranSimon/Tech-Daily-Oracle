from __future__ import annotations

from pathlib import Path

import pytest
import storage
from state import TechDailyState

from tech_daily.pipeline import actions
from tech_daily.pipeline.state import ReportInputState
from tech_daily.runtime.run_context import RunContext
from tech_daily.storage.context import StorageContext


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


def test_append_events_action_uses_event_storage_payload_boundary(monkeypatch) -> None:
    from tech_daily.storage import event_payloads as payload_module
    from tech_daily.storage import events as events_module

    state = _state()
    captured: dict[str, object] = {}

    class FakePayload:
        pass

    fake_payload = FakePayload()

    def fake_from_state(value: TechDailyState) -> object:
        captured["state"] = value
        return fake_payload

    def fake_append_event_payload(payload: object, *, storage_context=None) -> None:
        captured["payload"] = payload
        captured["storage_context"] = storage_context

    def fail_legacy_append(*args, **kwargs) -> None:
        raise AssertionError("legacy state-based storage append should not be used by pipeline action")

    monkeypatch.setattr(payload_module.EventStoragePayload, "from_state", fake_from_state)
    monkeypatch.setattr(events_module, "append_event_payload", fake_append_event_payload)
    monkeypatch.setattr(events_module, "append_events", fail_legacy_append)

    actions.append_events(state)

    assert captured["state"] is state
    assert captured["payload"] is fake_payload
    assert captured["storage_context"] is None


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
        storage_context=StorageContext.from_root(tmp_path),
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


def test_generate_daily_report_input_action_uses_typed_input_boundary(monkeypatch) -> None:
    state = _state()
    typed_input = ReportInputState.from_tech_daily_state(state)
    captured: dict[str, object] = {}

    def fake_generate_from_input(input_state: ReportInputState) -> str:
        captured["input_state"] = input_state
        return "# Tech Daily Brief — 2026-07-02\n"

    def fail_legacy_report(_state: TechDailyState) -> str:
        raise AssertionError("legacy TechDailyState report path should not be used")

    monkeypatch.setattr(actions, "generate_daily_report_from_input", fake_generate_from_input)
    monkeypatch.setattr(actions, "generate_daily_report", fail_legacy_report)

    report_state = actions.generate_daily_report_input_action(typed_input)

    assert captured["input_state"] is typed_input
    assert report_state.final_report == "# Tech Daily Brief — 2026-07-02\n"


def test_prediction_and_market_input_actions_use_typed_boundaries(monkeypatch) -> None:
    from pipeline_state import get_market_signal_input_state, get_prediction_input_state

    state = _state()
    prediction_input = get_prediction_input_state(state)
    market_input = get_market_signal_input_state(state)
    captured: dict[str, object] = {}

    def fake_run_prediction_updates_from_input(input_state, prompt_runner=None):
        captured["prediction_updates_input"] = input_state
        return ["update"]

    def fake_generate_new_predictions_from_input(input_state, prompt_runner=None):
        captured["new_predictions_input"] = input_state
        return ["new"], "high"

    def fake_analyze_market_signals_from_input(input_state, *, market_data, prior_signals, config):
        captured["market_input"] = input_state
        captured["market_data"] = market_data
        captured["prior_signals"] = prior_signals
        captured["config"] = config
        return {"NVDA": "analysis"}

    def fail_legacy_state_path(*args, **kwargs):
        raise AssertionError("legacy TechDailyState path should not be used by typed input action")

    monkeypatch.setattr(actions, "run_prediction_updates_from_input", fake_run_prediction_updates_from_input)
    monkeypatch.setattr(actions, "generate_new_predictions_from_input", fake_generate_new_predictions_from_input)
    monkeypatch.setattr(actions, "analyze_market_signals_from_input", fake_analyze_market_signals_from_input)
    monkeypatch.setattr(actions, "run_prediction_updates", fail_legacy_state_path)
    monkeypatch.setattr(actions, "generate_new_predictions", fail_legacy_state_path)
    monkeypatch.setattr(actions, "load_last_signal_per_ticker", lambda: {"NVDA": {"ticker": "NVDA"}})

    prediction_updates = actions.update_predictions_input_action(prediction_input)
    new_predictions = actions.generate_new_predictions_input_action(prediction_input)
    market = actions.analyze_market_signals_input_action(
        market_input,
        market_data=None,
        cfg={"market_signal": {"enabled": True}},
    )

    assert captured["prediction_updates_input"] is prediction_input
    assert captured["new_predictions_input"] is prediction_input
    assert captured["market_input"] is market_input
    assert prediction_updates.prediction_updates == ["update"]
    assert new_predictions.new_predictions == ["new"]
    assert new_predictions.signal_level == "high"
    assert market == {"NVDA": "analysis"}
    assert captured["market_data"] is None
    assert captured["prior_signals"] == {"NVDA": {"ticker": "NVDA"}}
