"""Small web-search provider boundary."""

from __future__ import annotations

from collections.abc import Callable
from inspect import signature
from typing import Any, Protocol, cast


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


class ClaudeWebSearchClient:
    """Adapter that delegates to the legacy Claude web-search implementation."""

    def search(
        self,
        prompt: str,
        max_uses: int = 3,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        from claude_client import call_claude_web_search

        result_limit = max_uses if max_results is None else max_results
        legacy_search = cast(Callable[..., list[dict[str, Any]]], call_claude_web_search)
        if "max_results" in signature(call_claude_web_search).parameters:
            return legacy_search(prompt, max_results=result_limit)
        return legacy_search(prompt, max_uses=result_limit)
