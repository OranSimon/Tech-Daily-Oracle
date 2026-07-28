from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from threading import Barrier, BrokenBarrierError, Lock
from typing import Any, cast

import claude_client
import run_monthly_review
import run_weekly_review
from pydantic import BaseModel

from tech_daily.llm import client as client_module
from tech_daily.llm.client import ProviderLLMClient
from tech_daily.llm.contracts import (
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.router import ProviderRouter
from tech_daily.reports import daily as daily_report


class ExampleSchema(BaseModel):
    name: str


class FakeRouter:
    def __init__(self, *, text: str = "ok") -> None:
        self.text = text
        self.last_text_request: TextRequest | None = None
        self.last_json_request: TextRequest | None = None
        self.last_structured_request: StructuredRequest | None = None
        self.last_search_request: SearchRequest | None = None

    def generate_text(self, request: TextRequest, *, auto_continue: bool = False) -> LLMResponse:
        self.last_text_request = request
        return LLMResponse(self.text, "deepseek", "deepseek-model")

    def generate_structured(
        self,
        request: StructuredRequest,
        schema: type[ExampleSchema],
    ) -> ExampleSchema:
        self.last_structured_request = request
        return schema(name="structured")

    def generate_json(self, request: TextRequest) -> dict[str, bool]:
        self.last_json_request = request
        return {"ok": True}

    def search_web(self, request: SearchRequest) -> SearchResponse:
        self.last_search_request = request
        return SearchResponse(
            [{"title": "result", "url": "https://example.com"}],
            "deepseek",
            "deepseek-model",
        )


class FakeProviderLLMClient:
    def __init__(self, *, text: str = "neutral") -> None:
        self.text = text
        self.last_request: TextRequest | None = None
        self.last_json: dict[str, Any] | None = None
        self.last_structured: dict[str, Any] | None = None
        self.last_search: dict[str, Any] | None = None

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
        self.last_request = TextRequest(
            system,
            user,
            role=role,
            max_output_tokens=max_output_tokens,
            cache_system=cache_system,
        )
        return self.text

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[ExampleSchema],
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
        cache_system: bool = True,
    ) -> ExampleSchema:
        self.last_structured = {
            "system": system,
            "user": user,
            "schema": schema,
            "role": role,
            "max_output_tokens": max_output_tokens,
            "cache_system": cache_system,
        }
        return schema(name="structured")

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
        cache_system: bool = True,
    ) -> dict[str, bool]:
        self.last_json = {
            "system": system,
            "user": user,
            "role": role,
            "max_output_tokens": max_output_tokens,
            "cache_system": cache_system,
        }
        return {"ok": True}

    def search_web(
        self,
        *,
        prompt: str,
        max_results: int = 5,
        role: ModelRole = ModelRole.DEFAULT,
        max_output_tokens: int = 4096,
    ) -> list[dict[str, Any]]:
        self.last_search = {
            "prompt": prompt,
            "max_results": max_results,
            "role": role,
            "max_output_tokens": max_output_tokens,
        }
        return [{"title": "result", "url": "https://example.com"}]


def test_new_client_accepts_role_without_claude_model_name() -> None:
    fake_router = FakeRouter(text="ok")
    client = ProviderLLMClient(router=cast(ProviderRouter, fake_router))

    result = client.generate_text(system="s", user="u", role=ModelRole.DEEP)

    assert result == "ok"
    assert fake_router.last_text_request == TextRequest("s", "u", role=ModelRole.DEEP)


def test_new_client_routes_structured_and_search_requests() -> None:
    fake_router = FakeRouter()
    client = ProviderLLMClient(router=cast(ProviderRouter, fake_router))

    structured = client.generate_structured(
        system="s",
        user="u",
        schema=ExampleSchema,
        role=ModelRole.FAST,
        max_output_tokens=321,
    )
    json_value = client.generate_json(
        system="json-system",
        user="json-user",
        role=ModelRole.FAST,
        max_output_tokens=432,
    )
    search = client.search_web(
        prompt="query",
        max_results=3,
        role=ModelRole.DEEP,
        max_output_tokens=654,
    )

    assert structured == ExampleSchema(name="structured")
    assert json_value == {"ok": True}
    assert fake_router.last_json_request == TextRequest(
        "json-system",
        "json-user",
        role=ModelRole.FAST,
        max_output_tokens=432,
    )
    assert fake_router.last_structured_request == StructuredRequest(
        "s",
        "u",
        ExampleSchema.model_json_schema(),
        role=ModelRole.FAST,
        max_output_tokens=321,
    )
    assert search == [{"title": "result", "url": "https://example.com"}]
    assert fake_router.last_search_request == SearchRequest(
        "query",
        max_results=3,
        role=ModelRole.DEEP,
        max_output_tokens=654,
    )


def test_default_client_builds_one_configured_router(monkeypatch) -> None:
    settings = object()
    adapters = object()
    router = FakeRouter()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(client_module, "_default_client", None)
    monkeypatch.setattr(client_module, "load_llm_settings", lambda: settings)
    monkeypatch.setattr(
        client_module,
        "build_provider_adapters",
        lambda value: calls.append(("adapters", value)) or adapters,
    )
    monkeypatch.setattr(
        client_module,
        "ProviderRouter",
        lambda value: calls.append(("router", value)) or router,
    )

    first = client_module.get_default_client()
    second = client_module.get_default_client()

    assert first is second
    assert calls == [("adapters", settings), ("router", adapters)]


