from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import Any

import anthropic
import httpx
import openai
import pytest

from tech_daily.llm.config import LLMSettings, ProviderSettings
from tech_daily.llm.contracts import FinishReason, ModelRole, TextRequest
from tech_daily.llm.errors import (
    AuthenticationFailure,
    InvalidProviderResponse,
    NetworkFailure,
    ProviderUnavailable,
    QuotaExceeded,
    RateLimited,
)
from tech_daily.llm.providers import (
    ClaudeAdapter,
    DeepSeekAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    build_provider_adapters,
)
from tech_daily.llm.providers import gemini as gemini_provider

CONTINUE_PROMPT = "上一轮回复因输出上限被截断。请从停止位置继续，不重复已输出内容，不要添加引言或元说明。"


class FakeAnthropicClient:
    def __init__(
        self,
        *,
        text: str = "ok",
        finish_reason: str = "end_turn",
        error: BaseException | None = None,
    ) -> None:
        self.last_request: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create)
        self._error = error
        self._response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=finish_reason,
        )

    def _create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class FakeOpenAICompatibleClient:
    def __init__(
        self,
        *,
        text: str = "ok",
        finish_reason: str = "stop",
        error: BaseException | None = None,
    ) -> None:
        self.last_request: dict[str, Any] = {}
        self.raw_request: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._error = error
        self._response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=finish_reason,
                    message=SimpleNamespace(content=text, refusal=None),
                )
            ]
        )

    def _create(self, **kwargs: Any) -> Any:
        self.raw_request = kwargs
        self.last_request = {**kwargs, **kwargs.get("extra_body", {})}
        if self._error is not None:
            raise self._error
        return self._response


class FakeGeminiClient:
    def __init__(
        self,
        *,
        text: str = "ok",
        finish_reason: str = "STOP",
        error: BaseException | None = None,
    ) -> None:
        self.last_request: dict[str, Any] = {}
        self.models = SimpleNamespace(generate_content=self._generate_content)
        self._error = error
        self._response = SimpleNamespace(
            text=text,
            candidates=[SimpleNamespace(finish_reason=finish_reason)],
        )

    def _generate_content(self, **kwargs: Any) -> Any:
        config = kwargs["config"]
        self.last_request = {**kwargs, **config}
        if self._error is not None:
            raise self._error
        return self._response


class FakeGoogleGenAIAPIError(Exception):
    def __init__(self, code: int, details: object) -> None:
        self.code = code
        self.details = details


class FakeGoogleGenAIClientError(FakeGoogleGenAIAPIError):
    pass


class FakeGoogleGenAIServerError(FakeGoogleGenAIAPIError):
    pass


FakeGoogleGenAIAPIError.__module__ = "google.genai.errors"


def _install_fake_google_genai_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    errors = ModuleType("google.genai.errors")
    errors.APIError = FakeGoogleGenAIAPIError
    monkeypatch.setitem(sys.modules, "google.genai.errors", errors)
    monkeypatch.setattr(gemini_provider, "_GOOGLE_GENAI_API_ERRORS", None)


def _settings(name: str) -> ProviderSettings:
    model = f"{name}-fixture-model"
    return ProviderSettings(name, {role: model for role in ModelRole})


def make_deepseek_adapter(
    *,
    text: str = "ok",
    finish_reason: str = "stop",
    error: BaseException | None = None,
) -> tuple[DeepSeekAdapter, FakeOpenAICompatibleClient]:
    client = FakeOpenAICompatibleClient(text=text, finish_reason=finish_reason, error=error)
    return DeepSeekAdapter(_settings("deepseek"), client=client), client


def make_claude_adapter(
    *,
    text: str = "ok",
    finish_reason: str = "end_turn",
    error: BaseException | None = None,
) -> tuple[ClaudeAdapter, FakeAnthropicClient]:
    client = FakeAnthropicClient(text=text, finish_reason=finish_reason, error=error)
    return ClaudeAdapter(_settings("claude"), client=client), client


def make_openai_adapter(
    *,
    text: str = "ok",
    finish_reason: str = "stop",
    error: BaseException | None = None,
) -> tuple[OpenAIAdapter, FakeOpenAICompatibleClient]:
    client = FakeOpenAICompatibleClient(text=text, finish_reason=finish_reason, error=error)
    return OpenAIAdapter(_settings("openai"), client=client), client


def make_gemini_adapter(
    *,
    text: str = "ok",
    finish_reason: str = "STOP",
    error: BaseException | None = None,
) -> tuple[GeminiAdapter, FakeGeminiClient]:
    client = FakeGeminiClient(text=text, finish_reason=finish_reason, error=error)
    return GeminiAdapter(_settings("gemini"), client=client), client


