"""Topic & Sector Analysis Workflow — analyze events by topic."""

from __future__ import annotations

import json
import os
from typing import Any

import yaml

from claude_client import call_claude_json
from state import NormalizedEvent, TopicSummary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_taxonomy() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "topic_taxonomy.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "topic_analysis.md")) as f:
        return f.read()


def _events_for_topic(topic_id: str, keywords: list[str],
                       events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    matched = []
    kw_lower = [k.lower() for k in keywords]
    for e in events:
        text = f"{e.canonical_title} {e.summary}".lower()
        if topic_id in e.topics or any(k in text for k in kw_lower):
            matched.append(e)
    return matched


def _build_user_message(topic_id: str, topic_label: str, keywords: list[str],
                         events: list[NormalizedEvent],
                         prev_status: str | None) -> str:
    events_payload = [
        {
            "event_id": e.event_id,
            "title": e.canonical_title,
            "summary": e.summary,
            "source_type": e.source_type,
            "companies": e.companies,
            "importance_score": e.importance_score,
        }
        for e in events[:30]
    ]
    return json.dumps({
        "topic": {"id": topic_id, "label": topic_label},
        "events": events_payload,
        "previous_trend_status": prev_status,
        "history_summary": None,
    }, ensure_ascii=False)


def analyze_topics(
    events: list[NormalizedEvent],
    previous_trend_statuses: dict[str, str] | None = None,
) -> dict[str, TopicSummary]:
    taxonomy = _load_taxonomy()
    prompt_system = _load_prompt()
    prev = previous_trend_statuses or {}
    summaries: dict[str, TopicSummary] = {}

    topics = taxonomy.get("topics", {})

    for topic_id, topic_data in topics.items():
        label = topic_data.get("label", topic_id)
        keywords = topic_data.get("keywords", [])
        matched_events = _events_for_topic(topic_id, keywords, events)

        if not matched_events:
            # No events → unchanged, not report-worthy
            summaries[topic_id] = TopicSummary(
                topic_id=topic_id,
                topic_label=label,
                trend_status="unchanged",
                trend_change="same",
                confidence="low",
                signal_count=0,
                key_signal_summary="今日无信号",
                key_events=[],
                multi_signal_check={},
                signal_classification="unclear",
                classification_reasoning="No events found",
                short_term_signals=[],
                medium_term_signals=[],
                long_term_signals=[],
                contradictions=[],
                report_worthy=False,
                report_snippet="",
            )
            continue

        try:
            user_msg = _build_user_message(
                topic_id, label, keywords, matched_events, prev.get(topic_id)
            )
            result = call_claude_json(
                system=prompt_system,
                user=user_msg,
                max_tokens=1024,
            )
            summaries[topic_id] = TopicSummary(
                topic_id=result.get("topic_id", topic_id),
                topic_label=result.get("topic_label", label),
                trend_status=result.get("trend_status", "unchanged"),
                trend_change=result.get("trend_change", "same"),
                confidence=result.get("confidence", "low"),
                signal_count=result.get("signal_count", len(matched_events)),
                key_signal_summary=result.get("key_signal_summary", ""),
                key_events=result.get("key_events", []),
                multi_signal_check=result.get("multi_signal_check", {}),
                signal_classification=result.get("signal_classification", "unclear"),
                classification_reasoning=result.get("classification_reasoning", ""),
                short_term_signals=result.get("short_term_signals", []),
                medium_term_signals=result.get("medium_term_signals", []),
                long_term_signals=result.get("long_term_signals", []),
                contradictions=result.get("contradictions", []),
                report_worthy=result.get("report_worthy", True),
                report_snippet=result.get("report_snippet", ""),
            )
            print(f"  [Topics] {topic_id}: {summaries[topic_id].trend_status} "
                  f"({len(matched_events)} events)")
        except Exception as e:
            print(f"  [Topics] {topic_id} analysis failed: {e}")
            summaries[topic_id] = TopicSummary(
                topic_id=topic_id,
                topic_label=label,
                trend_status=prev.get(topic_id, "unchanged"),
                trend_change="same",
                confidence="low",
                signal_count=len(matched_events),
                key_signal_summary=f"分析失败: {e}",
                key_events=[e.event_id for e in matched_events[:3]],
                multi_signal_check={},
                signal_classification="unclear",
                classification_reasoning=str(e),
                short_term_signals=[],
                medium_term_signals=[],
                long_term_signals=[],
                contradictions=[],
                report_worthy=len(matched_events) > 0,
                report_snippet="",
            )

    return summaries