def test_default_client_cold_start_is_singleton_across_threads(monkeypatch) -> None:
    worker_count = 5
    settings = object()
    adapters = object()
    router = object()
    construction_barrier = Barrier(worker_count)
    calls_lock = Lock()
    construction_calls: list[str] = []
    clients: list[object] = []

    def load_settings() -> object:
        with calls_lock:
            construction_calls.append("settings")
        with suppress(BrokenBarrierError):
            construction_barrier.wait(timeout=0.2)
        return settings

    def build_adapters(value: object) -> object:
        assert value is settings
        with calls_lock:
            construction_calls.append("adapters")
        return adapters

    def build_router(value: object) -> object:
        assert value is adapters
        with calls_lock:
            construction_calls.append("router")
        return router

    def build_client(*, router: object) -> object:
        clients.append(object())
        return clients[-1]

    monkeypatch.setattr(client_module, "_default_client", None)
    monkeypatch.setattr(client_module, "load_llm_settings", load_settings)
    monkeypatch.setattr(client_module, "build_provider_adapters", build_adapters)
    monkeypatch.setattr(client_module, "ProviderRouter", build_router)
    monkeypatch.setattr(client_module, "ProviderLLMClient", build_client)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(lambda _: client_module.get_default_client(), range(worker_count)))

    assert construction_calls == ["settings", "adapters", "router"]
    assert len(clients) == 1
    assert all(result is clients[0] for result in results)


def test_legacy_call_claude_forwards_to_neutral_client(monkeypatch) -> None:
    fake = FakeProviderLLMClient(text="neutral")
    monkeypatch.setattr(claude_client, "get_default_client", lambda: fake)

    result = claude_client.call_claude("s", "u", model="claude-haiku", max_tokens=20)

    assert result == "neutral"
    assert fake.last_request == TextRequest(
        "s",
        "u",
        role=ModelRole.FAST,
        max_output_tokens=20,
    )


def test_legacy_json_and_search_wrappers_keep_public_return_types(monkeypatch) -> None:
    fake = FakeProviderLLMClient()
    monkeypatch.setattr(claude_client, "get_default_client", lambda: fake)

    parsed = claude_client.call_claude_json("s", "u", model="claude-opus", max_tokens=30)
    results = claude_client.call_claude_web_search(
        "query",
        max_uses=2,
        model="claude-haiku",
        max_tokens=40,
    )

    assert parsed == {"ok": True}
    assert fake.last_json == {
        "system": "s",
        "user": "u",
        "role": ModelRole.DEEP,
        "max_output_tokens": 30,
        "cache_system": True,
    }
    assert results == [{"title": "result", "url": "https://example.com"}]
    assert fake.last_search == {
        "prompt": "query",
        "max_results": 2,
        "role": ModelRole.FAST,
        "max_output_tokens": 40,
    }


def test_neutral_call_helpers_forward_to_default_client(monkeypatch) -> None:
    fake = FakeProviderLLMClient(text="neutral")
    monkeypatch.setattr(client_module, "get_default_client", lambda: fake)

    result = client_module.call_llm(
        "s",
        "u",
        role=ModelRole.DEEP,
        max_output_tokens=55,
    )
    structured = client_module.call_llm_structured(
        "structured-system",
        "structured-user",
        ExampleSchema,
        role=ModelRole.FAST,
        max_output_tokens=66,
    )
    json_value = client_module.call_llm_json(
        "json-system",
        "json-user",
        role=ModelRole.FAST,
        max_output_tokens=67,
    )
    search = client_module.call_llm_web_search(
        "query",
        max_results=7,
        role=ModelRole.DEEP,
        max_output_tokens=77,
    )

    assert result == "neutral"
    assert fake.last_request == TextRequest(
        "s",
        "u",
        role=ModelRole.DEEP,
        max_output_tokens=55,
    )
    assert structured == ExampleSchema(name="structured")
    assert json_value == {"ok": True}
    assert fake.last_json == {
        "system": "json-system",
        "user": "json-user",
        "role": ModelRole.FAST,
        "max_output_tokens": 67,
        "cache_system": True,
    }
    assert fake.last_structured == {
        "system": "structured-system",
        "user": "structured-user",
        "schema": ExampleSchema,
        "role": ModelRole.FAST,
        "max_output_tokens": 66,
        "cache_system": True,
    }
    assert search == [{"title": "result", "url": "https://example.com"}]
    assert fake.last_search == {
        "prompt": "query",
        "max_results": 7,
        "role": ModelRole.DEEP,
        "max_output_tokens": 77,
    }


def test_report_defaults_use_neutral_roles() -> None:
    assert daily_report.DEFAULT_DAILY_MODEL is ModelRole.DEFAULT
    assert run_weekly_review.DEFAULT_WEEKLY_MODEL is ModelRole.DEFAULT
    assert run_monthly_review.DEFAULT_MONTHLY_MODEL is ModelRole.DEFAULT
