"""Static daily pipeline composition for the CLI runner."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import daily_step_actions as actions
from pipeline_policy import DailyStepPolicy, get_daily_step_policy
from pipeline_step import PipelineStep, PipelineStepResult, log_step_summary, run_recorded_step
from pipeline_state import (
    CollectionState,
    CorpusState,
    append_confidence_flag,
    append_source_warning,
    apply_collection_state,
    apply_corpus_state,
    apply_company_analysis_result,
    apply_github_project_analysis_result,
    apply_macro_impact_analysis_result,
    apply_market_signal_analysis_result,
    apply_new_predictions_result,
    apply_paper_analysis_result,
    apply_prediction_updates_result,
    apply_report_result,
    apply_report_state,
    apply_social_signal_analysis_result,
    apply_topic_analysis_result,
    apply_trending_analysis_result,
    get_analysis_state,
    get_collection_state,
    get_corpus_state,
    get_market_signal_input_state,
    get_prediction_state,
    get_prediction_input_state,
    get_report_state,
    get_report_input_state,
)
from run_context import AppConfig, RunContext
from run_logging import RunLogger
from state import TechDailyState


@dataclass
class DailyPipelineRuntime:
    """Execution-time dependencies and transient values for the daily run."""

    state: TechDailyState
    context: RunContext
    cfg: dict[str, Any]
    app_config: AppConfig
    logger: RunLogger
    root_dir: str | None = None
    step_results: list[PipelineStepResult] = field(default_factory=list)
    market_data: dict[str, Any] | None = None
    trending_snapshot: Any = None
    trending_history: list[Any] | None = None
    report_path: str = ""


@dataclass(frozen=True)
class DailyPipelineResult:
    step_results: list[PipelineStepResult]
    report_path: str


@dataclass(frozen=True)
class DailyStepDefinition:
    policy: DailyStepPolicy
    action: Callable[[DailyPipelineRuntime], Any]
    fallback: Any = None
    record_count: Callable[[Any], int] | None = None
    failure_message: str = "failed"
    enabled_if: Callable[[DailyPipelineRuntime], bool] | None = None
    after_result: Callable[[DailyPipelineRuntime, PipelineStepResult], None] | None = None
    heading: str | None = None
    show_heading: bool = True
    show_heading_when_disabled: bool = False

    @property
    def name(self) -> str:
        return self.policy.name

    @property
    def fatal(self) -> bool:
        return self.policy.proposed_policy == "fatal"

    def enabled(self, runtime: DailyPipelineRuntime) -> bool:
        return True if self.enabled_if is None else self.enabled_if(runtime)

    def heading_text(self) -> str:
        return self.heading or self.name


def build_daily_step_definitions(runtime: DailyPipelineRuntime) -> list[DailyStepDefinition]:
    return [
        DailyStepDefinition(
            policy=get_daily_step_policy("Loading historical context"),
            action=lambda rt: actions.load_historical_context_action(rt.state),
            record_count=lambda context_values: sum(len(value) for value in context_values.values()),
            failure_message="historical context loading failed",
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Collecting sources"),
            action=lambda rt: actions.collect_sources_state_action(rt.cfg, rt.context),
            fallback=CollectionState(),
            record_count=lambda collection_state: len(collection_state.raw_events),
            failure_message="source collection failed",
            after_result=_after_collect_sources,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Collecting market data (yfinance / FRED)"),
            action=lambda rt: actions.collect_market_data_action(rt.cfg, rt.root_dir or str(rt.context.root_dir)),
            fallback=None,
            record_count=lambda data: len((data or {}).get("per_ticker", {})),
            enabled_if=lambda rt: rt.app_config.market_signal_enabled and rt.app_config.market_live_data_enabled,
            after_result=_after_collect_market_data,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Collecting trending snapshot (OSSInsight + HuggingFace)"),
            action=lambda rt: actions.collect_trending_snapshot_action(rt.context, rt.cfg),
            fallback=None,
            record_count=lambda snapshot: 1 if snapshot is not None else 0,
            failure_message="trending snapshot collection failed",
            after_result=_after_collect_trending_snapshot,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Normalizing and deduplicating events"),
            action=lambda rt: actions.normalize_collection_state_action(get_collection_state(rt.state), rt.context),
            fallback=CorpusState(),
            record_count=lambda corpus_state: len(corpus_state.normalized_events),
            failure_message="normalization failed",
            after_result=_after_normalize_sources,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing topics"),
            action=lambda rt: actions.analyze_topics_state_action(get_corpus_state(rt.state)),
            fallback={},
            record_count=len,
            failure_message="topic analysis failed",
            after_result=_after_analyze_topics,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing companies"),
            action=lambda rt: actions.analyze_companies_state_action(get_corpus_state(rt.state)),
            fallback={},
            record_count=len,
            failure_message="company analysis failed",
            after_result=_after_analyze_companies,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing papers"),
            action=lambda rt: actions.analyze_papers_state_action(get_corpus_state(rt.state)),
            fallback={},
            record_count=len,
            failure_message="paper analysis failed",
            after_result=_after_analyze_papers,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing GitHub projects"),
            action=lambda rt: actions.analyze_github_projects_state_action(get_corpus_state(rt.state)),
            fallback={},
            record_count=len,
            failure_message="github analysis failed",
            after_result=_after_analyze_github_projects,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Loading trending history"),
            action=lambda rt: actions.load_trending_history_action(),
            record_count=len,
            failure_message="trending history loading failed",
            enabled_if=lambda rt: rt.trending_snapshot is not None,
            after_result=_after_load_trending_history,
            heading="Analyzing trending items",
            show_heading_when_disabled=True,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing trending items"),
            action=lambda rt: actions.analyze_trending_action(
                rt.trending_snapshot,
                rt.trending_history or [],
                rt.app_config,
            ),
            fallback=None,
            record_count=lambda analysis: 1 if analysis is not None else 0,
            failure_message="trending analysis failed",
            enabled_if=lambda rt: rt.trending_snapshot is not None and rt.trending_history is not None,
            after_result=_after_analyze_trending,
            show_heading=False,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing social signals"),
            action=lambda rt: actions.analyze_social_signals_state_action(get_corpus_state(rt.state)),
            fallback={},
            record_count=len,
            failure_message="social analysis failed",
            after_result=_after_analyze_social_signals,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing macro/geopolitical impact"),
            action=lambda rt: actions.analyze_macro_impact_state_action(
                get_corpus_state(rt.state),
                get_prediction_state(rt.state),
            ),
            fallback={},
            record_count=len,
            failure_message="macro analysis failed",
            after_result=_after_analyze_macro_impact,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Analyzing market signals (MarketSignalAgent)"),
            action=lambda rt: actions.analyze_market_signals_input_action(
                get_market_signal_input_state(rt.state),
                market_data=rt.market_data,
                cfg=rt.cfg,
            ),
            fallback={},
            record_count=len,
            failure_message="market signal analysis failed",
            enabled_if=lambda rt: rt.app_config.market_signal_enabled,
            after_result=_after_analyze_market_signals,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Updating predictions"),
            action=lambda rt: actions.update_predictions_input_action(get_prediction_input_state(rt.state)),
            fallback=get_prediction_state(runtime.state),
            record_count=lambda prediction_state: len(prediction_state.prediction_updates),
            failure_message="prediction updates failed",
            after_result=_after_update_predictions,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Generating new predictions"),
            action=lambda rt: actions.generate_new_predictions_input_action(get_prediction_input_state(rt.state)),
            fallback=get_prediction_state(runtime.state),
            record_count=lambda prediction_state: len(prediction_state.new_predictions),
            failure_message="new predictions failed",
            after_result=_after_generate_new_predictions,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Generating daily brief report"),
            action=lambda rt: actions.generate_daily_report_input_action(get_report_input_state(rt.state)),
            fallback=get_report_state(runtime.state),
            failure_message="report generation failed",
            after_result=_after_generate_daily_report,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Saving outputs"),
            action=lambda rt: actions.save_outputs_state_action(
                rt.state,
                get_report_state(rt.state),
                get_prediction_state(rt.state),
                get_analysis_state(rt.state),
                run_date=rt.context.run_date,
                trending_snapshot=rt.trending_snapshot,
            ),
            failure_message="saving outputs failed",
            after_result=_after_save_outputs,
        ),
        DailyStepDefinition(
            policy=get_daily_step_policy("Publishing to Notion"),
            action=lambda rt: actions.publish_to_notion_action(rt.context.run_date, rt.state.final_report, rt.cfg),
            fallback=None,
            record_count=lambda notion_url: 1 if notion_url else 0,
            failure_message="notion publish failed",
            enabled_if=lambda rt: rt.app_config.notion_enabled,
            after_result=_after_publish_to_notion,
            show_heading=False,
        ),
    ]


def execute_daily_pipeline(
    runtime: DailyPipelineRuntime,
    *,
    step_printer: Callable[[str], None],
) -> DailyPipelineResult:
    for definition in build_daily_step_definitions(runtime):
        is_enabled = definition.enabled(runtime)
        if definition.show_heading and (is_enabled or definition.show_heading_when_disabled):
            step_printer(definition.heading_text())
        if not is_enabled:
            continue

        step = PipelineStep(
            name=definition.name,
            action=lambda definition=definition: definition.action(runtime),
            fatal=definition.fatal,
            fallback=definition.fallback,
            record_count=definition.record_count,
            failure_message=definition.failure_message,
        )
        try:
            result = run_recorded_step(step, runtime.logger, runtime.step_results)
        except Exception as exc:
            if definition.name == "Loading trending history":
                print(f"  [ERROR] Trending analysis failed (non-fatal): {exc}")
                runtime.trending_history = None
                continue
            raise
        if definition.after_result is not None:
            definition.after_result(runtime, result)

    log_step_summary(runtime.step_results, runtime.logger)
    return DailyPipelineResult(step_results=runtime.step_results, report_path=runtime.report_path)


def _after_collect_sources(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_collection_state(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Source collection failed: {error}")
        append_source_warning(runtime.state, f"Source collection error: {error}")
    print(f"  Collection took {result.duration_seconds:.1f}s")


def _after_collect_market_data(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    runtime.market_data = result.value
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [MarketData] Collection failed (non-fatal): {error}")


def _after_collect_trending_snapshot(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    runtime.trending_snapshot = result.value
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Trending collection failed (non-fatal): {error}")


def _after_normalize_sources(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_corpus_state(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Normalization failed: {error}")


def _after_analyze_topics(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_topic_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Topic analysis failed: {error}")
        append_confidence_flag(runtime.state, f"Topic analysis error: {error}")


def _after_analyze_companies(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_company_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Company analysis failed: {error}")
        append_confidence_flag(runtime.state, f"Company analysis error: {error}")


def _after_analyze_papers(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_paper_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Paper analysis failed: {error}")
        append_confidence_flag(runtime.state, f"Paper analysis error: {error}")


def _after_analyze_github_projects(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_github_project_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] GitHub analysis failed: {error}")
        append_confidence_flag(runtime.state, f"GitHub analysis error: {error}")


def _after_load_trending_history(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    runtime.trending_history = result.value


def _after_analyze_trending(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_trending_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Trending analysis failed (non-fatal): {error}")


def _after_analyze_social_signals(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_social_signal_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Social analysis failed: {error}")


def _after_analyze_macro_impact(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_macro_impact_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Macro analysis failed: {error}")


def _after_analyze_market_signals(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_market_signal_analysis_result(runtime.state, result.value)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [MarketSignal] Analysis failed (non-fatal): {error}")
        if result.exception is not None:
            traceback.print_exception(result.exception)


def _after_update_predictions(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_prediction_updates_result(runtime.state, result.value.prediction_updates)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] Prediction updates failed: {error}")


def _after_generate_new_predictions(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    apply_new_predictions_result(runtime.state, result.value.new_predictions)
    if not result.success:
        error = result.error or "unknown error"
        print(f"  [ERROR] New predictions failed: {error}")


def _after_generate_daily_report(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    if result.success:
        apply_report_state(runtime.state, result.value)
    else:
        error = result.error or "unknown error"
        print(f"  [ERROR] Report generation failed: {error}")
        if result.exception is not None:
            traceback.print_exception(result.exception)
        apply_report_result(
            runtime.state,
            f"# Tech Daily Brief — {runtime.context.run_date}\n\n[Report generation failed: {error}]",
        )


def _after_save_outputs(runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    runtime.report_path = result.value


def _after_publish_to_notion(_runtime: DailyPipelineRuntime, result: PipelineStepResult) -> None:
    if result.success:
        notion_url = result.value
        if notion_url:
            print(f"  [Notion] Published: {notion_url}")
    else:
        error = result.error or "unknown error"
        print(f"  [Notion] Publish failed (non-fatal): {error}")
