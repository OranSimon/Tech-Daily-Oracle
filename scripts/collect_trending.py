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
    items: list[TrendingItem] = []
    params: dict = {
        "period": _OSS_PERIOD.get(period, "past_24_hours"),
        "page": 1,
        "pageSize": top_n,
    }
    if language:
        params["language"] = language
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
    except Exception as e:
        print(f"  [Trending] OSSInsight {period} failed: {e}")
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
