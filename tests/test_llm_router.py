from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

from tech_daily.llm.contracts import (
    FinishReason,
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.errors import LLMConfigurationError, ProviderExhaustedError, RateLimited
from tech_daily.llm.router import AttemptRecord, ProviderRouter


class StructuredStatus(BaseModel):
    status: str


@dataclass
class FakeAdapter:
    name: str
    text: str = "ok"
    model: str | None = None
    configured_model: str | None = None
    structured_text: str = '{"status":"ok"}'
    search_results: list[dict[str, str]] = field(
        default_factory=lambda: [{"title": "result", "url": "https://example.com/result"}]
    )
    text_error: BaseException | None = None
    has_credentials_result: bool = True
    finish_reason: FinishReason = FinishReason.COMPLETE
    calls: list[str] = field(default_factory=list)

    def has_credentials(self) -> bool:
        return self.has_credentials_result

    def model_for(self, role: ModelRole) -> str:
        return self.configured_model or f"{self.name}-{role.value}-configured"

    def generate_text(self, request: TextRequest) -> LLMResponse:
        self.calls.append("generate_text")
        if self.text_error:
            raise self.text_error
        return LLMResponse(self.text, self.name, self.model or f"{self.name}-model", self.finish_reason)

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        self.calls.append("generate_structured")
        return LLMResponse(self.structured_text, self.name, f"{self.name}-model", self.finish_reason)

    def search_web(self, request: SearchRequest) -> SearchResponse:
        self.calls.append("search_web")
        return SearchResponse(self.search_results, self.name, f"{self.name}-model")

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        self.calls.append("continue_text")
        return LLMResponse(self.text, self.name, f"{self.name}-model", self.finish_reason)


def test_router_falls_back_only_for_normalized_provider_failure() -> None:
    first = FakeAdapter("deepseek", text_error=RateLimited("deepseek"))
    second = FakeAdapter("claude", text="ok")

    response = ProviderRouter([first, second]).generate_text(TextRequest("s", "u"))

    assert response.text == "ok"
    assert response.provider == "claude"


def test_router_does_not_mask_programming_error() -> None:
    first = FakeAdapter("deepseek", text_error=TypeError("bad adapter code"))
    second = FakeAdapter("claude", text="must not run")

    with pytest.raises(TypeError, match="bad adapter code"):
        ProviderRouter([first, second]).generate_text(TextRequest("s", "u"))

    assert second.calls == []


def test_attempt_telemetry_never_contains_content_or_secrets() -> None:
    records: list[AttemptRecord] = []
    request = TextRequest("secret system", "secret user")

    ProviderRouter([FakeAdapter("deepseek", text="answer")], on_attempt=records.append).generate_text(request)

    serialized = repr(records)
    assert "secret system" not in serialized
    assert "secret user" not in serialized
    assert "answer" not in serialized


def test_attempt_telemetry_uses_configured_models_for_failure_and_success() -> None:
    records: list[AttemptRecord] = []
    first = FakeAdapter(
        "deepseek",
        configured_model="deepseek-v4-flash",
        text_error=RateLimited("deepseek"),
    )
    second = FakeAdapter("claude", configured_model="claude-sonnet-4-6")

    ProviderRouter([first, second], on_attempt=records.append).generate_text(TextRequest("s", "u"))

    assert [record.model for record in records] == ["deepseek-v4-flash", "claude-sonnet-4-6"]


def test_attempt_telemetry_omits_an_untrusted_response_model() -> None:
    records: list[AttemptRecord] = []
    secret = "sk-test-123456 secret model value"

    adapter = FakeAdapter(
        "deepseek",
        model=secret,
        configured_model="deepseek-v4-flash",
    )
    ProviderRouter([adapter], on_attempt=records.append).generate_text(TextRequest("s", "u"))

    assert secret not in repr(records)
    assert records[0].model == "deepseek-v4-flash"


def test_attempt_telemetry_redacts_an_unsafe_configured_model() -> None:
    records: list[AttemptRecord] = []
    unsafe_model = "deepseek-model\nsecret=value"
    adapter = FakeAdapter("deepseek", configured_model=unsafe_model)

    ProviderRouter([adapter], on_attempt=records.append).generate_text(TextRequest("s", "u"))

    assert "secret=value" not in repr(records)
    assert records[0].model is None


def test_router_rejects_an_unknown_provider_before_any_adapter_is_invoked() -> None:
    unknown = FakeAdapter("mistral")

    with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
        ProviderRouter([unknown])

    assert unknown.calls == []


def test_router_skips_missing_credentials_and_records_a_safe_failure() -> None:
    records: list[AttemptRecord] = []
    first = FakeAdapter("deepseek", has_credentials_result=False)
    second = FakeAdapter("claude")

    ProviderRouter([first, second], on_attempt=records.append).generate_text(TextRequest("s", "u"))

    assert first.calls == []
    assert records[0].provider == "deepseek"
    assert records[0].error_category == "missing_credential"
    assert records[1].outcome == "success"


def test_router_rejects_empty_text_before_falling_back() -> None:
    first = FakeAdapter("deepseek", text="")
    second = FakeAdapter("claude", text="replacement")

    response = ProviderRouter([first, second]).generate_text(TextRequest("s", "u"))

    assert response.provider == "claude"


def test_router_rejects_non_string_text_before_falling_back() -> None:
    first = FakeAdapter("deepseek")
    second = FakeAdapter("claude", text="replacement")

    first.text = None  # type: ignore[assignment]
    response = ProviderRouter([first, second]).generate_text(TextRequest("s", "u"))

    assert response.provider == "claude"


def test_router_rejects_non_complete_finish_reason_before_falling_back() -> None:
    first = FakeAdapter("deepseek", finish_reason=FinishReason.REFUSAL)
    second = FakeAdapter("claude", text="replacement")

    response = ProviderRouter([first, second]).generate_text(TextRequest("s", "u"))

    assert response.provider == "claude"


def test_router_dispatches_structured_and_search_capabilities() -> None:
    adapter = FakeAdapter("deepseek")
    router = ProviderRouter([adapter])

    structured = router.generate_structured(
        StructuredRequest("s", "u", StructuredStatus.model_json_schema()),
        StructuredStatus,
    )
    search = router.search_web(SearchRequest("latest AI news"))

    assert structured == StructuredStatus(status="ok")
    assert search.results == ({"title": "result", "url": "https://example.com/result"},)
    assert adapter.calls == ["generate_structured", "search_web"]


def test_router_rejects_empty_search_results() -> None:
    first = FakeAdapter("deepseek", search_results=[])
    second = FakeAdapter(
        "claude",
        search_results=[{"title": "replacement", "url": "https://example.com/replacement"}],
    )

    response = ProviderRouter([first, second]).search_web(SearchRequest("latest AI news"))

    assert response.provider == "claude"


def test_exhausted_router_exposes_only_sanitized_attempt_summaries() -> None:
    secret = "sk-test-123456 secret prompt and generated response"
    first = FakeAdapter("deepseek", text_error=RateLimited("deepseek", secret))
    second = FakeAdapter("claude", text_error=RateLimited("claude", secret))

    with pytest.raises(ProviderExhaustedError) as raised:
        ProviderRouter([first, second]).generate_text(TextRequest("secret system", "secret user"))

    exposed = f"{raised.value.attempts!r} {raised.value}"
    assert secret not in exposed
    assert raised.value.attempts == ("deepseek: rate_limited", "claude: rate_limited")
