from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SDKS = {
    "anthropic>=0.116.0",
    "openai>=2.44.0",
    "google-genai>=2.13.0",
}


def _requirements_txt_dependencies() -> set[str]:
    dependencies: set[str] = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        requirement = line.partition("#")[0].strip()
        if requirement:
            dependencies.add(requirement)
    return dependencies


def test_native_search_sdk_floors_match_in_both_dependency_manifests() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pyproject_dependencies = set(pyproject["project"]["dependencies"])
    requirements_dependencies = _requirements_txt_dependencies()

    assert pyproject_dependencies >= REQUIRED_SDKS
    assert requirements_dependencies >= REQUIRED_SDKS
    assert not any(
        dependency.startswith("google-generativeai")
        for dependency in pyproject_dependencies | requirements_dependencies
    )
