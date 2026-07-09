"""GitHub Project Analysis Layer — identify top 3 high-signal repos."""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from analyzer_helpers import schema_to_dataclass
from llm_schemas import GitHubProjectAnalysisResponse
from prompt_runner import PromptRunner
from state import NormalizedEvent, ProjectAnalysis

MAX_WORKERS = 5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "github_trending_config.yml")) as f:
        return yaml.safe_load(f)


def _days_ago(dt_str: str) -> int:
    if not dt_str:
        return 9999
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return delta.days
    except (TypeError, ValueError):
        return 9999


async def _fetch_repo_details(
    client: httpx.AsyncClient, owner: str, repo: str, github_token: str | None
) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    try:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  [GitHub] Repo detail fetch failed for {owner}/{repo}: {exc}")
    return {}


def _analyze_one_repo(
    item: dict[str, Any],
    prompt_runner: PromptRunner,
    repo_count: int,
    top_n: int,
) -> tuple[float, str, ProjectAnalysis] | None:
    meta = item["meta"]
    details = item["details"]
    owner = meta.get("owner", "")
    repo_name = meta.get("repo", meta.get("name", ""))
    full_name = f"{owner}/{repo_name}" if owner else repo_name

    stars = details.get("stargazers_count") or meta.get("stars", 0)
    forks = details.get("forks_count") or meta.get("forks", 0)
    language = details.get("language") or meta.get("language", "")
    pushed_at = details.get("pushed_at") or meta.get("pushed_at", "")
    created_at = details.get("created_at") or meta.get("created_at", "")
    open_issues = details.get("open_issues_count") or meta.get("open_issues", 0)
    license_info = (details.get("license") or {}).get("spdx_id") or meta.get("license", "")
    description = details.get("description") or item.get("description", "")
    topics = details.get("topics") or meta.get("topics", [])
    stars_today = meta.get("stars_today", meta.get("stars_daily", 0)) or 0
    stars_weekly = meta.get("stars_weekly", 0) or 0
    contributors_count = details.get("contributors_count") or meta.get("contributors_count", 0) or 0

    payload = {
        "repo": {
            "full_name": full_name,
            "name": repo_name,
            "owner": owner,
            "description": description,
            "stars": stars,
            "forks": forks,
            "language": language,
            "created_at": created_at,
            "pushed_at": pushed_at,
            "open_issues": open_issues,
            "license": license_info,
            "topics": topics,
        },
        "star_history": {
            "stars_today": stars_today,
            "stars_weekly": stars_weekly,
            "stars_total": stars,
        },
        "readme_excerpt": description[:500],
        "topics": topics,
        "contributors_count": contributors_count,
        "open_issues": open_issues,
        "license": license_info,
        # subscribers_count = people watching for notifications (genuine engagement).
        # watchers_count is a legacy alias for stargazers_count — do not use.
        # True contributor count requires a separate /contributors API call; skipped here.
        "watchers_count": details.get("subscribers_count", 0),
        "context": f"Analyzing {repo_count} repos, selecting top {top_n}",
    }

    result = prompt_runner.run_json(
        prompt_path="github_project_analysis.md",
        payload=json.dumps(payload, ensure_ascii=False),
        schema=GitHubProjectAnalysisResponse,
        max_tokens=4096,
    )

    if not result.report_worthy:
        print(f"  [GitHub] Filtered: {full_name} — {result.filter_out_reason or ''}")
        return None

    analysis = schema_to_dataclass(result, ProjectAnalysis)
    total_score = result.scores.get("total", 0)
    print(f"  [GitHub] {full_name}: score={total_score} verdict={analysis.verdict}")
    return (total_score, full_name, analysis)


def analyze_github_projects(
    events: list[NormalizedEvent],
    prompt_runner: PromptRunner | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict[str, ProjectAnalysis]:
    cfg = _load_config()
    runner = prompt_runner or PromptRunner()
    github_token = os.environ.get("GITHUB_TOKEN")
    top_n = cfg.get("fetch", {}).get("top_n_in_report", 3)

    github_events = [e for e in events if e.source_type == "github" or e.event_type == "github_trending"]

    if not github_events:
        return {}

    # Sort by importance score
    github_events = sorted(github_events, key=lambda e: e.importance_score, reverse=True)

    # Fetch additional details for top candidates
    async def enrich_repos(evts: list[NormalizedEvent]) -> list[dict[str, Any]]:
        enriched = []
        async with httpx.AsyncClient() as client:
            for e in evts[:30]:
                meta = e.metadata if hasattr(e, "metadata") else {}
                owner = meta.get("owner", "")
                repo_name = meta.get("repo", "")
                details = {}
                if owner and repo_name:
                    details = await _fetch_repo_details(client, owner, repo_name, github_token)
                enriched.append(
                    {
                        "event_id": e.event_id,
                        "url": e.primary_source_url,
                        "description": e.summary,
                        "meta": meta,
                        "details": details,
                    }
                )
        return enriched

    enriched_data = asyncio.run(enrich_repos(github_events))

    analyses: dict[str, ProjectAnalysis] = {}
    scored_repos: list[tuple[float, str, ProjectAnalysis]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_one_repo, item, runner, len(enriched_data), top_n): item for item in enriched_data
        }
        for future in as_completed(futures):
            item = futures[future]
            meta = item["meta"]
            owner = meta.get("owner", "")
            repo_name = meta.get("repo", meta.get("name", ""))
            full_name = f"{owner}/{repo_name}" if owner else repo_name
            try:
                result = future.result()
                if result is not None:
                    scored_repos.append(result)
            except Exception as e:
                print(f"  [GitHub] Analysis failed for {full_name}: {e}")

    # Sort by score and take top N
    scored_repos.sort(key=lambda x: x[0], reverse=True)
    for _, name, analysis in scored_repos[:top_n]:
        analyses[name] = analysis

    return analyses
