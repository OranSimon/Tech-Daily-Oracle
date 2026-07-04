# Storage Hardening

The storage layer preserves the existing file formats and paths. Reports remain
Markdown files under `reports/`, and data artifacts remain JSONL files under
`data/`.

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
| `data/*scorecard.csv` | CSV | append or external writer depending on script | existing CSV append policy | header contract tests | no migration |

`append_jsonl_rows_safely(...)` serializes an entire batch before opening the
target file. If a row is not JSON-serializable, existing valid content is left
unchanged and no partial rows from that batch are appended.
