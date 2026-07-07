"""Typed storage artifact paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageContext:
    """Typed paths for storage artifacts without changing existing defaults."""

    root_dir: Path
    data_dir: Path
    reports_dir: Path
    prediction_log: Path
    trending_log: Path
    market_signals_log: Path
    collector_runs_log: Path

    @classmethod
    def from_root(cls, root_dir: str | os.PathLike[str]) -> StorageContext:
        root = Path(root_dir)
        data_dir = root / "data"
        return cls(
            root_dir=root,
            data_dir=data_dir,
            reports_dir=root / "reports",
            prediction_log=data_dir / "prediction_log.jsonl",
            trending_log=data_dir / "trending_snapshots.jsonl",
            market_signals_log=data_dir / "market_signals.jsonl",
            collector_runs_log=data_dir / "collector_runs.jsonl",
        )

    @classmethod
    def from_globals(
        cls,
        *,
        root_dir: str | os.PathLike[str] | None = None,
        data_dir: str | os.PathLike[str] | None = None,
        reports_dir: str | os.PathLike[str] | None = None,
        prediction_log: str | os.PathLike[str] | None = None,
        trending_log: str | os.PathLike[str] | None = None,
        market_signals_log: str | os.PathLike[str] | None = None,
        collector_runs_log: str | os.PathLike[str] | None = None,
    ) -> StorageContext:
        root = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[3]
        data = Path(data_dir) if data_dir is not None else root / "data"
        reports = Path(reports_dir) if reports_dir is not None else root / "reports"
        return cls(
            root_dir=root,
            data_dir=data,
            reports_dir=reports,
            prediction_log=Path(prediction_log) if prediction_log is not None else data / "prediction_log.jsonl",
            trending_log=Path(trending_log) if trending_log is not None else data / "trending_snapshots.jsonl",
            market_signals_log=Path(market_signals_log)
            if market_signals_log is not None
            else data / "market_signals.jsonl",
            collector_runs_log=Path(collector_runs_log)
            if collector_runs_log is not None
            else data / "collector_runs.jsonl",
        )

    def daily_report_path(self, run_date: str) -> Path:
        return self.reports_dir / "daily" / f"{run_date}.md"

    def weekly_report_path(self, week: str) -> Path:
        return self.reports_dir / "weekly" / f"{week}.md"

    def monthly_report_path(self, month: str) -> Path:
        return self.reports_dir / "monthly" / f"{month}.md"

    def prediction_log_path(self) -> Path:
        return self.prediction_log

    def trending_log_path(self) -> Path:
        return self.trending_log

    def market_signals_log_path(self) -> Path:
        return self.market_signals_log

    def collector_telemetry_path(self) -> Path:
        return self.collector_runs_log

    def run_summary_log_path(self) -> Path:
        return self.data_dir / "run_summaries.jsonl"
