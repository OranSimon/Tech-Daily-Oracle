# Daily Pipeline Policy

`scripts/pipeline_policy.py` is the source of truth for daily step metadata:
step name, order, fatal/non-fatal policy, responsibility, and fallback
description. `scripts/daily_pipeline.py` is the static composition layer that
references those policy objects and supplies execution-specific wiring.
`scripts/run_daily.py` remains the CLI-compatible runner: it parses arguments,
builds runtime context/state, executes the daily pipeline, and prints the final
summary.

This is intentionally not a workflow engine. There is no dynamic loading,
plugin discovery, dependency graph, async scheduler, or topological sorting.

## Error Policy

- `fatal`: preserve existing abort behavior. `PipelineStep` logs the structured
  error and re-raises.
- `non_fatal`: preserve existing continue behavior. `PipelineStep` logs the
  structured error and returns the configured fallback.

The daily pipeline callbacks still own user-facing prints and `TechDailyState`
mutation. `DailyStepDefinition` derives `name` and `fatal` from its policy
object; step definitions only hold action callables, fallbacks, record-count
functions, enable conditions, and result callbacks.

## Module Layout

- `scripts/daily_step_actions.py`: named action functions for each daily step.
  These call the existing collectors, analyzers, prediction helpers, report
  generator, storage helpers, and optional Notion publisher.
- `scripts/daily_pipeline.py`: static step definitions plus result callbacks
  that preserve state mutation, fallback handling, and user-facing messages.
- `scripts/pipeline_state.py`: typed compatibility state slices and helper
  functions for applying step results back to `TechDailyState`.
- `scripts/pipeline_step.py`: timing, structured logging, and fatal/non-fatal
  wrapper primitives.
- `scripts/pipeline_policy.py`: documented step classification table.
- `scripts/run_daily.py`: CLI, skip/force behavior, context/config/logger/state
  construction, pipeline execution, final summary, and exit behavior.

## Adding A Daily Step

1. Add a named action function in `scripts/daily_step_actions.py`.
2. Add one `DailyStepPolicy` entry in `scripts/pipeline_policy.py` at the
   intended position.
3. Register one explicit `DailyStepDefinition` in `scripts/daily_pipeline.py`
   that references the policy with `get_daily_step_policy(...)`.
4. Preserve existing fatal/non-fatal behavior and fallback values.
5. Add tests for the action, definition/policy integrity, and any fallback path.

New steps should not call Claude directly. JSON/text generation should go
through the existing LLM boundary, and web search should go through
`WebSearchClient`.

## Step Classification

| Order | Step | Policy | Fallback | Wrapped |
| --- | --- | --- | --- | --- |
| 1 | Loading historical context | fatal | No fallback; abort before downstream analysis. | yes |
| 2 | Collecting sources | non_fatal | Empty raw-event list. | yes |
| 3 | Collecting market data (yfinance / FRED) | non_fatal | No market data. | yes |
| 4 | Collecting trending snapshot (OSSInsight + HuggingFace) | non_fatal | No trending snapshot. | yes |
| 5 | Normalizing and deduplicating events | non_fatal | Empty normalized-event list. | yes |
| 6 | Analyzing topics | non_fatal | Default empty topic summaries plus existing confidence flag behavior. | yes |
| 7 | Analyzing companies | non_fatal | Default empty company analyses plus existing confidence flag behavior. | yes |
| 8 | Analyzing papers | non_fatal | Default empty paper analyses plus existing confidence flag behavior. | yes |
| 9 | Analyzing GitHub projects | non_fatal | Default empty GitHub project analyses plus existing confidence flag behavior. | yes |
| 10 | Loading trending history | fatal inside trending analysis | Raise to the existing non-fatal trending analysis handler. | yes |
| 11 | Analyzing trending items | non_fatal | Default/no trending analysis. | yes |
| 12 | Analyzing social signals | non_fatal | Default empty social signal analyses. | yes |
| 13 | Analyzing macro/geopolitical impact | non_fatal | Default empty macro impact analyses. | yes |
| 14 | Analyzing market signals (MarketSignalAgent) | non_fatal | Default empty market signal analyses. | yes |
| 15 | Updating predictions | non_fatal | Default empty prediction updates. | yes |
| 16 | Generating new predictions | non_fatal | Default empty new predictions. | yes |
| 17 | Generating daily brief report | non_fatal | Existing Markdown error-report fallback. | yes |
| 18 | Saving outputs | fatal for core writes | No fallback for core writes; optional sub-writes remain non-fatal. | yes |
| 19 | Publishing to Notion | non_fatal | No Notion URL. | yes |

## Current Status

All major daily runner steps are now wrapped for timing, structured logging, and
fatal/non-fatal policy. Prediction, report, and storage business logic remains
inside the existing modules; only orchestration calls are wrapped.

Step summaries are emitted as structured logs only. They are not persisted and
are not included in generated reports.

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
the `daily_pipeline.py` action boundary. The action wrappers build temporary
compatibility `TechDailyState` objects for existing internals, so prompt
payloads, report Markdown, prediction IDs/statuses, and storage formats remain
unchanged.

## Recommended Phase 5

Phase 5 should reduce `TechDailyState` gradually by grouping state around clear
domains such as collection, analysis, predictions, report output, and
diagnostics. That work should be done behind compatibility adapters so existing
report generation, storage, and CLI behavior remain unchanged.
