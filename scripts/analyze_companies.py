"""Company / Startup Analysis Layer."""

from __future__ import annotations

import json
import os
from typing import Any

import yaml

from claude_client import call_claude_json
from state import NormalizedEvent, CompanyAnalysis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_watchlist() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "company_watchlist.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "company_analysis.md")) as f:
        return f.read()


def _all_watched_companies(watchlist: dict[str, Any]) -> list[dict[str, Any]]:
    companies = []
    category_map = {
        "global_big_tech": "big_tech",
        "ai_labs": "ai_lab",
        "robotics_embodied_ai": "robotics",
        "ai_infrastructure": "infra",
        "hardware_devices": "hardware",
        "china_tech": "china_tech",
    }
    for section, cat in category_map.items():
        for c in watchlist.get(section, []):
            companies.append({"name": c["name"], "category": cat,
                               "ticker": c.get("ticker"), "domains": c.get("domains", [])})
    return companies


def _events_for_company(company_name: str, aliases: list[str],
                          events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    all_names = [company_name] + aliases
    matched = []
    for e in events:
        if company_name in e.companies:
            matched.append(e)
            continue
        text = f"{e.canonical_title} {e.summary}"
        if any(name in text for name in all_names):
            matched.append(e)
    return matched


def analyze_companies(events: list[NormalizedEvent]) -> dict[str, CompanyAnalysis]:
    watchlist = _load_watchlist()
    prompt_system = _load_prompt()
    watched = _all_watched_companies(watchlist)
    analyses: dict[str, CompanyAnalysis] = {}

    for company in watched:
        name = company["name"]
        cat = company["category"]
        aliases = company.get("domains", [])

        matched = _events_for_company(name, aliases, events)
        if not matched:
            continue

        try:
            user_msg = json.dumps({
                "company": name,
                "category": cat,
                "ticker": company.get("ticker"),
                "events": [
                    {
                        "event_id": e.event_id,
                        "title": e.canonical_title,
                        "summary": e.summary,
                        "source_type": e.source_type,
                        "importance_score": e.importance_score,
                        "source_urls": e.source_urls[:2],
                    }
                    for e in matched[:15]
                ],
                "history_summary": None,
            }, ensure_ascii=False)

            result = call_claude_json(
                system=prompt_system,
                user=user_msg,
                max_tokens=1024,
            )

            if not result.get("report_worthy", True):
                continue

            analyses[name] = CompanyAnalysis(
                company=name,
                category=result.get("category", cat),
                report_worthy=result.get("report_worthy", True),
                significance=result.get("significance", "medium"),
                event_ids=result.get("event_ids", []),
                summary=result.get("summary", ""),
                analysis_by_category=result.get("analysis_by_category", {}),
                confidence=result.get("confidence", "medium"),
                source_quality=result.get("source_quality", "media"),
                watchlist_action=result.get("watchlist_action", "none"),
                watchlist_notes=result.get("watchlist_notes"),
            )
            print(f"  [Companies] {name}: {analyses[name].significance} "
                  f"({len(matched)} events)")
        except Exception as e:
            print(f"  [Companies] {name} analysis failed: {e}")

    return analyses
