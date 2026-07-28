"""Small web-search provider boundary."""

from __future__ import annotations

from typing import Any, Protocol

from tech_daily.llm import client as llm_client

__all__ = [
    "ClaudeWebSearchClient",
    "ProviderWebSearchClient",
    "WebSearchClient",
    "get_default_client",
]


class WebSearchClient(Protocol):
    """Boundary for web-search collection clients."""

    def search(
        self,
        prompt: str,
        max_uses: int = 3,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return web-search result dictionaries for one prompt."""


class _ProviderSearchBackend(Protocol):
    def search_web(self, *, prompt: str, max_results: int) -> list[dict[str, Any]]: ...


def get_default_client() -> _ProviderSearchBackend:
    """Return the canonical provider-neutral production client."""

    return llm_client.get_default_client()


class ProviderWebSearchClient:
    """Web-search client backed by configured provider priority."""

    def search(
        self,
        prompt: str,
        max_uses: int = 3,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = max_uses if max_results is None else max_results
        return get_default_client().search_web(prompt=prompt, max_results=limit)


class ClaudeWebSearchClient(ProviderWebSearchClient):
    """Deprecated compatibility name for the provider-neutral search client."""
