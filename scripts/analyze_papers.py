"""Paper / Research Analysis Layer."""

from __future__ import annotations

import json
import os
from typing import Any

from claude_client import call_claude_json
from state import NormalizedEvent, PaperAnalysis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "paper_analysis.md")) as f:
        return f.read()


def analyze_papers(
    events: list[NormalizedEvent],
    max_to_analyze: int = 30,
) -> dict[str, PaperAnalysis]:
    prompt_system = _load_prompt()

    paper_events = [
        e for e in events
        if e.source_type == "paper" or "papers_research" in e.topics
        or e.event_type == "paper"
    ]
    paper_events = sorted(paper_events, key=lambda e: e.importance_score, reverse=True)
    paper_events = paper_events[:max_to_analyze]

    analyses: dict[str, PaperAnalysis] = {}

    for event in paper_events:
        # Extract paper metadata from raw event fields
        authors = event.metadata.get("authors", []) if hasattr(event, "metadata") else []
        arxiv_id = event.metadata.get("arxiv_id", "") if hasattr(event, "metadata") else ""
        institution = ""
        if authors:
            institution = "Unknown"

        try:
            user_msg = json.dumps({
                "paper": {
                    "title": event.canonical_title,
                    "abstract": event.summary,
                    "authors": authors,
                    "institution": institution,
                    "source": event.source_name if hasattr(event, "source_name") else event.source_type,
                    "categories": event.topics,
                    "link": event.primary_source_url,
                    "arxiv_id": arxiv_id,
                },
                "context": {
                    "trending_topics": event.topics,
                },
            }, ensure_ascii=False)

            result = call_claude_json(
                system=prompt_system,
                user=user_msg,
                max_tokens=1024,
            )

            if result.get("signal_strength") == "skip":
                continue

            paper_id = result.get("paper_id") or event.event_id

            analyses[paper_id] = PaperAnalysis(
                paper_id=paper_id,
                title=result.get("title", event.canonical_title),
                authors=result.get("authors", []),
                institution=result.get("institution", ""),
                source=result.get("source", event.source_type),
                categories=result.get("categories", []),
                link=result.get("link", event.primary_source_url),
                code_available=result.get("code_available", False),
                report_worthy=result.get("report_worthy", True),
                signal_strength=result.get("signal_strength", "medium"),
                technical_contribution=result.get("technical_contribution", ""),
                engineering_product_impact=result.get("engineering_product_impact"),
                novelty_score=result.get("novelty_score", 0.5),
                impact_score=result.get("impact_score", 0.5),
                overall_score=result.get("overall_score", 0.5),
                why_notable=result.get("why_notable", ""),
                caveats=result.get("caveats", ""),
                topic_tags=result.get("topic_tags", []),
                related_companies=result.get("related_companies", []),
                related_predictions=result.get("related_predictions", []),
                hype_risk=result.get("hype_risk", "low"),
                hype_risk_reason=result.get("hype_risk_reason"),
            )
            print(f"  [Papers] {event.canonical_title[:60]}: "
                  f"{analyses[paper_id].signal_strength}")
        except Exception as e:
            print(f"  [Papers] Analysis failed for '{event.canonical_title[:40]}': {e}")

    return analyses
