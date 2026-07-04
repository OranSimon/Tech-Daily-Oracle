"""Small boundary for external web-search collection."""

from __future__ import annotations

from typing import Any, Protocol


class WebSearchClient(Protocol):
    """Minimal protocol for web-search collectors and test fakes."""

    def search(self, prompt: str, max_uses: int = 3) -> list[dict[str, Any]]:
        """Return structured web-search result dictionaries for a prompt."""


class ClaudeWebSearchClient:
    """Adapter around the existing Claude built-in web-search helper."""

    def search(self, prompt: str, max_uses: int = 3) -> list[dict[str, Any]]:
        from claude_client import call_claude_web_search

        return call_claude_web_search(prompt, max_uses=max_uses)
