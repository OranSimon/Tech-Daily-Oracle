from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from state import NormalizedEvent, RawEvent, TechDailyState


def _raw_event() -> RawEvent:
    return RawEvent(
        source_name="Fixture",
        source_type="rss",
        raw_title="Fixture raw event",
        raw_url="https://example.com/raw",
        raw_content="Fixture content",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
    )


def _normalized_event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="event-fixture",
        canonical_title="Fixture normalized event",
        summary="Fixture summary",
        source_urls=["https://example.com/raw"],
        primary_source_url="https://example.com/raw",
        source_type="company",
        published_at="2026-07-02T00:00:00+00:00",
        companies=["OpenAI"],
        projects=[],
        papers=[],
        people=[],
        topics=["ai_models"],
        geography=[],
        event_type="product_launch",
    )


def test_tech_daily_state_default_construction_remains_compatible() -> None:
    state = TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
    )

    assert state.raw_events == []
    assert state.normalized_events == []
    assert state.topic_summaries == {}
    assert state.company_analyses == {}
    assert state.paper_analyses == {}
    assert state.github_project_analyses == {}
    assert state.github_project_analysis_status == {
        "reason": "source_empty",
        "source": "none",
        "candidate_count": 0,
        "analyzed_count": 0,
        "filtered_count": 0,
        "failed_count": 0,
        "failures": [],
    }
    assert state.social_signal_analyses == {}
    assert state.macro_impact_analyses == {}
    assert state.company_mentions == {}
    assert state.project_mentions == {}
    assert state.paper_mentions == {}
    assert state.previous_reports == []
    assert state.weekly_reviews == []
    assert state.monthly_reviews == []
    assert state.recent_topic_trends == []
    assert state.recent_company_mentions == []
    assert state.open_predictions == []
    assert state.prediction_updates == []
    assert state.new_predictions == []
    assert state.source_warnings == []
    assert state.confidence_flags == []
    assert state.trending_analysis is None
    assert state.market_signal_analyses == {}
    assert state.final_report == ""
    assert state.signal_level == "normal"


def test_prediction_resolution_contract_preserves_existing_dict_shape() -> None:
    from tech_daily.state.contracts import PredictionResolution

    resolution = PredictionResolution(
        resolved=True,
        resolved_as="true",
        resolution_reasoning="The observable criteria were met.",
    )

    assert resolution.to_persisted_dict() == {
        "resolved": True,
        "resolved_as": "true",
        "resolution_reasoning": "The observable criteria were met.",
    }


def test_unresolved_prediction_resolution_contract_preserves_none_shape() -> None:
    from tech_daily.state.contracts import PredictionResolution

    resolution = PredictionResolution(resolved=False)

    assert resolution.to_persisted_dict() == {
        "resolved": False,
        "resolved_as": None,
        "resolution_reasoning": None,
    }


def test_prediction_signal_monitor_contract_preserves_existing_dict_shape() -> None:
    from tech_daily.state.contracts import SignalToMonitor

    signal = SignalToMonitor(
        signal="orders",
        threshold="increase",
        meaning="demand",
    )

    assert signal.to_persisted_dict() == {
        "signal": "orders",
        "threshold": "increase",
        "meaning": "demand",
    }


def test_market_signal_monitor_contract_preserves_existing_dict_shape() -> None:
    from tech_daily.state.contracts import SignalToMonitor

    signal = SignalToMonitor(
        signal="Datacenter demand",
        current="strong",
        threshold="weakening",
        meaning="Demand inflection",
    )

    assert signal.to_persisted_dict() == {
        "signal": "Datacenter demand",
        "current": "strong",
        "threshold": "weakening",
        "meaning": "Demand inflection",
    }


