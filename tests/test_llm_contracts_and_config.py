from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tech_daily.llm.config import LLMConfigurationError, load_llm_settings, resolve_role
from tech_daily.llm.contracts import (
    FinishReason,
    LLMResponse,
    ModelRole,
    SearchRequest,
    SearchResponse,
    StructuredRequest,
    TextRequest,
)
from tech_daily.llm.errors import (
    AuthenticationFailure,
    InvalidProviderResponse,
    MissingCredential,
    NetworkFailure,
    ProviderExhaustedError,
    ProviderUnavailable,
    QuotaExceeded,
    RateLimited,
    is_fallback_eligible,
)


def test_only_approved_provider_errors_are_fallback_eligible() -> None:
    eligible = [
        MissingCredential("deepseek"),
        AuthenticationFailure("deepseek"),
        RateLimited("deepseek"),
        QuotaExceeded("deepseek"),
        NetworkFailure("deepseek"),
        ProviderUnavailable("deepseek"),
        InvalidProviderResponse("deepseek"),
    ]
    assert all(is_fallback_eligible(error) for error in eligible)
    assert not is_fallback_eligible(TypeError("programming defect"))


def test_malformed_yaml_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("ai_providers: [", encoding="utf-8")
    with pytest.raises(LLMConfigurationError):
        load_llm_settings(path)


def test_model_hint_is_converted_to_neutral_role() -> None:
    assert resolve_role("claude-haiku-4-5") is ModelRole.FAST
    assert resolve_role("gemini-3.1-pro-preview") is ModelRole.DEEP
    assert resolve_role("default") is ModelRole.DEFAULT


def test_neutral_requests_are_immutable_and_keep_their_normalized_defaults() -> None:
    request = TextRequest("system", "user")

    assert request.role is ModelRole.DEFAULT
    assert request.max_output_tokens == 4096
    assert request.cache_system is True
    with pytest.raises(FrozenInstanceError):
        request.user = "replacement"  # type: ignore[misc]

    assert StructuredRequest("system", "user", {"type": "object"}).json_schema == {"type": "object"}
    assert SearchRequest("recent AI news").max_results == 5
    assert LLMResponse("ok", "deepseek", "deepseek-v4-flash", FinishReason.COMPLETE).text == "ok"


def test_missing_provider_section_uses_current_safe_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("run: {}\n", encoding="utf-8")

    settings = load_llm_settings(path)

    assert settings.provider_order == ("deepseek", "claude", "openai", "gemini")
    assert settings.providers["deepseek"].models[ModelRole.DEFAULT] == "deepseek-v4-flash"
    assert settings.providers["claude"].models[ModelRole.FAST] == "claude-haiku-4-5-20251001"
    assert settings.providers["openai"].models[ModelRole.DEFAULT] == "gpt-5.5"
    assert settings.providers["gemini"].models[ModelRole.DEEP] == "gemini-3.1-pro-preview"


def test_exhausted_error_keeps_only_an_immutable_attempt_tuple() -> None:
    error = ProviderExhaustedError("generate_text", ["deepseek: rate_limited"])

    assert error.capability == "generate_text"
    assert error.attempts == ("deepseek: rate_limited",)


def test_exhausted_error_redacts_untrusted_attempt_details() -> None:
    secret = "sk-test-123456 secret prompt and generated response"
    error = ProviderExhaustedError("generate_text", [secret, f"deepseek: rate_limited; {secret}"])

    exposed = f"{error.attempts!r} {error}"

    assert secret not in exposed
    assert error.attempts == ("provider_failure", "provider_failure")


def test_null_provider_section_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("ai_providers: null\n", encoding="utf-8")

    with pytest.raises(LLMConfigurationError):
        load_llm_settings(path)


def test_structured_request_defensively_freezes_nested_schema_data() -> None:
    schema = {"properties": {"answer": {"enum": ["original"]}}}
    request = StructuredRequest("system", "user", schema)

    schema["properties"]["answer"]["enum"].append("leaked")

    assert request.json_schema["properties"]["answer"]["enum"] == ("original",)
    with pytest.raises(TypeError):
        request.json_schema["properties"] = {}  # type: ignore[index]


def test_search_response_defensively_freezes_nested_result_data() -> None:
    results = [{"title": "original", "metadata": {"topics": ["AI"]}}]
    response = SearchResponse(results, "deepseek", "deepseek-v4-flash")

    results[0]["metadata"]["topics"].append("leaked")

    assert response.results[0]["metadata"]["topics"] == ("AI",)
    with pytest.raises(TypeError):
        response.results[0]["title"] = "replacement"  # type: ignore[index]
