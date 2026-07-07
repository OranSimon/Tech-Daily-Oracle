"""Typed configuration models for domain rules."""

from __future__ import annotations

import warnings as py_warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

from tech_daily.config.normalization_policy import NormalizationScoringPolicy

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZATION_CONFIG_PATH = ROOT_DIR / "config" / "normalization_rules.yml"
REQUIRED_TOPIC_GROUPS = ("core_tech_topics", "cross_domain_topics", "high_priority_topics")
LEGACY_TOPIC_GROUP_DEFAULTS = {
    "core_tech_topics": [
        "ai_models",
        "ai_agents",
        "embodied_ai_robotics",
        "ai_infrastructure",
        "semiconductors",
        "startups_unicorns",
        "papers_research",
    ],
    "cross_domain_topics": [
        "science_breakthrough",
        "health_biotech",
        "astronomy_space",
        "materials_science",
        "global_events",
    ],
    "high_priority_topics": [
        "ai_models",
        "embodied_ai_robotics",
        "ai_infrastructure",
        "semiconductors",
        "papers_research",
        "startups_unicorns",
    ],
}


class ConfigValidationError(ValueError):
    """Raised when a domain configuration has an invalid shape."""


class ConfigRuntimeWarning(UserWarning):
    """Emitted for backward-compatible config fallbacks that may affect semantics."""


@dataclass(frozen=True)
class ConfigWarning:
    field: str
    message: str


@dataclass
class ConfigDiagnostics:
    warnings: list[ConfigWarning] = field(default_factory=list)

    def add(self, *, field: str, message: str) -> None:
        self.warnings.append(ConfigWarning(field=field, message=message))


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping_without_duplicate_keys(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_without_duplicate_keys,
)


@dataclass(frozen=True)
class NormalizationConfig:
    topic_keywords: dict[str, list[str]]
    company_keywords: dict[str, list[str]]
    topic_groups: dict[str, list[str]] = field(default_factory=dict)
    scoring_policy: NormalizationScoringPolicy = field(default_factory=NormalizationScoringPolicy)

    @classmethod
    def from_mapping(
        cls,
        data: dict[str, Any],
        *,
        allow_duplicate_company_aliases: bool = False,
        strict_topic_groups: bool = False,
        diagnostics: ConfigDiagnostics | None = None,
        warn_missing_topic_groups: bool = False,
    ) -> NormalizationConfig:
        for field_name in ["topic_keywords", "company_keywords"]:
            if field_name not in data:
                raise ConfigValidationError(f"normalization config missing required section {field_name}")
        topic_keywords = _validate_keywords(data.get("topic_keywords", {}), "topic_keywords")
        company_keywords = _validate_keywords(data.get("company_keywords", {}), "company_keywords")
        topic_groups = _validate_topic_groups(
            data.get("topic_groups"),
            topic_keywords,
            require_non_empty_groups="topic_groups" in data,
            strict_topic_groups=strict_topic_groups,
            diagnostics=diagnostics,
            warn_missing_topic_groups=warn_missing_topic_groups,
        )
        if not allow_duplicate_company_aliases:
            _validate_unique_company_aliases(company_keywords)
        return cls(
            topic_keywords=topic_keywords,
            company_keywords=company_keywords,
            topic_groups=topic_groups,
            scoring_policy=NormalizationScoringPolicy(),
        )


