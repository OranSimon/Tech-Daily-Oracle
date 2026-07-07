"""Compatibility wrapper for package-owned daily step actions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tech_daily.pipeline import actions as _actions  # noqa: E402
from tech_daily.pipeline.actions import *  # noqa: F403,E402

sys.modules[__name__] = _actions
