#!/usr/bin/env python3
"""Main Daily Workflow Orchestrator.

Run: python scripts/run_daily.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timezone

import yaml

# Ensure scripts/ is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state import TechDailyState, new_run_id
from collect_sources import collect_sources
from normalize_sources import normalize_events
from analyze_topics import analyze_topics
from analyze_companies import analyze_companies
from analyze_papers import analyze_papers
from analyze_github_projects import analyze_github_projects
from analyze_social_signals import analyze_social_signals
from analyze_macro_impact import analyze_macro_impact
from update_predictions import run_prediction_updates, generate_new_predictions
from generate_report import generate_daily_report
from collect_trending import collect_trending_snapshot
from analyze_trending import analyze_trending
from storage import (
    save_daily_report, save_predictions, append_events,
    load_open_predictions, load_recent_reports,
    load_recent_weekly_reviews, load_recent_monthly_reviews,
    load_topic_trends_recent, load_company_mentions_recent,
    save_trending_snapshot, load_trending_history,
)
from publish_notion import publish_to_notion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _step(name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")


def run_daily(run_date: str | None = None, force: bool = False) -> str:
    cfg = _load_config()
    if run_date is None:
        # Default to yesterday: the script runs in the morning and reports on
        # the previous day's events (news fully accumulated by end of prior day).
        run_date = (date.today() - timedelta(days=1)).isoformat()

    # Idempotency: skip if this date's report already exists (unless --force)
    _existing = os.path.join(ROOT, "reports", "daily", f"{run_date}.md")
    if os.path.exists(_existing) and not force:
        print(f"\n  [Daily] Report for {run_date} already exists — skipping "
              f"(pass --force to regenerate).")
        with open(_existing, encoding="utf-8") as _f:
            return _f.read()

    print(f"\n{'#'*60}")
    print(f"  Tech Daily Agent — {run_date}")
    print(f"{'#'*60}\n")

    # Initialize blackboard
    state = TechDailyState(
        run_id=new_run_id(),
        run_date=run_date,
        time_window=f"last_{cfg.get('run', {}).get('report_window_hours', 24)}h",
    )

    # -----------------------------------------------------------------------
    # Step 1: Load historical context
    # -----------------------------------------------------------------------
    _step("Loading historical context")
    state.previous_reports = load_recent_reports(7)
    state.weekly_reviews = load_recent_weekly_reviews(4)
    state.monthly_reviews = load_recent_monthly_reviews(3)
    state.recent_topic_trends = load_topic_trends_recent(30)
    state.recent_company_mentions = load_company_mentions_recent(90)
    state.open_predictions = load_open_predictions()
    print(f"  Loaded {len(state.previous_reports)} daily, "
          f"{len(state.weekly_reviews)} weekly, "
          f"{len(state.monthly_reviews)} monthly reports; "
          f"{len(state.open_predictions)} open predictions")

    # -----------------------------------------------------------------------
    # Step 2: Source Collection
    # -----------------------------------------------------------------------
    _step("Collecting sources")
    t0 = time.time()
    try:
        state.raw_events = collect_sources(cfg, run_date=run_date)
    except Exception as e:
        print(f"  [ERROR] Source collection failed: {e}")
        state.source_warnings.append(f"Source collection error: {e}")
        state.raw_events = []
    print(f"  Collection took {time.time()-t0:.1f}s")

    # -----------------------------------------------------------------------
    # Step 2.5: Trending Snapshot Collection (parallel with source collection)
    # -----------------------------------------------------------------------
    _step("Collecting trending snapshot (OSSInsight + HuggingFace)")
    trending_snapshot = None
    try:
        trending_snapshot = collect_trending_snapshot("daily", run_date, cfg)
    except Exception as e:
        print(f"  [ERROR] Trending collection failed (non-fatal): {e}")

    # -----------------------------------------------------------------------
    # Step 3: Normalize & Deduplicate
    # -----------------------------------------------------------------------
    _step("Normalizing and deduplicating events")
    try:
        state.normalized_events = normalize_events(state.raw_events, run_date=run_date)
    except Exception as e:
        print(f"  [ERROR] Normalization failed: {e}")
        state.normalized_events = []

    # -----------------------------------------------------------------------
    # Step 4: Topic Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing topics")
    try:
        state.topic_summaries = analyze_topics(state.normalized_events)
    except Exception as e:
        print(f"  [ERROR] Topic analysis failed: {e}")
        state.confidence_flags.append(f"Topic analysis error: {e}")

    # -----------------------------------------------------------------------
    # Step 5: Company Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing companies")
    try:
        state.company_analyses = analyze_companies(state.normalized_events)
    except Exception as e:
        print(f"  [ERROR] Company analysis failed: {e}")
        state.confidence_flags.append(f"Company analysis error: {e}")

    # -----------------------------------------------------------------------
    # Step 6: Paper Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing papers")
    try:
        state.paper_analyses = analyze_papers(state.normalized_events)
    except Exception as e:
        print(f"  [ERROR] Paper analysis failed: {e}")
        state.confidence_flags.append(f"Paper analysis error: {e}")

    # -----------------------------------------------------------------------
    # Step 7: GitHub Project Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing GitHub projects")
    try:
        state.github_project_analyses = analyze_github_projects(state.normalized_events)
    except Exception as e:
        print(f"  [ERROR] GitHub analysis failed: {e}")
        state.confidence_flags.append(f"GitHub analysis error: {e}")

    # -----------------------------------------------------------------------
    # Step 7.5: Trending Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing trending items")
    if trending_snapshot is not None:
        try:
            history = load_trending_history(days=30)
            top_n = cfg.get("trending", {}).get("top_n", 5)
            state.trending_analysis = analyze_trending(trending_snapshot, history, top_n=top_n)
        except Exception as e:
            print(f"  [ERROR] Trending analysis failed (non-fatal): {e}")

    # -----------------------------------------------------------------------
    # Step 8: Social Signal Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing social signals")
    try:
        state.social_signal_analyses = analyze_social_signals(state.normalized_events)
    except Exception as e:
        print(f"  [ERROR] Social analysis failed: {e}")

    # -----------------------------------------------------------------------
    # Step 9: Macro Impact Analysis
    # -----------------------------------------------------------------------
    _step("Analyzing macro/geopolitical impact")
    try:
        state.macro_impact_analyses = analyze_macro_impact(
            state.normalized_events, state.open_predictions
        )
    except Exception as e:
        print(f"  [ERROR] Macro analysis failed: {e}")

    # -----------------------------------------------------------------------
    # Step 10: Prediction Updates
    # -----------------------------------------------------------------------
    _step("Updating predictions")
    try:
        state.prediction_updates = run_prediction_updates(state)
    except Exception as e:
        print(f"  [ERROR] Prediction updates failed: {e}")

    # -----------------------------------------------------------------------
    # Step 11: New Predictions
    # -----------------------------------------------------------------------
    _step("Generating new predictions")
    try:
        state.new_predictions = generate_new_predictions(state)
    except Exception as e:
        print(f"  [ERROR] New predictions failed: {e}")

    # -----------------------------------------------------------------------
    # Step 12: Report Generation
    # -----------------------------------------------------------------------
    _step("Generating daily brief report")
    try:
        state.final_report = generate_daily_report(state)
    except Exception as e:
        print(f"  [ERROR] Report generation failed: {e}")
        traceback.print_exc()
        state.final_report = f"# Tech Daily Brief — {run_date}\n\n[Report generation failed: {e}]"

    # -----------------------------------------------------------------------
    # Step 13: Storage
    # -----------------------------------------------------------------------
    _step("Saving outputs")
    report_path = save_daily_report(run_date, state.final_report)
    save_predictions(state.new_predictions, state.prediction_updates)
    append_events(state)
    if trending_snapshot is not None:
        try:
            save_trending_snapshot(trending_snapshot)
        except Exception as e:
            print(f"  [Storage] Trending snapshot save failed (non-fatal): {e}")

    if cfg.get("notion", {}).get("enabled", False):
        try:
            notion_url = publish_to_notion(run_date, state.final_report, cfg)
            if notion_url:
                print(f"  [Notion] Published: {notion_url}")
        except Exception as e:
            print(f"  [Notion] Publish failed (non-fatal): {e}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'#'*60}")
    print(f"  DONE — {run_date}")
    print(f"  Raw events:       {len(state.raw_events)}")
    print(f"  Normalized:       {len(state.normalized_events)}")
    print(f"  Topics analyzed:  {len(state.topic_summaries)}")
    print(f"  Companies:        {len(state.company_analyses)}")
    print(f"  Papers:           {len(state.paper_analyses)}")
    print(f"  GitHub repos:     {len(state.github_project_analyses)}")
    print(f"  Pred updates:     {len(state.prediction_updates)}")
    print(f"  New predictions:  {len(state.new_predictions)}")
    print(f"  Report:           {report_path}")
    print(f"{'#'*60}\n")

    return state.final_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tech Daily Agent")
    parser.add_argument("--date", help="Run date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if a report already exists for this date")
    args = parser.parse_args()
    run_daily(args.date, force=args.force)
