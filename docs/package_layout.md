# Package Layout Migration Plan

Phase 17 does not move runtime code. It records the target package layout and
the compatibility rules for a future migration.

No runtime package wrapper is introduced in Phase 17. The existing script
entrypoints remain authoritative:

- `scripts/run_daily.py`
- `scripts/run_weekly_review.py`
- `scripts/run_monthly_review.py`

These files should remain as compatibility facade entrypoints until the package
entrypoints have equivalent CLI coverage, smoke tests, and rollback instructions.

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
7. Add package CLI wrappers only after `scripts/run_daily.py` still passes the
   existing daily smoke tests.

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
.venv/bin/ruff format --check tests scripts/config_models.py scripts/collectors/retry.py scripts/collectors/telemetry.py scripts/pipeline_errors.py scripts/pipeline_policy.py scripts/pipeline_state.py scripts/pipeline_step.py scripts/run_context.py scripts/run_logging.py scripts/storage_io.py scripts/storage_validation.py
.venv/bin/ruff check tests scripts/config_models.py scripts/collectors/retry.py scripts/collectors/telemetry.py scripts/pipeline_errors.py scripts/pipeline_policy.py scripts/pipeline_state.py scripts/pipeline_step.py scripts/run_context.py scripts/run_logging.py scripts/storage_io.py scripts/storage_validation.py
.venv/bin/mypy
.venv/bin/python -m compileall -q scripts
.venv/bin/python scripts/run_daily.py --date 2026-07-02
```
