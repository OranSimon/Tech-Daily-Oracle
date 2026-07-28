# Source Collectors

`scripts/collect_sources.py` is the compatibility facade used by `scripts/run_daily.py`. It loads configuration, creates shared HTTP clients, delegates source-specific config mapping to `scripts/collectors/registry.py`, runs enabled collectors, and returns `list[RawEvent]`.

Source-specific logic lives under `scripts/collectors/`:

- `base.py` — shared date/time/XML helpers and the minimal collector protocol.
- `rss.py` — RSS and Atom feeds.
- `hackernews.py` — Hacker News top stories.
- `huggingface.py` — Hugging Face daily papers.
- `arxiv.py` — arXiv category queries.
- `github.py` — GitHub daily and weekly trending repository queries.
- `web_search.py` — configured web-search queries and result-to-`RawEvent` conversion.
- `registry.py` — explicit collector registry and config-to-call mapping.
- `telemetry.py` — shared per-source collector run result types.

## Adding A Collector

Add new source-specific code in a dedicated module under `scripts/collectors/`, then register it in `scripts/collectors/registry.py`.

Collectors must preserve the existing event contract:

- Return `list[RawEvent]`.
- Keep existing `source_type` values stable unless a downstream schema change is planned.
- Put source-specific details in `RawEvent.metadata`.
- Catch source-local failures and return an empty list when the existing collector pattern does so.
- Avoid persistence, report rendering, and state mutation.

## Registry And Config Mapping

The registry is deliberately explicit. There is no dynamic plugin loading.

Async collectors are listed in `ASYNC_COLLECTORS`; web search is listed separately as `WEB_SEARCH_COLLECTOR` because it runs after the async HTTP collectors and accepts the optional `WebSearchClient` dependency.

Each registry entry declares:

- `name` — stable collector name used by tests and docs.
- `config_key` — key under `config["sources"]`.
- `build_tasks` or `run` — the small adapter that maps config defaults into the collector function call.

To add a new async collector:

1. Create `scripts/collectors/<source>.py`.
2. Export a function that returns `list[RawEvent]`.
3. Add a `_build_<source>_tasks(...)` mapper in `registry.py`.
4. Add an `AsyncCollectorRegistration(...)` entry to `ASYNC_COLLECTORS`.
5. Add fake-input tests for the collector module and registry mapping.

Keep defaults in the registry mapper so `collect_sources.collect_all(...)` does not learn source-specific config shapes.

## Telemetry

The default public entrypoints still return only `list[RawEvent]`:

- `collect_sources.collect_all(...)`
- `collect_sources.collect_sources(...)`

For tests and future orchestration, use the telemetry helpers:

- `collect_sources.collect_all_with_telemetry(...)`
- `collect_sources.collect_sources_with_telemetry(...)`

Telemetry is represented by `CollectorRunResult`:

- `collector_name` — registry collector name.
- `status` — `success`, `partial`, `failed`, or `skipped`.
- `duration_seconds` — wall-clock execution time for the collector group.
- `record_count` — number of `RawEvent` records produced.
- `warnings` — non-fatal warning records.
- `error_message` — short summary when a collector failed with no records.

Status rules:

- `success` — collector ran without warnings.
- `partial` — collector produced records and also warnings.
- `failed` — collector produced no records and had warnings or an exception.
- `skipped` — collector was disabled or had no runnable tasks.

New collectors should keep source-local failures non-fatal when that matches the existing collector pattern. Let unexpected task exceptions surface to the orchestrator so telemetry can record them.

Daily runs persist telemetry by calling the telemetry entrypoints with `persist_telemetry=True`. Persisted rows are written to `data/collector_runs.jsonl` through the storage layer. Persistence failures are logged as non-fatal messages and are not surfaced in reports. The storage layer keeps the last 90 run dates and caps the artifact at the most recent 5,000 valid rows.

### Local Diagnostics

Use the local diagnostics command to inspect recent collector health without
running collectors or calling external APIs:

```bash
python scripts/diagnose_collectors.py --days 7
python scripts/diagnose_collectors.py --collector rss
python scripts/diagnose_collectors.py --status failed --limit 25
```

