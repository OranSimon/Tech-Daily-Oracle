from __future__ import annotations

from datetime import UTC, datetime

from normalize_sources import normalize_collection_state, normalize_events
from pipeline_state import CollectionState
from state import RawEvent


def _raw(title: str, **metadata: object) -> RawEvent:
    return RawEvent(
        source_name="Fixture",
        source_type="rss",
        raw_title=title,
        raw_url=f"https://example.com/{abs(hash(title))}",
        raw_content="OpenAI and Nvidia announced a GPU inference benchmark.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={"priority": 1, "feed_source_type": "media", **metadata},
    )


def test_normalize_events_deduplicates_title_token_permutations() -> None:
    first = _raw("OpenAI releases GPT benchmark")
    second = _raw("Benchmark: GPT releases OpenAI")

    normalized = normalize_events([first, second], run_date="2026-07-02")

    assert len(normalized) == 1
    event = normalized[0]
    assert event.event_id.startswith("event-2026-07-02-")
    assert event.source_urls == [first.raw_url, second.raw_url]
    assert event.raw_event_ids == [first.raw_id, second.raw_id]
    assert "ai_models" in event.topics
    assert "OpenAI" in event.companies


def test_high_score_non_tech_hacker_news_story_becomes_general_interesting() -> None:
    raw = RawEvent(
        source_name="Hacker News",
        source_type="hacker_news",
        raw_title="Ask HN: What changed your career?",
        raw_url="https://news.ycombinator.com/item?id=1",
        raw_content="A community discussion.",
        published_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC).isoformat(),
        metadata={"score": 350, "comments": 100},
    )

    event = normalize_events([raw], run_date="2026-07-02")[0]

    assert event.source_type == "social"
    assert event.topics == ["general_interesting"]
    assert event.social_heat_score == 0.35


def test_normalization_scoring_policy_preserves_cross_domain_boost() -> None:
    raw = RawEvent(
        source_name="Fixture",
        source_type="rss",
        raw_title="OpenAI robotics breakthrough for new cancer biology lab",
        raw_url="https://example.com/fixture",
        raw_content="OpenAI robotics platform accelerates biotech discovery.",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
        metadata={"priority": 1, "feed_source_type": "company"},
    )

    [event] = normalize_events([raw], run_date="2026-07-02")

    assert "embodied_ai_robotics" in event.topics
    assert "health_biotech" in event.topics
    assert event.importance_score == 1.0
    assert event.reliability_score == 0.95


def test_normalization_reliability_policy_preserves_existing_priority_default_scores() -> None:
    paper = RawEvent(
        source_name="arXiv",
        source_type="arxiv",
        raw_title="Benchmark paper",
        raw_url="https://example.com/paper",
        raw_content="A new inference paper.",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
        metadata={},
    )
    github = RawEvent(
        source_name="GitHub",
        source_type="github",
        raw_title="Benchmark repo",
        raw_url="https://example.com/repo",
        raw_content="A new inference repo.",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
        metadata={},
    )

    paper_event, github_event = normalize_events([paper, github], run_date="2026-07-02")

    assert paper_event.reliability_score == 0.55
    assert github_event.reliability_score == 0.55


def test_normalize_collection_state_matches_legacy_normalize_events() -> None:
    raw_events = [
        _raw("OpenAI releases GPT benchmark"),
        _raw("Benchmark: GPT releases OpenAI"),
    ]

    legacy = normalize_events(raw_events, run_date="2026-07-02")
    typed = normalize_collection_state(CollectionState(raw_events=raw_events), run_date="2026-07-02")

    assert typed.normalized_events == legacy
