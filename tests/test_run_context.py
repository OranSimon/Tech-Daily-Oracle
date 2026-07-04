from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import run_daily
from run_context import AppConfig, RunContext
from run_logging import RunLogger


def test_run_context_builds_paths_and_metadata(tmp_path: Path) -> None:
    raw_config = {"run": {"report_window_hours": 36, "timezone": "Asia/Shanghai"}}
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config=raw_config,
    )

    assert context.run_date == "2026-07-02"
    assert context.run_id == "run-fixture"
    assert context.root_dir == tmp_path
    assert context.data_dir == tmp_path / "data"
    assert context.reports_dir == tmp_path / "reports"
    assert context.config.raw is raw_config
    assert context.daily_report_path == tmp_path / "reports" / "daily" / "2026-07-02.md"
    assert context.time_window == "last_36h"


def test_app_config_preserves_raw_access_and_common_helpers() -> None:
    raw = {
        "run": {"timezone": "Asia/Shanghai", "report_window_hours": 24},
        "market_signal": {"enabled": True, "live_data": False},
        "notion": {"enabled": False},
        "trending": {"top_n": 7},
    }

    config = AppConfig(raw)

    assert config.raw is raw
    assert config.section("run") == raw["run"]
    assert config.get("run", "timezone", "UTC") == "Asia/Shanghai"
    assert config.timezone == "Asia/Shanghai"
    assert config.report_window_hours == 24
    assert config.market_signal_enabled is True
    assert config.market_live_data_enabled is False
    assert config.notion_enabled is False
    assert config.trending_top_n == 7


def test_structured_logger_emits_json_fields(tmp_path: Path) -> None:
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=tmp_path,
        config={},
    )
    output = StringIO()
    logger = RunLogger(context, output=output, json_lines=True)

    logger.info(
        step="Collecting sources",
        message="completed",
        duration_seconds=1.25,
        record_count=4,
    )

    event = json.loads(output.getvalue())
    assert event == {
        "run_id": "run-fixture",
        "run_date": "2026-07-02",
        "step": "Collecting sources",
        "severity": "info",
        "message": "completed",
        "duration_seconds": 1.25,
        "record_count": 4,
    }


def test_run_daily_skip_path_remains_compatible(monkeypatch, tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "daily" / "2026-07-02.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Existing report", encoding="utf-8")

    monkeypatch.setattr(run_daily, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        run_daily,
        "_load_config",
        lambda: {"run": {"timezone": "Asia/Shanghai", "report_window_hours": 24}},
    )

    assert run_daily.run_daily("2026-07-02") == "# Existing report"
