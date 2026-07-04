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
    assert "No runtime package wrapper is introduced in Phase 17" in text
