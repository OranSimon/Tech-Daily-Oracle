"""Trending data collector.

Sources:
  - OSSInsight  → GitHub velocity-based trending (sliding window: 24h / 7d / 30d)
  - HuggingFace → daily papers (editorial, with ?date= for history)
                → model trending (HF's internal ~7-day sliding window)

OSSInsight API endpoint:
  GET https://api.ossinsight.io/v1/repos/trending
  params: period=past_24_hours|past_week|past_month  language=  page=1  pageSize=N
  No auth required for public trending; responses include stars_increment (velocity).

HuggingFace paper rolling windows are built by aggregating multiple daily calls.
A paper appearing across more days → stronger rolling signal.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date, timedelta

import httpx

from state import TrendingItem, TrendingSnapshot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OSSINSIGHT_BASE = "https://api.ossinsight.io"
HF_API_BASE = "https://huggingface.co/api"

_OSS_PERIOD = {
    "daily": "past_24_hours",
    "weekly": "past_week",
    "monthly": "past_month",
}


# ---------------------------------------------------------------------------
# OSSInsight — GitHub velocity trending
# ---------------------------------------------------------------------------

async def _fetch_ossinsight(
    client: httpx.AsyncClient,
    period: str,
    language: str = "",
    top_n: int = 20,
) -> list[TrendingItem]:
    """OSSInsight with retry. Falls back to github.com/trending HTML if 'daily' period fails."""
    items: list[TrendingItem] = []
    params: dict = {
        "period": _OSS_PERIOD.get(period, "past_24_hours"),
        "page": 1,
        "pageSize": top_n,
    }
    if language:
        params["language"] = language

    # Retry OSSInsight up to 3 times with exponential backoff for transient 5xx errors
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(
                f"{OSSINSIGHT_BASE}/v1/repos/trending",
                params=params,
                timeout=25,
            )
            resp.raise_for_status()
            rows = resp.json().get("data", {}).get("rows", [])
            for i, row in enumerate(rows[:top_n], start=1):
                repo_name = row.get("repo_name", "")
                items.append(TrendingItem(
                    item_id=repo_name,
                    item_type="github_repo",
                    source="ossinsight",
                    title=repo_name,
                    url=f"https://github.com/{repo_name}",
                    description=(row.get("description") or "")[:400],
                    period=period,
                    rank=i,
                    velocity_score=float(row.get("stars_increment", 0)),
                    language=row.get("primary_language") or "",
                    topics=[],
                    snapshot_date="",  # stamped by caller
                    extra={
                        "forks_increment": row.get("forks_increment", 0),
                        "prs_increment": row.get("prs_increment", 0),
                        "issues_increment": row.get("issues_increment", 0),
                        "total_score": row.get("total_score", 0),
                        "collection_names": row.get("collection_names", []),
                    },
                ))
            if items:
                return items
            break  # 200 OK with empty rows — don't retry, just fall through to fallback
        except Exception as e:
            last_err = e
            if attempt < 2:
                wait_s = 2 ** attempt   # 1s, then 2s
                print(f"  [Trending] OSSInsight {period} attempt {attempt + 1}/3 failed ({e}); retrying in {wait_s}s")
                await asyncio.sleep(wait_s)
            else:
                print(f"  [Trending] OSSInsight {period} exhausted retries: {e}")

    # Fallback: scrape github.com/trending HTML — public page, no auth, real velocity data.
    # Only meaningful for 'daily' period; the trending page mirrors past-24h activity.
    if period == "daily":
        print(f"  [Trending] Falling back to github.com/trending HTML scrape")
        fallback_items = await _fetch_github_trending_html(client, language, top_n)
        if fallback_items:
            return fallback_items

    return items


# ---------------------------------------------------------------------------
# Fallback: github.com/trending HTML scraping
# ---------------------------------------------------------------------------

_GH_TRENDING_ARTICLE_RE = re.compile(r'<article class="Box-row">(.*?)</article>', re.DOTALL)
_GH_TRENDING_REPO_RE = re.compile(r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+?)"', re.DOTALL)
_GH_TRENDING_DESC_RE = re.compile(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', re.DOTALL)
_GH_TRENDING_STARS_TODAY_RE = re.compile(r'([\d,]+)\s+stars?\s+today')
_GH_TRENDING_LANG_RE = re.compile(r'itemprop="programmingLanguage">\s*(.+?)\s*</span>')
_GH_TRENDING_TOTAL_STARS_RE = re.compile(r'aria-label="star"></svg>\s*([\d,]+)', re.DOTALL)
_GH_TRENDING_FORKS_RE = re.compile(r'/forks">\s*([\d,]+)', re.DOTALL)


def _to_int(s: str) -> int:
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


async def _fetch_github_trending_html(
    client: httpx.AsyncClient, language: str = "", top_n: int = 20
) -> list[TrendingItem]:
    """Scrape github.com/trending — public HTML page, no auth, real stars-today velocity.

    Why this exists: OSSInsight API has occasional 500 outages. The GitHub trending
    page itself is the original source of "trending" semantics with genuine velocity
    metrics (stars-today), so it's the most reliable fallback when OSSInsight is down.
    """
    items: list[TrendingItem] = []
    url = f"https://github.com/trending/{language}" if language else "https://github.com/trending"
    try:
        resp = await client.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (TechDailyOracle trending fallback)",
                "Accept": "text/html",
            },
        )
        resp.raise_for_status()
        html = resp.text
        articles = _GH_TRENDING_ARTICLE_RE.findall(html)
        for i, article in enumerate(articles[:top_n], start=1):
            repo_match = _GH_TRENDING_REPO_RE.search(article)
            if not repo_match:
                continue
            # The href captures "owner/\n        repo" — strip whitespace inside
            owner_repo = re.sub(r"\s+", "", repo_match.group(1).strip())
            if "/" not in owner_repo:
                continue

            desc_match = _GH_TRENDING_DESC_RE.search(article)
            description = re.sub(r"\s+", " ", desc_match.group(1).strip()) if desc_match else ""

            stars_today_match = _GH_TRENDING_STARS_TODAY_RE.search(article)
            stars_today = _to_int(stars_today_match.group(1)) if stars_today_match else 0

            total_stars_match = _GH_TRENDING_TOTAL_STARS_RE.search(article)
            total_stars = _to_int(total_stars_match.group(1)) if total_stars_match else 0

            forks_match = _GH_TRENDING_FORKS_RE.search(article)
            forks = _to_int(forks_match.group(1)) if forks_match else 0

            lang_match = _GH_TRENDING_LANG_RE.search(article)
            lang = lang_match.group(1).strip() if lang_match else ""

            items.append(TrendingItem(
                item_id=owner_repo,
                item_type="github_repo",
                source="github_trending_html",
                title=owner_repo,
                url=f"https://github.com/{owner_repo}",
                description=description[:400],
                period="daily",
                rank=i,
                velocity_score=float(stars_today),  # real stars-today velocity
                language=lang,
                topics=[],
                snapshot_date="",  # stamped by caller
                extra={
                    "total_stars": total_stars,
                    "forks": forks,
                    "fallback_source": "github.com/trending",
                },
            ))
        print(f"  [Trending] github.com/trending HTML fallback: {len(items)} repos")
    except Exception as e:
        print(f"  [Trending] github.com/trending HTML fallback failed: {e}")
    return items


# ---------------------------------------------------------------------------
# HuggingFace papers — rolling window via date aggregation
# ---------------------------------------------------------------------------

async def _fetch_hf_papers_one_day(
    client: httpx.AsyncClient,
    date_str: str,
    hf_token: str | None,
    sem: asyncio.Semaphore,
) -> list[tuple[dict, str]]:
    """Fetch HF daily papers for one date. Returns list of (raw_paper, date_str)."""
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    async with sem:
        try:
            params = {} if date_str == date.today().isoformat() else {"date": date_str}
            resp = await client.get(
                f"{HF_API_BASE}/daily_papers",
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            return [(p, date_str) for p in resp.json()]
        except Exception as e:
            print(f"  [Trending] HF papers {date_str} failed: {e}")
            return []


async def _fetch_hf_papers_rolling(
    client: httpx.AsyncClient,
    dates: list[str],
    hf_token: str | None,
    top_n: int = 20,
    period: str = "daily",
) -> list[TrendingItem]:
    """
    Aggregate HF daily papers across `dates` to form a synthetic rolling window.

    Ranking formula: days_appeared (primary) × upvotes_sum (secondary).
    A paper showing up multiple days has higher editorial signal; upvotes break ties.
    """
    sem = asyncio.Semaphore(5)
    tasks = [_fetch_hf_papers_one_day(client, d, hf_token, sem) for d in dates]
    day_results: list[list[tuple[dict, str]]] = await asyncio.gather(*tasks)

    # Aggregate per arxiv_id
    agg: dict[str, dict] = {}
    for day_list in day_results:
        for raw_p, day in day_list:
            paper = raw_p.get("paper", {})
            arxiv_id = paper.get("id", "")
            if not arxiv_id:
                continue
            if arxiv_id not in agg:
                agg[arxiv_id] = {
                    "paper": paper,
                    "dates": [],
                    "upvotes_sum": 0,
                }
            agg[arxiv_id]["dates"].append(day)
            agg[arxiv_id]["upvotes_sum"] += raw_p.get("upvotes", raw_p.get("numUpvotes", 0))

    # Rank: most days appeared first, then total upvotes
    ranked = sorted(
        agg.items(),
        key=lambda kv: (len(kv[1]["dates"]), kv[1]["upvotes_sum"]),
        reverse=True,
    )

    items: list[TrendingItem] = []
    for i, (arxiv_id, info) in enumerate(ranked[:top_n], start=1):
        p = info["paper"]
        authors = [a.get("name", "") for a in p.get("authors", [])]
        days_cnt = len(info["dates"])
        items.append(TrendingItem(
            item_id=arxiv_id,
            item_type="hf_paper",
            source="huggingface_papers",
            title=p.get("title", ""),
            url=f"https://arxiv.org/abs/{arxiv_id}",
            description=(p.get("summary") or "")[:500],
            period=period,
            rank=i,
            velocity_score=float(info["upvotes_sum"]),
            language="",
            topics=[],
            snapshot_date="",
            extra={
                "authors": authors[:5],
                "days_appeared": days_cnt,
                "avg_upvotes": round(info["upvotes_sum"] / max(days_cnt, 1), 1),
                "hf_url": f"https://huggingface.co/papers/{arxiv_id}",
            },
        ))
    return items


# ---------------------------------------------------------------------------
# HuggingFace models — HF's internal ~7-day sliding trending score
# ---------------------------------------------------------------------------

async def _fetch_hf_models(
    client: httpx.AsyncClient,
    hf_token: str | None,
    top_n: int = 20,
    period: str = "daily",
) -> list[TrendingItem]:
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    items: list[TrendingItem] = []
    try:
        resp = await client.get(
            f"{HF_API_BASE}/models",
            params={"sort": "trending", "limit": top_n, "direction": -1},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        for i, m in enumerate(resp.json()[:top_n], start=1):
            model_id = m.get("id", "")
            items.append(TrendingItem(
                item_id=model_id,
                item_type="hf_model",
                source="huggingface_models",
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                description="",
                period=period,
                rank=i,
                velocity_score=float(m.get("trendingScore", 0)),
                language=m.get("library_name") or "",
                topics=(m.get("tags") or [])[:5],
                snapshot_date="",
                extra={
                    "pipeline_tag": m.get("pipeline_tag", ""),
                    "downloads": m.get("downloads", 0),
                    "likes": m.get("likes", 0),
                },
            ))
    except Exception as e:
        print(f"  [Trending] HF models trending failed: {e}")
    return items


# ---------------------------------------------------------------------------
# Main async orchestrator
# ---------------------------------------------------------------------------

async def _collect_async(period: str, run_date: str, config: dict) -> TrendingSnapshot:
    tcfg = config.get("trending", {})
    top_n: int = tcfg.get("top_n", 5)
    hf_token: str | None = os.environ.get("HF_TOKEN")
    languages: list[str] = (tcfg.get("ossinsight", {}) or {}).get("languages", []) or []
    lang = languages[0] if languages else ""

    today = date.fromisoformat(run_date)
    if period == "daily":
        dates = [run_date]
    elif period == "weekly":
        dates = [(today - timedelta(days=i)).isoformat() for i in range(7)]
    else:  # monthly
        dates = [(today - timedelta(days=i)).isoformat() for i in range(30)]

    async with httpx.AsyncClient(
        headers={"User-Agent": "TechDailyOracle/1.0"},
        follow_redirects=True,
    ) as client:
        gh_task = _fetch_ossinsight(client, period, lang, top_n * 2)
        papers_task = _fetch_hf_papers_rolling(client, dates, hf_token, top_n * 2, period)
        models_task = _fetch_hf_models(client, hf_token, top_n * 2, period)

        github_items, hf_paper_items, hf_model_items = await asyncio.gather(
            gh_task, papers_task, models_task
        )

    # Stamp snapshot date on all items
    for item in github_items + hf_paper_items + hf_model_items:
        item.snapshot_date = run_date

    print(
        f"  [Trending] {period}: {len(github_items)} GitHub repos, "
        f"{len(hf_paper_items)} HF papers, {len(hf_model_items)} HF models"
    )
    return TrendingSnapshot(
        snapshot_date=run_date,
        period=period,
        github_items=github_items[:top_n],
        hf_paper_items=hf_paper_items[:top_n],
        hf_model_items=hf_model_items[:top_n],
    )


def collect_trending_snapshot(period: str, run_date: str, config: dict) -> TrendingSnapshot:
    """Collect a trending snapshot. Synchronous wrapper around the async pipeline."""
    _empty = TrendingSnapshot(
        snapshot_date=run_date, period=period,
        github_items=[], hf_paper_items=[], hf_model_items=[],
    )
    if not config.get("trending", {}).get("enabled", True):
        return _empty
    try:
        return asyncio.run(_collect_async(period, run_date, config))
    except RuntimeError:
        # Already inside an event loop (shouldn't happen in our sync runners)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(asyncio.run, _collect_async(period, run_date, config))
            return fut.result(timeout=120)
    except Exception as e:
        print(f"  [Trending] Collection failed: {e}")
        return _empty
