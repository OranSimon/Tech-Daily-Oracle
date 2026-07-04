"""Typed configuration models for domain rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_NORMALIZATION_CONFIG_PATH = ROOT_DIR / "config" / "normalization_rules.yml"


class ConfigValidationError(ValueError):
    """Raised when a domain configuration has an invalid shape."""


@dataclass(frozen=True)
class NormalizationConfig:
    topic_keywords: dict[str, list[str]]
    company_keywords: dict[str, list[str]]

    @classmethod
    def from_mapping(
        cls,
        data: dict[str, Any],
        *,
        allow_duplicate_company_aliases: bool = False,
    ) -> NormalizationConfig:
        topic_keywords = _validate_keywords(data.get("topic_keywords", {}), "topic_keywords")
        company_keywords = _validate_keywords(data.get("company_keywords", {}), "company_keywords")
        if not allow_duplicate_company_aliases:
            _validate_unique_company_aliases(company_keywords)
        return cls(topic_keywords=topic_keywords, company_keywords=company_keywords)


def load_normalization_config(
    path: str | Path | None = None,
    *,
    allow_missing: bool = False,
) -> NormalizationConfig:
    selected_path = DEFAULT_NORMALIZATION_CONFIG_PATH if path is None else Path(path)
    if selected_path.exists():
        with open(selected_path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ConfigValidationError("normalization config must be a mapping")
        return NormalizationConfig.from_mapping(
            loaded,
            allow_duplicate_company_aliases=_is_default_normalization_path(selected_path),
        )

    if path is not None and not allow_missing:
        raise FileNotFoundError(selected_path)

    # Compatibility default: import the current in-code normalization rules.
    # This keeps matching behavior fixed if the external rules file is absent.
    from normalize_sources import COMPANY_KEYWORDS, TOPIC_KEYWORDS

    return NormalizationConfig.from_mapping(
        {
            "topic_keywords": TOPIC_KEYWORDS,
            "company_keywords": COMPANY_KEYWORDS,
        },
        allow_duplicate_company_aliases=True,
    )


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
