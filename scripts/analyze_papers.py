"""Paper / Research Analysis Layer (parallel)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from claude_client import call_claude_json
from state import NormalizedEvent, PaperAnalysis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_WORKERS = 5   # concurrent Claude calls


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "paper_analysis.md")) as f:
        return f.read()


def _analyze_one_paper(
    event: NormalizedEvent,
    prompt_system: str,
) -> PaperAnalysis | None:
    authors = event.metadata.get("authors", []) if hasattr(event, "metadata") else []
    arxiv_id = event.metadata.get("arxiv_id", "") if hasattr(event, "metadata") else ""
    institution = "Unknown" if authors else ""

    try:
        user_msg = json.dumps({
            "paper": {
                "title": event.canonical_title,
                "abstract": event.summary,
                "authors": authors,
                "institution": institution,
                # source_name is stored in metadata by normalize_sources.py (not a direct field)
                "source": event.metadata.get("source_name", event.source_type),
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
            max_tokens=4096,
        )

        if result.get("signal_strength") == "skip":
            return None

        paper_id = result.get("paper_id") or event.event_id
        analysis = PaperAnalysis(
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
        print(f"  [Papers] {event.canonical_title[:60]}: {analysis.signal_strength}")
        return analysis

    except Exception as e:
        print(f"  [Papers] Analysis failed for '{event.canonical_title[:40]}': {e}")
        return None


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

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_analyze_one_paper, event, prompt_system): event.event_id
            for event in paper_events
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                analyses[result.paper_id] = result

    return analyses