The command reads `data/collector_runs.jsonl` and prints a plain Markdown-style
summary grouped by collector:

```text
Collector Health (last 7 days)
Rows analyzed: 12

| Collector | Success | Partial | Failed | Skipped | Latest Status | Latest Records | Avg Duration |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rss | 6 | 1 | 0 | 0 | success | 14 | 1.42s |

Recent warnings/errors:
- 2026-07-05 github [failed] api unavailable
```

Malformed telemetry rows are skipped through the storage diagnostics path and
reported as a count. This command is read-only and does not affect daily
reports.

Optional health-check mode can return a nonzero exit code when recent collector
health violates explicit thresholds:

```bash
python scripts/diagnose_collectors.py --health-check --max-failed-rate 0.25
python scripts/diagnose_collectors.py --health-check --collector github --max-consecutive-failures 1
python scripts/diagnose_collectors.py --health-check --require-recent-success --min-record-count 1
```

Health-check options:

- `--max-failed-rate`
- `--max-partial-rate`
- `--max-consecutive-failures`
- `--min-record-count`
- `--max-avg-duration`
- `--require-recent-success`

Exit code `0` means the selected telemetry is healthy. Exit code `1` means no
matching telemetry was found or one or more thresholds were violated. The health
check is local and read-only; it is not wired into CI or daily runs by default.

### Manual Workflow

`.github/workflows/collector-health.yml` provides an optional manual GitHub
Actions entrypoint named `Collector Health Check`. It only runs from
`workflow_dispatch`; it is not part of push/PR CI and is not required for
merges.

The workflow checks the existing `data/collector_runs.jsonl` artifact. It does
not run collectors, does not run the daily pipeline, does not call external
APIs, and has read-only repository permissions. If the telemetry artifact is
missing, the workflow prints a clear message and fails the health check.

Manual inputs mirror the local command:

- `days`
- `collector`
- `max_failed_rate`
- `max_partial_rate`
- `max_consecutive_failures`
- `min_record_count`
- `max_avg_duration`
- `require_recent_success`

Equivalent local command:

```bash
python scripts/diagnose_collectors.py \
  --health-check \
  --days 7 \
  --max-failed-rate 0.25 \
  --max-consecutive-failures 1
```

## Retry Policy

Network collectors use `scripts/collectors/retry.py` for safe, idempotent calls. The shared helper supports:

- `max_attempts`
- `initial_delay_seconds`
- exponential `backoff_multiplier`
- optional `jitter_seconds`
- retryable exception filtering
- warning records for retry attempts and final failures

The default network retry policy is conservative: low attempt count and short delay. It is meant to smooth transient network/service failures, not hide persistent source problems.

Retry these operations:

- HTTP `GET` calls to RSS, Hacker News, Hugging Face, arXiv, and GitHub.
- Web-search client `search(...)` calls.
- Other idempotent source reads.

Do not retry:

- XML/JSON parsing errors after a response is received.
- Invalid source configuration.
- Deterministic data-shape errors.
- Non-retryable client errors such as most HTTP 4xx responses. HTTP 408 and 429 remain retryable.

Retry warnings are appended to collector telemetry. A collector that succeeds after a retry may be reported as `partial` because it produced records and warnings. A collector that exhausts retries with no records is reported as `failed`. Failures remain non-fatal unless the collector was already fatal before this policy existed.

## Provider-Neutral Web Search

Collectors must not import a provider SDK or a legacy provider-named client directly. Text/JSON LLM work belongs behind `PromptRunner`; web-search collection belongs behind `WebSearchClient`. Production uses `ProviderWebSearchClient`, which sends search through the same configured provider order as other LLM capabilities. Deprecated provider-named wrappers remain confined to the compatibility boundary.

Allowed web-search dependency:

```python
from web_search_client import WebSearchClient
```

Forbidden in collector modules:

```python
import anthropic
import openai
```

Provider-native search support depends on the configured model, account, region, and tool availability. Eligible provider failures fall through to the next configured provider; invalid search result shapes are rejected before collection succeeds.

`tests/test_migrated_analyzers_no_direct_claude.py` scans production scripts recursively and confines legacy provider-named calls to explicit compatibility files.
