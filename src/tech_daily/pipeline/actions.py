"""Named daily pipeline step actions.

These helpers keep orchestration actions testable without moving business state
out of TechDailyState or changing the daily runner's public behavior.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import yaml

from tech_daily.pipeline.state import (
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
from tech_daily.runtime.run_context import AppConfig, RunContext

if TYPE_CHECKING:
    from state import TechDailyState

    from tech_daily.storage.context import StorageContext


def analyze_companies(normalized_events: list[Any]) -> dict[str, Any]:
    from analyze_companies import analyze_companies as _analyze_companies

    return _analyze_companies(normalized_events)


def analyze_github_projects(normalized_events: list[Any], trending_snapshot: Any = None) -> Any:
    from analyze_github_projects import analyze_github_projects as _analyze_github_projects

    return _analyze_github_projects(normalized_events, trending_snapshot=trending_snapshot)


def analyze_macro_impact(normalized_events: list[Any], open_predictions: list[Any]) -> dict[str, Any]:
    from analyze_macro_impact import analyze_macro_impact as _analyze_macro_impact

    return _analyze_macro_impact(normalized_events, open_predictions)


def analyze_market_signals_from_input(
    input_state: MarketSignalInputState,
    *,
    market_data: dict[str, Any] | None,
    prior_signals: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    from analyze_market_signals import analyze_market_signals_from_input as _analyze_market_signals_from_input

    return _analyze_market_signals_from_input(
        input_state,
        market_data=market_data,
        prior_signals=prior_signals,
        config=config,
    )


def analyze_papers(normalized_events: list[Any]) -> dict[str, Any]:
    from analyze_papers import analyze_papers as _analyze_papers

    return _analyze_papers(normalized_events)


def analyze_social_signals(normalized_events: list[Any]) -> dict[str, Any]:
    from analyze_social_signals import analyze_social_signals as _analyze_social_signals

    return _analyze_social_signals(normalized_events)


def analyze_topics(normalized_events: list[Any]) -> dict[str, Any]:
    from analyze_topics import analyze_topics as _analyze_topics

    return _analyze_topics(normalized_events)


def analyze_trending(trending_snapshot: Any, history: list[Any], *, top_n: int) -> Any:
    from analyze_trending import analyze_trending as _analyze_trending

    return _analyze_trending(trending_snapshot, history, top_n=top_n)


def append_events(state: TechDailyState, *, storage_context: StorageContext | None = None) -> None:
    from tech_daily.storage.event_payloads import EventStoragePayload
    from tech_daily.storage.events import append_event_payload

    append_event_payload(EventStoragePayload.from_state(state), storage_context=storage_context)


def collect_sources_with_telemetry(
    cfg: dict[str, Any],
    run_date: str,
    *,
    persist_telemetry: bool,
    run_id: str,
) -> tuple[list[Any], list[Any]]:
    from collect_sources import collect_sources_with_telemetry as _collect_sources_with_telemetry

    return _collect_sources_with_telemetry(
        cfg,
        run_date=run_date,
        persist_telemetry=persist_telemetry,
        run_id=run_id,
    )


def collect_trending_snapshot(scope: str, run_date: str, cfg: dict[str, Any]) -> Any:
    from collect_trending import collect_trending_snapshot as _collect_trending_snapshot

    return _collect_trending_snapshot(scope, run_date, cfg)


def generate_daily_report(state: TechDailyState) -> str:
    from generate_report import generate_daily_report as _generate_daily_report

    return _generate_daily_report(state)


def generate_daily_report_from_input(input_state: ReportInputState) -> str:
    from generate_report import generate_daily_report_from_input as _generate_daily_report_from_input

    return _generate_daily_report_from_input(input_state)


def generate_new_predictions(state: TechDailyState) -> list[Any]:
    from update_predictions import generate_new_predictions as _generate_new_predictions

    return _generate_new_predictions(state)


def generate_new_predictions_from_input(input_state: PredictionInputState) -> tuple[list[Any], str]:
    from update_predictions import generate_new_predictions_from_input as _generate_new_predictions_from_input

    return _generate_new_predictions_from_input(input_state)


def load_company_mentions_recent(days: int) -> list[Any]:
    from tech_daily.storage.events import load_company_mentions_recent as _load_company_mentions_recent

    return _load_company_mentions_recent(days)


def load_last_signal_per_ticker() -> dict[str, dict[str, Any]]:
    from tech_daily.storage.events import load_last_signal_per_ticker as _load_last_signal_per_ticker

    return _load_last_signal_per_ticker()


def load_open_predictions() -> list[Any]:
    from tech_daily.storage.predictions import load_open_predictions as _load_open_predictions

    return _load_open_predictions()


def load_recent_monthly_reviews(limit: int) -> list[Any]:
    from tech_daily.storage.reports import load_recent_monthly_reviews as _load_recent_monthly_reviews

    return _load_recent_monthly_reviews(limit)


def load_recent_reports(limit: int) -> list[Any]:
    from tech_daily.storage.reports import load_recent_reports as _load_recent_reports

    return _load_recent_reports(limit)


def load_recent_weekly_reviews(limit: int) -> list[Any]:
    from tech_daily.storage.reports import load_recent_weekly_reviews as _load_recent_weekly_reviews

    return _load_recent_weekly_reviews(limit)


def load_topic_trends_recent(days: int) -> list[Any]:
    from tech_daily.storage.events import load_topic_trends_recent as _load_topic_trends_recent

    return _load_topic_trends_recent(days)


def load_trending_history(*, days: int) -> list[Any]:
    from tech_daily.storage.events import load_trending_history as _load_trending_history

    return _load_trending_history(days=days)


def normalize_events(raw_events: list[Any], *, run_date: str) -> list[Any]:
    from normalize_sources import normalize_events as _normalize_events

    return _normalize_events(raw_events, run_date=run_date)


def publish_to_notion(run_date: str, final_report: str, cfg: dict[str, Any]) -> str | None:
    from publish_notion import publish_to_notion as _publish_to_notion

    return _publish_to_notion(run_date, final_report, cfg)


def run_prediction_updates(state: TechDailyState) -> list[Any]:
    from update_predictions import run_prediction_updates as _run_prediction_updates

    return _run_prediction_updates(state)


def run_prediction_updates_from_input(input_state: PredictionInputState) -> list[Any]:
    from update_predictions import run_prediction_updates_from_input as _run_prediction_updates_from_input

    return _run_prediction_updates_from_input(input_state)


def save_daily_report(run_date: str, final_report: str, *, storage_context: StorageContext | None = None) -> str:
    from tech_daily.storage.reports import save_daily_report as _save_daily_report

    return _save_daily_report(run_date, final_report, storage_context=storage_context)


def save_market_signals(run_date: str, market_signal_analyses: dict[str, Any]) -> None:
    from tech_daily.storage.events import save_market_signals as _save_market_signals

    _save_market_signals(run_date, market_signal_analyses)


def save_predictions(
    new_predictions: list[Any],
    prediction_updates: list[Any],
    *,
    storage_context: StorageContext | None = None,
) -> None:
    from tech_daily.storage.predictions import save_predictions as _save_predictions

    _save_predictions(new_predictions, prediction_updates, storage_context=storage_context)


def save_trending_snapshot(trending_snapshot: Any) -> None:
    from tech_daily.storage.events import save_trending_snapshot as _save_trending_snapshot

    _save_trending_snapshot(trending_snapshot)


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


def analyze_github_projects_state_action(corpus_state: CorpusState, trending_snapshot: Any = None) -> Any:
    return analyze_github_projects(corpus_state.normalized_events, trending_snapshot)


def analyze_github_projects_action(state: TechDailyState) -> Any:
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
    analyze_func = analyze_market_signals_func or analyze_market_signals_from_input
    prior_signals = load_last_signal_per_ticker()
    return analyze_func(
        input_state,
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
    return PredictionState(
        open_predictions=input_state.prediction.open_predictions,
        prediction_updates=run_prediction_updates_from_input(input_state),
        new_predictions=input_state.prediction.new_predictions,
        signal_level=input_state.prediction.signal_level,
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
    new_predictions, signal_level = generate_new_predictions_from_input(input_state)
    return PredictionState(
        open_predictions=input_state.prediction.open_predictions,
        prediction_updates=input_state.prediction.prediction_updates,
        new_predictions=new_predictions,
        signal_level=signal_level,
    )


def generate_daily_report_action(state: TechDailyState) -> str:
    return generate_daily_report(state)


def generate_daily_report_state_action(state: TechDailyState) -> ReportState:
    return generate_daily_report_input_action(get_report_input_state(state))


def generate_daily_report_input_action(input_state: ReportInputState) -> ReportState:
    report = generate_daily_report_from_input(input_state)
    return ReportState(final_report=report)


def save_outputs_state_action(
    state: TechDailyState,
    report_state: ReportState,
    prediction_state: PredictionState,
    analysis_state: AnalysisState,
    *,
    run_date: str,
    trending_snapshot: Any,
    storage_context: StorageContext | None = None,
) -> str:
    apply_report_state(state, report_state)
    apply_prediction_state(state, prediction_state)
    apply_analysis_state(state, analysis_state)
    return save_outputs_action(
        state,
        run_date=run_date,
        trending_snapshot=trending_snapshot,
        storage_context=storage_context,
    )


def save_outputs_action(
    state: TechDailyState,
    *,
    run_date: str,
    trending_snapshot: Any,
    storage_context: StorageContext | None = None,
) -> str:
    saved_report_path = save_daily_report(run_date, state.final_report, storage_context=storage_context)
    save_predictions(state.new_predictions, state.prediction_updates, storage_context=storage_context)
    append_events(state, storage_context=storage_context)
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


__all__ = [
    "analyze_companies_action",
    "analyze_companies_state_action",
    "analyze_github_projects_action",
    "analyze_github_projects_state_action",
    "analyze_macro_impact_action",
    "analyze_macro_impact_state_action",
    "analyze_market_signals_action",
    "analyze_market_signals_input_action",
    "analyze_papers_action",
    "analyze_papers_state_action",
    "analyze_social_signals_action",
    "analyze_social_signals_state_action",
    "analyze_topics_action",
    "analyze_topics_state_action",
    "analyze_trending_action",
    "collect_market_data_action",
    "collect_sources_action",
    "collect_sources_state_action",
    "collect_trending_snapshot_action",
    "generate_daily_report_action",
    "generate_daily_report_input_action",
    "generate_daily_report_state_action",
    "generate_new_predictions_action",
    "generate_new_predictions_input_action",
    "generate_new_predictions_state_action",
    "load_historical_context_action",
    "load_trending_history_action",
    "normalize_collection_state_action",
    "normalize_sources_action",
    "publish_to_notion_action",
    "save_outputs_action",
    "save_outputs_state_action",
    "update_predictions_action",
    "update_predictions_input_action",
    "update_predictions_state_action",
]
