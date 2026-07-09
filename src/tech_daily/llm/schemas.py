"""Pydantic schemas for migrated LLM JSON responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

__all__ = [
    "MarketSignalConfidence",
    "NewPredictionConfidence",
    "RiskLevel",
    "PredictionImpact",
    "TopicSummaryResponse",
    "CompanyAnalysisResponse",
    "PaperAnalysisResponse",
    "GitHubProjectAnalysisResponse",
    "MacroImpactAnalysisResponse",
    "SocialSignalAnalysisResponse",
    "TrendingItemAnalysisResponse",
    "TrendingAnalysisResponse",
    "MarketSignalAnalysisResponse",
    "PredictionUpdateResponse",
    "PredictionUpdatesResponse",
    "NewPredictionResponse",
    "NewPredictionsResponse",
]

MarketSignalConfidence = Literal["low", "medium", "medium-high", "high"]
NewPredictionConfidence = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "medium-high", "high"]
PredictionImpact = Literal[
    "strengthens",
    "weakens",
    "neutral",
    "contradicts",
    "resolves_true",
    "resolves_false",
    "needs_more_data",
]


def _normalize_probability(value: Any) -> Any:
    """Accept either 0.55 or 55.0 from LLM JSON, then validate as 0.0-1.0."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith("%"):
            stripped = stripped[:-1].strip()
        try:
            value = float(stripped)
        except ValueError:
            return value
    if isinstance(value, int | float) and value >= 10 and value <= 100:
        return value / 100
    return value


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

    @field_validator("technical_contribution", mode="before")
    @classmethod
    def default_technical_contribution(cls, value: Any) -> str:
        if value is None or value == "":
            return "Unspecified technical contribution."
        return str(value)


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

    @field_validator("stars_today", "stars_weekly", mode="before")
    @classmethod
    def default_missing_star_velocity(cls, value: Any) -> int:
        if value is None or value == "":
            return 0
        return int(value)

    @field_validator("language", mode="before")
    @classmethod
    def default_missing_language(cls, value: Any) -> str:
        if value is None or value == "":
            return "Unknown"
        return str(value)


class MacroImpactAnalysisResponse(BaseModel):
    event_id: str
    event_title: str = ""
    event_type: str = ""
    report_worthy: bool
    exclusion_reason: str | None = None
    transmission_path: str = ""
    affected_companies: list[str] = Field(default_factory=list)
    affected_sectors: list[str] = Field(default_factory=list)
    affected_directions: list[str] = Field(default_factory=list)
    time_dimension: str = ""
    time_reasoning: str = ""
    severity: str = ""
    confidence: str = ""
    prediction_impacts: list[dict[str, str]] = Field(default_factory=list)
    report_snippet: str = ""

    @model_validator(mode="after")
    def require_analysis_fields_when_report_worthy(self) -> MacroImpactAnalysisResponse:
        if not self.report_worthy:
            return self
        missing = [
            field_name
            for field_name in (
                "event_title",
                "event_type",
                "transmission_path",
                "time_dimension",
                "time_reasoning",
                "severity",
                "confidence",
                "report_snippet",
            )
            if not getattr(self, field_name)
        ]
        if missing:
            raise ValueError(f"report_worthy macro analysis missing fields: {', '.join(missing)}")
        return self


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
    risk_level: RiskLevel
    confidence: MarketSignalConfidence
    signals_to_monitor: list[dict[str, str]]
    source_events: list[str]


class PredictionUpdateResponse(BaseModel):
    prediction_id: str
    update_date: str
    evidence_summary: str
    impact: PredictionImpact
    probability_before: float = Field(ge=0.0, le=1.0)
    probability_after: float = Field(ge=0.0, le=1.0)
    reasoning: str
    source_event_ids: list[str]
    resolution: dict[str, Any] = Field(
        default_factory=lambda: {
            "resolved": False,
            "resolved_as": None,
            "resolution_reasoning": None,
        }
    )

    @field_validator("probability_before", "probability_after", mode="before")
    @classmethod
    def normalize_update_probability(cls, value: Any) -> Any:
        return _normalize_probability(value)


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
    probability: float = Field(ge=0.0, le=1.0)
    evidence: str
    resolution_criteria: str
    falsification_condition: str
    signals_to_monitor: list[dict[str, str]]
    confidence: NewPredictionConfidence

    @field_validator("probability", mode="before")
    @classmethod
    def normalize_prediction_probability(cls, value: Any) -> Any:
        return _normalize_probability(value)


class NewPredictionsResponse(RootModel[list[NewPredictionResponse]]):
    pass