def test_typed_state_round_trip_preserves_core_values() -> None:
    from pipeline_state import (
        AnalysisState,
        CollectionState,
        CorpusState,
        DiagnosticsState,
        HistoricalContextState,
        PredictionState,
        ReportState,
        RunMetadataState,
    )

    state = TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
    )
    state.raw_events = [_raw_event()]
    state.normalized_events = [_normalized_event()]
    state.source_warnings = ["source warning"]
    state.confidence_flags = ["confidence flag"]
    state.topic_summaries = {"ai_models": object()}
    state.company_analyses = {"OpenAI": object()}
    state.paper_analyses = {"paper": object()}
    state.github_project_analyses = {"example/repo": object()}
    state.github_project_analysis_status = {
        "reason": "accepted_projects_available",
        "source": "ossinsight",
        "candidate_count": 4,
        "analyzed_count": 4,
        "filtered_count": 3,
        "failed_count": 0,
        "failures": [],
    }
    state.social_signal_analyses = {"social": object()}
    state.macro_impact_analyses = {"macro": object()}
    state.market_signal_analyses = {"NVDA": object()}
    state.trending_analysis = object()
    state.previous_reports = ["daily"]
    state.weekly_reviews = ["weekly"]
    state.monthly_reviews = ["monthly"]
    state.recent_topic_trends = [{"topic": "ai"}]
    state.recent_company_mentions = [{"company": "OpenAI"}]
    state.open_predictions = ["open"]
    state.prediction_updates = ["update"]
    state.new_predictions = ["new"]
    state.final_report = "# Report\n"
    state.signal_level = "high"

    target = TechDailyState(
        run_id="target",
        run_date="2026-07-03",
        time_window="last_12h",
    )

    for state_type in [
        RunMetadataState,
        CollectionState,
        CorpusState,
        HistoricalContextState,
        AnalysisState,
        PredictionState,
        ReportState,
        DiagnosticsState,
    ]:
        state_type.from_tech_daily_state(state).apply_to_tech_daily_state(target)

    assert target.run_id == "run-fixture"
    assert target.run_date == "2026-07-02"
    assert target.time_window == "last_24h"
    assert target.raw_events == state.raw_events
    assert target.normalized_events == state.normalized_events
    assert target.source_warnings == ["source warning"]
    assert target.confidence_flags == ["confidence flag"]
    assert target.topic_summaries == state.topic_summaries
    assert target.company_analyses == state.company_analyses
    assert target.paper_analyses == state.paper_analyses
    assert target.github_project_analyses == state.github_project_analyses
    assert target.github_project_analysis_status == state.github_project_analysis_status
    assert target.social_signal_analyses == state.social_signal_analyses
    assert target.macro_impact_analyses == state.macro_impact_analyses
    assert target.market_signal_analyses == state.market_signal_analyses
    assert target.trending_analysis is state.trending_analysis
    assert target.previous_reports == ["daily"]
    assert target.weekly_reviews == ["weekly"]
    assert target.monthly_reviews == ["monthly"]
    assert target.recent_topic_trends == [{"topic": "ai"}]
    assert target.recent_company_mentions == [{"company": "OpenAI"}]
    assert target.open_predictions == ["open"]
    assert target.prediction_updates == ["update"]
    assert target.new_predictions == ["new"]
    assert target.final_report == "# Report\n"
    assert target.signal_level == "high"


def test_docs_state_documents_every_tech_daily_state_field() -> None:
    doc = Path("docs/state.md").read_text(encoding="utf-8")

    for field in fields(TechDailyState):
        assert f"| `{field.name}` |" in doc


def test_state_helper_preferred_actions_are_available() -> None:
    from pipeline_state import (
        PredictionInputState,
        ReportInputState,
        apply_analysis_state,
        apply_collection_result,
        apply_collection_state,
        apply_corpus_result,
        apply_corpus_state,
        apply_prediction_state,
        apply_report_result,
        apply_report_state,
        apply_topic_analysis_result,
        get_analysis_state,
        get_collection_state,
        get_corpus_state,
        get_market_signal_input_state,
        get_prediction_input_state,
        get_prediction_state,
        get_report_input_state,
        get_report_state,
        set_mention_indexes,
        set_normalized_events,
        set_raw_events,
        set_source_warnings,
    )

    assert apply_collection_result
    assert apply_collection_state
    assert apply_corpus_result
    assert apply_corpus_state
    assert apply_analysis_state
    assert apply_prediction_state
    assert apply_report_state
    assert get_collection_state
    assert get_corpus_state
    assert get_analysis_state
    assert get_prediction_state
    assert get_prediction_input_state
    assert get_report_input_state
    assert get_market_signal_input_state
    assert get_report_state
    assert PredictionInputState
    assert ReportInputState
    assert apply_topic_analysis_result
    assert apply_report_result
    assert set_raw_events
    assert set_normalized_events
    assert set_source_warnings
    assert set_mention_indexes


