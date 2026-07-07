# Configuration Models

The project still preserves the existing `config.yml` format. New typed config
wrappers should be introduced only where they reduce raw dictionary access
without changing runtime behavior.

## NormalizationConfig

`scripts/config_models.py` defines `NormalizationConfig` for topic and company
keyword rules:

- `topic_keywords`: mapping of topic id to keyword strings
- `company_keywords`: mapping of company name to alias strings
- `topic_groups`: mapping of semantic group name to topic ids

The default rules live in `config/normalization_rules.yml`, which is the
authoritative source for topic keywords, company aliases, and topic group
membership.
`load_normalization_config()` reads that file by default. If a caller provides a
custom path with `allow_missing=True` and that file is absent, the loader falls
back to the authoritative default YAML file.

The default rules intentionally allow historical alias overlap, such as aliases
shared between parent companies and sub-brands.

External YAML files loaded through `load_normalization_config(path)` are
validated more strictly:

- top-level data must be a mapping
- `topic_keywords` and `company_keywords` are required sections
- duplicate YAML keys are rejected instead of silently overwritten
- `topic_keywords` and `company_keywords` must be mappings
- each key must be a non-empty string
- each keyword list must contain strings
- company alias lists must not be empty
- company aliases cannot be duplicated across companies
- `topic_groups` entries must reference existing `topic_keywords` ids
- duplicate topic group members are rejected
- configured required topic groups must not be empty

`scripts/normalize_sources.py` contains runtime normalization logic only. It no
longer duplicates the authoritative keyword, alias, or topic group tables.
The default YAML currently owns these normalization groups:

- `core_tech_topics`: topics treated as core technology signals for
  cross-domain and high-score Hacker News logic.
- `cross_domain_topics`: science/global topics that earn a boost when paired
  with a core tech topic.
- `high_priority_topics`: topics that receive the existing high-priority
  importance boost.

Older custom normalization YAML files without `topic_groups` still load for
compatibility. In that case, the loader derives empty or legacy-compatible
groups from topic ids present in the custom file; new configs should define
`topic_groups` explicitly. Loading a custom file without `topic_groups` now
emits a `ConfigRuntimeWarning`; callers that need structured reporting can pass
`ConfigDiagnostics` to `load_normalization_config(...)`.

Use `load_normalization_config(path, strict_topic_groups=True)` when validating
new or CI-managed custom configs. Strict mode rejects configs that omit
`topic_groups` instead of deriving fallback groups.

Callers that need deterministic tests can pass a `NormalizationConfig` directly
to `normalize_events(...)` or `normalize_collection_state(...)`.

## Normalization Scoring Policy

Normalization scoring now reads from `NormalizationConfig.scoring_policy`. The
default policy intentionally preserves the historical constants. YAML parsing
for scoring weights is deferred until each field has fixture coverage.
Source reliability defaults now live under
`NormalizationConfig.scoring_policy.source_reliability_policy`, with
compatibility accessors on `NormalizationScoringPolicy` preserving the existing
default values.

To add a new reportable topic safely:

1. Add the topic id and keyword list under `topic_keywords`.
2. Add the topic id to any relevant `topic_groups`.
3. Run the config and normalization tests so invalid references or accidental
   drift fail before runtime.

## Adding Typed Config

When adding a new typed config model:

- keep the existing config file format compatible
- validate only fields the code currently consumes
- keep raw config access available while migration is partial
- add tests that compare typed defaults against existing behavior
- document any compatibility exceptions explicitly
