#!/usr/bin/env python3
"""Main Daily Workflow Orchestrator.

Run: python scripts/run_daily.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

# Ensure scripts/ is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_pipeline import DailyPipelineRuntime, execute_daily_pipeline
from run_context import AppConfig, RunContext
from run_logging import RunLogger
from state import TechDailyState, new_run_id

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _step(name: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  STEP: {name}")
    print(f"{'=' * 60}")


def run_daily(run_date: str | None = None, force: bool = False) -> str:
    cfg = _load_config()
    app_config = AppConfig(cfg)
    if run_date is None:
        # Default to "yesterday" in the project's local timezone (Asia/Shanghai).
        # Why timezone-aware: the GitHub Actions runner uses UTC, but the cron
        # fires at 23:00 UTC = 07:00 CST next morning. Using UTC's date.today()
        # would be off-by-one for manual reruns during CST daytime, and naive
        # subtraction (UTC today − 1) gives "day before yesterday in CST" at
        # cron time. Anchoring to CST avoids both off-by-one cases.
        tz_name = app_config.timezone
        local_today = datetime.now(ZoneInfo(tz_name)).date()
        run_date = (local_today - timedelta(days=1)).isoformat()

    context = RunContext.from_config(
        run_date=run_date,
        run_id=new_run_id(),
        root_dir=ROOT,
        config=cfg,
    )
    logger = RunLogger(context)

    # Idempotency: skip if this date's report already exists (unless --force)
    if context.daily_report_path.exists() and not force:
        print(f"\n  [Daily] Report for {run_date} already exists — skipping (pass --force to regenerate).")
        with open(context.daily_report_path, encoding="utf-8") as _f:
            return _f.read()

    print(f"\n{'#' * 60}")
    print(f"  Tech Daily Agent — {run_date}")
    print(f"{'#' * 60}\n")

    # Initialize blackboard
    state = TechDailyState(
        run_id=context.run_id,
        run_date=context.run_date,
        time_window=context.time_window,
    )
    runtime = DailyPipelineRuntime(
        state=state,
        context=context,
        cfg=cfg,
        app_config=app_config,
        logger=logger,
        root_dir=ROOT,
    )
    pipeline_result = execute_daily_pipeline(runtime, step_printer=_step)
    report_path = pipeline_result.report_path

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'#' * 60}")
    print(f"  DONE — {run_date}")
    print(f"  Raw events:       {len(state.raw_events)}")
    print(f"  Normalized:       {len(state.normalized_events)}")
    print(f"  Topics analyzed:  {len(state.topic_summaries)}")
    print(f"  Companies:        {len(state.company_analyses)}")
    print(f"  Papers:           {len(state.paper_analyses)}")
    print(f"  GitHub repos:     {len(state.github_project_analyses)}")
    print(f"  Pred updates:     {len(state.prediction_updates)}")
    print(f"  New predictions:  {len(state.new_predictions)}")
    print(f"  Market signals:   {len(state.market_signal_analyses)}")
    print(f"  Report:           {report_path}")
    print(f"{'#' * 60}\n")

    return state.final_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tech Daily Agent")
    parser.add_argument("--date", help="Run date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a report already exists for this date")
    args = parser.parse_args()
    run_daily(args.date, force=args.force)