def test_collection_and_corpus_access_helpers_are_lossless() -> None:
    from pipeline_state import (
        apply_collection_state,
        apply_corpus_state,
        get_collection_state,
        get_corpus_state,
        set_mention_indexes,
        set_normalized_events,
        set_raw_events,
        set_source_warnings,
    )

    state = TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
    )
    raw_events = [_raw_event()]
    normalized_events = [_normalized_event()]

    collection_state = set_source_warnings(set_raw_events(get_collection_state(state), raw_events), ["warning"])
    apply_collection_state(state, collection_state)

    corpus_state = set_mention_indexes(
        set_normalized_events(get_corpus_state(state), normalized_events),
        company_mentions={"OpenAI": ["event-fixture"]},
        project_mentions={"repo": ["event-fixture"]},
        paper_mentions={"paper": ["event-fixture"]},
    )
    apply_corpus_state(state, corpus_state)

    assert state.raw_events == raw_events
    assert state.source_warnings == ["warning"]
    assert state.normalized_events == normalized_events
    assert state.company_mentions == {"OpenAI": ["event-fixture"]}
    assert state.project_mentions == {"repo": ["event-fixture"]}
    assert state.paper_mentions == {"paper": ["event-fixture"]}
    assert get_collection_state(state) == collection_state
    assert get_corpus_state(state) == corpus_state


def test_normalize_collection_state_matches_legacy_normalize_action(monkeypatch) -> None:
    import daily_step_actions as actions
    from pipeline_state import CollectionState
    from run_context import RunContext

    raw_events = [_raw_event()]
    normalized_events = [_normalized_event()]
    context = RunContext.from_config(
        run_date="2026-07-02",
        run_id="run-fixture",
        root_dir=".",
        config={},
    )
    state = TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
        raw_events=raw_events,
    )

    monkeypatch.setattr(actions, "normalize_events", lambda events, run_date: normalized_events)

    assert actions.normalize_sources_action(state, context) == normalized_events
    assert (
        actions.normalize_collection_state_action(CollectionState(raw_events=raw_events), context).normalized_events
        == normalized_events
    )


def test_typed_analyzer_prediction_and_report_action_paths_match_legacy(monkeypatch) -> None:
    import daily_step_actions as actions
    from pipeline_state import (
        CorpusState,
        PredictionState,
        ReportState,
        get_market_signal_input_state,
        get_prediction_input_state,
        get_report_input_state,
    )

    normalized_events = [_normalized_event()]
    state = TechDailyState(
        run_id="run-fixture",
        run_date="2026-07-02",
        time_window="last_24h",
        normalized_events=normalized_events,
    )
    corpus_state = CorpusState(normalized_events=normalized_events)

    monkeypatch.setattr(actions, "analyze_topics", lambda events: {"topics": events})
    monkeypatch.setattr(actions, "run_prediction_updates", lambda state: ["update"])
    monkeypatch.setattr(actions, "run_prediction_updates_from_input", lambda input_state: ["update"])
    monkeypatch.setattr(actions, "generate_new_predictions", lambda state: ["new"])
    monkeypatch.setattr(
        actions,
        "generate_new_predictions_from_input",
        lambda input_state: (["new"], input_state.prediction.signal_level),
    )
    monkeypatch.setattr(actions, "generate_daily_report", lambda state: "# Report\n")
    monkeypatch.setattr(actions, "generate_daily_report_from_input", lambda input_state: "# Report\n")
    monkeypatch.setattr(actions, "load_last_signal_per_ticker", lambda: {"NVDA": {"ticker": "NVDA"}})

    def fake_market(input_state, *, market_data, prior_signals, config):
        return {
            "state_run_date": input_state.run_metadata.run_date,
            "event_count": len(input_state.corpus.normalized_events),
            "prior_signals": prior_signals,
            "market_data": market_data,
            "config": config,
        }

    assert actions.analyze_topics_action(state) == actions.analyze_topics_state_action(corpus_state)

    prediction_state = PredictionState.from_tech_daily_state(state)
    assert actions.update_predictions_action(state) == ["update"]
    assert actions.update_predictions_state_action(state, prediction_state).prediction_updates == ["update"]
    assert actions.update_predictions_input_action(get_prediction_input_state(state)).prediction_updates == ["update"]
    assert actions.generate_new_predictions_action(state) == ["new"]
    assert actions.generate_new_predictions_state_action(state, prediction_state).new_predictions == ["new"]
    assert actions.generate_new_predictions_input_action(get_prediction_input_state(state)).new_predictions == ["new"]

    assert actions.generate_daily_report_action(state) == "# Report\n"
    assert actions.generate_daily_report_state_action(state).final_report == ReportState("# Report\n").final_report
    assert actions.generate_daily_report_input_action(get_report_input_state(state)).final_report == "# Report\n"
    assert actions.analyze_market_signals_input_action(
        get_market_signal_input_state(state),
        market_data={"per_ticker": {}},
        cfg={"market_signal": {"enabled": True}},
        analyze_market_signals_func=fake_market,
    ) == {
        "state_run_date": "2026-07-02",
        "event_count": 1,
        "prior_signals": {"NVDA": {"ticker": "NVDA"}},
        "market_data": {"per_ticker": {}},
        "config": {"market_signal": {"enabled": True}},
    }


