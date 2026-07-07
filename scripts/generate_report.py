"""Compatibility alias for package-owned daily report generation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prompt_runner import PromptRunner
    from state import TechDailyState

    from tech_daily.pipeline.state import ReportInputState

    ROOT: str
    DEFAULT_DAILY_MODEL: str

    def _load_config() -> Any: ...

    def _load_preferences() -> Any: ...

    def _previous_reports_summary_from_input(input_state: ReportInputState) -> list[dict[str, Any]]: ...

    def _safe_dict(obj: Any) -> Any: ...

    def _build_report_payload(state: TechDailyState) -> dict[str, Any]: ...

    def build_daily_report_payload_from_input(input_state: ReportInputState) -> dict[str, Any]: ...

    def generate_daily_report(state: TechDailyState, prompt_runner: PromptRunner | None = None) -> str: ...

    def generate_daily_report_from_input(
        input_state: ReportInputState, prompt_runner: PromptRunner | None = None
    ) -> str: ...


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

sys.modules[__name__] = importlib.import_module("tech_daily.reports.daily")