def test_importing_provider_package_does_not_load_google_genai_sdk() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::DeprecationWarning",
            "-c",
            (
                "import sys; "
                "import tech_daily.llm.providers; "
                "assert 'google.genai' not in sys.modules; "
                "assert 'google.genai.errors' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("adapter_factory", "expected_limit_field"),
    [
        (make_deepseek_adapter, "max_tokens"),
        (make_claude_adapter, "max_tokens"),
        (make_openai_adapter, "max_completion_tokens"),
        (make_gemini_adapter, "max_output_tokens"),
    ],
)
def test_each_adapter_translates_text_token_budget(
    adapter_factory: Callable[..., tuple[Any, Any]],
    expected_limit_field: str,
) -> None:
    adapter, fake_client = adapter_factory(text="ok")

    response = adapter.generate_text(TextRequest("system", "user", max_output_tokens=321))

    assert response.text == "ok"
    assert response.finish_reason is FinishReason.COMPLETE
    assert fake_client.last_request[expected_limit_field] == 321


def test_claude_continuation_uses_anthropic_assistant_history() -> None:
    adapter, client = make_claude_adapter(text="rest")

    response = adapter.continue_text(TextRequest("system", "user", max_output_tokens=321), "part")

    assert response.text == "rest"
    assert client.last_request["messages"] == [
        {"role": "user", "content": "user"},
        {"role": "assistant", "content": "part"},
        {"role": "user", "content": CONTINUE_PROMPT},
    ]


@pytest.mark.parametrize("adapter_factory", [make_deepseek_adapter, make_openai_adapter])
def test_openai_compatible_continuation_uses_chat_assistant_history(
    adapter_factory: Callable[..., tuple[Any, FakeOpenAICompatibleClient]],
) -> None:
    adapter, client = adapter_factory(text="rest")

    response = adapter.continue_text(TextRequest("system", "user", max_output_tokens=321), "part")

    assert response.text == "rest"
    assert client.last_request["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
        {"role": "assistant", "content": "part"},
        {"role": "user", "content": CONTINUE_PROMPT},
    ]


def test_gemini_continuation_uses_model_history() -> None:
    adapter, client = make_gemini_adapter(text="rest")

    response = adapter.continue_text(TextRequest("system", "user", max_output_tokens=321), "part")

    assert response.text == "rest"
    assert client.last_request["contents"] == [
        {"role": "user", "parts": [{"text": "user"}]},
        {"role": "model", "parts": [{"text": "part"}]},
        {"role": "user", "parts": [{"text": CONTINUE_PROMPT}]},
    ]


def test_build_provider_adapters_preserves_configured_order() -> None:
    order = ("gemini", "openai", "claude", "deepseek")
    settings = LLMSettings(
        provider_order=order,
        providers={name: _settings(name) for name in order},
    )

    adapters = build_provider_adapters(settings)

    assert tuple(adapter.name for adapter in adapters) == order


@pytest.mark.parametrize(
    "adapter_factory",
    [make_deepseek_adapter, make_claude_adapter, make_openai_adapter, make_gemini_adapter],
)
def test_arbitrary_programming_errors_propagate(
    adapter_factory: Callable[..., tuple[Any, Any]],
) -> None:
    adapter, _ = adapter_factory(error=TypeError("programming defect"))

    with pytest.raises(TypeError, match="programming defect"):
        adapter.generate_text(TextRequest("system", "user"))


def test_spoofed_google_api_error_provenance_does_not_load_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class APIError(Exception):
        pass

    APIError.__module__ = "google.genai.errors"
    provider_error = APIError("unexpected")
    adapter, _ = make_gemini_adapter(error=provider_error)
    monkeypatch.setattr(gemini_provider, "_GOOGLE_GENAI_API_ERRORS", None)
    monkeypatch.delitem(sys.modules, "google.genai.errors", raising=False)
    monkeypatch.setattr(
        gemini_provider,
        "_load_google_genai_api_errors",
        lambda: pytest.fail("unexpected Google Gen AI SDK load"),
    )

    with pytest.raises(APIError) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value is provider_error


def test_claude_translates_documented_authentication_failure() -> None:
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com"))
    provider_error = anthropic.AuthenticationError("secret", response=response, body=None)
    adapter, _ = make_claude_adapter(error=provider_error)

    with pytest.raises(AuthenticationFailure) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


def test_deepseek_translates_documented_rate_limit_failure() -> None:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.deepseek.com"))
    provider_error = openai.RateLimitError("secret", response=response, body=None)
    adapter, _ = make_deepseek_adapter(error=provider_error)

    with pytest.raises(RateLimited) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


def test_openai_distinguishes_quota_exhaustion_from_rate_limiting() -> None:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com"))
    provider_error = openai.RateLimitError(
        "secret",
        response=response,
        body={"error": {"code": "insufficient_quota"}},
    )
    adapter, _ = make_openai_adapter(error=provider_error)

    with pytest.raises(QuotaExceeded) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


