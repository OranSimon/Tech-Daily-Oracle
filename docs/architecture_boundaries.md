# Architecture Boundaries

This project is a maintainable automation system, not a distributed platform.
Architecture changes should reduce coupling, duplicate paths, or operational risk.
They should not add layers only to make the code look more enterprise.

## Intentional Compatibility Boundary

TechDailyState remains the compatibility shell for the daily pipeline.
Do not delete it or rename its public fields unless a separate migration plan
also protects report format, storage format, prediction schema, and CLI behavior.

Typed state slices are useful for new code, but they are adapters around the
compatibility state rather than a mandate to rewrite all existing behavior.

## Package and Script Boundary

New business logic should live under src/tech_daily/.
scripts/ entrypoints may remain as compatibility wrappers for existing user and
GitHub Actions behavior.

Compatibility wrappers should be thin:

- import or re-export package-owned functions and classes
- avoid owning business rules
- avoid duplicating parser, storage, LLM, or pipeline behavior

## Non-Goals

Do not introduce a workflow engine.
Do not introduce dynamic plugin loading.
Do not introduce a database.
Do not split every analyzer into multiple layers.
Do not migrate the whole repository in one broad package-layout change.

## Preferred Guardrails

Prefer focused tests over new frameworks:

- report contract tests
- storage schema and append-safety tests
- no-direct-Claude boundary tests
- package/script CLI parity tests
- package-only import tests
- quality-path scope tests
