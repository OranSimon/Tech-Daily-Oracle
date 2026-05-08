"""GitHub Project Analysis Layer — identify top 3 high-signal repos."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml

from claude_client import call_claude_json
from state import NormalizedEvent, ProjectAnalysis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "github_trending_config.yml")) as f:
        return yaml.safe_load(f)


def _load_prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "github_project_analysis.md")) as f:
        return f.read()


def _days_ago(dt_str: str) -> int:
    if not dt_str:
        return 9999
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.days
    except Exception:
        return 9999


async def _fetch_repo_details(client: httpx.AsyncClient, owner: str, repo: str,
                               github_token: str | None) -> dict[str, Any]:
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
    except Exception:
        pass
    return {}


def analyze_github_projects(
    events: list[NormalizedEvent],
) -> dict[str, ProjectAnalysis]:
    cfg = _load_config()
    prompt_system = _load_prompt()
    github_token = os.environ.get("GITHUB_TOKEN")
    top_n = cfg.get("fetch", {}).get("top_n_in_report", 3)

    github_events = [
        e for e in events
        if e.source_type == "github" or e.event_type == "github_trending"
    ]

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
                enriched.append({
                    "event_id": e.event_id,
                    "url": e.primary_source_url,
                    "description": e.summary,
                    "meta": meta,
                    "details": details,
                })
        return enriched

    enriched_data = asyncio.run(enrich_repos(github_events))

    analyses: dict[str, ProjectAnalysis] = {}
    scored_repos: list[tuple[float, str, ProjectAnalysis]] = []

    for item in enriched_data:
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

        try:
            user_msg = json.dumps({
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
                "readme_excerpt": description[:500],
                "contributors_count": details.get("watchers_count", 0),
                "context": f"Analyzing {len(enriched_data)} repos, selecting top {top_n}",
            }, ensure_ascii=False)

            result = call_claude_json(
                system=prompt_system,
                user=user_msg,
                max_tokens=1024,
            )

            if not result.get("report_worthy", True):
                print(f"  [GitHub] Filtered: {full_name} — {result.get('filter_out_reason', '')}")
                continue

            analysis = ProjectAnalysis(
                repo=result.get("repo", full_name),
                url=result.get("url", item["url"]),
                tagline=result.get("tagline", description[:100]),
                stars_total=result.get("stars_total", stars),
                stars_today=result.get("stars_today", 0),
                stars_weekly=result.get("stars_weekly", 0),
                language=result.get("language", language),
                created_days_ago=result.get("created_days_ago", _days_ago(created_at)),
                last_commit_days_ago=result.get("last_commit_days_ago", _days_ago(pushed_at)),
                contributors=result.get("contributors", 0),
                license=result.get("license", license_info),
                report_worthy=result.get("report_worthy", True),
                filter_out_reason=result.get("filter_out_reason"),
                scores=result.get("scores", {}),
                what_it_does=result.get("what_it_does", ""),
                why_it_matters=result.get("why_it_matters", ""),
                risk_label=result.get("risk_label", "promising"),
                verdict=result.get("verdict", "Track"),
                topic_tags=result.get("topic_tags", []),
                hype_risk=result.get("hype_risk", "medium"),
                signals_to_monitor=result.get("signals_to_monitor", []),
            )

            total_score = result.get("scores", {}).get("total", 0)
            scored_repos.append((total_score, full_name, analysis))
            print(f"  [GitHub] {full_name}: score={total_score} verdict={analysis.verdict}")

        except Exception as e:
            print(f"  [GitHub] Analysis failed for {full_name}: {e}")

    # Sort by score and take top N
    scored_repos.sort(key=lambda x: x[0], reverse=True)
    for _, name, analysis in scored_repos[:top_n]:
        analyses[name] = analysis

    return analyses
