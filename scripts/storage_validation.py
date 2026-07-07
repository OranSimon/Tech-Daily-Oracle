"""Compatibility wrapper for storage validation package module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.storage.validation import (  # noqa: E402
    StorageDiagnostics,
    StorageWarning,
    migrate_collector_telemetry_row,
    validate_collector_telemetry_row,
    validate_open_prediction_row,
)

__all__ = [
    "StorageDiagnostics",
    "StorageWarning",
    "migrate_collector_telemetry_row",
    "validate_collector_telemetry_row",
    "validate_open_prediction_row",
]
