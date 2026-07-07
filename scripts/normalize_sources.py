"""Source Normalization & Deduplication Layer."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime

from config_models import NormalizationConfig, load_normalization_config
from pipeline_state import CollectionState, CorpusState
from state import NormalizedEvent, RawEvent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _title_hash(title: str) -> str:
    clean = re.sub(r"[^a-z0-9 ]", "", title.lower())
    tokens = sorted(clean.split())
    return hashlib.md5(" ".join(tokens).encode()).hexdigest()[:12]


def _detect_topics(text: str, config: NormalizationConfig) -> list[str]:
    text_lower = text.lower()
    matched = []
    for topic, keywords in config.topic_keywords.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(topic)
    return matched or ["general"]


def _detect_companies(text: str, config: NormalizationConfig) -> list[str]:
    matched = []
    for company, keywords in config.company_keywords.items():
        if any(kw in text for kw in keywords):
            matched.append(company)
    return matched


def _infer_source_type(raw: RawEvent) -> str:
    st = raw.source_type
    if st == "arxiv" or st == "huggingface":
        return "paper"
    if st == "github":
        return "github"
    if st == "hacker_news":
        return "social"
    meta_type = raw.metadata.get("feed_source_type", "")
    if meta_type == "company":
        return "company"
    if meta_type == "media":
        return "media"
    return "media"


def _infer_event_type(raw: RawEvent, topics: list[str], config: NormalizationConfig) -> str:
    title_lower = raw.raw_title.lower()
    if raw.source_type in ("arxiv", "huggingface"):
        return "paper"
    if raw.source_type == "github":
        return "github_trending"
    for rule in config.scoring_policy.event_type_rules:
        if any(keyword in title_lower for keyword in rule.keywords):
            return rule.event_type
    return "product_launch"


def _topic_group(config: NormalizationConfig, group_name: str) -> set[str]:
    return set(config.topic_groups.get(group_name, []))


def _score_importance(
    raw: RawEvent,
    topics: list[str],
    companies: list[str],
    config: NormalizationConfig,
) -> float:
    policy = config.scoring_policy
    score = policy.baseline_importance
    # Source type boost
    src_priority = raw.metadata.get("priority", 3)
    score += max(0.0, (5 - src_priority) * policy.source_priority_weight)
    # HN social heat
    hn_score = raw.metadata.get("score", 0)
    for threshold, boost in sorted(policy.hn_social_heat_thresholds.items(), reverse=True):
        if hn_score > threshold:
            score += boost
            break
    # Watchlist company
    if companies:
        score += policy.company_boost
    if any(t in _topic_group(config, "high_priority_topics") for t in topics):
        score += policy.high_priority_topic_boost
    # Cross-domain boost: AI/CS + science/global co-occurrence signals rare & important events
    if any(t in _topic_group(config, "core_tech_topics") for t in topics) and any(
        t in _topic_group(config, "cross_domain_topics") for t in topics
    ):
        score += policy.cross_domain_boost
    return min(1.0, score)


def _score_reliability(raw: RawEvent, config: NormalizationConfig) -> float:
    policy = config.scoring_policy.source_reliability_policy
    priority = raw.metadata.get("priority", raw.metadata.get("feed_source_type", 3))
    if isinstance(priority, int):
        return policy.source_reliability_by_priority.get(priority, policy.default_reliability)
    if raw.source_type in ("arxiv", "huggingface"):
        return policy.paper_reliability
    if raw.source_type == "github":
        return policy.github_reliability
    return policy.default_reliability


def normalize_events(
    raw_events: list[RawEvent],
    run_date: str = "",
    config: NormalizationConfig | None = None,
) -> list[NormalizedEvent]:
    domain_config = config or load_normalization_config()
    seen_hashes: dict[str, NormalizedEvent] = {}
    normalized: list[NormalizedEvent] = []

    for raw in raw_events:
        combined_text = f"{raw.raw_title} {raw.raw_content}"
        topics = _detect_topics(combined_text, domain_config)
        companies = _detect_companies(combined_text, domain_config)

        # Hacker News high-score stories with no core-tech topic → tag as general_interesting
        # These are genuinely interesting stories that would pass HN's community filter at ≥300.
        if (raw.source_type == "hacker_news"
                and raw.metadata.get("score", 0) >= 300
                and not any(t in _topic_group(domain_config, "core_tech_topics") for t in topics)):
            topics = ["general_interesting"] + [t for t in topics if t != "general"]

        source_type = _infer_source_type(raw)
        event_type = _infer_event_type(raw, topics, domain_config)
        importance = _score_importance(raw, topics, companies, domain_config)
        reliability = _score_reliability(raw, domain_config)

        th = _title_hash(raw.raw_title)

        if th in seen_hashes:
            # Merge: add source URL
            existing = seen_hashes[th]
            if raw.raw_url not in existing.source_urls:
                existing.source_urls.append(raw.raw_url)
            existing.importance_score = max(existing.importance_score, importance)
            existing.raw_event_ids.append(raw.raw_id)
            continue

        date_tag = run_date or datetime.now(UTC).strftime("%Y-%m-%d")
        event_id = f"event-{date_tag}-{th}"

        event = NormalizedEvent(
            event_id=event_id,
            canonical_title=raw.raw_title,
            summary=raw.raw_content[:500],
            source_urls=[raw.raw_url],
            primary_source_url=raw.raw_url,
            source_type=source_type,
            published_at=raw.published_at,
            companies=companies,
            projects=list(raw.metadata.get("topics", [])),
            papers=[],
            people=[],
            topics=topics,
            geography=[],
            event_type=event_type,
            importance_score=importance,
            novelty_score=0.8,
            reliability_score=reliability,
            social_heat_score=min(1.0, raw.metadata.get("score", 0) / 1000),
            raw_event_ids=[raw.raw_id],
            metadata={**raw.metadata, "source_name": raw.source_name},
        )
        seen_hashes[th] = event
        normalized.append(event)

    # Sort by importance descending
    normalized.sort(key=lambda e: e.importance_score, reverse=True)
    print(f"  [Normalize] {len(normalized)} unique events (from {len(raw_events)} raw)")
    return normalized


def normalize_collection_state(
    collection_state: CollectionState,
    run_date: str = "",
    config: NormalizationConfig | None = None,
) -> CorpusState:
    return CorpusState(
        normalized_events=normalize_events(collection_state.raw_events, run_date=run_date, config=config),
    )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    # Quick test with dummy data
    dummy = RawEvent(
        source_name="Test",
        source_type="rss",
        raw_title="OpenAI releases GPT-5 with major reasoning improvements",
        raw_url="https://openai.com/blog/gpt5",
        raw_content="OpenAI today announced GPT-5, featuring significant improvements...",
        published_at=datetime.now(UTC).isoformat(),
        fetched_at=datetime.now(UTC).isoformat(),
        metadata={"priority": 1, "feed_source_type": "company"},
    )
    results = normalize_events([dummy])
    print(json.dumps([
        {"id": e.event_id, "title": e.canonical_title, "topics": e.topics,
         "companies": e.companies, "importance": e.importance_score}
        for e in results
    ], indent=2, ensure_ascii=False))
