"""Compatibility wrapper for package-owned daily pipeline composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.pipeline import daily as _daily  # noqa: E402
from tech_daily.pipeline.daily import *  # noqa: F403,E402

sys.modules[__name__] = _daily
