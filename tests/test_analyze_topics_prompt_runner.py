from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import analyze_topics
from state import NormalizedEvent


class FakeTopicRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_json(self, *, prompt_path: str, payload: dict[str, Any], schema: type[Any], max_tokens: int = 4096):
        self.calls.append(
            {
                "prompt_path": prompt_path,
                "payload": payload,
                "schema": schema,
                "max_tokens": max_tokens,
            }
        )
        return schema(
            topic_id=payload["topic"]["id"],
            topic_label=payload["topic"]["label"],
            trend_status="accelerating",
            trend_change="up",
            confidence="medium",
            signal_count=len(payload["events"]),
            key_signal_summary="Fixture summary",
            key_events=[payload["events"][0]["event_id"]],
            multi_signal_check={},
            signal_classification="single_signal",
            classification_reasoning="Fixture reasoning",
            short_term_signals=[],
            medium_term_signals=[],
            long_term_signals=[],
            contradictions=[],
            report_worthy=True,
            report_snippet="Fixture snippet",
        )


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-topic",
        canonical_title="OpenAI releases fixture model",
        summary="A fixture model release for topic analysis.",
        source_urls=["https://example.com/topic"],
        primary_source_url="https://example.com/topic",
        source_type="company",
        published_at=published,
        companies=["OpenAI"],
        projects=[],
        papers=[],
        people=[],
        topics=["ai_models"],
        geography=[],
        event_type="product_launch",
        importance_score=0.9,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-1"],
        metadata={},
    )


def test_analyze_topics_accepts_fake_prompt_runner(monkeypatch) -> None:
    fake_runner = FakeTopicRunner()
    monkeypatch.setattr(
        analyze_topics,
        "_load_taxonomy",
        lambda: {
            "topics": {
                "ai_models": {"label": "AI Models", "keywords": ["OpenAI"]},
                "semiconductors": {"label": "Semiconductors", "keywords": ["chip"]},
            }
        },
    )

    summaries = analyze_topics.analyze_topics([_event()], prompt_runner=fake_runner, max_workers=1)

    assert summaries["ai_models"].trend_status == "accelerating"
    assert summaries["semiconductors"].report_worthy is False
    assert fake_runner.calls[0]["prompt_path"] == "topic_analysis.md"
    assert fake_runner.calls[0]["payload"]["topic"]["id"] == "ai_models"
    assert fake_runner.calls[0]["schema"] is analyze_topics.TopicSummaryResponse
