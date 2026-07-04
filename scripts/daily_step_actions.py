"""Named daily pipeline step actions.

These helpers keep orchestration actions testable without moving business state
out of TechDailyState or changing the daily runner's public behavior.
"""

from __future__ import annotations

import os
from typing import Any

import yaml

from analyze_companies import analyze_companies
from analyze_github_projects import analyze_github_projects
from analyze_macro_impact import analyze_macro_impact
from analyze_papers import analyze_papers
from analyze_social_signals import analyze_social_signals
from analyze_topics import analyze_topics
from analyze_trending import analyze_trending
from collect_sources import collect_sources_with_telemetry
from collect_trending import collect_trending_snapshot
from generate_report import generate_daily_report
from normalize_sources import normalize_events
from pipeline_state import (
    AnalysisState,
    CollectionState,
    CorpusState,
    MarketSignalInputState,
    PredictionInputState,
    PredictionState,
    ReportInputState,
    ReportState,
    apply_analysis_state,
    apply_historical_context_result,
    apply_prediction_state,
    apply_report_state,
    get_collection_state,
    get_corpus_state,
    get_market_signal_input_state,
    get_prediction_input_state,
    get_report_input_state,
)
from publish_notion import publish_to_notion
from run_context import AppConfig, RunContext
from state import TechDailyState
from storage import (
    append_events,
    load_company_mentions_recent,
    load_last_signal_per_ticker,
    load_open_predictions,
    load_recent_monthly_reviews,
    load_recent_reports,
    load_recent_weekly_reviews,
    load_topic_trends_recent,
    load_trending_history,
    save_daily_report,
    save_market_signals,
    save_predictions,
    save_trending_snapshot,
)
from update_predictions import generate_new_predictions, run_prediction_updates


def load_historical_context_action(state: TechDailyState) -> dict[str, Any]:
    historical_context = {
        "previous_reports": load_recent_reports(7),
        "weekly_reviews": load_recent_weekly_reviews(4),
        "monthly_reviews": load_recent_monthly_reviews(3),
        "recent_topic_trends": load_topic_trends_recent(30),
        "recent_company_mentions": load_company_mentions_recent(90),
        "open_predictions": load_open_predictions(),
    }
    apply_historical_context_result(state, historical_context)
    print(
        f"  Loaded {len(state.previous_reports)} daily, "
        f"{len(state.weekly_reviews)} weekly, "
        f"{len(state.monthly_reviews)} monthly reports; "
        f"{len(state.open_predictions)} open predictions"
    )
    return historical_context


def collect_sources_state_action(cfg: dict[str, Any], context: RunContext) -> CollectionState:
    raw_events = collect_sources_with_telemetry(
        cfg,
        run_date=context.run_date,
        persist_telemetry=True,
        run_id=context.run_id,
    )[0]
    return CollectionState(raw_events=raw_events)


def collect_sources_action(cfg: dict[str, Any], context: RunContext) -> list[Any]:
    return collect_sources_state_action(cfg, context).raw_events


def collect_market_data_action(cfg: dict[str, Any], root_dir: str) -> dict[str, Any]:
    watchlist_file = cfg.get("market_signal", {}).get("watchlist_file", "sources/market_watchlist.yml")
    with open(os.path.join(root_dir, watchlist_file)) as watchlist_handle:
        watchlist = yaml.safe_load(watchlist_handle)
    tickers = [ticker_config["ticker"] for ticker_config in watchlist.get("tickers", [])]
    from collect_market_data import collect_market_data

    return collect_market_data(tickers, cfg)


def collect_trending_snapshot_action(context: RunContext, cfg: dict[str, Any]) -> Any:
    return collect_trending_snapshot("daily", context.run_date, cfg)


def normalize_collection_state_action(collection_state: CollectionState, context: RunContext) -> CorpusState:
    return CorpusState(
        normalized_events=normalize_events(collection_state.raw_events, run_date=context.run_date),
    )


def normalize_sources_action(state: TechDailyState, context: RunContext) -> list[Any]:
    return normalize_collection_state_action(get_collection_state(state), context).normalized_events


def analyze_topics_state_action(corpus_state: CorpusState) -> dict[str, Any]:
    return analyze_topics(corpus_state.normalized_events)


def analyze_topics_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_topics_state_action(get_corpus_state(state))


def analyze_companies_state_action(corpus_state: CorpusState) -> dict[str, Any]:
    return analyze_companies(corpus_state.normalized_events)


def analyze_companies_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_companies_state_action(get_corpus_state(state))


def analyze_papers_state_action(corpus_state: CorpusState) -> dict[str, Any]:
    return analyze_papers(corpus_state.normalized_events)


def analyze_papers_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_papers_state_action(get_corpus_state(state))


def analyze_github_projects_state_action(corpus_state: CorpusState) -> dict[str, Any]:
    return analyze_github_projects(corpus_state.normalized_events)


def analyze_github_projects_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_github_projects_state_action(get_corpus_state(state))


def load_trending_history_action() -> list[Any]:
    return load_trending_history(days=30)


def analyze_trending_action(trending_snapshot: Any, history: list[Any], app_config: AppConfig) -> Any:
    return analyze_trending(trending_snapshot, history, top_n=app_config.trending_top_n)


