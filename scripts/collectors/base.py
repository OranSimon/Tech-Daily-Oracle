"""Shared helpers for source collectors."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Protocol

from state import RawEvent


class SourceCollector(Protocol):
    """Minimal async collector shape for source-specific fetchers."""

    async def __call__(self) -> list[RawEvent]:
        """Return raw events for a source."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def cutoff_dt(hours: int) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def text(el: ET.Element, tag: str, ns: dict | None = None) -> str:
    found = el.find(tag, ns) if ns else el.find(tag)
    return found.text.strip() if found is not None and found.text else ""


def parse_date(s: str) -> datetime | None:
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None
