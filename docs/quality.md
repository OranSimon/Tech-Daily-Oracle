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

## Mypy

Mypy currently checks the stable production foundation modules listed in
`tool.mypy.files`. It uses `follow_imports = "silent"` so the gate does not
accidentally expand into legacy script modules before they are intentionally
migrated.

Do not add the whole `scripts/` tree at once. Add modules one domain at a time
after their tests and typing surface are ready.
