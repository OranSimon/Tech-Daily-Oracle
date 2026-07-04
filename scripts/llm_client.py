"""Minimal LLM boundary used by analyzers and prompt runners."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Small protocol that production and fake LLM clients can both satisfy."""

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
        auto_continue: bool = False,
    ) -> str:
        """Generate text from a system prompt and user payload."""


class ClaudeLLMClient:
    """Adapter around the existing multi-provider Claude client behavior."""

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
        auto_continue: bool = False,
    ) -> str:
        from claude_client import call_claude

        return call_claude(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            cache_system=cache_system,
            auto_continue=auto_continue,
        )
