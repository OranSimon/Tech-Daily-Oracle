# Package Layout Migration Plan

Phase 17 recorded the target package layout and compatibility rules. Phase 22
added the first package facade. Phase 27 migrated the low-risk runtime context
foundation module into the package while preserving the script import path.

The existing script entrypoints remain authoritative unless a package-owned
replacement is called out explicitly:

- `scripts/run_daily.py`
- `scripts/run_weekly_review.py`
- `scripts/run_monthly_review.py`

`src/tech_daily/cli/run_daily.py` is now the primary daily CLI implementation.
It preserves the existing `--date` and `--force` behavior, owns the daily
orchestration flow, and remains import-compatible for package callers.
`scripts/run_daily.py` is the compatibility wrapper for direct script
invocation. Both daily entrypoints use
`tech_daily.cli.daily_parser.build_daily_arg_parser()` so user-facing options
do not drift while both surfaces remain supported.

`src/tech_daily/runtime/run_context.py` now owns `AppConfig` and `RunContext`.
`scripts/run_context.py` is a compatibility facade that re-exports those classes
for existing script imports. New package-oriented code should import from
`tech_daily.runtime.run_context`; existing scripts may continue using
`run_context` during the migration.

`src/tech_daily/runtime/run_logging.py` now owns `RunLogger` and
`RunLogEvent`. `scripts/run_logging.py` is the matching compatibility facade for
legacy script imports.

`src/tech_daily/pipeline/step.py` now owns `PipelineStep`,
`PipelineStepResult`, and step-summary helpers. `scripts/pipeline_step.py` is
the matching compatibility facade for legacy script imports.

`src/tech_daily/pipeline/policy.py` now owns step IDs and daily step policy.
`src/tech_daily/pipeline/state.py` now owns typed compatibility state slices.
`src/tech_daily/pipeline/daily.py` now owns daily pipeline composition.
`src/tech_daily/pipeline/actions.py` now owns named daily step action
functions.
The matching `scripts/` modules are compatibility facades.

`src/tech_daily/storage/context.py` now owns `StorageContext` and typed storage
path helpers. Storage behavior is now split across
`tech_daily.storage.reports`, `tech_daily.storage.predictions`,
`tech_daily.storage.events`, and `tech_daily.storage.telemetry`.
`scripts/storage.py` remains the business-facing storage facade and re-exports
the package-owned storage surface for callers that still import from `storage`.

`src/tech_daily/llm/client.py`, `src/tech_daily/llm/prompt_runner.py`, and
`src/tech_daily/llm/schemas.py` now own the LLM boundary. The matching
`scripts/llm_client.py`, `scripts/prompt_runner.py`, and
`scripts/llm_schemas.py` modules are transitional compatibility facades so
existing script imports keep resolving to the package-owned implementation.

`src/tech_daily/reports/daily.py` now owns daily report payload construction
and prompt-driven report generation. `scripts/generate_report.py` is the
matching compatibility facade for legacy script imports and script execution.

Low-risk consumers should import migrated foundation modules from package paths
instead of going through script facades. For example:

- use `tech_daily.runtime.run_context` instead of `run_context`
- use `tech_daily.runtime.run_logging` instead of `run_logging`
- use `tech_daily.pipeline.step` instead of `pipeline_step`
- use `tech_daily.llm.client` or `tech_daily.llm.prompt_runner` instead of
  `llm_client` and `prompt_runner`
- use `tech_daily.llm.schemas` instead of `llm_schemas`
- use `tech_daily.storage.io` instead of `storage_io`
- use `tech_daily.storage.validation` instead of `storage_validation`
- use `tech_daily.storage.context` for typed storage paths

The script facades remain available for compatibility, but new production code
should prefer the package import path once a module has moved.

## Target Shape

The eventual target is an installable package under `src/tech_daily/`:

```text
src/tech_daily/
  collectors/
  config/
  llm/
  pipeline/
  reports/
  storage/
  state/
```

Suggested namespace mapping:

- `tech_daily.collectors`: per-source collectors, registry, retry, telemetry,
  and web-search collection boundary.
- `tech_daily.llm`: `LLMClient`, `PromptRunner`, schemas, and provider
  adapters.
- `tech_daily.pipeline`: run context, step wrappers, step policy, daily
  orchestration helpers, and typed state slices.
- `tech_daily.reports`: daily, weekly, and monthly report rendering/generation
  paths.
- `tech_daily.storage`: atomic writes, JSONL validation, telemetry persistence,
  and artifact loaders.
- `tech_daily.config`: typed configuration models and externalized domain
  rules.

## Migration Order

1. Keep all existing `scripts/*` entrypoints working.
2. Move foundation modules first: config models, errors, storage IO,
   runtime context, logging, pipeline step helpers, and collector telemetry.
3. Add script-level compatibility facade modules that import from the package
   after each move.
4. Move collectors after their facade imports and no-network tests are in
   place.
5. Move LLM boundary modules only after adapter tests prove imports remain
   network-free.
