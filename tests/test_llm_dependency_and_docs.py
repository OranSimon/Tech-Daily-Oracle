import tomllib
from pathlib import Path

APPROVED_SDK_FLOORS = {
    "anthropic>=0.116.0",
    "openai>=2.44.0",
    "google-genai>=2.13.0",
}


def test_gemini_uses_maintained_sdk() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert any(item.startswith("google-genai") for item in dependencies)
    assert not any(item.startswith("google-generativeai") for item in dependencies)


def test_provider_sdk_floors_match_installation_files() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_dependencies = set(project["project"]["dependencies"])
    requirements = {
        line.split("#", 1)[0].strip()
        for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert project_dependencies >= APPROVED_SDK_FLOORS
    assert requirements >= APPROVED_SDK_FLOORS


def test_docs_do_not_claim_web_search_is_claude_only() -> None:
    text = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in ["README.md", "docs/llm_boundary.md", "docs/collectors.md"]
    )
    assert "web_search is Claude-only" not in text
    assert "Claude fallback + web search" not in text


def test_operator_docs_cover_neutral_routing_contract() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    boundary = Path("docs/llm_boundary.md").read_text(encoding="utf-8")

    assert "one provider key is sufficient" in readme
    assert "subject to model and tool availability" in readme
    assert "fast / default / deep" in readme
    for category in [
        "MissingCredential",
        "AuthenticationFailure",
        "RateLimited",
        "QuotaExceeded",
        "NetworkFailure",
        "ProviderUnavailable",
        "InvalidProviderResponse",
    ]:
        assert category in boundary
    assert "src/tech_daily/llm/providers/" in boundary
    assert "must not import provider SDKs directly" in boundary
    assert "Generated content and credentials are never logged" in boundary