def test_gemini_translates_documented_quota_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = FakeGoogleGenAIClientError(
        429,
        {"error": {"status": "RESOURCE_EXHAUSTED"}},
    )
    adapter, _ = make_gemini_adapter(error=provider_error)
    _install_fake_google_genai_errors(monkeypatch)

    with pytest.raises(QuotaExceeded) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error
    assert (FakeGoogleGenAIAPIError,) == gemini_provider._GOOGLE_GENAI_API_ERRORS


@pytest.mark.parametrize(
    "adapter_factory",
    [make_deepseek_adapter, make_claude_adapter, make_openai_adapter, make_gemini_adapter],
)
def test_http_network_failures_are_normalized(
    adapter_factory: Callable[..., tuple[Any, Any]],
) -> None:
    provider_error = httpx.ConnectError(
        "secret",
        request=httpx.Request("POST", "https://provider.invalid"),
    )
    adapter, _ = adapter_factory(error=provider_error)

    with pytest.raises(NetworkFailure) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


def test_openai_uses_legacy_compatible_extra_body_for_current_token_limit() -> None:
    adapter, client = make_openai_adapter()

    adapter.generate_text(TextRequest("system", "user", max_output_tokens=321))

    assert "max_completion_tokens" not in client.raw_request
    assert client.raw_request["extra_body"] == {"max_completion_tokens": 321}


@pytest.mark.parametrize("adapter_factory", [make_deepseek_adapter, make_openai_adapter])
def test_openai_compatible_message_without_optional_refusal_is_valid(
    adapter_factory: Callable[..., tuple[Any, FakeOpenAICompatibleClient]],
) -> None:
    adapter, client = adapter_factory()
    client._response.choices[0].message = SimpleNamespace(content="ok")

    response = adapter.generate_text(TextRequest("system", "user"))

    assert response.text == "ok"


@pytest.mark.parametrize(
    ("adapter_factory", "malformed_response"),
    [
        (make_claude_adapter, SimpleNamespace(content=[], stop_reason="end_turn")),
        (make_deepseek_adapter, SimpleNamespace(choices=[])),
        (make_openai_adapter, SimpleNamespace(choices=[])),
        (make_gemini_adapter, SimpleNamespace(text="", candidates=[])),
    ],
)
def test_malformed_provider_response_shapes_are_normalized(
    adapter_factory: Callable[..., tuple[Any, Any]],
    malformed_response: object,
) -> None:
    adapter, client = adapter_factory()
    client._response = malformed_response

    with pytest.raises(InvalidProviderResponse):
        adapter.generate_text(TextRequest("system", "user"))


@pytest.mark.parametrize(
    ("adapter_factory", "error_factory"),
    [
        (
            make_claude_adapter,
            lambda response: anthropic.APIResponseValidationError(response=response, body=None),
        ),
        (
            make_openai_adapter,
            lambda response: openai.APIResponseValidationError(response=response, body=None),
        ),
    ],
)
def test_sdk_response_validation_failures_are_normalized(
    adapter_factory: Callable[..., tuple[Any, Any]],
    error_factory: Callable[[httpx.Response], BaseException],
) -> None:
    response = httpx.Response(200, request=httpx.Request("POST", "https://provider.invalid"))
    provider_error = error_factory(response)
    adapter, _ = adapter_factory(error=provider_error)

    with pytest.raises(InvalidProviderResponse) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


@pytest.mark.parametrize("adapter_factory", [make_claude_adapter, make_openai_adapter])
def test_http_408_is_normalized_as_network_failure(
    adapter_factory: Callable[..., tuple[Any, Any]],
) -> None:
    request = httpx.Request("POST", "https://provider.invalid")
    response = httpx.Response(408, request=request)
    provider_error = httpx.HTTPStatusError("timeout", request=request, response=response)
    adapter, _ = adapter_factory(error=provider_error)

    with pytest.raises(NetworkFailure) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (FakeGoogleGenAIClientError(401, {}), AuthenticationFailure),
        (FakeGoogleGenAIClientError(408, {}), NetworkFailure),
        (FakeGoogleGenAIClientError(429, {}), RateLimited),
        (
            FakeGoogleGenAIClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}}),
            QuotaExceeded,
        ),
        (FakeGoogleGenAIServerError(503, {}), ProviderUnavailable),
    ],
)
def test_google_genai_api_errors_are_normalized(
    provider_error: FakeGoogleGenAIAPIError,
    expected_error: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = make_gemini_adapter(error=provider_error)
    _install_fake_google_genai_errors(monkeypatch)

    with pytest.raises(expected_error) as raised:
        adapter.generate_text(TextRequest("system", "user"))

    assert raised.value.__cause__ is provider_error
    assert (FakeGoogleGenAIAPIError,) == gemini_provider._GOOGLE_GENAI_API_ERRORS
