"""Pydantic schemas for migrated LLM JSON responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, RootModel


class TopicSummaryResponse(BaseModel):
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


class CompanyAnalysisResponse(BaseModel):
    category: str
    report_worthy: bool
    significance: str
    event_ids: list[str]
    summary: str
    analysis_by_category: dict[str, Any]
    confidence: str
    source_quality: str
    watchlist_action: str
    watchlist_notes: str | None = None


class PaperAnalysisResponse(BaseModel):
    paper_id: str | None = None
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
    engineering_product_impact: str | None = None
    novelty_score: float
    impact_score: float
    overall_score: float
    why_notable: str
    caveats: str
    topic_tags: list[str]
    related_companies: list[str]
    related_predictions: list[str]
    hype_risk: str
    hype_risk_reason: str | None = None


class GitHubProjectAnalysisResponse(BaseModel):
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
    filter_out_reason: str | None = None
    scores: dict[str, int]
    what_it_does: str
    why_it_matters: str
    risk_label: str
    verdict: str
    topic_tags: list[str]
    hype_risk: str
    signals_to_monitor: list[str]


class MacroImpactAnalysisResponse(BaseModel):
    event_id: str
    event_title: str
    event_type: str
    report_worthy: bool
    exclusion_reason: str | None = None
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


class SocialSignalAnalysisResponse(BaseModel):
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


class TrendingItemAnalysisResponse(BaseModel):
    item_id: str
    why_trending: str
    what_it_signals: str
    topics: list[str]
    hype_risk: str
    report_snippet: str


class TrendingAnalysisResponse(RootModel[list[TrendingItemAnalysisResponse]]):
    pass


class MarketSignalAnalysisResponse(BaseModel):
    date: str
    ticker: str
    company: str
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
    risk_level: str
    confidence: str
    signals_to_monitor: list[dict[str, str]]
    source_events: list[str]


class PredictionUpdateResponse(BaseModel):
    prediction_id: str
    update_date: str
    evidence_summary: str
    impact: str
    probability_before: float
    probability_after: float
    reasoning: str
    source_event_ids: list[str]
    resolution: dict[str, Any]


class PredictionUpdatesResponse(RootModel[list[PredictionUpdateResponse]]):
    pass


class NewPredictionResponse(BaseModel):
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
    confidence: str


class NewPredictionsResponse(RootModel[list[NewPredictionResponse]]):
    pass