def analyze_social_signals_state_action(corpus_state: CorpusState) -> dict[str, Any]:
    return analyze_social_signals(corpus_state.normalized_events)


def analyze_social_signals_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_social_signals_state_action(get_corpus_state(state))


def analyze_macro_impact_state_action(
    corpus_state: CorpusState,
    prediction_state: PredictionState,
) -> dict[str, Any]:
    return analyze_macro_impact(corpus_state.normalized_events, prediction_state.open_predictions)


def analyze_macro_impact_action(state: TechDailyState) -> dict[str, Any]:
    return analyze_macro_impact_state_action(get_corpus_state(state), PredictionState.from_tech_daily_state(state))


def analyze_market_signals_action(
    *,
    state: TechDailyState,
    market_data: dict[str, Any] | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    return analyze_market_signals_input_action(
        get_market_signal_input_state(state),
        market_data=market_data,
        cfg=cfg,
    )


def analyze_market_signals_input_action(
    input_state: MarketSignalInputState,
    *,
    market_data: dict[str, Any] | None,
    cfg: dict[str, Any],
    analyze_market_signals_func: Any | None = None,
) -> dict[str, Any]:
    from analyze_market_signals import analyze_market_signals

    analyze_func = analyze_market_signals_func or analyze_market_signals
    prior_signals = load_last_signal_per_ticker()
    return analyze_func(
        state=input_state.to_tech_daily_state(),
        market_data=market_data,
        prior_signals=prior_signals,
        config=cfg,
    )


def update_predictions_action(state: TechDailyState) -> list[Any]:
    return run_prediction_updates(state)


def update_predictions_state_action(
    state: TechDailyState,
    prediction_state: PredictionState,
) -> PredictionState:
    input_state = get_prediction_input_state(state)
    input_state.prediction.open_predictions = prediction_state.open_predictions
    input_state.prediction.prediction_updates = prediction_state.prediction_updates
    input_state.prediction.new_predictions = prediction_state.new_predictions
    input_state.prediction.signal_level = prediction_state.signal_level
    return update_predictions_input_action(input_state)


def update_predictions_input_action(input_state: PredictionInputState) -> PredictionState:
    compatibility_state = input_state.to_tech_daily_state()
    return PredictionState(
        open_predictions=input_state.prediction.open_predictions,
        prediction_updates=run_prediction_updates(compatibility_state),
        new_predictions=input_state.prediction.new_predictions,
        signal_level=compatibility_state.signal_level,
    )


def generate_new_predictions_action(state: TechDailyState) -> list[Any]:
    return generate_new_predictions(state)


def generate_new_predictions_state_action(
    state: TechDailyState,
    prediction_state: PredictionState,
) -> PredictionState:
    input_state = get_prediction_input_state(state)
    input_state.prediction.open_predictions = prediction_state.open_predictions
    input_state.prediction.prediction_updates = prediction_state.prediction_updates
    input_state.prediction.new_predictions = prediction_state.new_predictions
    input_state.prediction.signal_level = prediction_state.signal_level
    return generate_new_predictions_input_action(input_state)


def generate_new_predictions_input_action(input_state: PredictionInputState) -> PredictionState:
    compatibility_state = input_state.to_tech_daily_state()
    return PredictionState(
        open_predictions=input_state.prediction.open_predictions,
        prediction_updates=input_state.prediction.prediction_updates,
        new_predictions=generate_new_predictions(compatibility_state),
        signal_level=compatibility_state.signal_level,
    )


def generate_daily_report_action(state: TechDailyState) -> str:
    return generate_daily_report(state)


def generate_daily_report_state_action(state: TechDailyState) -> ReportState:
    return generate_daily_report_input_action(get_report_input_state(state))


def generate_daily_report_input_action(input_state: ReportInputState) -> ReportState:
    compatibility_state = input_state.to_tech_daily_state()
    report = generate_daily_report(compatibility_state)
    compatibility_state.final_report = report
    return ReportState(final_report=report)


def save_outputs_state_action(
    state: TechDailyState,
    report_state: ReportState,
    prediction_state: PredictionState,
    analysis_state: AnalysisState,
    *,
    run_date: str,
    trending_snapshot: Any,
) -> str:
    apply_report_state(state, report_state)
    apply_prediction_state(state, prediction_state)
    apply_analysis_state(state, analysis_state)
    return save_outputs_action(state, run_date=run_date, trending_snapshot=trending_snapshot)


def save_outputs_action(
    state: TechDailyState,
    *,
    run_date: str,
    trending_snapshot: Any,
) -> str:
    saved_report_path = save_daily_report(run_date, state.final_report)
    save_predictions(state.new_predictions, state.prediction_updates)
    append_events(state)
    if trending_snapshot is not None:
        try:
            save_trending_snapshot(trending_snapshot)
        except Exception as exc:
            print(f"  [Storage] Trending snapshot save failed (non-fatal): {exc}")
    if state.market_signal_analyses:
        try:
            save_market_signals(run_date, state.market_signal_analyses)
        except Exception as exc:
            print(f"  [Storage] Market signals save failed (non-fatal): {exc}")
    return saved_report_path


def publish_to_notion_action(run_date: str, final_report: str, cfg: dict[str, Any]) -> str | None:
    return publish_to_notion(run_date, final_report, cfg)
