#!/usr/bin/env python3
"""Weekly Review Workflow.

Run: python scripts/run_weekly_review.py [--week 2026-W19]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_client import call_claude, DEFAULT_MODEL
from storage import (
    save_weekly_review, load_recent_reports, load_open_predictions,
    load_trending_history, load_market_signals_history,
)
from score_predictions import compute_scorecard
from collect_trending import collect_trending_snapshot
from analyze_trending import analyze_trending

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "weekly_review.md")) as f:
        return f.read()


def _iso_week(d: date) -> str:
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def _load_week_reports(week_str: str) -> list[dict]:
    """Load daily reports from the current week."""
    reports = load_recent_reports(10)
    weekly = []
    for r in reports:
        try:
            d = date.fromisoformat(r.report_date)
            if _iso_week(d) == week_str:
                weekly.append({
                    "date": r.report_date,
                    "content": r.content[:3000],   # truncate for prompt
                })
        except Exception:
            pass
    return weekly


def _load_topic_trends_week(week_str: str) -> list[dict]:
    path = os.path.join(ROOT, "data", "topic_trends.jsonl")
    if not os.path.exists(path):
        return []
    trends = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                try:
                    dt = date.fromisoformat(d.get("run_date", ""))
                    if _iso_week(dt) == week_str:
                        trends.append(d)
                except Exception:
                    pass
            except Exception:
                pass
    return trends


def _load_resolved_predictions_week(week_str: str) -> list[dict]:
    path = os.path.join(ROOT, "data", "prediction_log.jsonl")
    if not os.path.exists(path):
        return []
    resolved = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("status", "").startswith("resolved"):
                    # Check if resolved this week via updates
                    updates = d.get("updates", [])
                    if updates:
                        last_update = updates[-1].get("update_date", "")
                        try:
                            dt = date.fromisoformat(last_update)
                            if _iso_week(dt) == week_str:
                                resolved.append(d)
                        except Exception:
                            pass
            except Exception:
                pass
    return resolved


def run_weekly_review(week_str: str | None = None) -> str:
    cfg = _load_config()
    # Local-timezone "today" so the ISO-week calculation matches the CST workweek
    # (the cron fires at 23:00 UTC Fri = 07:00 CST Sat).
    tz_name = cfg.get("run", {}).get("timezone", "Asia/Shanghai")
    today = datetime.now(ZoneInfo(tz_name)).date()

    if week_str is None:
        # Default to the ISO week that contains the most recent Friday (inclusive today).
        # (today.weekday() - 4) % 7  == 0 when today IS Friday → days_back = 0 → use today.
        # Works correctly whether this runs on Friday (the workflow day) or Saturday/later.
        days_since_friday = (today.weekday() - 4) % 7
        last_friday = today - timedelta(days=days_since_friday)
        week_str = _iso_week(last_friday)

    # Guard: ensure enough daily reports exist for this week
    daily_reports = _load_week_reports(week_str)
    min_daily = cfg.get("review_guards", {}).get("min_daily_for_weekly", 3)
    if len(daily_reports) < min_daily:
        print(
            f"\n  [Weekly] Only {len(daily_reports)} daily report(s) found for "
            f"{week_str} (need ≥ {min_daily}). Weekly review skipped.\n"
        )
        return ""

    print(f"\n{'#'*60}")
    print(f"  Tech Weekly Review — {week_str}")
    print(f"{'#'*60}\n")

    prompt_system = _load_prompt()
    # daily_reports was already loaded by the guard check above
    topic_trends = _load_topic_trends_week(week_str)
    resolved_predictions = _load_resolved_predictions_week(week_str)
    open_predictions = load_open_predictions()
    scorecard = compute_scorecard()

    # Weekly trending: collect rolling 7-day window, analyse with history
    trending_section = ""
    try:
        top_n = cfg.get("trending", {}).get("top_n", 5)
        weekly_snapshot = collect_trending_snapshot("weekly", today.isoformat(), cfg)
        history = load_trending_history(days=60)
        weekly_trending = analyze_trending(weekly_snapshot, history, top_n=top_n)
        trending_section = weekly_trending.report_section
        print(f"  [Trending] Weekly snapshot collected")
    except Exception as e:
        print(f"  [Trending] Weekly collection failed (non-fatal): {e}")

    # Load prediction updates this week
    all_preds = []
    pred_path = os.path.join(ROOT, "data", "prediction_log.jsonl")
    if os.path.exists(pred_path):
        with open(pred_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_preds.append(json.loads(line))
                    except Exception:
                        pass

    pred_updates_this_week = []
    for p in all_preds:
        for u in p.get("updates", []):
            try:
                dt = date.fromisoformat(u.get("update_date", ""))
                if _iso_week(dt) == week_str:
                    pred_updates_this_week.append({
                        "prediction_id": p["prediction_id"],
                        "prediction": p["prediction"],
                        **u,
                    })
            except Exception:
                pass

    # Market signal history for this week (Phase 4+; empty list when disabled)
    try:
        all_market_signals = load_market_signals_history(days=14)
        market_signals_this_week = [
            s for s in all_market_signals
            if _iso_week(date.fromisoformat(s.get("run_date", "1970-01-01"))) == week_str
        ]
    except Exception:
        market_signals_this_week = []

    user_msg = json.dumps({
        "week": week_str,
        "daily_reports": daily_reports,
        "prediction_updates_this_week": pred_updates_this_week,
        "resolved_predictions": resolved_predictions,
        "open_predictions": [
            {"prediction_id": p.prediction_id, "prediction": p.prediction,
             "probability": p.probability, "time_horizon": p.time_horizon}
            for p in open_predictions
        ],
        "brier_scores": scorecard,
        "topic_trend_history": topic_trends,
        "trending_weekly_summary": trending_section or None,
        "market_signal_performance": market_signals_this_week or None,
    }, ensure_ascii=False)

    max_tokens = cfg.get("model", {}).get("max_tokens_weekly", 16000)
    model = cfg.get("model", {}).get("default", DEFAULT_MODEL)

    review = call_claude(
        system=prompt_system,
        user=user_msg,
        model=model,
        max_tokens=max_tokens,
        cache_system=True,
    )

    if trending_section:
        review = review + "\n\n---\n" + trending_section

    path = save_weekly_review(week_str, review)
    print(f"  Weekly review saved: {path}")
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tech Weekly Review")
    parser.add_argument("--week", help="ISO week string e.g. 2026-W19")
    args = parser.parse_args()
    run_weekly_review(args.week)
