# Storage Hardening

The storage layer preserves the existing file formats and paths. Reports remain
Markdown files under `reports/`, and data artifacts remain JSONL files under
`data/`.

Artifact behavior now lives in package modules by family:

- `tech_daily.storage.reports`
- `tech_daily.storage.predictions`
- `tech_daily.storage.events`
- `tech_daily.storage.telemetry`
- `tech_daily.storage.run_summary`

`scripts/storage.py` remains the compatibility facade for legacy `import storage`
callers and continues to honor the existing module-level path constants.

## StorageContext

`tech_daily.storage.context` defines `StorageContext`, a small typed path object
for storage artifacts. `scripts/storage.py` re-exports the same class for
legacy callers, but the package module is the authoritative home for typed
storage paths.

Use `StorageContext.from_root(root_dir)` in tests or future orchestration code
when a caller needs explicit paths. It provides helpers for:

- `daily_report_path(run_date)`
- `weekly_report_path(week)`
- `monthly_report_path(month)`
- `prediction_log_path()`
- `trending_log_path()`
- `market_signals_log_path()`
- `collector_telemetry_path()`
- `run_summary_log_path()`

Existing public storage functions still work without a context. Report,
prediction, event append, historical context, trending snapshot, market signal,
and collector telemetry functions accept optional `storage_context=...`
parameters. When omitted, they use the existing globals such as `DATA_DIR`,
`REPORTS_DIR`, `PREDICTION_LOG`, and `COLLECTOR_RUNS_LOG`, preserving
compatibility with older callers and tests.

Future storage work should prefer threading `StorageContext` through new code
instead of adding more module-level path globals. Do not use `StorageContext` to
change artifact names, directories, or formats.

The context-aware storage functions include:

- report saves: `save_daily_report(...)`, `save_weekly_review(...)`,
  `save_monthly_review(...)`
- prediction storage: `load_open_predictions(...)`, `save_predictions(...)`
- event/history storage: `append_events(...)`, `load_recent_reports(...)`,
  `load_recent_weekly_reviews(...)`, `load_recent_monthly_reviews(...)`,
  `load_topic_trends_recent(...)`, `load_company_mentions_recent(...)`
- trending storage: `save_trending_snapshot(...)`,
  `load_trending_history(...)`
- market signal storage: `save_market_signals(...)`,
  `load_market_signals_history(...)`, `load_last_signal_per_ticker(...)`
- collector telemetry: `save_collector_telemetry(...)`,
  `load_collector_telemetry(...)`, `compact_collector_telemetry(...)`
- run summary diagnostics: `save_run_summary(...)`

## Event Storage Payload Boundary

New package code should call `append_event_payload(EventStoragePayload, ...)`
instead of passing whole `TechDailyState` to storage. `append_events(state, ...)`
remains as a compatibility wrapper while legacy callers are migrated.

## Atomic Writes

Full-file rewrites must use the helpers in `scripts/storage_io.py`:

- `atomic_write_text(...)`
- `atomic_write_json(...)`
- `atomic_write_jsonl(...)`
- `atomic_replace(...)`

The helpers write to a temporary file in the target directory, flush and fsync
the contents, then replace the target with `os.replace(...)`. This protects
existing files from partial overwrite if a process fails while writing.

Append-only logs still use append mode. Do not convert append-only artifacts to
full rewrites unless the persistence format is intentionally changed in a later
phase.

Append-only artifacts should use `append_jsonl_rows_safely(...)` when new code
adds rows. The helper preserves JSONL append semantics, creates parent
directories, flushes the file handle, and fsyncs before returning. It does not
deduplicate rows or rewrite existing content.

## JSONL Validation

Loaders can accept `StorageDiagnostics` from `scripts/storage_validation.py` to
capture malformed JSONL rows without changing their public return values.
Diagnostics include the artifact path, line number, message, raw value, and
exception type when available.

Prediction-log rows are validated for the fields currently consumed by
`load_open_predictions(...)`. The validation is intentionally lightweight and
compatible with historical rows; it does not change the JSONL schema.

Malformed rows are skipped as before, but callers can now opt into structured
warnings instead of relying on silent skips or console output.

## Quarantine

`quarantine_jsonl_row(...)` can record malformed rows in a local quarantine
JSONL artifact such as `data/quarantine/prediction_log.quarantine.jsonl`.
Quarantine rows include:

- `artifact`
- `line_number`
- `message`
- `raw_value`

