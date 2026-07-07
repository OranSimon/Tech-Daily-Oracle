# Pipeline State

`TechDailyState` remains the public compatibility shell for the daily pipeline.
Phase 5 adds typed state slices in `tech_daily.pipeline.state` so orchestration
can gradually move away from broad blackboard mutation without changing report
formats, storage formats, prediction schemas, CLI behavior, or pipeline order.

Typed pipeline state slices are package-owned in `tech_daily.pipeline.state`.
`TechDailyState` remains the public compatibility shell.

Typed state objects are compatibility shadows. They group related fields and
apply values back to `TechDailyState`; they do not own business logic.

Nested dictionary fields remain public for compatibility, but new code should
construct them through package-owned helper contracts such as
`PredictionResolution` and `SignalToMonitor` when writing new persistence or
prompt-boundary code.

## Typed State Slices

- `RunMetadataState`: run identity, date, time window, and signal level.
- `CollectionState`: raw collected events and source collection warnings.
- `CorpusState`: normalized events and mention indexes.
- `HistoricalContextState`: reports, reviews, trends, mentions, and open predictions loaded before analysis.
- `AnalysisState`: topic, company, paper, GitHub, social, macro, market, and trending analysis outputs.
- `PredictionState`: open predictions plus updates and new predictions generated this run.
- `ReportState`: final Markdown report text.
- `DiagnosticsState`: source warnings and confidence flags.

## Field Ownership Audit

| Field | Domain | Writer | Readers | Required | Default | Fallback behavior | Persisted | Appears in reports | Source of truth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `run_id` | run metadata | `run_daily.py` creates `TechDailyState`; `RunMetadataState` can shadow/apply it | storage/event append, logs/context-adjacent code | yes | constructor required | none; run cannot start without it | event artifacts may include it | no | source |
| `run_date` | run metadata | `run_daily.py`; `RunMetadataState` can shadow/apply it | report generation, predictions, storage, market analysis | yes | constructor required | none; run cannot start without it | reports/predictions/events use it | yes | source |
| `time_window` | run metadata | `run_daily.py`; `RunMetadataState` can shadow/apply it | prompt/report context | yes | constructor required | derived from config report window | no direct artifact | possible prompt context | derived |
| `raw_events` | collection | source collection callback through `CollectionState` helper | normalization, final summary | no | `[]` | source failure uses `[]` | no, normalized events are persisted | no | source |
| `normalized_events` | corpus | normalization callback through `CorpusState` helper | analyzers, predictions, report generation, storage | no | `[]` | normalization failure uses `[]` | source events JSONL | yes | source |
| `topic_summaries` | analysis | topic analysis callback through `AnalysisState` helper | predictions, report generation, storage trends | no | `{}` | topic failure uses `{}` and confidence flag | topic trend artifacts | yes | source |
| `company_analyses` | analysis | company analysis callback through `AnalysisState` helper | market analysis, predictions, report generation, storage | no | `{}` | company failure uses `{}` and confidence flag | company mention artifacts | yes | source |
| `paper_analyses` | analysis | paper analysis callback through `AnalysisState` helper | report generation, storage | no | `{}` | paper failure uses `{}` and confidence flag | source/event artifacts may reference papers | yes | source |
| `github_project_analyses` | analysis | GitHub analysis callback through `AnalysisState` helper | report generation, storage | no | `{}` | GitHub failure uses `{}` and confidence flag | source/event artifacts may reference projects | yes | source |
| `social_signal_analyses` | analysis | social analysis callback through `AnalysisState` helper | report generation | no | `{}` | social failure uses `{}` | no dedicated current artifact | yes | source |
| `macro_impact_analyses` | analysis | macro analysis callback through `AnalysisState` helper | market analysis, report generation | no | `{}` | macro failure uses `{}` | no dedicated current artifact | yes | source |
| `company_mentions` | corpus indexes | compatibility field; future corpus/index builder | report/storage consumers if populated | no | `{}` | remains `{}` if not built | company mention artifacts are loaded separately | possible | derived |
| `project_mentions` | corpus indexes | compatibility field; future corpus/index builder | future/report consumers if populated | no | `{}` | remains `{}` if not built | no dedicated current artifact | possible | derived |
| `paper_mentions` | corpus indexes | compatibility field; future corpus/index builder | future/report consumers if populated | no | `{}` | remains `{}` if not built | no dedicated current artifact | possible | derived |
| `previous_reports` | historical context | historical context action through `HistoricalContextState` helper | report generation, prompts | no | `[]` | historical load is fatal; no fallback | loaded from report files | no direct new output | source |
| `weekly_reviews` | historical context | historical context action through `HistoricalContextState` helper | report generation, prompts | no | `[]` | historical load is fatal; no fallback | loaded from report files | no direct new output | source |
| `monthly_reviews` | historical context | historical context action through `HistoricalContextState` helper | report generation, prompts | no | `[]` | historical load is fatal; no fallback | loaded from report files | no direct new output | source |
| `recent_topic_trends` | historical context | historical context action through `HistoricalContextState` helper | report generation, prompts | no | `[]` | historical load is fatal; no fallback | loaded from data artifacts | yes as context | source |
| `recent_company_mentions` | historical context | historical context action through `HistoricalContextState` helper | report generation, prompts | no | `[]` | historical load is fatal; no fallback | loaded from data artifacts | yes as context | source |
| `open_predictions` | prediction/history | historical context action through `HistoricalContextState`/`PredictionState` helpers | macro analysis, prediction update, report generation | no | `[]` | historical load is fatal; no fallback | prediction JSONL | yes | source |
| `prediction_updates` | prediction | prediction update callback through `PredictionState` helper | report generation, storage | no | `[]` | prediction update failure uses `[]` | prediction JSONL | yes | source |
| `new_predictions` | prediction | new prediction callback through `PredictionState` helper | report generation, storage | no | `[]` | new prediction failure uses `[]` | prediction JSONL | yes | source |
| `source_warnings` | diagnostics/collection | source collection callback through `DiagnosticsState` helper | report generation, tests | no | `[]` | source failure appends warning and continues | no dedicated current artifact | yes | source |
| `confidence_flags` | diagnostics | analyzer callbacks through `DiagnosticsState` helper | report generation, tests | no | `[]` | topic/company/paper/GitHub failures append flags | no dedicated current artifact | yes | source |
| `trending_analysis` | analysis | trending analysis callback through `AnalysisState` helper | report generation | no | `None` | trending collection/history/analysis failure leaves `None` | no dedicated current artifact | yes | source |
| `market_signal_analyses` | analysis | market signal callback through `AnalysisState` helper | report generation, storage | no | `{}` | market signal failure uses `{}` | market signals JSONL | yes | source |
| `final_report` | report | report generation callback through `ReportState` helper | storage, Notion publishing, return value | no | `""` | report failure writes existing Markdown error body | daily report Markdown | yes | source |
| `signal_level` | prediction/report metadata | default state, prediction logic may adjust it; `RunMetadataState`/`PredictionState` can shadow/apply it | prediction generation, report generation, summaries | no | `"normal"` | remains `"normal"` unless prediction logic changes it | no dedicated current artifact | yes | source |

