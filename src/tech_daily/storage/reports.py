"""Report artifact storage helpers."""

from __future__ import annotations

from pathlib import Path

from tech_daily.pipeline.state import Report
from tech_daily.storage._shared import ensure_dirs
from tech_daily.storage._shared import storage_context as resolve_storage_context
from tech_daily.storage.context import StorageContext
from tech_daily.storage.io import atomic_write_text


def save_daily_report(run_date: str, content: str, *, storage_context: StorageContext | None = None) -> str:
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)
    path = context.daily_report_path(run_date)
    atomic_write_text(path, content)
    print(f"  [Storage] Saved daily report: {path}")
    return str(path)


def save_weekly_review(week: str, content: str, *, storage_context: StorageContext | None = None) -> str:
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)
    path = context.weekly_report_path(week)
    atomic_write_text(path, content)
    print(f"  [Storage] Saved weekly review: {path}")
    return str(path)


def save_monthly_review(month: str, content: str, *, storage_context: StorageContext | None = None) -> str:
    context = resolve_storage_context(storage_context)
    ensure_dirs(context)
    path = context.monthly_report_path(month)
    atomic_write_text(path, content)
    print(f"  [Storage] Saved monthly review: {path}")
    return str(path)


def _load_recent_reports_for_dir(directory: Path, report_type: str, n: int) -> list[Report]:
    if not directory.exists():
        return []

    report_files = sorted((path for path in directory.iterdir() if path.suffix == ".md"), reverse=True)
    reports: list[Report] = []
    for path in report_files[:n]:
        report_date = path.stem
        try:
            reports.append(
                Report(
                    report_type=report_type,
                    report_date=report_date,
                    content=path.read_text(encoding="utf-8"),
                )
            )
        except Exception as exception:
            print(f"  [Storage] Failed to load {report_type} report {path.name}: {exception}")
    return reports


def load_recent_reports(n: int = 7, *, storage_context: StorageContext | None = None) -> list[Report]:
    daily_dir = resolve_storage_context(storage_context).reports_dir / "daily"
    return _load_recent_reports_for_dir(daily_dir, "daily", n)


def load_recent_weekly_reviews(n: int = 4, *, storage_context: StorageContext | None = None) -> list[Report]:
    weekly_dir = resolve_storage_context(storage_context).reports_dir / "weekly"
    return _load_recent_reports_for_dir(weekly_dir, "weekly", n)


def load_recent_monthly_reviews(n: int = 3, *, storage_context: StorageContext | None = None) -> list[Report]:
    monthly_dir = resolve_storage_context(storage_context).reports_dir / "monthly"
    return _load_recent_reports_for_dir(monthly_dir, "monthly", n)