def test_daily_pipeline_uses_typed_state_helpers_for_shadowed_groups() -> None:
    source = Path("src/tech_daily/pipeline/daily.py").read_text(encoding="utf-8")

    for helper_name in [
        "apply_collection_state",
        "get_collection_state",
        "append_source_warning",
        "apply_corpus_state",
        "apply_topic_analysis_result",
        "get_analysis_state",
        "apply_company_analysis_result",
        "apply_paper_analysis_result",
        "apply_github_project_analysis_result",
        "apply_trending_analysis_result",
        "apply_social_signal_analysis_result",
        "apply_macro_impact_analysis_result",
        "apply_market_signal_analysis_result",
        "get_market_signal_input_state",
        "apply_prediction_updates_result",
        "get_prediction_input_state",
        "get_prediction_state",
        "apply_new_predictions_result",
        "apply_report_result",
        "get_report_input_state",
        "get_report_state",
        "apply_report_state",
    ]:
        assert helper_name in source

    for broad_state_action in [
        "actions.update_predictions_state_action(rt.state",
        "actions.generate_new_predictions_state_action(rt.state",
        "actions.generate_daily_report_state_action(rt.state",
        "actions.analyze_market_signals_action(\n                state=rt.state",
    ]:
        assert broad_state_action not in source


def test_documented_state_helpers_exist() -> None:
    import pipeline_state

    doc = Path("docs/state.md").read_text(encoding="utf-8")
    helper_names = set(re.findall(r"`(apply_[a-z_]+|append_[a-z_]+)`", doc))

    assert helper_names
    for helper_name in helper_names:
        assert hasattr(pipeline_state, helper_name)


def test_collection_corpus_ownership_docs_cover_phase_6_fields() -> None:
    doc = Path("docs/state.md").read_text(encoding="utf-8")

    for field_name in [
        "raw_events",
        "source_warnings",
        "normalized_events",
        "company_mentions",
        "project_mentions",
        "paper_mentions",
    ]:
        assert f"| `{field_name}` |" in doc

    for helper_name in [
        "get_collection_state",
        "apply_collection_state",
        "set_raw_events",
        "set_source_warnings",
        "normalize_collection_state",
        "get_corpus_state",
        "apply_corpus_state",
        "set_normalized_events",
        "set_mention_indexes",
    ]:
        assert f"`{helper_name}`" in doc


def test_daily_pipeline_collection_corpus_callbacks_do_not_assign_compat_fields_directly() -> None:
    source = Path("scripts/daily_pipeline.py").read_text(encoding="utf-8")

    for assignment in [
        "runtime.state.raw_events =",
        "runtime.state.source_warnings =",
        "runtime.state.normalized_events =",
        "runtime.state.company_mentions =",
        "runtime.state.project_mentions =",
        "runtime.state.paper_mentions =",
    ]:
        assert assignment not in source
