"""Source Collector Layer — fetch raw events from all configured sources."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import yaml

from claude_client import call_claude_web_search
from state import RawEvent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict[str, Any]:
    with open(os.path.join(ROOT, "config.yml")) as f:
        return yaml.safe_load(f)


def _load_source_registry() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "source_registry.yml")) as f:
        return yaml.safe_load(f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_dt(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# RSS collector
# ---------------------------------------------------------------------------

async def _fetch_rss(client: httpx.AsyncClient, feed: dict[str, Any], cutoff: datetime) -> list[RawEvent]:
    events: list[RawEvent] = []
    try:
        resp = await client.get(feed["url"], timeout=20, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Try Atom entries first, then fall back to RSS <item> elements
        entries = root.findall("atom:entry", ns)
        if not entries:
            entries = root.findall(".//item")

        for entry in entries:
            # Try both Atom and RSS field names
            title = (
                _text(entry, "atom:title", ns)
                or _text(entry, "title")
                or ""
            )
            # Atom <link> stores the URL in the href attribute, not .text
            atom_link_el = entry.find("atom:link", ns)
            atom_link = (atom_link_el.get("href", "") if atom_link_el is not None else "")
            link = (
                atom_link
                or _text(entry, "link")
                or entry.get("href", "")
            )
            pub = (
                _text(entry, "pubDate")
                or _text(entry, "published")
                or _text(entry, "atom:published", ns)
                or _text(entry, "updated")
                or ""
            )
            content = (
                _text(entry, "description")
                or _text(entry, "atom:summary", ns)
                or _text(entry, "content")
                or ""
            )

            # Skip if too old
            if pub:
                try:
                    parsed_pub = _parse_date(pub)
                    if parsed_pub and parsed_pub < cutoff:
                        continue
                except Exception:
                    pass

            if title and link:
                events.append(RawEvent(
                    source_name=feed["name"],
                    source_type="rss",
                    raw_title=title.strip(),
                    raw_url=link.strip(),
                    raw_content=content[:2000],
                    published_at=pub,
                    fetched_at=_now_iso(),
                    metadata={"feed_source_type": feed.get("source_type", "media"),
                               "priority": feed.get("priority", 3),
                               "topics": feed.get("topics", [])},
                ))
    except Exception as e:
        print(f"  [RSS] Failed {feed['name']}: {e}")
    return events


def _text(el: ET.Element, tag: str, ns: dict | None = None) -> str:
    found = el.find(tag, ns) if ns else el.find(tag)
    return found.text.strip() if found is not None and found.text else ""


def _parse_date(s: str) -> datetime | None:
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
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Hacker News collector
# ---------------------------------------------------------------------------

HN_BASE = "https://hacker-news.firebaseio.com/v0"


async def _fetch_hn(client: httpx.AsyncClient, top_n: int, min_score: int) -> list[RawEvent]:
    events: list[RawEvent] = []
    try:
        resp = await client.get(f"{HN_BASE}/topstories.json", timeout=20)
        ids = resp.json()[:top_n * 2]   # over-fetch to filter

        semaphore = asyncio.Semaphore(10)

        async def fetch_item(item_id: int) -> RawEvent | None:
            async with semaphore:
                try:
                    r = await client.get(f"{HN_BASE}/item/{item_id}.json", timeout=10)
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
                        published_at=datetime.fromtimestamp(
                            item.get("time", 0), tz=timezone.utc
                        ).isoformat(),
                        fetched_at=_now_iso(),
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


# ---------------------------------------------------------------------------
# Hugging Face collector
# ---------------------------------------------------------------------------

async def _fetch_hf_daily_papers(client: httpx.AsyncClient, hf_token: str | None) -> list[RawEvent]:
    events: list[RawEvent] = []
    headers = {}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        resp = await client.get(
            "https://huggingface.co/api/daily_papers",
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        papers = resp.json()
        for p in papers:
            paper = p.get("paper", {})
            title = paper.get("title", "")
            arxiv_id = paper.get("id", "")
            url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "https://huggingface.co/papers"
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            events.append(RawEvent(
                source_name="Hugging Face Daily Papers",
                source_type="huggingface",
                raw_title=title,
                raw_url=url,
                raw_content=paper.get("summary", "")[:2000],
                published_at=p.get("publishedAt", _now_iso()),
                fetched_at=_now_iso(),
                metadata={
                    "arxiv_id": arxiv_id,
                    "authors": authors,
                    "upvotes": p.get("upvotes", p.get("numUpvotes", 0)),
                    "hf_paper_url": f"https://huggingface.co/papers/{arxiv_id}",
                },
            ))
    except Exception as e:
        print(f"  [HF] Daily papers failed: {e}")
    return events


# ---------------------------------------------------------------------------
# arXiv collector
# ---------------------------------------------------------------------------

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom",
             "arxiv": "http://arxiv.org/schemas/atom"}


async def _fetch_arxiv(client: httpx.AsyncClient, categories: list[str],
                       max_per_cat: int, days_back: int) -> list[RawEvent]:
    events: list[RawEvent] = []
    cutoff = _cutoff_dt(days_back * 24)

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
            resp = await client.get(url, timeout=30)
            root = ET.fromstring(resp.text)

            for entry in root.findall("atom:entry", ARXIV_NS):
                title = _text(entry, "atom:title", ARXIV_NS).replace("\n", " ").strip()
                pub = _text(entry, "atom:published", ARXIV_NS)
                summary = _text(entry, "atom:summary", ARXIV_NS).replace("\n", " ").strip()
                arxiv_id_el = entry.find("atom:id", ARXIV_NS)
                arxiv_url = arxiv_id_el.text.strip() if arxiv_id_el is not None else ""
                authors = [
                    _text(a, "atom:name", ARXIV_NS)
                    for a in entry.findall("atom:author", ARXIV_NS)
                ]

                # Skip old papers
                if pub:
                    try:
                        parsed = _parse_date(pub)
                        if parsed and parsed < cutoff:
                            continue
                    except Exception:
                        pass

                events.append(RawEvent(
                    source_name=f"arXiv {cat}",
                    source_type="arxiv",
                    raw_title=title,
                    raw_url=arxiv_url,
                    raw_content=summary[:2000],
                    published_at=pub,
                    fetched_at=_now_iso(),
                    metadata={
                        "category": cat,
                        "authors": authors,
                        "arxiv_url": arxiv_url,
                        # Extract bare ID (e.g. "2501.12345") from the full abs URL
                        "arxiv_id": arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else "",
                    },
                ))
        except Exception as e:
            print(f"  [arXiv] {cat} failed: {e}")

    return events


# ---------------------------------------------------------------------------
# GitHub Trending collector
# ---------------------------------------------------------------------------

GITHUB_TRENDING_SCRAPE = "https://github.com/trending"


async def _fetch_github_trending(client: httpx.AsyncClient, github_token: str | None,
                                  top_n: int) -> list[RawEvent]:
    """Fetch trending repos via GitHub Search API (star-sorted, created recently)."""
    events: list[RawEvent] = []
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    params = {
        "q": f"created:>{since} stars:>50",
        "sort": "stars",
        "order": "desc",
        "per_page": min(top_n, 30),
    }
    try:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            params=params,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        for repo in data.get("items", []):
            events.append(RawEvent(
                source_name="GitHub Trending",
                source_type="github",
                raw_title=repo.get("full_name", ""),
                raw_url=repo.get("html_url", ""),
                raw_content=repo.get("description", "") or "",
                published_at=repo.get("created_at", _now_iso()),
                fetched_at=_now_iso(),
                metadata={
                    "owner": repo.get("owner", {}).get("login", ""),
                    "repo": repo.get("name", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                    "license": (repo.get("license") or {}).get("spdx_id", ""),
                    "pushed_at": repo.get("pushed_at", ""),
                    "open_issues": repo.get("open_issues_count", 0),
                },
            ))
    except Exception as e:
        print(f"  [GitHub] Trending fetch failed: {e}")

    # Also fetch weekly trending (different query)
    try:
        since_week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        params_week = {
            "q": f"pushed:>{since_week} stars:>200",
            "sort": "stars",
            "order": "desc",
            "per_page": 15,
        }
        resp2 = await client.get(
            "https://api.github.com/search/repositories",
            params=params_week,
            headers=headers,
            timeout=30,
        )
        resp2.raise_for_status()
        data2 = resp2.json()
        seen = {e.raw_url for e in events}
        for repo in data2.get("items", []):
            if repo.get("html_url", "") in seen:
                continue
            events.append(RawEvent(
                source_name="GitHub Weekly Trending",
                source_type="github",
                raw_title=repo.get("full_name", ""),
                raw_url=repo.get("html_url", ""),
                raw_content=repo.get("description", "") or "",
                published_at=repo.get("created_at", _now_iso()),
                fetched_at=_now_iso(),
                metadata={
                    "owner": repo.get("owner", {}).get("login", ""),
                    "repo": repo.get("name", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                    "license": (repo.get("license") or {}).get("spdx_id", ""),
                    "pushed_at": repo.get("pushed_at", ""),
                    "open_issues": repo.get("open_issues_count", 0),
                },
            ))
    except Exception as e:
        print(f"  [GitHub] Weekly trending fetch failed: {e}")

    return events


# ---------------------------------------------------------------------------
# Web Search collector (via Anthropic built-in web_search tool)
# ---------------------------------------------------------------------------

_WEB_SEARCH_QUERIES = [
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
]


def _web_search_query_to_events(query: str, date_str: str) -> list[RawEvent]:
    prompt = (
        f"Date: {date_str}\n"
        f"Use web search to find recent news (past 24–48 hours) about: {query}\n\n"
        "Return a JSON array of the most important results found (max 5):\n"
        '[{"title": "...", "url": "...", "source": "...", "summary": "...", '
        '"published_at": "YYYY-MM-DD or ISO string or empty string"}]\n\n'
        "Return only the JSON array. No other text."
    )
    try:
        items = call_claude_web_search(prompt, max_uses=3)
    except Exception as e:
        print(f"  [WebSearch] Query failed ({query[:40]}...): {e}")
        return []

    events = []
    for item in items:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        if not title or not url:
            continue
        events.append(RawEvent(
            source_name=item.get("source", "Web Search"),
            source_type="rss",
            raw_title=title,
            raw_url=url,
            raw_content=item.get("summary", "")[:2000],
            published_at=item.get("published_at", _now_iso()),
            fetched_at=_now_iso(),
            metadata={"priority": 3, "feed_source_type": "media",
                       "via": "web_search", "query": query},
        ))
    return events


def _fetch_web_search_sync(queries: list[str], date_str: str) -> list[RawEvent]:
    """Run all web search queries in parallel (each is an independent Claude API call)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_events: list[RawEvent] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(5, len(queries))) as executor:
        futures = {executor.submit(_web_search_query_to_events, q, date_str): q for q in queries}
        for future in as_completed(futures):
            for event in future.result():
                if event.raw_url not in seen_urls:
                    seen_urls.add(event.raw_url)
                    all_events.append(event)

    print(f"  [WebSearch] Fetched {len(all_events)} events from {len(queries)} queries")
    return all_events


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

