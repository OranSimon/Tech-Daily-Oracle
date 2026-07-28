"""Web-search boundary package."""

from tech_daily.web_search.client import (
    ClaudeWebSearchClient,
    ProviderWebSearchClient,
    WebSearchClient,
)

__all__ = ["ClaudeWebSearchClient", "ProviderWebSearchClient", "WebSearchClient"]
