from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "collector-health.yml"


def _load_workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_collector_health_workflow_is_manual_only() -> None:
    workflow = _load_workflow()

    assert set(workflow["on"].keys()) == {"workflow_dispatch"}
    assert "push" not in workflow["on"]
    assert "pull_request" not in workflow["on"]
    assert "schedule" not in workflow["on"]


def test_collector_health_workflow_exposes_threshold_inputs() -> None:
    inputs = _load_workflow()["on"]["workflow_dispatch"]["inputs"]

    for name in [
        "days",
        "collector",
        "max_failed_rate",
        "max_partial_rate",
        "max_consecutive_failures",
        "min_record_count",
        "max_avg_duration",
        "require_recent_success",
    ]:
        assert name in inputs


def test_collector_health_workflow_is_read_only_and_does_not_run_collectors() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = _load_workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert "scripts/diagnose_collectors.py" in workflow_text
    assert "scripts/run_daily.py" not in workflow_text
    assert "collect_sources" not in workflow_text
    assert "git push" not in workflow_text
