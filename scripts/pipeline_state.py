"""Typed compatibility state slices for the daily pipeline.

Phase 5 keeps TechDailyState as the public compatibility shell. These dataclasses
group related fields so orchestration can move toward clearer boundaries without
changing report, storage, or CLI behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from state import (
    CompanyAnalysis,
    MacroImpactAnalysis,
    MarketSignalAnalysis,
    NormalizedEvent,
    PaperAnalysis,
    Prediction,
    PredictionUpdate,
    ProjectAnalysis,
    RawEvent,
    Report,
    SocialSignalAnalysis,
    TechDailyState,
    TopicSummary,
)


@dataclass
class RunMetadataState:
    run_id: str
    run_date: str
    time_window: str
    signal_level: str = "normal"

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> RunMetadataState:
        return cls(
            run_id=state.run_id,
            run_date=state.run_date,
            time_window=state.time_window,
            signal_level=state.signal_level,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.run_id = self.run_id
        state.run_date = self.run_date
        state.time_window = self.time_window
        state.signal_level = self.signal_level


@dataclass
class CollectionState:
    raw_events: list[RawEvent] = field(default_factory=list)
    source_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> CollectionState:
        return cls(
            raw_events=state.raw_events,
            source_warnings=state.source_warnings,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.raw_events = self.raw_events
        state.source_warnings = self.source_warnings


@dataclass
class CorpusState:
    normalized_events: list[NormalizedEvent] = field(default_factory=list)
    company_mentions: dict[str, list[str]] = field(default_factory=dict)
    project_mentions: dict[str, list[str]] = field(default_factory=dict)
    paper_mentions: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> CorpusState:
        return cls(
            normalized_events=state.normalized_events,
            company_mentions=state.company_mentions,
            project_mentions=state.project_mentions,
            paper_mentions=state.paper_mentions,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.normalized_events = self.normalized_events
        state.company_mentions = self.company_mentions
        state.project_mentions = self.project_mentions
        state.paper_mentions = self.paper_mentions


def get_collection_state(state: TechDailyState) -> CollectionState:
    return CollectionState.from_tech_daily_state(state)


def apply_collection_state(state: TechDailyState, collection_state: CollectionState) -> None:
    collection_state.apply_to_tech_daily_state(state)


def get_corpus_state(state: TechDailyState) -> CorpusState:
    return CorpusState.from_tech_daily_state(state)


def apply_corpus_state(state: TechDailyState, corpus_state: CorpusState) -> None:
    corpus_state.apply_to_tech_daily_state(state)


def set_raw_events(collection_state: CollectionState, raw_events: list[RawEvent]) -> CollectionState:
    return CollectionState(
        raw_events=raw_events,
        source_warnings=collection_state.source_warnings,
    )


def set_source_warnings(collection_state: CollectionState, source_warnings: list[str]) -> CollectionState:
    return CollectionState(
        raw_events=collection_state.raw_events,
        source_warnings=source_warnings,
    )


def set_normalized_events(corpus_state: CorpusState, normalized_events: list[NormalizedEvent]) -> CorpusState:
    return CorpusState(
        normalized_events=normalized_events,
        company_mentions=corpus_state.company_mentions,
        project_mentions=corpus_state.project_mentions,
        paper_mentions=corpus_state.paper_mentions,
    )


def set_mention_indexes(
    corpus_state: CorpusState,
    *,
    company_mentions: dict[str, list[str]],
    project_mentions: dict[str, list[str]],
    paper_mentions: dict[str, list[str]],
) -> CorpusState:
    return CorpusState(
        normalized_events=corpus_state.normalized_events,
        company_mentions=company_mentions,
        project_mentions=project_mentions,
        paper_mentions=paper_mentions,
    )


@dataclass
class HistoricalContextState:
    previous_reports: list[Report] = field(default_factory=list)
    weekly_reviews: list[Report] = field(default_factory=list)
    monthly_reviews: list[Report] = field(default_factory=list)
    recent_topic_trends: list[dict[str, Any]] = field(default_factory=list)
    recent_company_mentions: list[dict[str, Any]] = field(default_factory=list)
    open_predictions: list[Prediction] = field(default_factory=list)

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> HistoricalContextState:
        return cls(
            previous_reports=state.previous_reports,
            weekly_reviews=state.weekly_reviews,
            monthly_reviews=state.monthly_reviews,
            recent_topic_trends=state.recent_topic_trends,
            recent_company_mentions=state.recent_company_mentions,
            open_predictions=state.open_predictions,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.previous_reports = self.previous_reports
        state.weekly_reviews = self.weekly_reviews
        state.monthly_reviews = self.monthly_reviews
        state.recent_topic_trends = self.recent_topic_trends
        state.recent_company_mentions = self.recent_company_mentions
        state.open_predictions = self.open_predictions


@dataclass
class AnalysisState:
    topic_summaries: dict[str, TopicSummary] = field(default_factory=dict)
    company_analyses: dict[str, CompanyAnalysis] = field(default_factory=dict)
    paper_analyses: dict[str, PaperAnalysis] = field(default_factory=dict)
    github_project_analyses: dict[str, ProjectAnalysis] = field(default_factory=dict)
    social_signal_analyses: dict[str, SocialSignalAnalysis] = field(default_factory=dict)
    macro_impact_analyses: dict[str, MacroImpactAnalysis] = field(default_factory=dict)
    trending_analysis: Any = None
    market_signal_analyses: dict[str, MarketSignalAnalysis] = field(default_factory=dict)

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> AnalysisState:
        return cls(
            topic_summaries=state.topic_summaries,
            company_analyses=state.company_analyses,
            paper_analyses=state.paper_analyses,
            github_project_analyses=state.github_project_analyses,
            social_signal_analyses=state.social_signal_analyses,
            macro_impact_analyses=state.macro_impact_analyses,
            trending_analysis=state.trending_analysis,
            market_signal_analyses=state.market_signal_analyses,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.topic_summaries = self.topic_summaries
        state.company_analyses = self.company_analyses
        state.paper_analyses = self.paper_analyses
        state.github_project_analyses = self.github_project_analyses
        state.social_signal_analyses = self.social_signal_analyses
        state.macro_impact_analyses = self.macro_impact_analyses
        state.trending_analysis = self.trending_analysis
        state.market_signal_analyses = self.market_signal_analyses


def get_analysis_state(state: TechDailyState) -> AnalysisState:
    return AnalysisState.from_tech_daily_state(state)


def apply_analysis_state(state: TechDailyState, analysis_state: AnalysisState) -> None:
    analysis_state.apply_to_tech_daily_state(state)


@dataclass
class PredictionState:
    open_predictions: list[Prediction] = field(default_factory=list)
    prediction_updates: list[PredictionUpdate] = field(default_factory=list)
    new_predictions: list[Prediction] = field(default_factory=list)
    signal_level: str = "normal"

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> PredictionState:
        return cls(
            open_predictions=state.open_predictions,
            prediction_updates=state.prediction_updates,
            new_predictions=state.new_predictions,
            signal_level=state.signal_level,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.open_predictions = self.open_predictions
        state.prediction_updates = self.prediction_updates
        state.new_predictions = self.new_predictions
        state.signal_level = self.signal_level


def get_prediction_state(state: TechDailyState) -> PredictionState:
    return PredictionState.from_tech_daily_state(state)


def apply_prediction_state(state: TechDailyState, prediction_state: PredictionState) -> None:
    prediction_state.apply_to_tech_daily_state(state)


@dataclass
class ReportState:
    final_report: str = ""

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> ReportState:
        return cls(final_report=state.final_report)

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.final_report = self.final_report


def get_report_state(state: TechDailyState) -> ReportState:
    return ReportState.from_tech_daily_state(state)


def apply_report_state(state: TechDailyState, report_state: ReportState) -> None:
    report_state.apply_to_tech_daily_state(state)


@dataclass
class DiagnosticsState:
    source_warnings: list[str] = field(default_factory=list)
    confidence_flags: list[str] = field(default_factory=list)

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> DiagnosticsState:
        return cls(
            source_warnings=state.source_warnings,
            confidence_flags=state.confidence_flags,
        )

    def apply_to_tech_daily_state(self, state: TechDailyState) -> None:
        state.source_warnings = self.source_warnings
        state.confidence_flags = self.confidence_flags


def get_diagnostics_state(state: TechDailyState) -> DiagnosticsState:
    return DiagnosticsState.from_tech_daily_state(state)


def apply_diagnostics_state(state: TechDailyState, diagnostics_state: DiagnosticsState) -> None:
    diagnostics_state.apply_to_tech_daily_state(state)


def _new_compatibility_state(run_metadata: RunMetadataState) -> TechDailyState:
    state = TechDailyState(
        run_id=run_metadata.run_id,
        run_date=run_metadata.run_date,
        time_window=run_metadata.time_window,
    )
    state.signal_level = run_metadata.signal_level
    return state


@dataclass
class MarketSignalInputState:
    run_metadata: RunMetadataState
    corpus: CorpusState
    analysis: AnalysisState

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> MarketSignalInputState:
        return cls(
            run_metadata=RunMetadataState.from_tech_daily_state(state),
            corpus=CorpusState.from_tech_daily_state(state),
            analysis=AnalysisState.from_tech_daily_state(state),
        )

    def to_tech_daily_state(self) -> TechDailyState:
        state = _new_compatibility_state(self.run_metadata)
        self.corpus.apply_to_tech_daily_state(state)
        self.analysis.apply_to_tech_daily_state(state)
        return state


def get_market_signal_input_state(state: TechDailyState) -> MarketSignalInputState:
    return MarketSignalInputState.from_tech_daily_state(state)


@dataclass
class PredictionInputState:
    run_metadata: RunMetadataState
    corpus: CorpusState
    analysis: AnalysisState
    prediction: PredictionState

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> PredictionInputState:
        return cls(
            run_metadata=RunMetadataState.from_tech_daily_state(state),
            corpus=CorpusState.from_tech_daily_state(state),
            analysis=AnalysisState.from_tech_daily_state(state),
            prediction=PredictionState.from_tech_daily_state(state),
        )

    def to_tech_daily_state(self) -> TechDailyState:
        state = _new_compatibility_state(self.run_metadata)
        self.corpus.apply_to_tech_daily_state(state)
        self.analysis.apply_to_tech_daily_state(state)
        self.prediction.apply_to_tech_daily_state(state)
        return state


def get_prediction_input_state(state: TechDailyState) -> PredictionInputState:
    return PredictionInputState.from_tech_daily_state(state)


@dataclass
class ReportInputState:
    run_metadata: RunMetadataState
    corpus: CorpusState
    historical_context: HistoricalContextState
    analysis: AnalysisState
    prediction: PredictionState
    diagnostics: DiagnosticsState

    @classmethod
    def from_tech_daily_state(cls, state: TechDailyState) -> ReportInputState:
        return cls(
            run_metadata=RunMetadataState.from_tech_daily_state(state),
            corpus=CorpusState.from_tech_daily_state(state),
            historical_context=HistoricalContextState.from_tech_daily_state(state),
            analysis=AnalysisState.from_tech_daily_state(state),
            prediction=PredictionState.from_tech_daily_state(state),
            diagnostics=DiagnosticsState.from_tech_daily_state(state),
        )

    def to_tech_daily_state(self) -> TechDailyState:
        state = _new_compatibility_state(self.run_metadata)
        self.corpus.apply_to_tech_daily_state(state)
        self.historical_context.apply_to_tech_daily_state(state)
        self.analysis.apply_to_tech_daily_state(state)
        self.prediction.apply_to_tech_daily_state(state)
        self.diagnostics.apply_to_tech_daily_state(state)
        return state


def get_report_input_state(state: TechDailyState) -> ReportInputState:
    return ReportInputState.from_tech_daily_state(state)


def apply_historical_context_result(
    state: TechDailyState,
    context_values: dict[str, Any],
) -> HistoricalContextState:
    historical_state = HistoricalContextState(
        previous_reports=context_values["previous_reports"],
        weekly_reviews=context_values["weekly_reviews"],
        monthly_reviews=context_values["monthly_reviews"],
        recent_topic_trends=context_values["recent_topic_trends"],
        recent_company_mentions=context_values["recent_company_mentions"],
        open_predictions=context_values["open_predictions"],
    )
    historical_state.apply_to_tech_daily_state(state)
    return historical_state


def apply_collection_result(
    state: TechDailyState,
    raw_events: list[RawEvent],
    *,
    source_warnings: list[str] | None = None,
) -> CollectionState:
    collection_state = set_raw_events(get_collection_state(state), raw_events)
    if source_warnings is not None:
        collection_state = set_source_warnings(collection_state, source_warnings)
    apply_collection_state(state, collection_state)
    return collection_state


def append_source_warning(state: TechDailyState, warning: str) -> DiagnosticsState:
    diagnostics_state = DiagnosticsState.from_tech_daily_state(state)
    diagnostics_state.source_warnings.append(warning)
    diagnostics_state.apply_to_tech_daily_state(state)
    return diagnostics_state


def append_confidence_flag(state: TechDailyState, flag: str) -> DiagnosticsState:
    diagnostics_state = DiagnosticsState.from_tech_daily_state(state)
    diagnostics_state.confidence_flags.append(flag)
    diagnostics_state.apply_to_tech_daily_state(state)
    return diagnostics_state


def apply_corpus_result(
    state: TechDailyState,
    normalized_events: list[NormalizedEvent],
) -> CorpusState:
    corpus_state = set_normalized_events(get_corpus_state(state), normalized_events)
    apply_corpus_state(state, corpus_state)
    return corpus_state


def apply_topic_analysis_result(state: TechDailyState, result: dict[str, TopicSummary]) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.topic_summaries = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_company_analysis_result(state: TechDailyState, result: dict[str, CompanyAnalysis]) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.company_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_paper_analysis_result(state: TechDailyState, result: dict[str, PaperAnalysis]) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.paper_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_github_project_analysis_result(state: TechDailyState, result: dict[str, ProjectAnalysis]) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.github_project_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_trending_analysis_result(state: TechDailyState, result: Any) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.trending_analysis = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_social_signal_analysis_result(
    state: TechDailyState,
    result: dict[str, SocialSignalAnalysis],
) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.social_signal_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_macro_impact_analysis_result(
    state: TechDailyState,
    result: dict[str, MacroImpactAnalysis],
) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.macro_impact_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_market_signal_analysis_result(
    state: TechDailyState,
    result: dict[str, MarketSignalAnalysis],
) -> AnalysisState:
    analysis_state = AnalysisState.from_tech_daily_state(state)
    analysis_state.market_signal_analyses = result
    analysis_state.apply_to_tech_daily_state(state)
    return analysis_state


def apply_prediction_updates_result(
    state: TechDailyState,
    result: list[PredictionUpdate],
) -> PredictionState:
    prediction_state = PredictionState.from_tech_daily_state(state)
    prediction_state.prediction_updates = result
    prediction_state.apply_to_tech_daily_state(state)
    return prediction_state


def apply_new_predictions_result(
    state: TechDailyState,
    result: list[Prediction],
) -> PredictionState:
    prediction_state = PredictionState.from_tech_daily_state(state)
    prediction_state.new_predictions = result
    prediction_state.apply_to_tech_daily_state(state)
    return prediction_state


def apply_report_result(state: TechDailyState, report: str) -> ReportState:
    report_state = ReportState(final_report=report)
    report_state.apply_to_tech_daily_state(state)
    return report_state