6. Move daily orchestration helpers before moving CLI entrypoints.
7. Move CLI ownership into the package only after the corresponding script
   entrypoint still passes existing smoke tests. The daily CLI is now
   package-owned; weekly and monthly wrappers are still deferred.

When adding a daily CLI option, add it to
`tech_daily.cli.daily_parser.build_daily_arg_parser()` and keep the package
facade tests green. Do not add options separately in `scripts/run_daily.py` or
`src/tech_daily/cli/run_daily.py`.

The first migrated modules are `tech_daily.runtime.run_context`,
`tech_daily.runtime.run_logging`, and `tech_daily.pipeline.step`. Good next
foundation candidates are storage IO or validation helpers, one module at a
time.

The next package-owned orchestration modules are `tech_daily.pipeline.daily`
and `tech_daily.pipeline.actions`. `scripts/daily_pipeline.py` and
`scripts/daily_step_actions.py` remain as compatibility wrappers.

The next package-owned LLM modules are now `tech_daily.llm.client`,
`tech_daily.llm.prompt_runner`, and `tech_daily.llm.schemas`. The legacy
script paths remain wrappers only.

The next package-owned report module is now `tech_daily.reports.daily`.
`scripts/generate_report.py` remains a wrapper only.

## Compatibility Rules

- Do not remove `scripts/run_daily.py`, `scripts/run_weekly_review.py`, or
  `scripts/run_monthly_review.py` during the migration.
- Do not change report formats, storage formats, source-event schemas, or
  prediction JSONL schemas.
- Do not change prompt semantics or model defaults as part of package movement.
- Do not use package migration as a reason to split `TechDailyState`.
- Keep the old import path as a compatibility facade until downstream tests and
  workflows use the package path.

## Rollback Plan

Each moved module should be reversible by restoring the script module body and
removing the package import facade. Avoid cross-cutting moves that require
multiple domains to be rolled back together.

Run the full compatibility gate after every package move:

```bash
.venv/bin/python -m pytest -q
xargs .venv/bin/ruff format --check < stable_paths
xargs .venv/bin/ruff check < stable_paths
.venv/bin/mypy
.venv/bin/python -m compileall -q scripts
.venv/bin/python scripts/run_daily.py --date 2026-07-02
.venv/bin/python -m tech_daily.cli.run_daily --date 2026-07-02
```

The module entrypoint command requires either an editable install
(`.venv/bin/python -m pip install -e ".[dev]"`) or `src` on `PYTHONPATH`.
The `stable_paths` file should contain the paths from
`tool.tech_daily.quality.stable_paths`.

Some transitional facades still insert `src` or `scripts` onto `sys.path` so
legacy script execution keeps working before the full package migration. Treat
that as compatibility scaffolding: do not add new business logic to those
facades.

## Remaining Path Scaffolding

The following `sys.path` adjustments remain intentional:

- `scripts/run_daily.py` adds `scripts/` for legacy script modules and `src/`
  for package imports, then delegates to the package-owned daily CLI.
- `src/tech_daily/cli/run_daily.py` adds `scripts/` so the package-owned CLI
  can continue importing the transitional `state` module without changing daily
  behavior.
- `scripts/run_context.py`, `scripts/run_logging.py`,
  `scripts/pipeline_policy.py`, `scripts/pipeline_state.py`,
  `scripts/pipeline_step.py`, `scripts/daily_pipeline.py`,
  `scripts/daily_step_actions.py`, `scripts/llm_client.py`,
  `scripts/prompt_runner.py`, `scripts/llm_schemas.py`, `scripts/storage_io.py`,
  and `scripts/storage.py`, and `scripts/storage_validation.py` add `src/` only
  to re-export package-owned implementations for old import paths.
- `scripts/run_weekly_review.py`, `scripts/run_monthly_review.py`, and the
  `normalize_sources.py` direct-run helper still use script-path scaffolding
  because those paths have not been package-migrated yet.

Future package migration should remove these one at a time after each caller has
package-native imports and the corresponding script entrypoint compatibility
tests still pass.

## Package Boundary Guard

Package modules under `src/tech_daily/` must not import legacy script modules
such as `state`, `storage`, `run_daily`, `daily_pipeline`,
`daily_step_actions`, `pipeline_state`, or `pipeline_policy`. During the
transition, `src/tech_daily/cli/run_daily.py` and
`src/tech_daily/pipeline/state.py` are temporary `state` import exceptions
while `TechDailyState` remains compatibility-backed. The
`src/tech_daily/pipeline/daily.py` and `src/tech_daily/pipeline/actions.py`
modules still carry temporary `state` imports for type compatibility, but
storage access must stay on `tech_daily.storage` package modules.

New `sys.path.insert(...)` usage is forbidden outside the explicit transition
allowlist guarded by `tests/test_package_facade.py`.

## Simplification Policy

The package migration is intentionally incremental. The goal is not to remove
every script file immediately. The goal is to ensure new business logic has a
clear package home while old user-facing script entrypoints remain stable.

Good migration candidates are small foundation modules with few dependencies.
Avoid broad migrations that change report format, storage format, prediction
schema, source-event schema, or CLI behavior.

See `docs/architecture_boundaries.md` for non-goals and wrapper rules.
