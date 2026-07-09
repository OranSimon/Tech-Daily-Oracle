from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_market_data_runtime_dependency_is_installed() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert '"yfinance>=0.2.40"' in pyproject
    assert "\nyfinance>=0.2.40" in requirements


def test_daily_workflow_exposes_github_token_to_repo_analyzer() -> None:
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")

    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