async def collect_all(config: dict[str, Any], run_date: str = "") -> list[RawEvent]:
    source_cfg = config.get("sources", {})
    window_hours = config.get("run", {}).get("report_window_hours", 24)
    cutoff = _cutoff_dt(window_hours)
    date_str = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    github_token = os.environ.get("GITHUB_TOKEN")
    hf_token = os.environ.get("HF_TOKEN")

    registry = _load_source_registry()
    all_events: list[RawEvent] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": f"TechDailyAgent/1.0 ({os.environ.get('SEC_USER_EMAIL', '')})"},
        follow_redirects=True,
    ) as client:
        tasks = []

        # RSS feeds
        if source_cfg.get("rss", {}).get("enabled", True):
            for feed in registry.get("rss_feeds", []):
                tasks.append(_fetch_rss(client, feed, cutoff))

        # Hacker News
        if source_cfg.get("hacker_news", {}).get("enabled", True):
            hn_cfg = source_cfg.get("hacker_news", {})
            tasks.append(_fetch_hn(client,
                                    hn_cfg.get("top_stories", 50),
                                    hn_cfg.get("min_score", 100)))

        # Hugging Face
        if source_cfg.get("hugging_face", {}).get("enabled", True):
            hf_cfg = source_cfg.get("hugging_face", {})
            if hf_cfg.get("daily_papers", True):
                tasks.append(_fetch_hf_daily_papers(client, hf_token))

        # arXiv
        if source_cfg.get("arxiv", {}).get("enabled", True):
            arxiv_cfg = source_cfg.get("arxiv", {})
            tasks.append(_fetch_arxiv(
                client,
                arxiv_cfg.get("categories", ["cs.AI", "cs.LG", "cs.RO", "cs.CV", "cs.CL"]),
                arxiv_cfg.get("max_results_per_category", 20),
                arxiv_cfg.get("days_back", 2),
            ))

        # GitHub Trending
        if source_cfg.get("github_trending", {}).get("enabled", True):
            gh_cfg = source_cfg.get("github_trending", {})
            tasks.append(_fetch_github_trending(client, github_token,
                                                  gh_cfg.get("top_n", 25)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_events.extend(r)
            elif isinstance(r, Exception):
                print(f"  [Collector] Task error: {r}")

    # Web search runs after async tasks (synchronous, uses Anthropic API)
    ws_cfg = source_cfg.get("web_search", {})
    if ws_cfg.get("enabled", True):
        n_queries = ws_cfg.get("queries_per_run", 10)
        queries = _WEB_SEARCH_QUERIES[:n_queries]
        web_events = await asyncio.to_thread(
            _fetch_web_search_sync, queries, date_str
        )
        all_events.extend(web_events)

    print(f"  [Collector] Fetched {len(all_events)} raw events total")
    return all_events


def collect_sources(config: dict[str, Any], run_date: str = "") -> list[RawEvent]:
    """Synchronous entry point."""
    return asyncio.run(collect_all(config, run_date))


if __name__ == "__main__":
    cfg = _load_config()
    events = collect_sources(cfg)
    print(json.dumps([
        {"title": e.raw_title, "source": e.source_name, "url": e.raw_url}
        for e in events
    ], indent=2, ensure_ascii=False))
