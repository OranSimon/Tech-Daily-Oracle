"""Hacker News source collector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from state import RawEvent

from collectors.base import now_iso
from collectors.retry import NETWORK_RETRY_CONFIG, retry_async
from collectors.telemetry import CollectorWarning

HN_BASE = "https://hacker-news.firebaseio.com/v0"


async def fetch_hn(
    client: Any,
    top_n: int,
    min_score: int,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    try:

        async def fetch_topstories() -> Any:
            return await client.get(f"{HN_BASE}/topstories.json", timeout=20)

        resp = await retry_async(
            fetch_topstories,
            operation_name="Hacker News topstories",
            warnings=warnings,
            config=NETWORK_RETRY_CONFIG,
        )
        ids = resp.json()[: top_n * 2]  # over-fetch to filter

        semaphore = asyncio.Semaphore(10)

        async def fetch_item(item_id: int) -> RawEvent | None:
            async with semaphore:
                try:

                    async def fetch_hn_item() -> Any:
                        return await client.get(f"{HN_BASE}/item/{item_id}.json", timeout=10)

                    r = await retry_async(
                        fetch_hn_item,
                        operation_name=f"Hacker News item {item_id}",
                        warnings=warnings,
                        config=NETWORK_RETRY_CONFIG,
                    )
                    item = r.json()
                    if not item or item.get("type") != "story":
                        return None
                    if item.get("score", 0) < min_score:
                        return None
                    title = item.get("title", "")
                    url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
                    return RawEvent(
                        source_name="Hacker News",
                        source_type="hacker_news",
                        raw_title=title,
                        raw_url=url,
                        raw_content=item.get("text", "")[:1000],
                        published_at=datetime.fromtimestamp(item.get("time", 0), tz=UTC).isoformat(),
                        fetched_at=now_iso(),
                        metadata={
                            "hn_id": item_id,
                            "score": item.get("score", 0),
                            "comments": item.get("descendants", 0),
                            "hn_url": f"https://news.ycombinator.com/item?id={item_id}",
                        },
                    )
                except Exception:
                    return None

        tasks = [fetch_item(i) for i in ids]
        results = await asyncio.gather(*tasks)
        events = [r for r in results if r is not None][:top_n]
    except Exception as e:
        print(f"  [HN] Failed: {e}")
    return events
