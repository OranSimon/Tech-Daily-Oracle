# Daily Pipeline Policy

`tech_daily.pipeline.policy` is the source of truth for daily step metadata:
stable step id, display name, order, fatal/non-fatal policy, responsibility,
and fallback description. `tech_daily.pipeline.daily` is the static composition
layer that references those policy objects by `StepId` and supplies
execution-specific wiring.

`DAILY_STEP_POLICIES` and `build_daily_step_definitions(...)` must stay in the
same order. `tests/test_daily_pipeline_definitions.py` guards this because the
policy table documents behavior while the definitions execute it.

`StepId` is the stable identifier for policy lookup and control-flow branches.
The human-readable step name is only for logs, headings, and documentation.
`scripts/run_daily.py` remains the CLI-compatible runner: it parses arguments,
builds runtime context/state, executes the daily pipeline, and prints the final
summary.

This is intentionally not a workflow engine. There is no dynamic loading,
plugin discovery, dependency graph, async scheduler, or topological sorting.

## Policy Shape

All daily steps now execute through `PipelineStep`. Because wrapping is no
longer partial, `DAILY_STEP_POLICIES` does not carry `wrapped` or
`safe_to_wrap_now` metadata. The policy table owns stable identity, display
name, responsibility, and fatal/non-fatal behavior. The executable step
definition owns callables, fallbacks, enabled conditions, and after-result
state application.

## Error Policy

- `fatal`: preserve existing abort behavior. `PipelineStep` logs the structured
  error and re-raises.
- `non_fatal`: preserve existing continue behavior. `PipelineStep` logs the
  structured error and returns the configured fallback.

The daily pipeline callbacks still own user-facing prints and `TechDailyState`
mutation. `DailyStepDefinition` derives `step_id`, `name`, and `fatal` from its
policy object; step definitions only hold action callables, fallbacks,
record-count functions, enable conditions, and result callbacks.

## Module Layout

- `src/tech_daily/pipeline/actions.py`: named action functions for each daily
  step. These call the existing collectors, analyzers, prediction helpers,
  report generator, storage helpers, and optional Notion publisher.
- `src/tech_daily/pipeline/daily.py`: static step definitions plus result
  callbacks that preserve state mutation, fallback handling, and user-facing
  messages.
- `scripts/daily_step_actions.py`: compatibility wrapper for the package-owned
  step actions module.
- `scripts/daily_pipeline.py`: compatibility wrapper for the package-owned
  pipeline composition module.
- `tech_daily.pipeline.state`: package-owned typed compatibility state slices
  and helper functions.
- `scripts/pipeline_state.py`: compatibility facade that re-exports typed state
  slices and helpers for legacy imports.
- `scripts/pipeline_policy.py`: compatibility facade for the package-owned
  policy table.
- `scripts/pipeline_step.py`: timing, structured logging, and fatal/non-fatal
  wrapper primitives.
- `scripts/run_daily.py`: CLI, skip/force behavior, context/config/logger/state
  construction, pipeline execution, final summary, and exit behavior.

## Adding A Daily Step

1. Add a named action function in `src/tech_daily/pipeline/actions.py`.
2. Add one `DailyStepPolicy` entry in `src/tech_daily/pipeline/policy.py`
   (`tech_daily.pipeline.policy`) at the intended position with a stable
   `StepId`. `scripts/pipeline_policy.py` is a compatibility-only facade.
3. Register one explicit `DailyStepDefinition` in
   `src/tech_daily/pipeline/daily.py`
   that references the policy with `get_daily_step_policy(StepId.OWNER_ACTION)`.
4. Preserve existing fatal/non-fatal behavior and fallback values.
5. Add tests for the action, definition/policy integrity, and any fallback path.

New steps should not call Claude directly. JSON/text generation should go
through the existing LLM boundary, and web search should go through
`WebSearchClient`.

## Step Classification

