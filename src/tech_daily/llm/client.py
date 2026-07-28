"""Provider-neutral production client and legacy compatibility boundary."""

from __future__ import annotations

from threading import Lock
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from tech_daily.llm.config import load_llm_settings, resolve_role
from tech_daily.llm.contracts import ModelRole, SearchRequest, StructuredRequest, TextRequest
from tech_daily.llm.providers import build_provider_adapters
from tech_daily.llm.router import JSONValue, ProviderRouter

__all__ = [
    "ClaudeLLMClient",
    "LLMClient",
    "ProviderLLMClient",
    "TextLLMClient",
    "call_llm",
    "call_llm_json",
    "call_llm_structured",
    "call_llm_web_search",
    "get_default_client",
]

T = TypeVar("T", bound=BaseModel)


class TextLLMClient(Protocol):
    """Compatibility protocol for clients that generate text."""

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


class LLMClient(TextLLMClient, Protocol):
    """Compatibility protocol for text and structured generation."""

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> T:
        """Generate and validate a response against ``schema``."""


class ProviderLLMClient:
    """Production client backed by one configured provider router."""

    def __init__(self, router: ProviderRouter | None = None) -> None:
        if router is None:
            settings = load_llm_settings()
            router = ProviderRouter(build_provider_adapters(settings))
        self._router = router

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
        cache_system: bool = True,
        auto_continue: bool = False,
    ) -> str:
        """Generate text using a provider-neutral model role."""

        response = self._router.generate_text(
            TextRequest(
                system=system,
                user=user,
                role=role,
                max_output_tokens=max_output_tokens,
                cache_system=cache_system,
            ),
            auto_continue=auto_continue,
        )
        return response.text

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
        cache_system: bool = True,
    ) -> T:
        """Generate and validate structured output using a neutral role."""

        request = StructuredRequest(
            system=system,
            user=user,
            json_schema=schema.model_json_schema(),
            role=role,
            max_output_tokens=max_output_tokens,
            cache_system=cache_system,
        )
        return self._router.generate_structured(request, schema)

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
        cache_system: bool = True,
    ) -> JSONValue:
        """Generate a JSON value inside the provider fallback boundary."""

        return self._router.generate_json(
            TextRequest(
                system=system,
                user=user,
                role=role,
                max_output_tokens=max_output_tokens,
                cache_system=cache_system,
            )
        )

    def search_web(
        self,
        *,
        prompt: str,
        max_results: int = 5,
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
    ) -> list[dict[str, Any]]:
        """Search the web using configured provider priority."""

        response = self._router.search_web(
            SearchRequest(
                query=prompt,
                max_results=max_results,
                role=role,
                max_output_tokens=max_output_tokens,
            )
        )
        return [dict(result) for result in response.results]


_default_client: ProviderLLMClient | None = None
_default_client_lock = Lock()


def get_default_client() -> ProviderLLMClient:
    """Return the process-wide provider-neutral production client."""

    global _default_client
    if _default_client is None:
        with _default_client_lock:
            if _default_client is None:
                settings = load_llm_settings()
                router = ProviderRouter(build_provider_adapters(settings))
                _default_client = ProviderLLMClient(router=router)
    return _default_client


def call_llm(
    system: str,
    user: str,
    role: ModelRole = ModelRole.DEFAULT,
    max_output_tokens: int = 4096,
    cache_system: bool = True,
    auto_continue: bool = False,
) -> str:
    """Generate text through the default provider-neutral client."""

    return get_default_client().generate_text(
        system=system,
        user=user,
        role=role,
        max_output_tokens=max_output_tokens,
        cache_system=cache_system,
        auto_continue=auto_continue,
    )


def call_llm_structured(
    system: str,
    user: str,
    schema: type[T],
    role: ModelRole = ModelRole.DEFAULT,
    max_output_tokens: int = 4096,
    cache_system: bool = True,
) -> T:
    """Generate structured output through the default neutral client."""

    return get_default_client().generate_structured(
        system=system,
        user=user,
        schema=schema,
        role=role,
        max_output_tokens=max_output_tokens,
        cache_system=cache_system,
    )


def call_llm_json(
    system: str,
    user: str,
    role: ModelRole = ModelRole.DEFAULT,
    max_output_tokens: int = 4096,
    cache_system: bool = True,
) -> JSONValue:
    """Generate a generic JSON value through the default neutral client."""

    return get_default_client().generate_json(
        system=system,
        user=user,
        role=role,
        max_output_tokens=max_output_tokens,
        cache_system=cache_system,
    )


def call_llm_web_search(
    prompt: str,
    max_results: int = 5,
    role: ModelRole = ModelRole.DEFAULT,
    max_output_tokens: int = 4096,
) -> list[dict[str, Any]]:
    """Search through the default provider-neutral client."""

    return get_default_client().search_web(
        prompt=prompt,
        max_results=max_results,
        role=role,
        max_output_tokens=max_output_tokens,
    )


class ClaudeLLMClient:
    """Deprecated compatibility client that translates model strings to roles."""

    def __init__(self, router: ProviderRouter | None = None) -> None:
        self._client = ProviderLLMClient(router=router) if router is not None else None

    def _backend(self) -> ProviderLLMClient:
        return self._client or get_default_client()

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
        return self._backend().generate_text(
            system=system,
            user=user,
            role=resolve_role(model),
            max_output_tokens=max_tokens,
            cache_system=cache_system,
            auto_continue=auto_continue,
        )

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> T:
        return self._backend().generate_structured(
            system=system,
            user=user,
            schema=schema,
            role=resolve_role(model),
            max_output_tokens=max_tokens,
            cache_system=cache_system,
        )
