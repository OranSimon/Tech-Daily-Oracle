"""Macro / Geopolitical Impact Layer."""

from __future__ import annotations

import json
import os
from typing import Any

import yaml
from analyzer_helpers import schema_to_dataclass
from llm_schemas import MacroImpactAnalysisResponse
from prompt_runner import PromptRunner
from state import MacroImpactAnalysis, NormalizedEvent, Prediction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_macro_watchlist() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "macro_watchlist.yml")) as f:
        return yaml.safe_load(f)


MACRO_KEYWORDS = [
    "export control",
    "sanction",
    "tariff",
    "trade war",
    "chip ban",
    "chip restriction",
    "AI regulation",
    "EU AI Act",
    "policy",
    "geopolitical",
    "war",
    "conflict",
    "supply chain",
    "mineral",
    "lithium",
    "cobalt",
    "gallium",
    "germanium",
    "rare earth",
    "TSMC",
    "Taiwan",
    "semiconductor restriction",
    "energy price",
    "data center energy",
    "strategic reserve",
    "critical infrastructure",
    "national security",
    "DOD",
    "Pentagon",
    "CFIUS",
    "Entity List",
]


def _is_macro_candidate(event: NormalizedEvent) -> bool:
    text = f"{event.canonical_title} {event.summary}".lower()
    return (
        "macro_geopolitical" in event.topics
        or event.event_type == "policy"
        or any(kw.lower() in text for kw in MACRO_KEYWORDS)
    )


def _analyze_one_macro_event(
    event: NormalizedEvent,
    company_watchlist: list[str],
    open_predictions: list[dict[str, Any]],
    prompt_runner: PromptRunner,
) -> MacroImpactAnalysis | None:
    payload = {
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
        "company_watchlist": company_watchlist,
        "open_predictions": open_predictions,
    }

    result = prompt_runner.run_json(
        prompt_path="macro_impact_analysis.md",
        payload=json.dumps(payload, ensure_ascii=False),
        schema=MacroImpactAnalysisResponse,
        max_tokens=4096,
    )

    if not result.report_worthy:
        print(f"  [Macro] Filtered: {event.canonical_title[:50]} — {result.exclusion_reason or ''}")
        return None

    return schema_to_dataclass(result, MacroImpactAnalysis)


def analyze_macro_impact(
    events: list[NormalizedEvent],
    open_predictions: list[Prediction] | None = None,
    prompt_runner: PromptRunner | None = None,
) -> dict[str, MacroImpactAnalysis]:
    watchlist = _load_macro_watchlist()
    runner = prompt_runner or PromptRunner()

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
            analysis = _analyze_one_macro_event(
                event,
                list(company_names.keys()),
                pred_summaries[:10],
                runner,
            )
            if analysis is not None:
                analyses[event.event_id] = analysis
                print(f"  [Macro] {event.canonical_title[:50]}: severity={analyses[event.event_id].severity}")

        except Exception as e:
            print(f"  [Macro] Analysis failed: {e}")

    return analyses
