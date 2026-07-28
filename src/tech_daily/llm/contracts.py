"""Provider-neutral requests and responses for LLM capabilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

__all__ = [
    "Capability",
    "FinishReason",
    "LLMResponse",
    "ModelRole",
    "SearchRequest",
    "SearchResponse",
    "StructuredRequest",
    "TextRequest",
]


class ModelRole(StrEnum):
    """Provider-independent model tiers selected by business code."""

    FAST = "fast"
    DEFAULT = "default"
    DEEP = "deep"


class Capability(StrEnum):
    """Operations an LLM provider adapter can perform."""

    TEXT = "generate_text"
    JSON = "generate_json"
    STRUCTURED = "generate_structured"
    SEARCH = "search_web"
    CONTINUATION = "continue_text"


class FinishReason(StrEnum):
    """Normalized reasons an LLM provider stopped producing text."""

    COMPLETE = "complete"
    MAX_TOKENS = "max_tokens"
    REFUSAL = "refusal"
    SAFETY = "safety"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TextRequest:
    """A provider-neutral text generation request."""

    system: str
    user: str
    role: ModelRole = ModelRole.DEFAULT
    max_output_tokens: int = 4096
    cache_system: bool = True


@dataclass(frozen=True)
class StructuredRequest:
    """A text request whose response must conform to ``json_schema``."""

    system: str
    user: str
    json_schema: Mapping[str, Any]
    role: ModelRole = ModelRole.DEFAULT
    max_output_tokens: int = 4096
    cache_system: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "json_schema", _freeze_mapping(self.json_schema))


@dataclass(frozen=True)
class SearchRequest:
    """A provider-neutral web-search request."""

    query: str
    max_results: int = 5
    role: ModelRole = ModelRole.DEFAULT
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class LLMResponse:
    """Normalized text returned by a provider."""

    text: str
    provider: str
    model: str
    finish_reason: FinishReason = FinishReason.COMPLETE


@dataclass(frozen=True)
class SearchResponse:
    """Normalized web-search results returned by a provider."""

    results: Sequence[Mapping[str, Any]]
    provider: str
    model: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(_freeze_mapping(result) for result in self.results))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return value
