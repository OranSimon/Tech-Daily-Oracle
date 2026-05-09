"""Macro / Geopolitical Impact Layer."""

from __future__ import annotations

import json
import os
from typing import Any

import yaml

from claude_client import call_claude_json
from state import NormalizedEvent, MacroImpactAnalysis, Prediction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_macro_watchlist() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "macro_watchlist.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "macro_impact_analysis.md")) as f:
        return f.read()


MACRO_KEYWORDS = [
    "export control", "sanction", "tariff", "trade war", "chip ban", "chip restriction",
    "AI regulation", "EU AI Act", "policy", "geopolitical", "war", "conflict",
    "supply chain", "mineral", "lithium", "cobalt", "gallium", "germanium",
    "rare earth", "TSMC", "Taiwan", "semiconductor restriction", "energy price",
    "data center energy", "strategic reserve", "critical infrastructure",
    "national security", "DOD", "Pentagon", "CFIUS", "Entity List",
]


def _is_macro_candidate(event: NormalizedEvent) -> bool:
    text = f"{event.canonical_title} {event.summary}".lower()
    return (
        "macro_geopolitical" in event.topics
        or event.event_type == "policy"
        or any(kw.lower() in text for kw in MACRO_KEYWORDS)
    )


def analyze_macro_impact(
    events: list[NormalizedEvent],
    open_predictions: list[Prediction] | None = None,
) -> dict[str, MacroImpactAnalysis]:
    watchlist = _load_macro_watchlist()
    prompt_system = _load_prompt()

    macro_candidates = [e for e in events if _is_macro_candidate(e)]
    if not macro_candidates:
        return {}

    # Sort by importance
    macro_candidates = sorted(macro_candidates, key=lambda e: e.importance_score, reverse=True)

    company_names = watchlist.get("key_policy_domains", {})
    pred_summaries = [
        {"id": p.prediction_id, "prediction": p.prediction, "topics": p.topic_tags}
        for p in (open_predictions or [])
        if "macro_geopolitical" in p.topic_tags or "semiconductors" in p.topic_tags
    ]

    analyses: dict[str, MacroImpactAnalysis] = {}

    for event in macro_candidates[:10]:
        try:
            user_msg = json.dumps({
                "event": {
                    "event_id": event.event_id,
                    "title": event.canonical_title,
                    "summary": event.summary,
                    "source_type": event.source_type,
                    "source_urls": event.source_urls[:2],
                    "topics": event.topics,
                    "geography": event.geography,
                    "importance_score": event.importance_score,
                },
                "company_watchlist": list(company_names.keys()),
                "open_predictions": pred_summaries[:10],
            }, ensure_ascii=False)

            result = call_claude_json(
                system=prompt_system,
                user=user_msg,
                max_tokens=4096,
            )

            if not result.get("report_worthy", True):
                print(f"  [Macro] Filtered: {event.canonical_title[:50]} "
                      f"— {result.get('exclusion_reason', '')}")
                continue

            analyses[event.event_id] = MacroImpactAnalysis(
                event_id=result.get("event_id", event.event_id),
                event_title=result.get("event_title", event.canonical_title),
                event_type=result.get("event_type", "other"),
                report_worthy=result.get("report_worthy", True),
                exclusion_reason=result.get("exclusion_reason"),
                transmission_path=result.get("transmission_path", ""),
                affected_companies=result.get("affected_companies", []),
                affected_sectors=result.get("affected_sectors", []),
                affected_directions=result.get("affected_directions", []),
                time_dimension=result.get("time_dimension", "medium"),
                time_reasoning=result.get("time_reasoning", ""),
                severity=result.get("severity", "medium"),
                confidence=result.get("confidence", "medium"),
                prediction_impacts=result.get("prediction_impacts", []),
                report_snippet=result.get("report_snippet", ""),
            )
            print(f"  [Macro] {event.canonical_title[:50]}: "
                  f"severity={analyses[event.event_id].severity}")

        except Exception as e:
            print(f"  [Macro] Analysis failed: {e}")

    return analyses
