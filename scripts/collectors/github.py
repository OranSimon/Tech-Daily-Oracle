"""GitHub Trending source collector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from state import RawEvent

from collectors.base import now_iso
from collectors.retry import NETWORK_RETRY_CONFIG, retry_async
from collectors.telemetry import CollectorWarning

GITHUB_TRENDING_SCRAPE = "https://github.com/trending"


async def fetch_github_trending(
    client: Any,
    github_token: str | None,
    top_n: int,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    """Fetch trending repos via GitHub Search API (star-sorted, created recently)."""
    events: list[RawEvent] = []
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    since = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    params = {
        "q": f"created:>{since} stars:>50",
        "sort": "stars",
        "order": "desc",
        "per_page": min(top_n, 30),
    }
    try:

        async def fetch_daily_trending() -> Any:
            response = await client.get(
                "https://api.github.com/search/repositories",
                params=params,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response

        resp = await retry_async(
            fetch_daily_trending,
            operation_name="GitHub daily trending",
            warnings=warnings,
            config=NETWORK_RETRY_CONFIG,
        )
        data = resp.json()
        for repo in data.get("items", []):
            events.append(
                RawEvent(
                    source_name="GitHub Trending",
                    source_type="github",
                    raw_title=repo.get("full_name", ""),
                    raw_url=repo.get("html_url", ""),
                    raw_content=repo.get("description", "") or "",
                    published_at=repo.get("created_at", now_iso()),
                    fetched_at=now_iso(),
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
                )
            )
    except Exception as e:
        print(f"  [GitHub] Trending fetch failed: {e}")

    # Also fetch weekly trending (different query)
    try:
        since_week = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
        params_week = {
            "q": f"pushed:>{since_week} stars:>200",
            "sort": "stars",
            "order": "desc",
            "per_page": 15,
        }

        async def fetch_weekly_trending() -> Any:
            response = await client.get(
                "https://api.github.com/search/repositories",
                params=params_week,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response

        resp2 = await retry_async(
            fetch_weekly_trending,
            operation_name="GitHub weekly trending",
            warnings=warnings,
            config=NETWORK_RETRY_CONFIG,
        )
        data2 = resp2.json()
        seen = {e.raw_url for e in events}
        for repo in data2.get("items", []):
            if repo.get("html_url", "") in seen:
                continue
            events.append(
                RawEvent(
                    source_name="GitHub Weekly Trending",
                    source_type="github",
                    raw_title=repo.get("full_name", ""),
                    raw_url=repo.get("html_url", ""),
                    raw_content=repo.get("description", "") or "",
                    published_at=repo.get("created_at", now_iso()),
                    fetched_at=now_iso(),
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
                )
            )
    except Exception as e:
        print(f"  [GitHub] Weekly trending fetch failed: {e}")

    return events
