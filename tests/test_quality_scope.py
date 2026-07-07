from __future__ import annotations

import tomllib
from pathlib import Path

EXPECTED_STABLE_PRODUCTION_PATHS = {
    "src/tech_daily/__init__.py",
    "src/tech_daily/cli/__init__.py",
    "src/tech_daily/cli/daily_parser.py",
    "src/tech_daily/cli/run_daily.py",
    "src/tech_daily/config/normalization_policy.py",
    "src/tech_daily/llm/__init__.py",
    "src/tech_daily/llm/client.py",
    "src/tech_daily/llm/prompt_runner.py",
    "src/tech_daily/llm/schemas.py",
    "src/tech_daily/pipeline/__init__.py",
    "src/tech_daily/pipeline/actions.py",
    "src/tech_daily/pipeline/daily.py",
    "src/tech_daily/pipeline/policy.py",
    "src/tech_daily/pipeline/run_summary.py",
    "src/tech_daily/pipeline/state.py",
    "src/tech_daily/pipeline/step.py",
    "src/tech_daily/predictions/__init__.py",
    "src/tech_daily/predictions/results.py",
    "src/tech_daily/quality_paths.py",
    "src/tech_daily/reports/__init__.py",
    "src/tech_daily/reports/daily.py",
    "src/tech_daily/runtime/__init__.py",
    "src/tech_daily/runtime/run_context.py",
    "src/tech_daily/runtime/run_logging.py",
    "src/tech_daily/state/__init__.py",
    "src/tech_daily/state/contracts.py",
    "src/tech_daily/storage/__init__.py",
    "src/tech_daily/storage/_shared.py",
    "src/tech_daily/storage/context.py",
    "src/tech_daily/storage/event_payloads.py",
    "src/tech_daily/storage/events.py",
    "src/tech_daily/storage/io.py",
    "src/tech_daily/storage/predictions.py",
    "src/tech_daily/storage/reports.py",
    "src/tech_daily/storage/run_summary.py",
    "src/tech_daily/storage/telemetry.py",
    "src/tech_daily/storage/validation.py",
    "scripts/config_models.py",
    "scripts/collectors/arxiv.py",
    "scripts/collectors/base.py",
    "scripts/collectors/github.py",
    "scripts/collectors/hackernews.py",
    "scripts/collectors/huggingface.py",
    "scripts/collectors/registry.py",
    "scripts/collectors/retry.py",
    "scripts/collectors/rss.py",
    "scripts/collectors/telemetry.py",
    "scripts/collectors/web_search.py",
    "scripts/pipeline_errors.py",
    "scripts/pipeline_policy.py",
    "scripts/pipeline_state.py",
    "scripts/pipeline_step.py",
    "scripts/daily_pipeline.py",
    "scripts/daily_step_actions.py",
    "scripts/generate_report.py",
    "scripts/llm_client.py",
    "scripts/llm_schemas.py",
    "scripts/prompt_runner.py",
    "scripts/run_context.py",
    "scripts/run_logging.py",
    "scripts/storage.py",
    "scripts/storage_io.py",
    "scripts/storage_validation.py",
}


def test_quality_scope_declares_stable_production_modules() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    stable_paths = set(pyproject["tool"]["tech_daily"]["quality"]["stable_paths"])

    assert stable_paths >= EXPECTED_STABLE_PRODUCTION_PATHS


def test_mypy_scope_includes_stable_production_modules() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    mypy_files = set(pyproject["tool"]["mypy"]["files"])

    assert "tests" not in mypy_files
    assert mypy_files >= EXPECTED_STABLE_PRODUCTION_PATHS
    assert pyproject["tool"]["mypy"]["follow_imports"] == "silent"


def test_ci_runs_ruff_on_stable_production_modules() -> None:
    from tech_daily.quality_paths import iter_quality_paths

    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    stable_paths = set(iter_quality_paths())

    for path in EXPECTED_STABLE_PRODUCTION_PATHS:
        assert path in stable_paths

    assert "xargs ruff format --check < quality-paths.txt" in workflow
    assert "xargs ruff check < quality-paths.txt" in workflow


def test_quality_paths_helper_reads_pyproject_stable_paths() -> None:
    from tech_daily.quality_paths import iter_quality_paths

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["tool"]["tech_daily"]["quality"]["stable_paths"]

    assert iter_quality_paths() == expected


def test_ci_generates_quality_paths_from_pyproject() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python -m tech_daily.quality_paths" in workflow
    assert "cat > quality-paths.txt" not in workflow


def test_mypy_has_stricter_package_foundation_scope() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    overrides = pyproject["tool"]["mypy"]["overrides"]
    package_foundation = next(
        override for override in overrides if override["module"] == ["tech_daily.runtime.*", "tech_daily.pipeline.*"]
    )

    assert package_foundation["check_untyped_defs"] is True
    assert package_foundation["warn_return_any"] is True


def test_mypy_has_stricter_storage_package_scope() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    overrides = pyproject["tool"]["mypy"]["overrides"]
    storage_override = next(override for override in overrides if override["module"] == ["tech_daily.storage.*"])

    assert storage_override["check_untyped_defs"] is True
    assert storage_override["warn_return_any"] is True


def test_mypy_has_stricter_predictions_package_scope() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    overrides = pyproject["tool"]["mypy"]["overrides"]
    predictions_override = next(
        override for override in overrides if override["module"] == ["tech_daily.predictions.*"]
    )

    assert predictions_override["check_untyped_defs"] is True
    assert predictions_override["warn_return_any"] is True