## Preferred Access Pattern

New orchestration code should prefer typed helpers from `scripts/pipeline_state.py`
when updating fields that are already shadowed. Direct `TechDailyState` reads
are still allowed for compatibility, especially inside analyzers, report
generation, storage, and prediction internals.

## Collection And Corpus Ownership

Collection/corpus fields are the first Phase 6 domain moving away from direct
blackboard access:

| Field | Current owner | Current writers | Current readers | Proposed typed owner | Compatibility strategy | Direct `TechDailyState` access |
| --- | --- | --- | --- | --- | --- | --- |
| `raw_events` | collection stage | `collect_sources_state_action` returns `CollectionState`; `daily_pipeline.py` applies it with `apply_collection_state` | normalization, final summary | `CollectionState` | keep `TechDailyState.raw_events` populated after each collection step | temporarily allowed for summaries and legacy consumers |
| `source_warnings` | diagnostics/collection stage | `append_source_warning` after collection failure | report generation, tests | `CollectionState`/`DiagnosticsState` | keep `TechDailyState.source_warnings` populated; diagnostics helper remains compatible | temporarily allowed in report generation |
| `normalized_events` | corpus stage | `normalize_collection_state_action` returns `CorpusState`; `daily_pipeline.py` applies it with `apply_corpus_state` | analyzers, predictions, market signals, report generation, storage, final summary | `CorpusState` | keep `TechDailyState.normalized_events` populated for all existing readers | temporarily allowed in analyzers/report/storage/predictions |
| `company_mentions` | corpus indexes | future index builder; currently compatibility field | future/report/storage consumers if populated | `CorpusState` | use `set_mention_indexes` when indexes are added | temporarily allowed |
| `project_mentions` | corpus indexes | future index builder; currently compatibility field | future/report/storage consumers if populated | `CorpusState` | use `set_mention_indexes` when indexes are added | temporarily allowed |
| `paper_mentions` | corpus indexes | future index builder; currently compatibility field | future/report/storage consumers if populated | `CorpusState` | use `set_mention_indexes` when indexes are added | temporarily allowed |