| Order | Step ID | Step | Policy | Fallback |
| --- | --- | --- | --- | --- |
| 1 | `load_historical_context` | Loading historical context | fatal | No fallback; abort before downstream analysis. |
| 2 | `collect_sources` | Collecting sources | non_fatal | Empty raw-event list. |
| 3 | `collect_market_data` | Collecting market data (yfinance / FRED) | non_fatal | No market data. |
| 4 | `collect_trending_snapshot` | Collecting trending snapshot (OSSInsight + HuggingFace) | non_fatal | No trending snapshot. |
| 5 | `normalize_events` | Normalizing and deduplicating events | non_fatal | Empty normalized-event list. |
| 6 | `analyze_topics` | Analyzing topics | non_fatal | Default empty topic summaries plus existing confidence flag behavior. |
| 7 | `analyze_companies` | Analyzing companies | non_fatal | Default empty company analyses plus existing confidence flag behavior. |
| 8 | `analyze_papers` | Analyzing papers | non_fatal | Default empty paper analyses plus existing confidence flag behavior. |
| 9 | `analyze_github_projects` | Analyzing GitHub projects | non_fatal | Default empty GitHub project analyses plus existing confidence flag behavior. |
| 10 | `load_trending_history` | Loading trending history | fatal inside trending analysis | Raise to the existing non-fatal trending analysis handler. |
| 11 | `analyze_trending` | Analyzing trending items | non_fatal | Default/no trending analysis. |
| 12 | `analyze_social_signals` | Analyzing social signals | non_fatal | Default empty social signal analyses. |
| 13 | `analyze_macro_impact` | Analyzing macro/geopolitical impact | non_fatal | Default empty macro impact analyses. |
| 14 | `analyze_market_signals` | Analyzing market signals (MarketSignalAgent) | non_fatal | Default empty market signal analyses. |
| 15 | `update_predictions` | Updating predictions | non_fatal | Default empty prediction updates. |
| 16 | `generate_new_predictions` | Generating new predictions | non_fatal | Default empty new predictions. |
| 17 | `generate_daily_report` | Generating daily brief report | non_fatal | Existing Markdown error-report fallback. |
| 18 | `save_outputs` | Saving outputs | fatal for core writes | No fallback for core writes; optional sub-writes remain non-fatal. |
| 19 | `publish_to_notion` | Publishing to Notion | non_fatal | No Notion URL. |

## Current Status

All major daily runner steps are now wrapped for timing, structured logging, and
fatal/non-fatal policy. Prediction, report, and storage business logic remains
inside the existing modules; only orchestration calls are wrapped.

Step summaries are always emitted as structured logs. Daily runs also attempt to
append a compact local diagnostics row to `data/run_summaries.jsonl`, using the
runtime root for path resolution instead of the process working directory. This
artifact is optional, non-fatal, and not included in generated reports.

## Phase 5 State Boundary

`TechDailyState` is still the public compatibility shell. Phase 5 introduces
typed state slices in `scripts/pipeline_state.py` and routes daily pipeline
result callbacks through those helpers. This shadows collection, corpus,
historical context, analysis, prediction, report, and diagnostics fields without
changing persisted formats or report semantics.

Phase 6 starts reducing direct collection/corpus access. Source collection now
returns a `CollectionState` through the typed action path, normalization accepts
that typed state and returns a `CorpusState`, and daily pipeline callbacks apply
those states back to compatibility fields. Legacy consumers still read
`TechDailyState.raw_events` and `TechDailyState.normalized_events` until their
domains are migrated.

Market signal analysis, prediction updates, new prediction generation, and
daily report generation now use typed input states from `pipeline_state.py` at
the `tech_daily.pipeline.daily` action boundary. Report generation builds the daily
prompt payload directly from `ReportInputState` through
`generate_daily_report_from_input(...)`. Prediction updates and new prediction
generation use `PredictionInputState` through
`run_prediction_updates_from_input(...)` and
`generate_new_predictions_from_input(...)`. Market signals use
`MarketSignalInputState` through `analyze_market_signals_from_input(...)`.
Legacy `TechDailyState` functions remain as compatibility adapters, so prompt
payloads, report Markdown, prediction IDs/statuses, and storage formats remain
unchanged.

## Recommended Phase 5

Phase 5 should reduce `TechDailyState` gradually by grouping state around clear
domains such as collection, analysis, predictions, report output, and
diagnostics. That work should be done behind compatibility adapters so existing
report generation, storage, and CLI behavior remain unchanged.
