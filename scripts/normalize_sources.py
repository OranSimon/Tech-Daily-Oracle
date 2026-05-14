"""Source Normalization & Deduplication Layer."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import anthropic
import yaml

from state import RawEvent, NormalizedEvent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Topic keywords for tagging (lightweight, no Claude call needed)
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "ai_models": ["LLM", "GPT", "language model", "foundation model", "multimodal", "reasoning",
                  "benchmark", "fine-tuning", "RLHF", "model release", "Llama", "Gemini",
                  "Claude", "GPT-4", "o1", "o3", "Qwen", "Mistral"],
    "ai_agents": ["AI agent", "agentic", "MCP", "computer use", "tool use", "function calling",
                  "multi-agent", "autonomous agent", "workflow automation"],
    "embodied_ai_robotics": ["robot", "humanoid", "embodied", "locomotion", "manipulation",
                              "dexterous", "mobile robot", "robot learning"],
    "ai_infrastructure": ["inference", "GPU cluster", "H100", "H200", "B200", "Blackwell",
                           "Hopper", "training cluster", "vLLM", "TensorRT", "serving",
                           "CoreWeave", "Lambda", "Groq", "Cerebras"],
    "semiconductors": ["semiconductor", "chip", "TSMC", "ASML", "HBM", "CoWoS", "packaging",
                        "foundry", "gallium", "germanium", "Nvidia", "AMD", "Intel"],
    "startups_unicorns": ["startup", "unicorn", "Series A", "Series B", "seed", "funding",
                           "VC", "valuation", "IPO", "founder"],
    "papers_research": ["arXiv", "paper", "NeurIPS", "ICML", "ICLR", "CVPR", "preprint",
                          "research", "dataset", "benchmark"],
    "github_opensource": ["GitHub", "open source", "repository", "stars", "trending", "fork"],
    "macro_geopolitical": ["export control", "sanctions", "tariff", "trade war", "chip ban",
                            "AI regulation", "EU AI Act", "policy", "geopolitical"],
    "big_tech_strategy": ["earnings", "capex", "layoffs", "acquisition", "M&A", "antitrust",
                           "restructuring"],
    # --- Cross-domain / broad interest topics ---
    # general_interesting: no keywords — assigned programmatically for HN ≥300, non-tech
    "general_interesting": [],
    "science_breakthrough": ["particle physics", "quantum mechanics", "quantum physics",
                              "chemistry breakthrough", "molecule", "biology discovery",
                              "genetics", "CRISPR", "protein folding", "evolution",
                              "Nobel Prize", "scientific discovery"],
    "health_biotech": ["FDA approval", "clinical trial", "drug approval", "vaccine",
                       "cancer treatment", "genomics", "longevity", "pandemic", "outbreak",
                       "biotech", "pharmaceutical", "mRNA", "gene therapy",
                       "antibiotic resistance"],
    "global_events": ["earthquake", "hurricane", "typhoon", "flood", "volcanic eruption",
                      "natural disaster", "pandemic", "epidemic", "global crisis",
                      "UN resolution", "G7 summit", "G20 summit"],
    "astronomy_space": ["telescope", "galaxy", "black hole", "dark matter", "dark energy",
                         "exoplanet", "asteroid", "NASA", "ESA", "rocket launch",
                         "satellite orbit", "ISS", "James Webb", "JWST", "cosmology",
                         "supernova", "neutron star", "gravitational wave", "astronaut",
                         "lunar mission", "Mars mission", "SpaceX Starship"],
    "materials_science": ["superconductor", "graphene", "solid-state battery",
                           "energy storage material", "nanomaterial", "metamaterial",
                           "2D material", "perovskite", "room-temperature superconductor",
                           "topological material", "quantum material", "advanced alloy"],
}

# Core tech topics used in cross-domain logic
_CORE_TECH_TOPICS = frozenset({
    "ai_models", "ai_agents", "embodied_ai_robotics", "ai_infrastructure",
    "semiconductors", "startups_unicorns", "papers_research", "developer_tools",
    "autonomous_systems",
})
# Science/global topics that, when co-occurring with a tech topic, earn a cross-domain boost
_CROSS_DOMAIN_TOPICS = frozenset({
    "science_breakthrough", "health_biotech", "astronomy_space",
    "materials_science", "global_events",
})

COMPANY_KEYWORDS: dict[str, list[str]] = {
    "Apple": ["Apple", "AAPL", "iPhone", "Mac", "iOS", "WWDC"],
    "Microsoft": ["Microsoft", "MSFT", "Azure", "Windows", "Copilot"],
    "Google": ["Google", "Alphabet", "GOOGL", "Gemini", "DeepMind", "TPU", "Waymo"],
    "Amazon": ["Amazon", "AMZN", "AWS", "Alexa"],
    "Meta": ["Meta", "Facebook", "Llama", "WhatsApp", "Instagram", "META", "Ray-Ban"],
    "Nvidia": ["Nvidia", "NVDA", "GPU", "CUDA", "Blackwell", "Hopper", "H100", "GTC"],
    "Tesla": ["Tesla", "TSLA", "Elon Musk", "FSD", "Optimus"],
    "OpenAI": ["OpenAI", "ChatGPT", "GPT-4", "o1", "o3", "DALL-E", "Sora"],
    "Anthropic": ["Anthropic", "Claude"],
    "DeepMind": ["DeepMind", "AlphaFold", "Gemini"],
    "xAI": ["xAI", "Grok"],
    "Huawei": ["Huawei", "Kirin", "Ascend"],
    "ByteDance": ["ByteDance", "TikTok", "Doubao"],
    "Alibaba": ["Alibaba", "BABA", "Qwen", "Aliyun", "AliCloud"],
    "DeepSeek": ["DeepSeek"],
    "Figure AI": ["Figure AI", "Figure robot"],
    "Physical Intelligence": ["Physical Intelligence", "π0"],
    "Boston Dynamics": ["Boston Dynamics", "Spot", "Atlas"],
    "CoreWeave": ["CoreWeave"],
    "Groq": ["Groq"],
    "Mistral": ["Mistral"],
    "Perplexity": ["Perplexity"],
}


def _title_hash(title: str) -> str:
    clean = re.sub(r"[^a-z0-9 ]", "", title.lower())
    tokens = sorted(clean.split())
    return hashlib.md5(" ".join(tokens).encode()).hexdigest()[:12]


def _detect_topics(text: str) -> list[str]:
    text_lower = text.lower()
    matched = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(topic)
    return matched or ["general"]


def _detect_companies(text: str) -> list[str]:
    matched = []
    for company, keywords in COMPANY_KEYWORDS.items():
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


def _infer_event_type(raw: RawEvent, topics: list[str]) -> str:
    title_lower = raw.raw_title.lower()
    if raw.source_type in ("arxiv", "huggingface"):
        return "paper"
    if raw.source_type == "github":
        return "github_trending"
    if any(w in title_lower for w in ["funding", "raises", "series", "unicorn", "valuation"]):
        return "funding"
    if any(w in title_lower for w in ["layoff", "laid off", "job cuts", "restructur"]):
        return "layoffs"
    if any(w in title_lower for w in ["earnings", "revenue", "profit", "quarterly"]):
        return "earnings"
    if any(w in title_lower for w in ["launch", "release", "announce", "introduce", "unveil"]):
        return "product_launch"
    if any(w in title_lower for w in ["policy", "regulation", "ban", "sanction", "tariff", "export"]):
        return "policy"
    return "product_launch"


def _score_importance(raw: RawEvent, topics: list[str], companies: list[str]) -> float:
    score = 0.3  # baseline
    # Source type boost
    src_priority = raw.metadata.get("priority", 3)
    score += max(0.0, (5 - src_priority) * 0.1)  # priority 1 → +0.4, priority 5 → 0
    # HN social heat
    hn_score = raw.metadata.get("score", 0)
    if hn_score > 500:
        score += 0.3
    elif hn_score > 200:
        score += 0.2
    elif hn_score > 100:
        score += 0.1
    # Watchlist company
    if companies:
        score += 0.2
    # High-priority topic
    high_prio = {"ai_models", "embodied_ai_robotics", "ai_infrastructure", "semiconductors",
                  "papers_research", "startups_unicorns"}
    if any(t in high_prio for t in topics):
        score += 0.1
    # Cross-domain boost: AI/CS + science/global co-occurrence signals rare & important events
    if any(t in _CORE_TECH_TOPICS for t in topics) and any(t in _CROSS_DOMAIN_TOPICS for t in topics):
        score += 0.15
    return min(1.0, score)


def _score_reliability(raw: RawEvent) -> float:
    priority = raw.metadata.get("priority", raw.metadata.get("feed_source_type", 3))
    if isinstance(priority, int):
        mapping = {1: 0.95, 2: 0.75, 3: 0.55, 4: 0.35, 5: 0.15}
        return mapping.get(priority, 0.5)
    if raw.source_type in ("arxiv", "huggingface"):
        return 0.90
    if raw.source_type == "github":
        return 0.85
    return 0.50


def normalize_events(raw_events: list[RawEvent], run_date: str = "") -> list[NormalizedEvent]:
    seen_hashes: dict[str, NormalizedEvent] = {}
    normalized: list[NormalizedEvent] = []

    for raw in raw_events:
        combined_text = f"{raw.raw_title} {raw.raw_content}"
        topics = _detect_topics(combined_text)
        companies = _detect_companies(combined_text)

        # Hacker News high-score stories with no core-tech topic → tag as general_interesting
        # These are genuinely interesting stories that would pass HN's community filter at ≥300.
        if (raw.source_type == "hacker_news"
                and raw.metadata.get("score", 0) >= 300
                and not any(t in _CORE_TECH_TOPICS for t in topics)):
            topics = ["general_interesting"] + [t for t in topics if t != "general"]

        source_type = _infer_source_type(raw)
        event_type = _infer_event_type(raw, topics)
        importance = _score_importance(raw, topics, companies)
        reliability = _score_reliability(raw)

        th = _title_hash(raw.raw_title)

        if th in seen_hashes:
            # Merge: add source URL
            existing = seen_hashes[th]
            if raw.raw_url not in existing.source_urls:
                existing.source_urls.append(raw.raw_url)
            existing.importance_score = max(existing.importance_score, importance)
            existing.raw_event_ids.append(raw.raw_id)
            continue

        date_tag = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        published_at=datetime.now(timezone.utc).isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        metadata={"priority": 1, "feed_source_type": "company"},
    )
    results = normalize_events([dummy])
    print(json.dumps([
        {"id": e.event_id, "title": e.canonical_title, "topics": e.topics,
         "companies": e.companies, "importance": e.importance_score}
        for e in results
    ], indent=2, ensure_ascii=False))
