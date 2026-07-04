"""Hugging Face daily papers collector."""

from __future__ import annotations

from typing import Any

from state import RawEvent

from collectors.base import now_iso
from collectors.retry import NETWORK_RETRY_CONFIG, retry_async
from collectors.telemetry import CollectorWarning


async def fetch_hf_daily_papers(
    client: Any,
    hf_token: str | None,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    headers = {}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:

        async def fetch_daily_papers() -> Any:
            response = await client.get(
                "https://huggingface.co/api/daily_papers",
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            return response

        resp = await retry_async(
            fetch_daily_papers,
            operation_name="Hugging Face daily papers",
            warnings=warnings,
            config=NETWORK_RETRY_CONFIG,
        )
        papers = resp.json()
        for p in papers:
            paper = p.get("paper", {})
            title = paper.get("title", "")
            arxiv_id = paper.get("id", "")
            url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "https://huggingface.co/papers"
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            events.append(
                RawEvent(
                    source_name="Hugging Face Daily Papers",
                    source_type="huggingface",
                    raw_title=title,
                    raw_url=url,
                    raw_content=paper.get("summary", "")[:2000],
                    published_at=p.get("publishedAt", now_iso()),
                    fetched_at=now_iso(),
                    metadata={
                        "arxiv_id": arxiv_id,
                        "authors": authors,
                        "upvotes": p.get("upvotes", p.get("numUpvotes", 0)),
                        "hf_paper_url": f"https://huggingface.co/papers/{arxiv_id}",
                    },
                )
            )
    except Exception as e:
        print(f"  [HF] Daily papers failed: {e}")
    return events
