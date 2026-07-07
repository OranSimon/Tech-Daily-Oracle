from __future__ import annotations

from pathlib import Path


def test_package_layout_migration_plan_exists() -> None:
    doc = Path("docs/package_layout.md")

    assert doc.exists()


def test_package_layout_plan_preserves_legacy_entrypoints() -> None:
    text = Path("docs/package_layout.md").read_text(encoding="utf-8")

    assert "scripts/run_daily.py" in text
    assert "scripts/run_weekly_review.py" in text
    assert "scripts/run_monthly_review.py" in text
    assert "compatibility facade" in text


def test_package_layout_plan_has_incremental_target_structure() -> None:
    text = Path("docs/package_layout.md").read_text(encoding="utf-8")

    assert "src/tech_daily/" in text
    assert "tech_daily.collectors" in text
    assert "tech_daily.llm" in text
    assert "tech_daily.pipeline" in text
    assert "src/tech_daily/cli/run_daily.py" in text
    assert "primary daily CLI implementation" in text


def test_architecture_boundaries_document_intentional_non_goals() -> None:
    text = Path("docs/architecture_boundaries.md").read_text(encoding="utf-8")

    assert "TechDailyState remains the compatibility shell" in text
    assert "Do not introduce a workflow engine" in text
    assert "Do not introduce dynamic plugin loading" in text
    assert "Do not introduce a database" in text


def test_architecture_boundaries_document_wrapper_policy() -> None:
    text = Path("docs/architecture_boundaries.md").read_text(encoding="utf-8")

    assert "scripts/ entrypoints may remain as compatibility wrappers" in text
    assert "New business logic should live under src/tech_daily/" in text
