from __future__ import annotations

from pathlib import Path

FORBIDDEN_CLAUDE_TOKENS = [
    "from claude_client import",
    "import claude_client",
    "call_claude_json",
    "call_claude(",
    "call_claude_web_search",
]

ALLOWED_CLAUDE_BOUNDARY_FILES = {
    Path("scripts/claude_client.py"),
    Path("scripts/llm_client.py"),
    Path("scripts/web_search_client.py"),
}

MIGRATED_ANALYZERS = [
    Path("scripts/analyze_topics.py"),
    Path("scripts/analyze_companies.py"),
    Path("scripts/analyze_papers.py"),
    Path("scripts/analyze_github_projects.py"),
    Path("scripts/analyze_macro_impact.py"),
    Path("scripts/analyze_social_signals.py"),
    Path("scripts/analyze_trending.py"),
    Path("scripts/analyze_market_signals.py"),
    Path("scripts/update_predictions.py"),
    Path("scripts/generate_report.py"),
    Path("scripts/run_weekly_review.py"),
    Path("scripts/run_monthly_review.py"),
    Path("scripts/collect_sources.py"),
]


def test_migrated_analyzers_do_not_import_or_call_claude_directly() -> None:
    for path in MIGRATED_ANALYZERS:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_CLAUDE_TOKENS:
            assert token not in text, f"{path} contains direct Claude dependency: {token}"


def test_only_boundary_files_use_legacy_claude_client_directly() -> None:
    production_scripts = sorted(Path("scripts").rglob("*.py"))

    for path in production_scripts:
        if path in ALLOWED_CLAUDE_BOUNDARY_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_CLAUDE_TOKENS:
            assert token not in text, (
                f"{path} contains direct Claude dependency {token!r}; use PromptRunner or WebSearchClient instead"
            )
