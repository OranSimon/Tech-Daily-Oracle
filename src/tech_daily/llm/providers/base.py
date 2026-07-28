"""Protocol shared by provider-specific LLM adapters."""

from __future__ import annotations

from typing import Protocol

from tech_daily.llm.contracts import (
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)

__all__ = ["ProviderAdapter"]


class ProviderAdapter(Protocol):
    """Provider-specific implementation of the neutral LLM capabilities."""

    name: str

    def has_credentials(self) -> bool:
        """Return whether this adapter can make authenticated requests."""

    def model_for(self, role: ModelRole) -> str:
        """Return the configured model identifier for a neutral role."""

    def generate_text(self, request: TextRequest) -> LLMResponse:
        """Generate plain text."""

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        """Generate text constrained to a JSON schema."""

    def search_web(self, request: SearchRequest) -> SearchResponse:
        """Run a provider-native web search."""

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        """Continue a partial text response from this provider."""
