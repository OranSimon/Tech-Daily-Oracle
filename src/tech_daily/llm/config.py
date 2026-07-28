"""Configuration loading and legacy model-name compatibility for the LLM boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml

from tech_daily.llm.contracts import ModelRole
from tech_daily.llm.errors import LLMConfigurationError

__all__ = ["LLMConfigurationError", "LLMSettings", "ProviderSettings", "load_llm_settings", "resolve_role"]


_DEFAULT_PROVIDER_ORDER: Final = ("deepseek", "claude", "openai", "gemini")
_DEFAULT_PROVIDER_MODELS: Final = {
    "deepseek": {
        ModelRole.DEFAULT: "deepseek-v4-flash",
        ModelRole.FAST: "deepseek-v4-flash",
        ModelRole.DEEP: "deepseek-v4-pro",
    },
    "claude": {
        ModelRole.DEFAULT: "claude-sonnet-4-6",
        ModelRole.FAST: "claude-haiku-4-5-20251001",
        ModelRole.DEEP: "claude-opus-4-7",
    },
    "openai": {
        ModelRole.DEFAULT: "gpt-5.5",
        ModelRole.FAST: "gpt-5.4-nano",
        ModelRole.DEEP: "gpt-5.5",
    },
    "gemini": {
        ModelRole.DEFAULT: "gemini-2.5-flash",
        ModelRole.FAST: "gemini-2.5-flash-lite",
        ModelRole.DEEP: "gemini-3.1-pro-preview",
    },
}
_ROLE_KEYS: Final = {
    ModelRole.DEFAULT: "default",
    ModelRole.FAST: "fast",
    ModelRole.DEEP: "deep",
}
_DEFAULT_MODEL_HINTS: Final = frozenset(models[ModelRole.DEFAULT] for models in _DEFAULT_PROVIDER_MODELS.values())
_MISSING: Final = object()


@dataclass(frozen=True)
class ProviderSettings:
    """The model map for one configured provider."""

    name: str
    models: Mapping[ModelRole, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", MappingProxyType(dict(self.models)))

    def model_for(self, role: ModelRole) -> str:
        """Return the configured provider-native model for ``role``."""

        return self.models[role]


@dataclass(frozen=True)
class LLMSettings:
    """The configured provider priority and provider model maps."""

    provider_order: tuple[str, ...]
    providers: Mapping[str, ProviderSettings]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_order", tuple(self.provider_order))
        object.__setattr__(self, "providers", MappingProxyType(dict(self.providers)))


def load_llm_settings(path: Path | None = None) -> LLMSettings:
    """Load LLM provider configuration, using safe current defaults only when absent."""

    config_path = path or Path(__file__).resolve().parents[3] / "config.yml"
    raw_config = _read_yaml(config_path)
    provider_section = raw_config.get("ai_providers", _MISSING)
    if provider_section is _MISSING:
        return _default_settings()
    if not isinstance(provider_section, Mapping):
        raise LLMConfigurationError("The ai_providers section must be a mapping")

    provider_order = _provider_order(provider_section)
    providers = {
        provider_name: _provider_settings(provider_name, provider_section)
        for provider_name in provider_order
    }
    return LLMSettings(provider_order=provider_order, providers=providers)


def resolve_role(model_hint: str | ModelRole) -> ModelRole:
    """Translate legacy model hints into a provider-neutral model role."""

    if isinstance(model_hint, ModelRole):
        return model_hint

    hint = model_hint.lower()
    if hint in ModelRole._value2member_map_:
        return ModelRole(hint)
    if hint in _DEFAULT_MODEL_HINTS or "sonnet" in hint:
        return ModelRole.DEFAULT
    if any(marker in hint for marker in ("opus", "-pro", "deep", "reasoning")):
        return ModelRole.DEEP
    if any(marker in hint for marker in ("haiku", "nano", "flash", "mini")):
        return ModelRole.FAST
    return ModelRole.DEFAULT


def _read_yaml(path: Path) -> Mapping[str, object]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LLMConfigurationError(f"Unable to read LLM configuration: {path}") from error

    try:
        parsed = yaml.safe_load(contents)
    except yaml.YAMLError as error:
        raise LLMConfigurationError(f"Malformed LLM configuration: {path}") from error

    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise LLMConfigurationError("LLM configuration must be a mapping")
    return parsed


def _provider_order(provider_section: Mapping[object, object]) -> tuple[str, ...]:
    configured_order = provider_section.get("order")
    if not isinstance(configured_order, Sequence) or isinstance(configured_order, (str, bytes)):
        raise LLMConfigurationError("The ai_providers.order value must be a list of provider names")
    if not configured_order or not all(isinstance(name, str) and name for name in configured_order):
        raise LLMConfigurationError("The ai_providers.order value must contain provider names")
    return tuple(configured_order)


def _provider_settings(provider_name: str, provider_section: Mapping[object, object]) -> ProviderSettings:
    raw_models = provider_section.get(provider_name)
    if not isinstance(raw_models, Mapping):
        raise LLMConfigurationError(f"Missing model map for provider: {provider_name}")

    models: dict[ModelRole, str] = {}
    for role, key in _ROLE_KEYS.items():
        model = raw_models.get(key)
        if not isinstance(model, str) or not model:
            raise LLMConfigurationError(f"Missing {key} model for provider: {provider_name}")
        models[role] = model
    return ProviderSettings(name=provider_name, models=models)


def _default_settings() -> LLMSettings:
    providers = {
        name: ProviderSettings(name=name, models=models)
        for name, models in _DEFAULT_PROVIDER_MODELS.items()
    }
    return LLMSettings(provider_order=_DEFAULT_PROVIDER_ORDER, providers=providers)
