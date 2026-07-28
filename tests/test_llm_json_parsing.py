from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import claude_client
import pytest

from tech_daily.llm.contracts import (
    FinishReason,
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.errors import ProviderExhaustedError
from tech_daily.llm.router import ProviderRouter


@dataclass
class FakeJsonAdapter:
    name: str
    text: str
    calls: list[str] = field(default_factory=list)

    def has_credentials(self) -> bool:
        return True

    def model_for(self, role: ModelRole) -> str:
        return f"{self.name}-{role.value}-model"

    def generate_text(self, request: TextRequest) -> LLMResponse:
        self.calls.append("generate_text")
        return LLMResponse(
            self.text,
            self.name,
            self.model_for(request.role),
            FinishReason.COMPLETE,
        )

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        raise NotImplementedError

    def search_web(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        raise NotImplementedError


@pytest.mark.parametrize(
    ("valid_response", "expected"),
    [
        ('{"ok": true}', {"ok": True}),
        ('```json\n[{"id": "one"}]\n```', [{"id": "one"}]),
    ],
)
def test_generic_json_route_falls_back_and_accepts_objects_or_arrays(
    valid_response: str,
    expected: dict[str, Any] | list[Any],
) -> None:
    malformed = FakeJsonAdapter("deepseek", "not json")
    valid = FakeJsonAdapter("claude", valid_response)

    result = ProviderRouter([malformed, valid]).generate_json(TextRequest("system", "user"))

    assert result == expected
    assert malformed.calls == ["generate_text"]
    assert valid.calls == ["generate_text"]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("true", True),
        ("null", None),
        ("42", 42),
        ('"value"', "value"),
    ],
)
def test_generic_json_route_accepts_scalar_values(response: str, expected: Any) -> None:
    adapter = FakeJsonAdapter("deepseek", response)

    result = ProviderRouter([adapter]).generate_json(TextRequest("system", "user"))

    assert result == expected
    assert adapter.calls == ["generate_text"]


def test_generic_json_route_exhausts_safely_when_every_response_is_malformed() -> None:
    secret_response = "not json secret-response"
    first = FakeJsonAdapter("deepseek", secret_response)
    second = FakeJsonAdapter("claude", "also not json")

    with pytest.raises(ProviderExhaustedError) as raised:
        ProviderRouter([first, second]).generate_json(TextRequest("secret-system", "secret-user"))

    assert raised.value.attempts == (
        "deepseek: invalid_provider_response",
        "claude: invalid_provider_response",
    )
    assert raised.value.capability == "generate_json"
    exposed = f"{raised.value.attempts!r} {raised.value}"
    assert "secret-system" not in exposed
    assert "secret-user" not in exposed
    assert secret_response not in exposed


def test_call_claude_json_forwards_to_neutral_json_route(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeProviderClient:
        def generate_json(self, **kwargs: Any) -> dict[str, bool]:
            calls.append(kwargs)
            return {"ok": True}

    monkeypatch.setattr(claude_client, "get_default_client", lambda: FakeProviderClient())

    result = claude_client.call_claude_json(
        "system",
        "user",
        model="claude-opus",
        max_tokens=321,
        cache_system=False,
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "system": "system",
            "user": "user",
            "role": ModelRole.DEEP,
            "max_output_tokens": 321,
            "cache_system": False,
        }
    ]
