"""Compatibility wrapper for the package-owned web-search boundary."""

from __future__ import annotations

from tech_daily.web_search.client import (
    ClaudeWebSearchClient,
    ProviderWebSearchClient,
    WebSearchClient,
)

__all__ = ["ClaudeWebSearchClient", "ProviderWebSearchClient", "WebSearchClient"]
