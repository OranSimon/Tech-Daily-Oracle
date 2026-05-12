"""Social Signal Analysis Layer — X + HN first, Reddit as supplement (parallel)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from claude_client import call_claude_json
from state import NormalizedEvent, SocialSignalAnalysis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_WORKERS = 5


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "social_signal_analysis.md")) as f:
        return f.read()


TRIGGER_KEYWORDS = [
    "launch", "release", "viral", "controversy", "benchmark",
    "disappointing", "impressive", "test", "review", "vs",
]

HN_HOT_THRESHOLD = 200  # HN score to consider "hot"


def _find_hot_subjects(events: list[NormalizedEvent]) -> list[dict[str, Any]]:
    """Identify subjects with meaningful social heat."""
    hot: list[dict[str, Any]] = []
    seen: set[str] = set()

    for e in events:
        hn_score = e.metadata.get("score", 0) if hasattr(e, "metadata") else 0
        if hn_score >= HN_HOT_THRESHOLD or e.social_heat_score >= 0.5:
            subjects = e.companies + e.projects
            for subject in subjects:
                if subject not in seen:
                    seen.add(subject)
                    related = [
                        ev for ev in events
                        if subject in (ev.companies + ev.projects)
                    ]
                    hot.append({
                        "subject": subject,
                        "subject_type": "ai_model" if "ai_models" in e.topics else
                                        "github_project" if e.source_type == "github" else
                                        "product",
                        "events": related,
                        "trigger_event": e,
                    })

    for e in events:
        if e.source_type == "github":
            # metadata["stars"] is total stargazers_count, not new stars today.
            # GitHub trending events come from newly-created repos (created yesterday),
            # so their total star count is a reasonable proxy for viral traction.
            total_stars = e.metadata.get("stars", 0) if hasattr(e, "metadata") else 0
            url_key = f"url:{e.primary_source_url}"
            if total_stars > 500 and url_key not in seen:
                seen.add(url_key)
                hot.append({
                    "subject": e.canonical_title,
                    "subject_type": "github_project",
                    "events": [e],
                    "trigger_event": e,
                })

    return hot[:5]


def _analyze_one_subject(
    subject_data: dict[str, Any],
    prompt_system: str,
) -> SocialSignalAnalysis | None:
    subject = subject_data["subject"]
    related = subject_data["events"]

    try:
        hn_items = [
            {
                "title": e.canonical_title,
                "url": e.primary_source_url,
                "score": e.metadata.get("score", 0) if hasattr(e, "metadata") else 0,
                "comments": e.metadata.get("comments", 0) if hasattr(e, "metadata") else 0,
                "hn_url": e.metadata.get("hn_url", "") if hasattr(e, "metadata") else "",
                "content": e.summary,
            }
            for e in related
            if e.source_type == "social"
        ]

        user_msg = json.dumps({
            "subject": subject,
            "subject_type": subject_data["subject_type"],
            "hacker_news_items": hn_items,
            "search_results": [
                {"title": e.canonical_title, "url": e.primary_source_url, "content": e.summary}
                for e in related
                if e.source_type != "social"
            ][:10],
            "event_ids": [e.event_id for e in related],
        }, ensure_ascii=False)

        result = call_claude_json(
            system=prompt_system,
            user=user_msg,
            max_tokens=4096,
        )

        if not result.get("trigger_condition_met", False):
            return None
        if not result.get("report_worthy", True):
            return None

        analysis = SocialSignalAnalysis(
            subject=result.get("subject", subject),
            subject_type=result.get("subject_type", "product"),
            trigger_condition_met=result.get("trigger_condition_met", True),
            trigger_reason=result.get("trigger_reason", ""),
            platforms_sampled=result.get("platforms_sampled", ["hacker_news"]),
            positive_points=result.get("positive_points", []),
            negative_points=result.get("negative_points", []),
            controversies=result.get("controversies", []),
            authority_opinions=result.get("authority_opinions", []),
            community_consensus=result.get("community_consensus", ""),
            hype_risk=result.get("hype_risk", "medium"),
            hype_risk_reason=result.get("hype_risk_reason", ""),
            signal_classification=result.get("signal_classification", "tech_curiosity"),
            report_worthy=result.get("report_worthy", True),
            report_snippet=result.get("report_snippet", ""),
        )
        print(f"  [Social] {subject}: {analysis.hype_risk} hype risk")
        return analysis

    except Exception as e:
        print(f"  [Social] Analysis failed for {subject}: {e}")
        return None


def analyze_social_signals(
    events: list[NormalizedEvent],
) -> dict[str, SocialSignalAnalysis]:
    prompt_system = _load_prompt()
    hot_subjects = _find_hot_subjects(events)
    if not hot_subjects:
        return {}

    analyses: dict[str, SocialSignalAnalysis] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_analyze_one_subject, subject_data, prompt_system): subject_data["subject"]
            for subject_data in hot_subjects
        }
        for future in as_completed(futures):
            subject = futures[future]
            result = future.result()
            if result is not None:
                analyses[subject] = result

    return analyses
