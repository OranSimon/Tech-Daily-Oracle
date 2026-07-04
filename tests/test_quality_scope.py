from __future__ import annotations

import tomllib
from pathlib import Path

EXPECTED_STABLE_PRODUCTION_PATHS = {
    "scripts/config_models.py",
    "scripts/collectors/retry.py",
    "scripts/collectors/telemetry.py",
    "scripts/pipeline_errors.py",
    "scripts/pipeline_policy.py",
    "scripts/pipeline_state.py",
    "scripts/pipeline_step.py",
    "scripts/run_context.py",
    "scripts/run_logging.py",
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
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for path in EXPECTED_STABLE_PRODUCTION_PATHS:
        assert path in workflow
