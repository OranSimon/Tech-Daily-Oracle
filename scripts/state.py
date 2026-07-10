"""TechDailyState blackboard — shared state object for all modules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Raw event (before normalization)
# ---------------------------------------------------------------------------

@dataclass
class RawEvent:
    source_name: str
    source_type: str          # rss | github | hacker_news | huggingface | arxiv | web_search
    raw_title: str
    raw_url: str
    raw_content: str
    published_at: str         # ISO datetime string
    fetched_at: str           # ISO datetime string
    raw_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalized event (after deduplication and scoring)
# ---------------------------------------------------------------------------

@dataclass
class NormalizedEvent:
    event_id: str
    canonical_title: str
    summary: str
    source_urls: list[str]
    primary_source_url: str
    source_type: str          # company | paper | github | social | media | filing | conference | macro | market
    published_at: str         # ISO datetime string
    companies: list[str]
    projects: list[str]
    papers: list[str]
    people: list[str]
    topics: list[str]
    geography: list[str]
    event_type: str
    importance_score: float = 0.0
    novelty_score: float = 0.0
    reliability_score: float = 0.0
    social_heat_score: float = 0.0
    raw_event_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Analysis result types
# ---------------------------------------------------------------------------

@dataclass
class TopicSummary:
    topic_id: str
    topic_label: str
    trend_status: str
    trend_change: str
    confidence: str
    signal_count: int
    key_signal_summary: str
    key_events: list[str]
    multi_signal_check: dict[str, Any]
    signal_classification: str
    classification_reasoning: str
    short_term_signals: list[str]
    medium_term_signals: list[str]
    long_term_signals: list[str]
    contradictions: list[str]
    report_worthy: bool
    report_snippet: str


@dataclass
class CompanyAnalysis:
    company: str
    category: str
    report_worthy: bool
    significance: str
    event_ids: list[str]
    summary: str
    analysis_by_category: dict[str, Any]
    confidence: str
    source_quality: str
    watchlist_action: str
    watchlist_notes: str | None


@dataclass
class PaperAnalysis:
    paper_id: str
    title: str
    authors: list[str]
    institution: str
    source: str
    categories: list[str]
    link: str
    code_available: bool
    report_worthy: bool
    signal_strength: str
    technical_contribution: str
    engineering_product_impact: str | None
    novelty_score: float
    impact_score: float
    overall_score: float
    why_notable: str
    caveats: str
    topic_tags: list[str]
    related_companies: list[str]
    related_predictions: list[str]
    hype_risk: str
    hype_risk_reason: str | None


@dataclass
class ProjectAnalysis:
    repo: str
    url: str
    tagline: str
    stars_total: int
    stars_today: int
    stars_weekly: int
    language: str
    created_days_ago: int
    last_commit_days_ago: int
    contributors: int
    license: str
    report_worthy: bool
    filter_out_reason: str | None
    scores: dict[str, int]
    what_it_does: str
    why_it_matters: str
    risk_label: str
    verdict: str
    topic_tags: list[str]
    hype_risk: str
    signals_to_monitor: list[str]


@dataclass
class SocialSignalAnalysis:
    subject: str
    subject_type: str
    trigger_condition_met: bool
    trigger_reason: str
    platforms_sampled: list[str]
    positive_points: list[str]
    negative_points: list[str]
    controversies: list[str]
    authority_opinions: list[dict[str, str]]
    community_consensus: str
    hype_risk: str
    hype_risk_reason: str
    signal_classification: str
    report_worthy: bool
    report_snippet: str


@dataclass
class MacroImpactAnalysis:
    event_id: str
    event_title: str
    event_type: str
    report_worthy: bool
    exclusion_reason: str | None
    transmission_path: str
    affected_companies: list[str]
    affected_sectors: list[str]
    affected_directions: list[str]
    time_dimension: str
    time_reasoning: str
    severity: str
    confidence: str
    prediction_impacts: list[dict[str, str]]
    report_snippet: str


# ---------------------------------------------------------------------------
# Trending types
# ---------------------------------------------------------------------------

@dataclass
class TrendingItem:
    item_id: str            # "owner/repo" | arxiv_id | "owner/model-id"
    item_type: str          # "github_repo" | "hf_paper" | "hf_model"
    source: str             # "ossinsight" | "huggingface_papers" | "huggingface_models"
    title: str
    url: str
    description: str
    period: str             # "daily" | "weekly" | "monthly"
    rank: int               # position in list (1 = top)
    velocity_score: float   # stars_increment (GH) | upvotes sum (papers) | trendingScore (models)
    language: str           # primary language (GH) or "" (papers)
    topics: list[str]       # inferred topic tags
    snapshot_date: str      # YYYY-MM-DD
    extra: dict[str, Any]   # raw API fields (authors, days_appeared, pipeline_tag, …)


@dataclass
class CrossListHit:
    """An entity that appears in both the GitHub and HuggingFace trending lists."""
    item_id: str
    match_type: str             # "exact" — same owner/name identifier
    github_item: Any            # TrendingItem | None
    hf_item: Any                # TrendingItem | None
    acceleration: str           # "accelerating" | "stable" | "decelerating" | "new"
    days_in_top_lists: int
    rank_history: list[int]     # last N days, lower = higher on list
    velocity_history: list[float]


@dataclass
class TrendingSnapshot:
    snapshot_date: str
    period: str                 # "daily" | "weekly" | "monthly"
    github_items: list[TrendingItem]
    hf_paper_items: list[TrendingItem]
    hf_model_items: list[TrendingItem]


@dataclass
class TrendingAnalysis:
    snapshot_date: str
    period: str
    top_github: list[TrendingItem]
    top_hf_papers: list[TrendingItem]
    top_hf_models: list[TrendingItem]
    cross_list_hits: list[CrossListHit]
    item_analyses: dict[str, str]   # item_id → report snippet
    report_section: str             # formatted markdown, injected into report


# ---------------------------------------------------------------------------
# Market signal types (Phase 4+)
# ---------------------------------------------------------------------------

@dataclass
class MarketSignalAnalysis:
    """Output from one MarketSignalAgent call for a single ticker."""
    ticker: str
    company: str
    date: str
    time_horizon: str
    event_context: list[str]
    conclusion: str
    conclusion_zh: str
    reasoning_zh: str
    base_case: str
    bull_case: str
    bear_case: str
    buy_observation_point: str
    sell_reduce_observation_point: str
    invalidation_condition: str
    risk_level: str        # low | medium | medium-high | high
    confidence: str        # low | medium | medium-high | high
    signals_to_monitor: list[dict[str, str]]
    source_events: list[str]
    has_price_data: bool = False   # True when Phase 5 live data was injected
    report_snippet: str = ""       # pre-formatted markdown for Section 13


# ---------------------------------------------------------------------------
# Prediction types
# ---------------------------------------------------------------------------

@dataclass
class Prediction:
    prediction_id: str
    created_date: str
    prediction: str
    topic_tags: list[str]
    companies: list[str]
    time_horizon: str
    horizon_date: str
    probability: float
    evidence: str
    resolution_criteria: str
    falsification_condition: str
    signals_to_monitor: list[dict[str, str]]
    status: str                    # open | resolved_true | resolved_false | expired
    confidence: str
    updates: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PredictionUpdate:
    prediction_id: str
    update_date: str
    evidence_summary: str
    impact: str
    probability_before: float
    probability_after: float
    reasoning: str
    source_event_ids: list[str]
    resolution: dict[str, Any]


# ---------------------------------------------------------------------------
# Report type
# ---------------------------------------------------------------------------

@dataclass
class Report:
    report_type: str              # daily | weekly | monthly
    report_date: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main blackboard
# ---------------------------------------------------------------------------


def default_github_project_analysis_status() -> dict[str, Any]:
    return {
        "reason": "source_empty",
        "source": "none",
        "candidate_count": 0,
        "analyzed_count": 0,
        "filtered_count": 0,
        "failed_count": 0,
        "failures": [],
    }


@dataclass
class TechDailyState:
    run_id: str
    run_date: str                  # YYYY-MM-DD
    time_window: str               # e.g. "last_24h"

    # Collected data
    raw_events: list[RawEvent] = field(default_factory=list)
    normalized_events: list[NormalizedEvent] = field(default_factory=list)

    # Analysis results
    topic_summaries: dict[str, TopicSummary] = field(default_factory=dict)
    company_analyses: dict[str, CompanyAnalysis] = field(default_factory=dict)
    paper_analyses: dict[str, PaperAnalysis] = field(default_factory=dict)
    github_project_analyses: dict[str, ProjectAnalysis] = field(default_factory=dict)
    github_project_analysis_status: dict[str, Any] = field(default_factory=default_github_project_analysis_status)
    social_signal_analyses: dict[str, SocialSignalAnalysis] = field(default_factory=dict)
    macro_impact_analyses: dict[str, MacroImpactAnalysis] = field(default_factory=dict)

    # Cross-reference indexes
    company_mentions: dict[str, list[str]] = field(default_factory=dict)
    project_mentions: dict[str, list[str]] = field(default_factory=dict)
    paper_mentions: dict[str, list[str]] = field(default_factory=dict)

    # Historical context (loaded at startup)
    previous_reports: list[Report] = field(default_factory=list)
    weekly_reviews: list[Report] = field(default_factory=list)
    monthly_reviews: list[Report] = field(default_factory=list)
    recent_topic_trends: list[dict] = field(default_factory=list)
    recent_company_mentions: list[dict] = field(default_factory=list)
    open_predictions: list[Prediction] = field(default_factory=list)

    # Generated this run
    prediction_updates: list[PredictionUpdate] = field(default_factory=list)
    new_predictions: list[Prediction] = field(default_factory=list)

    # Quality flags
    source_warnings: list[str] = field(default_factory=list)
    confidence_flags: list[str] = field(default_factory=list)

    # Trending analysis (daily snapshot)
    trending_analysis: Any = field(default=None)  # TrendingAnalysis | None

    # Market signal analyses (Phase 4+)
    market_signal_analyses: dict[str, MarketSignalAnalysis] = field(default_factory=dict)

    # Final output
    final_report: str = ""

    # Signal level for prediction count
    signal_level: str = "normal"   # low | normal | high

    def to_summary_dict(self) -> dict[str, Any]:
        """Return a compact summary for use in prompts."""
        return {
            "run_date": self.run_date,
            "signal_level": self.signal_level,
            "event_count": len(self.normalized_events),
            "topic_summaries": {
                k: {
                    "trend_status": v.trend_status,
                    "key_signal_summary": v.key_signal_summary,
                    "signal_classification": v.signal_classification,
                    "report_worthy": v.report_worthy,
                }
                for k, v in self.topic_summaries.items()
                if v.report_worthy
            },
            "top_events": [
                {
                    "event_id": e.event_id,
                    "title": e.canonical_title,
                    "summary": e.summary,
                    "source_type": e.source_type,
                    "importance_score": e.importance_score,
                    "companies": e.companies,
                    "topics": e.topics,
                }
                for e in sorted(
                    self.normalized_events,
                    key=lambda x: x.importance_score,
                    reverse=True,
                )[:20]
            ],
        }


def new_run_id() -> str:
    return f"run-{date.today().isoformat()}-{uuid.uuid4().hex[:6]}"