The helper is opt-in and does not change loader return values. Use it when a
caller needs durable local evidence of malformed persisted data without
blocking the daily run.

## Read-Time Migration

Migration helpers should be small, explicit, and read-time only unless a future
phase intentionally adds a file migration command. For example,
`migrate_collector_telemetry_row(...)` accepts earlier collector telemetry rows
that used `duration` and presents them to callers as `duration_seconds`.

These helpers must not change existing artifact paths or rewrite files as a side
effect of ordinary loads.

## Collector Telemetry

Collector telemetry is persisted at `data/collector_runs.jsonl`. Daily runs
write this artifact by default during source collection.

Each row represents one collector result from a collection run:

- `run_date`
- `run_id`
- `collector_name`
- `status`
- `duration_seconds`
- `record_count`
- `warnings`
- `error_message`
- `timestamp`

`warnings` is a compact list of `{message, exception_type}` objects. Raw source
payloads and full tracebacks are intentionally not stored.

The artifact uses JSONL with atomic full-file replacement. New rows are appended
to the existing valid rows in memory, then `atomic_write_jsonl(...)` replaces the
file. Malformed existing rows are skipped by the JSONL reader and can be reported
through `StorageDiagnostics`.

Retention is applied during telemetry saves and can also be run explicitly with
`compact_collector_telemetry(...)`. The default policy keeps telemetry from the
last 90 run dates and caps the artifact at the most recent 5,000 valid rows.
Compaction uses atomic full-file replacement and never touches unrelated data
artifacts.

Telemetry is not surfaced in reports yet, and a telemetry persistence failure
must not fail collection or report generation.

## Run Summary Diagnostics

Run summaries are persisted at `data/run_summaries.jsonl` as an optional local
diagnostics artifact. Each row captures the run date, run id, and a compact
list of executed step summaries with success, duration, record count, and
error text.

This artifact is append-only and uses `append_jsonl_rows_safely(...)`. It is
not loaded by report generation, not surfaced in report Markdown, and a
persistence failure must not fail the daily run.

## Artifact Policy

| Path | Format | Write mode | Atomicity strategy | Validation / diagnostics | Migration / quarantine |
| --- | --- | --- | --- | --- | --- |
| `reports/daily/*.md` | Markdown | full rewrite | `atomic_write_text(...)` | report contract tests validate historical structure | no migration |
| `reports/weekly/*.md` | Markdown | full rewrite | `atomic_write_text(...)` | weekly report contract tests | no migration |
| `reports/monthly/*.md` | Markdown | full rewrite | `atomic_write_text(...)` | monthly report contract tests | no migration |
| `data/prediction_log.jsonl` | JSONL | full rewrite when applying updates/new predictions | `atomic_write_jsonl(...)` | `load_open_predictions(..., diagnostics=...)` validates consumed fields | malformed rows are skipped with diagnostics; quarantine helper is opt-in |
| `data/source_events.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | historical artifact schema tests | no migration |
| `data/topic_trends.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | historical artifact schema tests | no migration |
| `data/company_mentions.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | historical artifact schema tests | no migration |
| `data/paper_mentions.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | historical artifact schema tests | no migration |
| `data/project_mentions.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | historical artifact schema tests | no migration |
| `data/trending_snapshots.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | loaded through JSONL diagnostics path | no migration |
| `data/market_signals.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | loaded through JSONL diagnostics path | no migration |
| `data/collector_runs.jsonl` | JSONL | append-by-rewrite with retention | `atomic_write_jsonl(...)` | `load_collector_telemetry(..., diagnostics=...)` validates rows | read-time migration accepts legacy `duration`; malformed rows are skipped with diagnostics |
| `data/run_summaries.jsonl` | JSONL | append-only | `append_jsonl_rows_safely(...)` | local diagnostics only; no report readers | no migration |
| `data/*scorecard.csv` | CSV | append or external writer depending on script | existing CSV append policy | header contract tests | no migration |

`append_jsonl_rows_safely(...)` serializes an entire batch before opening the
target file. If a row is not JSON-serializable, existing valid content is left
unchanged and no partial rows from that batch are appended.

## Internal Helper Ownership

Storage artifact modules must import shared private helpers from
`tech_daily.storage._shared`, not from `tech_daily.storage.__init__`.
The package `__init__` is a public export facade only. This prevents
storage submodules from depending on package import side effects.