def load_normalization_config(
    path: str | Path | None = None,
    *,
    allow_missing: bool = False,
    strict_topic_groups: bool = False,
    diagnostics: ConfigDiagnostics | None = None,
) -> NormalizationConfig:
    selected_path = DEFAULT_NORMALIZATION_CONFIG_PATH if path is None else Path(path)
    if selected_path.exists():
        with open(selected_path, encoding="utf-8") as handle:
            try:
                loaded = yaml.load(handle, Loader=_UniqueKeyLoader) or {}
            except ConstructorError as exc:
                raise ConfigValidationError(str(exc)) from exc
        if not isinstance(loaded, dict):
            raise ConfigValidationError("normalization config must be a mapping")
        return NormalizationConfig.from_mapping(
            loaded,
            allow_duplicate_company_aliases=_is_default_normalization_path(selected_path),
            strict_topic_groups=strict_topic_groups,
            diagnostics=diagnostics,
            warn_missing_topic_groups=not _is_default_normalization_path(selected_path),
        )

    if path is not None and not allow_missing:
        raise FileNotFoundError(selected_path)

    if selected_path != DEFAULT_NORMALIZATION_CONFIG_PATH and DEFAULT_NORMALIZATION_CONFIG_PATH.exists():
        return load_normalization_config(DEFAULT_NORMALIZATION_CONFIG_PATH)

    raise FileNotFoundError(selected_path)


def _is_default_normalization_path(path: Path) -> bool:
    return path.resolve() == DEFAULT_NORMALIZATION_CONFIG_PATH.resolve()


def _validate_keywords(value: Any, field_name: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"{field_name} must be a mapping")
    validated: dict[str, list[str]] = {}
    for key, keywords in value.items():
        if not isinstance(key, str) or not key:
            raise ConfigValidationError(f"{field_name} keys must be non-empty strings")
        if not isinstance(keywords, list) or not all(isinstance(keyword, str) for keyword in keywords):
            raise ConfigValidationError(f"{field_name}.{key} must be a list of strings")
        if not keywords and not (field_name == "topic_keywords" and key == "general_interesting"):
            raise ConfigValidationError(f"{field_name}.{key} must not be empty")
        validated[key] = list(keywords)
    return validated


def _validate_unique_company_aliases(company_keywords: dict[str, list[str]]) -> None:
    seen: dict[str, str] = {}
    for company, aliases in company_keywords.items():
        for alias in aliases:
            normalized = alias.casefold()
            previous = seen.get(normalized)
            if previous is not None and previous != company:
                raise ConfigValidationError(
                    f"duplicate company alias {alias!r} appears in both {previous!r} and {company!r}"
                )
            seen[normalized] = company


def _validate_topic_groups(
    value: Any,
    topic_keywords: dict[str, list[str]],
    *,
    require_non_empty_groups: bool,
    strict_topic_groups: bool,
    diagnostics: ConfigDiagnostics | None,
    warn_missing_topic_groups: bool,
) -> dict[str, list[str]]:
    if value is None:
        if strict_topic_groups:
            raise ConfigValidationError("normalization config missing required section topic_groups")
        if warn_missing_topic_groups:
            message = (
                "topic_groups is missing; legacy-compatible groups were derived; "
                "scoring behavior may differ if topic IDs differ from defaults"
            )
            if diagnostics is not None:
                diagnostics.add(field="topic_groups", message=message)
            py_warnings.warn(message, ConfigRuntimeWarning, stacklevel=3)
        return {
            group_name: [topic for topic in topics if topic in topic_keywords]
            for group_name, topics in LEGACY_TOPIC_GROUP_DEFAULTS.items()
        }
    if not isinstance(value, dict):
        raise ConfigValidationError("topic_groups must be a mapping")

    validated: dict[str, list[str]] = {}
    for group_name in REQUIRED_TOPIC_GROUPS:
        members = value.get(group_name)
        if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
            raise ConfigValidationError(f"topic_groups.{group_name} must be a list of strings")
        if require_non_empty_groups and not members:
            raise ConfigValidationError(f"topic_groups.{group_name} must not be empty")

        seen: set[str] = set()
        group_members: list[str] = []
        for member in members:
            if member in seen:
                raise ConfigValidationError(f"duplicate topic group member {member!r} in topic_groups.{group_name}")
            if member not in topic_keywords:
                raise ConfigValidationError(f"topic_groups.{group_name} references unknown topic {member!r}")
            seen.add(member)
            group_members.append(member)
        validated[group_name] = group_members
    return validated
