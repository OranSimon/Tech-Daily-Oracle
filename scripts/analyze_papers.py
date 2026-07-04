"""Paper / Research Analysis Layer (parallel)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from analyzer_helpers import schema_to_dataclass
from llm_schemas import PaperAnalysisResponse
from prompt_runner import PromptRunner
from state import NormalizedEvent, PaperAnalysis

MAX_WORKERS = 5  # concurrent LLM calls


def _analyze_one_paper(
    event: NormalizedEvent,
    prompt_runner: PromptRunner,
) -> PaperAnalysis | None:
    authors = event.metadata.get("authors", []) if hasattr(event, "metadata") else []
    arxiv_id = event.metadata.get("arxiv_id", "") if hasattr(event, "metadata") else ""
    institution = "Unknown" if authors else ""

    payload = {
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
    }

    result = prompt_runner.run_json(
        prompt_path="paper_analysis.md",
        payload=json.dumps(payload, ensure_ascii=False),
        schema=PaperAnalysisResponse,
        max_tokens=4096,
    )

    if result.signal_strength == "skip":
        return None

    analysis = schema_to_dataclass(
        result,
        PaperAnalysis,
        paper_id=result.paper_id or event.event_id,
    )
    print(f"  [Papers] {event.canonical_title[:60]}: {analysis.signal_strength}")
    return analysis


def analyze_papers(
    events: list[NormalizedEvent],
    max_to_analyze: int = 30,
    prompt_runner: PromptRunner | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict[str, PaperAnalysis]:
    runner = prompt_runner or PromptRunner()

    paper_events = [
        e for e in events if e.source_type == "paper" or "papers_research" in e.topics or e.event_type == "paper"
    ]
    paper_events = sorted(paper_events, key=lambda e: e.importance_score, reverse=True)
    paper_events = paper_events[:max_to_analyze]

    analyses: dict[str, PaperAnalysis] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_analyze_one_paper, event, runner): event.event_id for event in paper_events}
        for future in as_completed(futures):
            event_id = futures[future]
            try:
                result = future.result()
                if result is not None:
                    analyses[result.paper_id] = result
            except Exception as e:
                print(f"  [Papers] Analysis failed for '{event_id}': {e}")

    return analyses
