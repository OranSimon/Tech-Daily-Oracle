"""RSS and Atom source collector."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from state import RawEvent

from collectors.base import now_iso, parse_date, text
from collectors.retry import NETWORK_RETRY_CONFIG, retry_async
from collectors.telemetry import CollectorWarning


async def fetch_rss(
    client: Any,
    feed: dict[str, Any],
    cutoff: datetime,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    try:

        async def fetch_feed() -> Any:
            response = await client.get(feed["url"], timeout=20, follow_redirects=True)
            response.raise_for_status()
            return response

        resp = await retry_async(
            fetch_feed,
            operation_name=f"RSS {feed['name']}",
            warnings=warnings,
            config=NETWORK_RETRY_CONFIG,
        )
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Try Atom entries first, then fall back to RSS <item> elements
        entries = root.findall("atom:entry", ns)
        if not entries:
            entries = root.findall(".//item")

        for entry in entries:
            # Try both Atom and RSS field names
            title = text(entry, "atom:title", ns) or text(entry, "title") or ""
            # Atom <link> stores the URL in the href attribute, not .text
            atom_link_el = entry.find("atom:link", ns)
            atom_link = atom_link_el.get("href", "") if atom_link_el is not None else ""
            link = atom_link or text(entry, "link") or entry.get("href", "")
            pub = (
                text(entry, "pubDate")
                or text(entry, "published")
                or text(entry, "atom:published", ns)
                or text(entry, "updated")
                or ""
            )
            content = text(entry, "description") or text(entry, "atom:summary", ns) or text(entry, "content") or ""

            # Skip if too old
            if pub:
                try:
                    parsed_pub = parse_date(pub)
                    if parsed_pub and parsed_pub < cutoff:
                        continue
                except Exception:
                    pass

            if title and link:
                events.append(
                    RawEvent(
                        source_name=feed["name"],
                        source_type="rss",
                        raw_title=title.strip(),
                        raw_url=link.strip(),
                        raw_content=content[:2000],
                        published_at=pub,
                        fetched_at=now_iso(),
                        metadata={
                            "feed_source_type": feed.get("source_type", "media"),
                            "priority": feed.get("priority", 3),
                            "topics": feed.get("topics", []),
                        },
                    )
                )
    except Exception as e:
        print(f"  [RSS] Failed {feed['name']}: {e}")
    return events
