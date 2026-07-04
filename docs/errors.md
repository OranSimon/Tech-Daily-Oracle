# Error Taxonomy

`scripts/pipeline_errors.py` defines the shared error foundation for future
pipeline hardening. It is intentionally small and does not change current daily
pipeline behavior by itself.

## Error Classes

Use `TechDailyError` as the base class for expected pipeline failures. Prefer a
more specific subclass when the failure category is known:

- `ConfigError`
- `StorageError`
- `ValidationError`
- `ProviderError`
- `AnalyzerError`
- `ReportGenerationError`
- `NonFatalStepError`

Each typed error can produce an `ErrorDiagnostic` with:

- `category`
- `severity`
- `message`
- `exception_type`
- optional `step`
- optional `details`

Unexpected exceptions can be normalized with
`diagnostic_from_exception(...)`.

## Broad Exception Catches

Broad `except Exception` catches are allowed only at compatibility and boundary
points where the existing behavior is explicitly non-fatal, such as collector
fallbacks, storage diagnostics, provider adapters, and `PipelineStep` wrappers.

When touching code with broad catches:

- keep the catch as narrow as the behavior allows
- preserve existing fatal/non-fatal behavior
- record a structured warning or diagnostic when possible
- do not silently discard malformed persisted data
- do not catch provider or storage failures inside business logic unless the
  caller already expects fallback behavior

Bare `except:` blocks are not allowed in production scripts.

Migrated analyzers also have a focused regression guard: they may keep
compatibility fallback behavior, but they must not silently swallow
`Exception` with a `pass`-only handler. If a migrated analyzer catches a
best-effort failure, it should catch the narrow expected exception types where
possible and emit at least a concise diagnostic before returning the existing
fallback.

## Future Use

Future phases should gradually replace ad hoc string errors and silent warnings
with typed errors at module boundaries. This should be done one domain at a time
and should not change report formats, storage formats, or daily pipeline order.
