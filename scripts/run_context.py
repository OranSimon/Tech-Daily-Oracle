"""Compatibility wrapper for runtime context package module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.runtime.run_context import AppConfig, RunContext  # noqa: E402

__all__ = ["AppConfig", "RunContext"]
