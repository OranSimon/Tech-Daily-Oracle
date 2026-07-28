"""Web-search source collector."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from state import RawEvent
from web_search_client import ProviderWebSearchClient, WebSearchClient

from collectors.base import now_iso
from collectors.retry import RetryConfig, retry_sync
from collectors.telemetry import CollectorWarning
from tech_daily.llm.errors import ProviderExhaustedError


def _retryable_llm_exhaustion(error: BaseException) -> bool:
    return isinstance(error, ProviderExhaustedError)


LLM_RETRY_CONFIG = RetryConfig(retryable=_retryable_llm_exhaustion)

WEB_SEARCH_QUERIES = [
    # --- Core CS / AI beats ---
    "major AI model releases or announcements in the last 24 hours",
    "AI startup funding rounds or unicorn news today",
    "GPU chip semiconductor supply chain news today",
    "robotics embodied AI humanoid robot news today",
    "OpenAI Anthropic Google DeepMind Meta AI news today",
    "Nvidia Apple Microsoft Amazon earnings product news today",
    "China AI DeepSeek ByteDance Huawei tech news today",
    "GitHub trending open source AI developer tools today",
    "AI chip export controls trade policy tech regulation today",
    "AI infrastructure cloud compute data center news today",
    # --- Expanded cross-domain beats ---
    "major physics biology chemistry scientific discovery breakthrough today",
    "FDA drug approval clinical trial vaccine biotech health breakthrough today",
    "NASA ESA SpaceX telescope asteroid astronaut space news today",
    "earthquake pandemic flood disaster global crisis tech impact today",
    "superconductor graphene battery materials science discovery today",
]


def web_search_query_to_events(
    query: str,
    date_str: str,
    web_search_client: WebSearchClient,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    prompt = (
        f"Date: {date_str}\n"
        f"Use web search to find recent news (past 24–48 hours) about: {query}\n\n"
        "Return a JSON array of the most important results found (max 5):\n"
        '[{"title": "...", "url": "...", "source": "...", "summary": "...", '
        '"published_at": "YYYY-MM-DD or ISO string or empty string"}]\n\n'
        "Return only the JSON array. No other text."
    )
    try:
        items = retry_sync(
            lambda: web_search_client.search(prompt, max_uses=3),
            operation_name=f"Web search query: {query[:40]}",
            warnings=warnings,
            config=LLM_RETRY_CONFIG,
        )
    except ProviderExhaustedError as error:
        print(f"  [WebSearch] Query failed ({query[:40]}...): {error}")
        return []

    events = []
    for item in items:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        if not title or not url:
            continue
        events.append(
            RawEvent(
                source_name=item.get("source", "Web Search"),
                source_type="rss",
                raw_title=title,
                raw_url=url,
                raw_content=item.get("summary", "")[:2000],
                published_at=item.get("published_at", now_iso()),
                fetched_at=now_iso(),
                metadata={"priority": 3, "feed_source_type": "media", "via": "web_search", "query": query},
            )
        )
    return events


def fetch_web_search_sync(
    queries: list[str],
    date_str: str,
    web_search_client: WebSearchClient | None = None,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    """Run all web search queries in parallel."""

    client = web_search_client or ProviderWebSearchClient()
    all_events: list[RawEvent] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(5, len(queries))) as executor:
        futures = {executor.submit(web_search_query_to_events, q, date_str, client, warnings): q for q in queries}
        for future in as_completed(futures):
            for event in future.result():
                if event.raw_url not in seen_urls:
                    seen_urls.add(event.raw_url)
                    all_events.append(event)

    print(f"  [WebSearch] Fetched {len(all_events)} events from {len(queries)} queries")
    return all_events
