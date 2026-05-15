"""Report Generation Layer — produce the daily brief from the blackboard state."""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

import yaml

from claude_client import call_claude, DEFAULT_MODEL
from state import TechDailyState

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "daily_brief.md")) as f:
        return f.read()


def _load_config() -> dict[str, Any]:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _load_preferences() -> dict[str, Any]:
    prefs_path = os.path.join(ROOT, "data", "user_preferences.yml")
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            return yaml.safe_load(f)
    return {}


def _previous_reports_summary(state: TechDailyState) -> list[dict[str, Any]]:
    return [
        {
            "report_date": r.report_date,
            "type": r.report_type,
            "excerpt": r.content[:800],
        }
        for r in state.previous_reports[-7:]
    ]


def _safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_safe_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_dict(v) for k, v in obj.items()}
    return obj


def _build_report_payload(state: TechDailyState) -> dict[str, Any]:
    """Build the structured payload sent to Claude for report generation."""

    # Top events by importance
    top_events = sorted(state.normalized_events,
                        key=lambda e: e.importance_score, reverse=True)[:30]

    # Paper analyses — sort by score
    sorted_papers = sorted(
        state.paper_analyses.values(),
        key=lambda p: p.overall_score,
        reverse=True,
    )

    # GitHub — top 3 Watch verdicts
    top_github = [
        v for v in state.github_project_analyses.values()
        if v.verdict == "Watch"
    ][:3]

    # Company analyses — significant only
    sig_companies = {
        k: v for k, v in state.company_analyses.items()
        if v.significance in ("high", "medium")
    }

    return {
        "run_date": state.run_date,
        "normalized_events": [_safe_dict(e) for e in top_events],
        "topic_summaries": {k: _safe_dict(v) for k, v in state.topic_summaries.items()
                             if v.report_worthy},
        "company_analyses": {k: _safe_dict(v) for k, v in sig_companies.items()},
        "paper_analyses": [_safe_dict(p) for p in sorted_papers[:8] if p.report_worthy],
        "github_project_analyses": [_safe_dict(g) for g in top_github],
        "social_signal_analyses": {k: _safe_dict(v)
                                    for k, v in state.social_signal_analyses.items()
                                    if v.report_worthy},
        "macro_impact_analyses": {k: _safe_dict(v)
                                   for k, v in state.macro_impact_analyses.items()
                                   if v.report_worthy},
        "open_predictions": [_safe_dict(p) for p in state.open_predictions],
        "prediction_updates": [_safe_dict(u) for u in state.prediction_updates],
        "new_predictions": [_safe_dict(p) for p in state.new_predictions],
        "previous_reports_summary": _previous_reports_summary(state),
        "history_context": {
            "weekly_reviews": [
                {"week": r.report_date, "excerpt": r.content[:1500]}
                for r in state.weekly_reviews
            ],
            "monthly_reviews": [
                {"month": r.report_date, "excerpt": r.content[:2000]}
                for r in state.monthly_reviews
            ],
            "topic_trend_30d": state.recent_topic_trends[-90:],
            "company_mentions_90d": state.recent_company_mentions[-120:],
        },
        # Section 13 only needs ticker, company, and the pre-formatted snippet.
        # Sending the full dataclass (20 fields) wastes payload tokens redundantly.
        "market_signal_analyses": [
            {"ticker": v.ticker, "company": v.company, "report_snippet": v.report_snippet}
            for v in state.market_signal_analyses.values()
        ],
        "source_warnings": state.source_warnings,
        "confidence_flags": state.confidence_flags,
        "user_preferences": _load_preferences(),
        "signal_level": state.signal_level,
    }


def generate_daily_report(state: TechDailyState) -> str:
    cfg = _load_config()
    prompt_system = _load_prompt()
    max_tokens = cfg.get("model", {}).get("max_tokens_daily", 8000)
    model = cfg.get("model", {}).get("default", DEFAULT_MODEL)

    payload = _build_report_payload(state)
    user_msg = json.dumps(payload, ensure_ascii=False)

    print(f"  [Report] Generating daily brief for {state.run_date}...")
    report = call_claude(
        system=prompt_system,
        user=user_msg,
        model=model,
        max_tokens=max_tokens,
        cache_system=True,
    )

    # Append the pre-computed trending section (OSSInsight + HuggingFace)
    if state.trending_analysis is not None and state.trending_analysis.report_section:
        report = report + "\n\n---\n" + state.trending_analysis.report_section

    print(f"  [Report] Generated {len(report)} characters")
    return report
