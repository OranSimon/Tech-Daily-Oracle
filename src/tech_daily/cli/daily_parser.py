"""Shared parser construction for the daily CLI."""

from __future__ import annotations

import argparse


def build_daily_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Tech Daily Agent")
    parser.add_argument("--date", help="Run date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a report already exists for this date")
    return parser
