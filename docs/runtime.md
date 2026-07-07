# Runtime Context

`src/tech_daily/runtime/run_context.py` provides a small runtime context layer
for pipeline runs. `scripts/run_context.py` is a compatibility wrapper for
legacy script imports. The context layer is intentionally narrow: it centralizes
run metadata, key repository paths, and lightweight config access without
replacing `TechDailyState`.

## RunContext

`RunContext` contains:

- `run_date`
- `run_id`
- `root_dir`
- `data_dir`
- `reports_dir`
- `config`

It also exposes convenience properties such as `daily_report_path` and
`time_window`.

`RunContext` should hold stable runtime facts. It should not hold collected
events, analyzer outputs, predictions, report text, or other business state.
Those still belong in `TechDailyState`; `RunContext` is not a replacement for
the pipeline blackboard.

## AppConfig

`AppConfig` wraps the existing config dictionary without changing
`config.yml`. Raw config access remains available through `config.raw` for
compatibility.

Use helper properties for common runner-level values:

- `timezone`
- `report_window_hours`
- `market_signal_enabled`
- `market_live_data_enabled`
- `notion_enabled`
- `trending_top_n`

Do not move every config lookup at once. Prefer using `AppConfig` when touching
runner orchestration or adding future pipeline steps.

## Structured Logging

`src/tech_daily/runtime/run_logging.py` defines `RunLogger` and `RunLogEvent`.
`scripts/run_logging.py` is a compatibility wrapper for legacy script imports.
Log events carry:

- `run_id`
- `run_date`
- `step`
- `severity`
- `message`
- optional `duration_seconds`
- optional `record_count`
- optional `error`

The logger can emit JSON lines for machine-readable logs or structured plain
text for human-readable runs. `PipelineStep` uses this logger for
completion/failure records while preserving the current plain progress output
where useful.

## Daily Orchestration

The daily runner is split into a few small orchestration modules:

- `scripts/run_daily.py` handles CLI parsing, skip/force behavior, runtime
  construction, `TechDailyState` creation, pipeline execution, final summary,
  and exit behavior.
- `scripts/daily_step_actions.py` contains named action functions for daily
  steps.
- `scripts/daily_pipeline.py` contains static step definitions and result
  callbacks.
- `scripts/pipeline_state.py` contains typed state slices and compatibility
  helpers for applying step results back to `TechDailyState`.
- `scripts/pipeline_policy.py` is the source of truth for daily step order,
  step names, and fatal/non-fatal policy.

`RunContext` belongs in orchestration code and should be passed to actions that
need run metadata or stable paths. `TechDailyState` still owns business data:
events, analysis results, predictions, generated report text, warnings, and
confidence flags.

When a daily pipeline callback updates a field that has a typed state helper,
prefer the helper from `pipeline_state.py` over direct field assignment. Direct
reads from `TechDailyState` remain allowed for compatibility inside analyzers,
storage, report generation, and prediction internals.

For collection/corpus code, prefer `CollectionState` and `CorpusState` at new
function boundaries. Keep applying those states back to `TechDailyState` while
report generation, storage, analyzers, and predictions still expect the
compatibility shell.

For business-facing daily actions, prefer the typed input states from
`pipeline_state.py` when the action needs multiple slices:

- `MarketSignalInputState`
- `PredictionInputState`
- `ReportInputState`

These are compatibility adapters, not replacements for domain internals. They
let orchestration avoid passing the whole blackboard while preserving existing
prediction, report, and market-signal implementations.

## PipelineStep

`src/tech_daily/pipeline/step.py` defines a tiny `PipelineStep` wrapper for
timing, structured logging, and fatal/non-fatal error policy around daily runner
steps. `scripts/pipeline_step.py` is a compatibility wrapper for legacy script
imports. It returns a `PipelineStepResult` with:

- `name`
- `success`
- `duration_seconds`
- `value`
- optional `record_count`
- optional `error`

### Error Policy

Use `fatal=True` for steps that already abort the run when they fail. Use the
default `fatal=False` for steps that already continue with a fallback. The
wrapper should encode the existing behavior, not decide new behavior.

Current convention:

- Fatal/readiness steps raise after logging the structured error.
- Non-fatal steps return their configured fallback after logging the structured
  error.
- The caller still owns any existing user-facing print messages and
  `TechDailyState` mutation.

`PipelineStep` should not contain business logic, mutate `TechDailyState`
internals directly, or become a workflow engine. Keep the callable passed to a
step responsible for the existing operation, then let `daily_pipeline.py`
callbacks assign results to `TechDailyState` exactly as before.

All major daily orchestration steps are now wrapped. The wrappers cover timing,
structured logging, and fatal/non-fatal fallback policy only. Analyzer,
prediction, report, and storage business logic still lives in the existing
modules.

See `docs/pipeline.md` and `scripts/pipeline_policy.py` for the explicit daily
step classification table.

`log_step_summary(...)` emits a run-level structured log with step names,
success/failure status, durations, record counts, and error summaries for
wrapped steps. This summary is not persisted and does not affect report output.
It is not surfaced in generated reports.

Use `run_recorded_step(...)` from `scripts/daily_pipeline.py` when a step should
be executed and included in the run-level step summary. It is only a convenience
for `step.run(logger)` plus appending the result; it does not drive step order
or make policy decisions.

`DailyStepDefinition` references `DailyStepPolicy` objects instead of duplicating
step names and fatal flags. Keep new execution-specific wiring in
`daily_pipeline.py`, and keep step metadata in `pipeline_policy.py`.

## Phase 5 Direction

Do not put business state into `RunContext` to make future refactors easier.
Phase 6 should reduce direct `TechDailyState` access one domain at a time,
starting with collection/corpus and then analysis. Report formats, storage
formats, and CLI behavior should stay fixed while that happens.
