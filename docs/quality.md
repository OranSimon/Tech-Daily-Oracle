# Quality Scope

The default CI keeps quality gates explicit while the project is still partly
script-oriented.

## Ruff

Ruff format and lint currently run against:

- `tests`
- stable production foundation modules listed in
  `tool.tech_daily.quality.stable_paths`

New production modules should be added to that list when they are stable enough
for formatting and lint enforcement.

The current stable production scope includes:

- package facade files under `src/tech_daily/`
- package runtime context/logging files under `src/tech_daily/runtime/`
- collector modules under `scripts/collectors/`
- `scripts/daily_pipeline.py`
- `scripts/daily_step_actions.py`
- `scripts/generate_report.py`
- `scripts/storage.py` plus storage IO/validation helpers
- selected pipeline, runtime, and config foundation modules

## Mypy

Mypy currently checks the stable production foundation modules listed in
`tool.mypy.files`. It uses `follow_imports = "silent"` so the gate does not
accidentally expand into legacy script modules before they are intentionally
migrated.

Do not add the whole `scripts/` tree at once. Add modules one domain at a time
after their tests and typing surface are ready.

Package foundation modules under `tech_daily.runtime.*` and
`tech_daily.pipeline.*` have a stricter scoped mypy override:

- `check_untyped_defs = true`
- `warn_return_any = true`

`tech_daily.storage.*` is now under the same stricter scoped mypy settings:

- `check_untyped_defs = true`
- `warn_return_any = true`

## Newly Strict Domains

The LLM, report, and prediction result package modules are now in stable Ruff
and mypy scope. New package modules in these domains must be added to
`tool.tech_daily.quality.stable_paths` and `tool.mypy.files` in the same change.

Keep strictness scoped. Add another module group only after it has focused tests
and behavior-neutral type cleanup.

Do not enable global strict mode until the remaining script-oriented modules are
package-migrated into similarly testable scopes.

Still-excluded production modules are legacy or high-churn business modules such
as analyzer implementations, weekly/monthly review scripts, and remaining
package-migration targets. Add the next group by updating both
`tool.tech_daily.quality.stable_paths` and `tool.mypy.files`. CI generates
`quality-paths.txt` from `tool.tech_daily.quality.stable_paths` using
`python -m tech_daily.quality_paths`, so local and CI quality scopes stay in one
place.

Phase 28 added the main storage facade, `scripts/storage.py`, to both ruff and
mypy scope. The next likely quality-scope candidates are prediction update
logic or weekly/monthly review generation, but only after focused tests make any
typing cleanup behavior-neutral.
