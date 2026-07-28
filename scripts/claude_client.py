"""Deprecated Claude-named wrappers for the provider-neutral LLM client."""

from __future__ import annotations

from tech_daily.llm.client import get_default_client
from tech_daily.llm.config import resolve_role
from tech_daily.llm.router import JSONValue

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_PROVIDER_ORDER = ["deepseek", "claude", "openai", "gemini"]
MAX_CONTINUATIONS = 4


def call_claude(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    cache_system: bool = True,
    auto_continue: bool = True,
) -> str:
    """Forward the legacy text API to the provider-neutral client."""

    return get_default_client().generate_text(
        system=system,
        user=user,
        role=resolve_role(model),
        max_output_tokens=max_tokens,
        cache_system=cache_system,
        auto_continue=auto_continue,
    )


def call_claude_web_search(
    prompt: str,
    max_uses: int = 5,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> list[dict]:
    """Forward the legacy web-search API to the provider-neutral client."""

    return get_default_client().search_web(
        prompt=prompt,
        max_results=max_uses,
        role=resolve_role(model),
        max_output_tokens=max_tokens,
    )


def call_claude_json(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    cache_system: bool = True,
) -> JSONValue:
    """Forward the legacy JSON API and preserve its parsed return type."""

    return get_default_client().generate_json(
        system=system,
        user=user,
        role=resolve_role(model),
        max_output_tokens=max_tokens,
        cache_system=cache_system,
    )
