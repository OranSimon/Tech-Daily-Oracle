"""Provider adapter interfaces, implementations, and configured construction."""

from collections.abc import Callable

from tech_daily.llm.config import LLMSettings, ProviderSettings
from tech_daily.llm.errors import LLMConfigurationError
from tech_daily.llm.providers.anthropic import ClaudeAdapter
from tech_daily.llm.providers.base import ProviderAdapter
from tech_daily.llm.providers.gemini import GeminiAdapter
from tech_daily.llm.providers.openai_compatible import DeepSeekAdapter, OpenAIAdapter

__all__ = [
    "ClaudeAdapter",
    "DeepSeekAdapter",
    "GeminiAdapter",
    "OpenAIAdapter",
    "ProviderAdapter",
    "build_provider_adapters",
]


def build_provider_adapters(settings: LLMSettings) -> tuple[ProviderAdapter, ...]:
    """Build concrete adapters in configured fallback order."""

    adapter_types: dict[str, Callable[[ProviderSettings], ProviderAdapter]] = {
        "deepseek": DeepSeekAdapter,
        "claude": ClaudeAdapter,
        "openai": OpenAIAdapter,
        "gemini": GeminiAdapter,
    }
    try:
        return tuple(adapter_types[name](settings.providers[name]) for name in settings.provider_order)
    except KeyError as error:
        raise LLMConfigurationError("Unknown LLM provider configured") from error
