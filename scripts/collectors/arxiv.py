"""arXiv source collector."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

from state import RawEvent

from collectors.base import cutoff_dt, now_iso, parse_date, text
from collectors.retry import NETWORK_RETRY_CONFIG, retry_async
from collectors.telemetry import CollectorWarning

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


async def fetch_arxiv(
    client: Any,
    categories: list[str],
    max_per_cat: int,
    days_back: int,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    cutoff = cutoff_dt(days_back * 24)

    for cat in categories:
        try:
            await asyncio.sleep(0.5)  # polite rate limiting
            params = {
                "search_query": f"cat:{cat}",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": max_per_cat,
            }
            url = f"{ARXIV_API}?{urlencode(params)}"

            async def fetch_category(category_url: str = url) -> Any:
                response = await client.get(category_url, timeout=30)
                response.raise_for_status()
                return response

            resp = await retry_async(
                fetch_category,
                operation_name=f"arXiv {cat}",
                warnings=warnings,
                config=NETWORK_RETRY_CONFIG,
            )
            root = ET.fromstring(resp.text)

            for entry in root.findall("atom:entry", ARXIV_NS):
                title = text(entry, "atom:title", ARXIV_NS).replace("\n", " ").strip()
                pub = text(entry, "atom:published", ARXIV_NS)
                summary = text(entry, "atom:summary", ARXIV_NS).replace("\n", " ").strip()
                arxiv_id_el = entry.find("atom:id", ARXIV_NS)
                arxiv_url = (arxiv_id_el.text or "").strip() if arxiv_id_el is not None else ""
                authors = [text(a, "atom:name", ARXIV_NS) for a in entry.findall("atom:author", ARXIV_NS)]

                # Skip old papers
                if pub:
                    try:
                        parsed = parse_date(pub)
                        if parsed and parsed < cutoff:
                            continue
                    except Exception:
                        pass

                events.append(
                    RawEvent(
                        source_name=f"arXiv {cat}",
                        source_type="arxiv",
                        raw_title=title,
                        raw_url=arxiv_url,
                        raw_content=summary[:2000],
                        published_at=pub,
                        fetched_at=now_iso(),
                        metadata={
                            "category": cat,
                            "authors": authors,
                            "arxiv_url": arxiv_url,
                            # Extract bare ID (e.g. "2501.12345") from the full abs URL
                            "arxiv_id": arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else "",
                        },
                    )
                )
        except Exception as e:
            print(f"  [arXiv] {cat} failed: {e}")

    return events
