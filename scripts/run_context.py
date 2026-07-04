"""Runtime context and lightweight config access for pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    """Small wrapper around the existing config dictionary."""

    raw: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.section(section).get(key, default)

    @property
    def timezone(self) -> str:
        return str(self.get("run", "timezone", "Asia/Shanghai"))

    @property
    def report_window_hours(self) -> int:
        return int(self.get("run", "report_window_hours", 24))

    @property
    def market_signal_enabled(self) -> bool:
        return bool(self.get("market_signal", "enabled", False))

    @property
    def market_live_data_enabled(self) -> bool:
        return bool(self.get("market_signal", "live_data", False))

    @property
    def notion_enabled(self) -> bool:
        return bool(self.get("notion", "enabled", False))

    @property
    def trending_top_n(self) -> int:
        return int(self.get("trending", "top_n", 5))


@dataclass(frozen=True)
class RunContext:
    """Stable metadata and paths for one pipeline run."""

    run_date: str
    run_id: str
    root_dir: Path
    data_dir: Path
    reports_dir: Path
    config: AppConfig

    @classmethod
    def from_config(
        cls,
        *,
        run_date: str,
        run_id: str,
        root_dir: str | Path,
        config: Mapping[str, Any],
    ) -> RunContext:
        root_path = Path(root_dir)
        raw_config = config if isinstance(config, dict) else dict(config)
        return cls(
            run_date=run_date,
            run_id=run_id,
            root_dir=root_path,
            data_dir=root_path / "data",
            reports_dir=root_path / "reports",
            config=AppConfig(raw_config),
        )

    @property
    def daily_report_path(self) -> Path:
        return self.reports_dir / "daily" / f"{self.run_date}.md"

    @property
    def time_window(self) -> str:
        return f"last_{self.config.report_window_hours}h"