Preferred Phase 6 helpers for this domain are `get_collection_state`,
`apply_collection_state`, `set_raw_events`, `set_source_warnings`,
`normalize_collection_state`, `get_corpus_state`, `apply_corpus_state`,
`set_normalized_events`, and `set_mention_indexes`.

Current preferred helpers include:

- `apply_historical_context_result`
- `apply_collection_result`
- `append_source_warning`
- `apply_corpus_result`
- `apply_topic_analysis_result`
- `apply_company_analysis_result`
- `apply_paper_analysis_result`
- `apply_github_project_analysis_result`
- `apply_trending_analysis_result`
- `apply_social_signal_analysis_result`
- `apply_macro_impact_analysis_result`
- `apply_market_signal_analysis_result`
- `append_confidence_flag`
- `apply_prediction_updates_result`
- `apply_new_predictions_result`
- `apply_report_result`
- `get_market_signal_input_state`
- `get_prediction_input_state`
- `get_report_input_state`

Do not ban all direct `TechDailyState` usage yet. That would be too broad while
the report generator, storage layer, prediction updater, and analyzers still
use the compatibility shell.

## Typed Action Input Boundaries

Daily orchestration now prefers typed input states at the action boundary for
market signal analysis, prediction updates, new prediction generation, and daily
report generation:

| Boundary | Preferred input | Compatibility adapter | Direct `TechDailyState` retained |
| --- | --- | --- | --- |
| Market signals | `MarketSignalInputState` | `analyze_market_signals_input_action(...)` calls `analyze_market_signals_from_input(...)` directly | legacy `analyze_market_signals(state, ...)` remains as a compatibility adapter |
| Prediction updates | `PredictionInputState` | `update_predictions_input_action(...)` calls `run_prediction_updates_from_input(...)` directly | legacy `run_prediction_updates(state)` remains as a compatibility adapter |
| New predictions | `PredictionInputState` | `generate_new_predictions_input_action(...)` calls `generate_new_predictions_from_input(...)` directly | legacy `generate_new_predictions(state)` remains as a compatibility adapter and applies `signal_level` back to the shell |
| Daily report | `ReportInputState` | `generate_daily_report_input_action(...)` calls `generate_daily_report_from_input(...)` directly | legacy `generate_daily_report(state)` remains as a compatibility adapter |

Temporary compatibility-state reconstruction remains for older public
`TechDailyState` APIs, but the daily action path now uses typed prediction,
market-signal, and report inputs directly. Daily report generation builds its
prompt payload directly from `ReportInputState`, while the legacy
`generate_daily_report(state)` path still works for older callers.

## Prediction Operation Diagnostics

Prediction update/generation compatibility functions still return the legacy
values used by the daily pipeline. New code may use the `*_result_from_input`
variants to inspect `success`, `error_kind`, and `error_message` without
changing fallback behavior.

## Direct Access Map

Current direct `TechDailyState` access is intentionally grouped as follows:

| Area | Files | Reason retained |
| --- | --- | --- |
| Compatibility construction and apply helpers | `scripts/pipeline_state.py` | Central mapping layer between typed slices and the public shell |
| Daily runner summary | `scripts/run_daily.py` | User-facing final counts and return value |
| Legacy action wrappers | `scripts/daily_step_actions.py` | Backward-compatible public functions used by tests and older callers |
| Prediction internals | `scripts/update_predictions.py` | Typed input entrypoints exist; legacy state-based functions remain for compatibility |
| Report internals | `scripts/generate_report.py` | Markdown prompt payload construction is intentionally unchanged |
| Market signal internals | `scripts/analyze_market_signals.py` | Typed input entrypoint exists; legacy state-based function remains for compatibility |
| Storage persistence | `scripts/storage.py` | Existing persisted row shapes are derived from current dataclasses/state |

## Candidates For Phase 6

Phase 6 should choose one domain at a time and reduce direct `TechDailyState`
access behind compatibility helpers. The safest order is collection/corpus,
analysis outputs, prediction state, then report/publication state. Persisted
schemas and Markdown report structure should remain fixed during that work.
