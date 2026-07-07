"""Compatibility wrapper for storage I/O package module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.storage import io as _io  # noqa: E402
from tech_daily.storage.io import (  # noqa: E402
    append_jsonl_rows_safely,
    atomic_replace,
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    quarantine_jsonl_row,
)

os = _io.os

__all__ = [
    "append_jsonl_rows_safely",
    "atomic_replace",
    "atomic_write_json",
    "atomic_write_jsonl",
    "atomic_write_text",
    "os",
    "quarantine_jsonl_row",
]
