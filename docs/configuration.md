# Configuration Models

The project still preserves the existing `config.yml` format. New typed config
wrappers should be introduced only where they reduce raw dictionary access
without changing runtime behavior.

## NormalizationConfig

`scripts/config_models.py` defines `NormalizationConfig` for topic and company
keyword rules:

- `topic_keywords`: mapping of topic id to keyword strings
- `company_keywords`: mapping of company name to alias strings

The default rules live in `config/normalization_rules.yml`.
`load_normalization_config()` reads that file by default. If the default file is
missing, the loader falls back to the legacy in-code rules in
`scripts/normalize_sources.py` so existing script behavior remains compatible.

The default rules intentionally allow historical alias overlap, such as aliases
shared between parent companies and sub-brands.

External YAML files loaded through `load_normalization_config(path)` are
validated more strictly:

- top-level data must be a mapping
- `topic_keywords` and `company_keywords` must be mappings
- each key must be a non-empty string
- each keyword list must contain strings
- company aliases cannot be duplicated across companies

This lets future phases externalize domain rules safely while preserving the
existing normalization behavior today.

Callers that need deterministic tests can pass a `NormalizationConfig` directly
to `normalize_events(...)` or `normalize_collection_state(...)`.

## Adding Typed Config

When adding a new typed config model:

- keep the existing config file format compatible
- validate only fields the code currently consumes
- keep raw config access available while migration is partial
- add tests that compare typed defaults against existing behavior
- document any compatibility exceptions explicitly
