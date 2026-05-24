#!/usr/bin/env python3
"""Monthly Strategic Review Workflow.

Run: python scripts/run_monthly_review.py [--month 2026-05]
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
    save_monthly_review, load_recent_reports, load_open_predictions,
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
    with open(os.path.join(ROOT, "prompts", "monthly_review.md")) as f:
        return f.read()


def _week_in_month(week_str: str, month_str: str) -> bool:
    """Return True if any day of the ISO week falls within month_str (YYYY-MM)."""
    try:
        monday = datetime.strptime(f"{week_str}-1", "%G-W%V-%u").date()
        for i in range(7):
            if (monday + timedelta(days=i)).strftime("%Y-%m") == month_str:
                return True
        return False
    except ValueError:
        return False


def _load_weekly_reviews_for_month(month_str: str) -> list[dict]:
    weekly_dir = os.path.join(ROOT, "reports", "weekly")
    if not os.path.exists(weekly_dir):
        return []
    reviews = []
    for fname in sorted(os.listdir(weekly_dir)):
        if not fname.endswith(".md"):
            continue
        week_str = fname.replace(".md", "")   # e.g. "2026-W19"
        if not _week_in_month(week_str, month_str):
            continue
        path = os.path.join(weekly_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            reviews.append({
                "week": week_str,
                "content": content[:4000],
            })
        except Exception:
            pass
    return reviews


def _load_daily_summaries_for_month(month_str: str) -> list[dict]:
    """Load daily reports whose filename date falls within month_str (YYYY-MM)."""
    daily_dir = os.path.join(ROOT, "reports", "daily")
    if not os.path.exists(daily_dir):
        return []
    summaries = []
    for fname in sorted(os.listdir(daily_dir)):
        if not fname.endswith(".md"):
            continue
        report_date = fname.replace(".md", "")  # e.g. "2026-05-07"
        if not report_date.startswith(month_str):
            continue
        try:
            with open(os.path.join(daily_dir, fname), encoding="utf-8") as f:
                content = f.read()
            summaries.append({
                "date": report_date,
                "content": content[:2000],  # trim to keep payload manageable
            })
        except Exception:
            pass
    return summaries


def _load_topic_trends_month(month_str: str) -> list[dict]:
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
                run_date = d.get("run_date", "")
                if run_date.startswith(month_str):
                    trends.append(d)
            except Exception:
                pass
    return trends


def _load_company_mention_trends(month_str: str) -> list[dict]:
    path = os.path.join(ROOT, "data", "company_mentions.jsonl")
    if not os.path.exists(path):
        return []
    mentions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("run_date", "").startswith(month_str):
                    mentions.append(d)
            except Exception:
                pass
    return mentions


def _load_prediction_performance(month_str: str) -> dict:
    scorecard = compute_scorecard()
    # Add monthly breakdown
    pred_path = os.path.join(ROOT, "data", "prediction_log.jsonl")
    if not os.path.exists(pred_path):
        return scorecard
    opened_this_month = 0
    resolved_this_month_true = 0
    resolved_this_month_false = 0
    with open(pred_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
                if p.get("created_date", "").startswith(month_str):
                    opened_this_month += 1
                for u in p.get("updates", []):
                    if (u.get("update_date", "").startswith(month_str)
                            and u.get("resolution", {}).get("resolved")):
                        outcome = u["resolution"].get("resolved_as")
                        if outcome == "true":
                            resolved_this_month_true += 1
                        elif outcome == "false":
                            resolved_this_month_false += 1
            except Exception:
                pass
    return {
        **scorecard,
        "opened_this_month": opened_this_month,
        "resolved_this_month_true": resolved_this_month_true,
        "resolved_this_month_false": resolved_this_month_false,
    }


def run_monthly_review(month_str: str | None = None) -> str:
    cfg = _load_config()
    # Local-timezone "today" so "previous month" is computed in CST, not UTC.
    tz_name = cfg.get("run", {}).get("timezone", "Asia/Shanghai")
    today = datetime.now(ZoneInfo(tz_name)).date()

    if month_str is None:
        # Default to the previous calendar month.
        # This script runs on the 1st of each month at 02:00 UTC, so the
        # previous month's data (daily + weekly) is fully committed.
        first_of_this_month = today.replace(day=1)
        last_month = first_of_this_month - timedelta(days=1)
        month_str = last_month.strftime("%Y-%m")

    # Guard: ensure the target month has enough data before running
    weekly_reviews = _load_weekly_reviews_for_month(month_str)
    daily_summaries = _load_daily_summaries_for_month(month_str)
    min_weekly = cfg.get("review_guards", {}).get("min_weekly_for_monthly", 2)
    min_daily = cfg.get("review_guards", {}).get("min_daily_for_monthly", 10)
    if len(weekly_reviews) < min_weekly and len(daily_summaries) < min_daily:
        print(
            f"\n  [Monthly] Insufficient data for {month_str}: "
            f"{len(weekly_reviews)} weekly review(s) (need ≥ {min_weekly}) and "
            f"{len(daily_summaries)} daily report(s) (need ≥ {min_daily}). "
            f"Monthly review skipped.\n"
        )
        return ""

    print(f"\n{'#'*60}")
    print(f"  Tech Monthly Strategic Review — {month_str}")
    print(f"{'#'*60}\n")

    prompt_system = _load_prompt()
    # weekly_reviews and daily_summaries already loaded by the guard check above
    topic_trends = _load_topic_trends_month(month_str)

    # Monthly trending: collect rolling 30-day window using OSSInsight + HF aggregation
    trending_section = ""
    try:
        top_n = cfg.get("trending", {}).get("top_n", 5)
        monthly_snapshot = collect_trending_snapshot("monthly", today.isoformat(), cfg)
        history = load_trending_history(days=90)
        monthly_trending = analyze_trending(monthly_snapshot, history, top_n=top_n)
        trending_section = monthly_trending.report_section
        print(f"  [Trending] Monthly snapshot collected")
    except Exception as e:
        print(f"  [Trending] Monthly collection failed (non-fatal): {e}")
    company_trends = _load_company_mention_trends(month_str)
    prediction_perf = _load_prediction_performance(month_str)
    open_predictions = load_open_predictions()

    # Market signal history for this month (Phase 4+; empty list when disabled)
    try:
        all_market_signals = load_market_signals_history(days=95)  # full month + buffer
        market_signals_this_month = [
            s for s in all_market_signals
            if s.get("run_date", "")[:7] == month_str
        ]
    except Exception:
        market_signals_this_month = []

    user_msg = json.dumps({
        "month": month_str,
        "weekly_reviews": weekly_reviews,
        "daily_summaries": daily_summaries,
        "topic_trend_history": topic_trends,
        "prediction_performance": prediction_perf,
        "company_mention_trends": company_trends,
        "open_predictions": [
            {"prediction_id": p.prediction_id, "prediction": p.prediction,
             "probability": p.probability, "time_horizon": p.time_horizon}
            for p in open_predictions
        ],
        "trending_monthly_summary": trending_section or None,
        "market_signal_performance": market_signals_this_month or None,
    }, ensure_ascii=False)

    max_tokens = cfg.get("model", {}).get("max_tokens_monthly", 24000)
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

    path = save_monthly_review(month_str, review)
    print(f"  Monthly review saved: {path}")

    if cfg.get("notion", {}).get("enabled", False):
        try:
            from publish_notion import publish_to_notion
            # Use the 1st of the month as the representative date for Notion's Date property.
            notion_url = publish_to_notion(
                f"{month_str}-01",
                review,
                cfg,
                title=f"Tech Monthly Review — {month_str}",
            )
            if notion_url:
                print(f"  [Notion] Published: {notion_url}")
        except Exception as e:
            print(f"  [Notion] Publish failed (non-fatal): {e}")

    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tech Monthly Review")
    parser.add_argument("--month", help="Month string e.g. 2026-05")
    args = parser.parse_args()
    run_monthly_review(args.month)
