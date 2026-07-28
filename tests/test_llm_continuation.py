from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tech_daily.llm.contracts import (
    Capability,
    FinishReason,
    LLMResponse,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.errors import NetworkFailure
from tech_daily.llm.router import AttemptRecord, ProviderRouter


@dataclass(frozen=True)
class FakeCall:
    capability: Capability
    request: TextRequest
    partial: str | None = None


@dataclass
class FakeAdapter:
    name: str
    text: str | tuple[str, FinishReason] = "ok"
    continuation: str | tuple[str, FinishReason] = "rest"
    continuation_error: BaseException | None = None
    calls: list[FakeCall] = field(default_factory=list)

    def has_credentials(self) -> bool:
        return True

    def generate_text(self, request: TextRequest) -> LLMResponse:
        self.calls.append(FakeCall(Capability.TEXT, request))
        text, reason = self._result(self.text)
        return LLMResponse(text, self.name, f"{self.name}-model", reason)

    def generate_structured(self, request: StructuredRequest) -> LLMResponse:
        raise NotImplementedError

    def search_web(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError

    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        self.calls.append(FakeCall(Capability.CONTINUATION, request, partial))
        if self.continuation_error is not None:
            raise self.continuation_error
        text, reason = self._result(self.continuation)
        return LLMResponse(text, self.name, f"{self.name}-model", reason)

    @staticmethod
    def _result(value: str | tuple[str, FinishReason]) -> tuple[str, FinishReason]:
        if isinstance(value, tuple):
            return value
        return value, FinishReason.COMPLETE


class MalformedTextAdapter(FakeAdapter):
    def generate_text(self, request: TextRequest) -> LLMResponse:
        self.calls.append(FakeCall(Capability.TEXT, request))
        return object()  # type: ignore[return-value]


class MalformedContinuationAdapter(FakeAdapter):
    def continue_text(self, request: TextRequest, partial: str) -> LLMResponse:
        self.calls.append(FakeCall(Capability.CONTINUATION, request, partial))
        return object()  # type: ignore[return-value]


def test_continuation_stays_on_originating_provider() -> None:
    deepseek = FakeAdapter(
        "deepseek",
        text=("part", FinishReason.MAX_TOKENS),
        continuation="rest",
    )
    claude = FakeAdapter("claude", text="unused")

    result = ProviderRouter([deepseek, claude]).generate_text(
        TextRequest("s", "u"),
        auto_continue=True,
    )

    assert result.text == "partrest"
    assert [call.capability for call in deepseek.calls] == [
        Capability.TEXT,
        Capability.CONTINUATION,
    ]
    assert claude.calls == []


def test_successful_continuation_emits_sanitized_attempt_record() -> None:
    records: list[AttemptRecord] = []
    adapter = FakeAdapter(
        "deepseek",
        text=("secret partial", FinishReason.MAX_TOKENS),
        continuation="secret remainder",
    )

    result = ProviderRouter([adapter], on_attempt=records.append).generate_text(
        TextRequest("secret system", "secret user"),
        auto_continue=True,
    )

    assert result.text == "secret partialsecret remainder"
    assert records == [
        AttemptRecord(
            capability=Capability.CONTINUATION,
            provider="deepseek",
            model=None,
            attempt_number=1,
            outcome="success",
            error_category=None,
            fallback_reason=None,
        ),
        AttemptRecord(
            capability=Capability.TEXT,
            provider="deepseek",
            model=None,
            attempt_number=1,
            outcome="success",
            error_category=None,
            fallback_reason=None,
        ),
    ]
    assert "secret" not in repr(records)


def test_eligible_continuation_failure_restarts_full_request_on_next_provider() -> None:
    records: list[AttemptRecord] = []
    request = TextRequest("s", "u")
    deepseek = FakeAdapter(
        "deepseek",
        text=("part", FinishReason.MAX_TOKENS),
        continuation_error=NetworkFailure("deepseek"),
    )
    claude = FakeAdapter("claude", text="complete replacement")

    result = ProviderRouter([deepseek, claude], on_attempt=records.append).generate_text(
        request,
        auto_continue=True,
    )

    assert result.text == "complete replacement"
    assert claude.calls == [FakeCall(Capability.TEXT, request)]
    assert records == [
        AttemptRecord(
            capability=Capability.CONTINUATION,
            provider="deepseek",
            model=None,
            attempt_number=1,
            outcome="failure",
            error_category="network_failure",
            fallback_reason="network_failure",
        ),
        AttemptRecord(
            capability=Capability.TEXT,
            provider="deepseek",
            model=None,
            attempt_number=1,
            outcome="failure",
            error_category="network_failure",
            fallback_reason="network_failure",
        ),
        AttemptRecord(
            capability=Capability.TEXT,
            provider="claude",
            model=None,
            attempt_number=2,
            outcome="success",
            error_category=None,
            fallback_reason=None,
        ),
    ]


def test_unexpected_continuation_error_propagates_without_fallback() -> None:
    records: list[AttemptRecord] = []
    deepseek = FakeAdapter(
        "deepseek",
        text=("part", FinishReason.MAX_TOKENS),
        continuation_error=TypeError("adapter defect"),
    )
    claude = FakeAdapter("claude", text="must not run")

    with pytest.raises(TypeError, match="adapter defect"):
        ProviderRouter([deepseek, claude], on_attempt=records.append).generate_text(
            TextRequest("s", "u"),
            auto_continue=True,
        )

    assert claude.calls == []
    assert records == []


@pytest.mark.parametrize(
    "first",
    [
        MalformedTextAdapter("deepseek"),
        MalformedContinuationAdapter("deepseek", text=("part", FinishReason.MAX_TOKENS)),
    ],
)
def test_malformed_text_response_restarts_full_request_on_next_provider(first: FakeAdapter) -> None:
    replacement = FakeAdapter("claude", text="complete replacement")

    result = ProviderRouter([first, replacement]).generate_text(TextRequest("s", "u"), auto_continue=True)

    assert result.text == "complete replacement"
    assert [call.capability for call in replacement.calls] == [Capability.TEXT]
