#!/usr/bin/env python3
"""Monthly Strategic Review Workflow.

Run: python scripts/run_monthly_review.py [--month 2026-05]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_client import call_claude, DEFAULT_MODEL
from storage import save_monthly_review, load_recent_reports, load_open_predictions
from score_predictions import compute_scorecard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "monthly_review.md")) as f:
        return f.read()


def _load_weekly_reviews_for_month(month_str: str) -> list[dict]:
    weekly_dir = os.path.join(ROOT, "reports", "weekly")
    if not os.path.exists(weekly_dir):
        return []
    reviews = []
    # Load all weekly reviews and filter by month
    for fname in sorted(os.listdir(weekly_dir), reverse=True)[:8]:
        if not fname.endswith(".md"):
            continue
        path = os.path.join(weekly_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            reviews.append({
                "week": fname.replace(".md", ""),
                "content": content[:4000],
            })
        except Exception:
            pass
    return reviews


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
    today = date.today()

    if month_str is None:
        month_str = today.strftime("%Y-%m")

    print(f"\n{'#'*60}")
    print(f"  Tech Monthly Strategic Review — {month_str}")
    print(f"{'#'*60}\n")

    prompt_system = _load_prompt()
    weekly_reviews = _load_weekly_reviews_for_month(month_str)
    topic_trends = _load_topic_trends_month(month_str)
    company_trends = _load_company_mention_trends(month_str)
    prediction_perf = _load_prediction_performance(month_str)
    open_predictions = load_open_predictions()

    user_msg = json.dumps({
        "month": month_str,
        "weekly_reviews": weekly_reviews,
        "daily_summaries": [],
        "topic_trend_history": topic_trends,
        "prediction_performance": prediction_perf,
        "company_mention_trends": company_trends,
        "open_predictions": [
            {"prediction_id": p.prediction_id, "prediction": p.prediction,
             "probability": p.probability, "time_horizon": p.time_horizon}
            for p in open_predictions
        ],
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

    path = save_monthly_review(month_str, review)
    print(f"  Monthly review saved: {path}")
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tech Monthly Review")
    parser.add_argument("--month", help="Month string e.g. 2026-05")
    args = parser.parse_args()
    run_monthly_review(args.month)
