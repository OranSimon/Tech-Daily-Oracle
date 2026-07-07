from __future__ import annotations

import re
import tomllib
from pathlib import Path


def _normalise_requirement(value: str) -> str:
    return re.split(r"[<>=!~]", value.strip(), maxsplit=1)[0].strip().lower().replace("_", "-")


def test_requirements_txt_matches_project_runtime_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_deps = {_normalise_requirement(dep) for dep in pyproject["project"]["dependencies"]}
    requirements = {
        _normalise_requirement(line.split("#", maxsplit=1)[0])
        for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert requirements == project_deps


def test_scheduled_workflows_install_package_metadata() -> None:
    workflow_paths = [
        Path(".github/workflows/daily.yml"),
        Path(".github/workflows/weekly_review.yml"),
        Path(".github/workflows/monthly_review.yml"),
    ]

    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        assert "python -m pip install -e ." in text
        assert "pip install -r requirements.txt" not in text
