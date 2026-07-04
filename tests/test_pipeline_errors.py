from __future__ import annotations

from pathlib import Path

MIGRATED_ANALYZER_PATHS = [
    Path("scripts/analyze_topics.py"),
    Path("scripts/analyze_companies.py"),
    Path("scripts/analyze_papers.py"),
    Path("scripts/analyze_github_projects.py"),
    Path("scripts/analyze_macro_impact.py"),
    Path("scripts/analyze_social_signals.py"),
    Path("scripts/analyze_trending.py"),
    Path("scripts/analyze_market_signals.py"),
]


def test_pipeline_error_diagnostic_contains_category_and_context() -> None:
    from pipeline_errors import StorageError

    error = StorageError("failed to write artifact", details={"artifact": "data/x.jsonl"})
    diagnostic = error.to_diagnostic(step="save_outputs")

    assert diagnostic.category == "storage"
    assert diagnostic.severity == "error"
    assert diagnostic.step == "save_outputs"
    assert diagnostic.message == "failed to write artifact"
    assert diagnostic.exception_type == "StorageError"
    assert diagnostic.details == {"artifact": "data/x.jsonl"}


def test_unexpected_exception_can_be_normalized_to_diagnostic() -> None:
    from pipeline_errors import diagnostic_from_exception

    diagnostic = diagnostic_from_exception(
        ValueError("bad config"),
        step="load_config",
        category="config",
        severity="warning",
    )

    assert diagnostic.category == "config"
    assert diagnostic.severity == "warning"
    assert diagnostic.step == "load_config"
    assert diagnostic.message == "bad config"
    assert diagnostic.exception_type == "ValueError"


def test_error_policy_documentation_exists() -> None:
    doc = Path("docs/errors.md").read_text(encoding="utf-8")

    assert "TechDailyError" in doc
    assert "ProviderError" in doc
    assert "Broad Exception Catches" in doc


def test_scripts_do_not_use_bare_except() -> None:
    offenders: list[str] = []
    for path in Path("scripts").rglob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip() == "except:":
                offenders.append(f"{path}:{line_number}")

    assert offenders == []


def test_migrated_analyzers_do_not_silently_swallow_broad_exceptions() -> None:
    offenders: list[str] = []
    for path in MIGRATED_ANALYZER_PATHS:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if line.strip() == "except Exception:":
                body = [next_line.strip() for next_line in lines[line_number : line_number + 3] if next_line.strip()]
                if body and body[0] == "pass":
                    offenders.append(f"{path}:{line_number}")

    assert offenders == []
