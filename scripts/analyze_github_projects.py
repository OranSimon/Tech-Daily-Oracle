"""GitHub Project Analysis Layer — identify top 3 high-signal repos."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from analyzer_helpers import schema_to_dataclass
from llm_schemas import GitHubProjectAnalysisResponse
from prompt_runner import PromptRunner
from state import NormalizedEvent, ProjectAnalysis, TrendingSnapshot

MAX_WORKERS = 5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class GitHubRepoCandidate:
    full_name: str
    url: str
    description: str
    language: str
    stars_today: int
    stars_weekly: int
    metadata: dict[str, Any]
    event_id: str = ""


@dataclass
class GitHubProjectAnalysisOutcome(Mapping[str, ProjectAnalysis]):
    analyses: dict[str, ProjectAnalysis] = field(default_factory=dict)
    source: str = "none"
    candidate_count: int = 0
    analyzed_count: int = 0
    filtered_count: int = 0
    failed_count: int = 0
    failures: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> ProjectAnalysis:
        return self.analyses[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.analyses)

    def __len__(self) -> int:
        return len(self.analyses)

    @property
    def reason(self) -> str:
        if self.analyses:
            return "accepted_projects_available"
        if self.candidate_count == 0:
            return "source_empty"
        if self.analyzed_count == 0 and self.failed_count == self.candidate_count:
            return "analysis_failed"
        return "all_candidates_filtered"

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "source": self.source,
            "candidate_count": self.candidate_count,
            "analyzed_count": self.analyzed_count,
            "filtered_count": self.filtered_count,
            "failed_count": self.failed_count,
            "failures": list(self.failures),
        }


def _split_full_name(full_name: str) -> tuple[str, str]:
    if "/" not in full_name:
        return "", full_name
    owner, repo = full_name.split("/", 1)
    return owner, repo


def _candidates_from_snapshot(snapshot: TrendingSnapshot | None) -> list[GitHubRepoCandidate]:
    if snapshot is None:
        return []

    candidates: list[GitHubRepoCandidate] = []
    for item in snapshot.github_items:
        owner, repo = _split_full_name(item.item_id)
        extra = item.extra or {}
        stars_today = int(item.velocity_score) if item.period == "daily" else 0
        stars_weekly = int(item.velocity_score) if item.period == "weekly" else 0
        metadata = {
            "owner": owner,
            "repo": repo,
            "language": item.language,
            "topics": list(item.topics),
            "stars_today": stars_today,
            "stars_weekly": stars_weekly,
            "forks": extra.get("forks", 0),
            "source_name": item.source,
            **extra,
        }
        candidates.append(
            GitHubRepoCandidate(
                full_name=item.item_id,
                url=item.url,
                description=item.description,
                language=item.language,
                stars_today=stars_today,
                stars_weekly=stars_weekly,
                metadata=metadata,
                event_id=f"trending:{snapshot.snapshot_date}:{item.item_id}",
            )
        )
    return candidates


def _candidates_from_events(events: list[NormalizedEvent]) -> list[GitHubRepoCandidate]:
    github_events = [event for event in events if event.source_type == "github" or event.event_type == "github_trending"]
    github_events.sort(key=lambda event: event.importance_score, reverse=True)

    candidates: list[GitHubRepoCandidate] = []
    for event in github_events:
        metadata = dict(event.metadata) if hasattr(event, "metadata") else {}
        owner = str(metadata.get("owner", ""))
        repo = str(metadata.get("repo", ""))
        full_name = f"{owner}/{repo}" if owner else repo or event.canonical_title
        candidates.append(
            GitHubRepoCandidate(
                full_name=full_name,
                url=event.primary_source_url,
                description=event.summary,
                language=str(metadata.get("language", "")),
                stars_today=int(metadata.get("stars_today", metadata.get("stars_daily", 0)) or 0),
                stars_weekly=int(metadata.get("stars_weekly", 0) or 0),
                metadata=metadata,
                event_id=event.event_id,
            )
        )
    return candidates


def _deduplicate_candidates(candidates: list[GitHubRepoCandidate]) -> list[GitHubRepoCandidate]:
    seen: set[str] = set()
    unique: list[GitHubRepoCandidate] = []
    for candidate in candidates:
        key = candidate.full_name.casefold()
        if not candidate.full_name or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _select_candidates(
    events: list[NormalizedEvent],
    trending_snapshot: TrendingSnapshot | None,
) -> tuple[list[GitHubRepoCandidate], str]:
    snapshot_candidates = _deduplicate_candidates(_candidates_from_snapshot(trending_snapshot))
    if snapshot_candidates:
        source = trending_snapshot.github_items[0].source if trending_snapshot is not None else "trending_snapshot"
        return snapshot_candidates, source

    event_candidates = _deduplicate_candidates(_candidates_from_events(events))
    return event_candidates, "normalized_events" if event_candidates else "none"


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
    *,
    trending_snapshot: TrendingSnapshot | None = None,
) -> GitHubProjectAnalysisOutcome:
    cfg = _load_config()
    runner = prompt_runner or PromptRunner()
    github_token = os.environ.get("GITHUB_TOKEN")
    top_n = cfg.get("fetch", {}).get("top_n_in_report", 3)
    max_candidates = cfg.get("fetch", {}).get("max_repos_to_analyze", 25)

    candidates, source = _select_candidates(events, trending_snapshot)
    candidates = candidates[:max_candidates]
    if not candidates:
        return GitHubProjectAnalysisOutcome(source=source)

    # Fetch additional details for top candidates
    async def enrich_repos(repo_candidates: list[GitHubRepoCandidate]) -> list[dict[str, Any]]:
        enriched = []
        async with httpx.AsyncClient() as client:
            for candidate in repo_candidates:
                meta = dict(candidate.metadata)
                owner = meta.get("owner", "")
                repo_name = meta.get("repo", "")
                details = {}
                if owner and repo_name:
                    details = await _fetch_repo_details(client, owner, repo_name, github_token)
                enriched.append(
                    {
                        "event_id": candidate.event_id,
                        "url": candidate.url,
                        "description": candidate.description,
                        "meta": meta,
                        "details": details,
                    }
                )
        return enriched

    enriched_data = asyncio.run(enrich_repos(candidates))

    analyses: dict[str, ProjectAnalysis] = {}
    scored_repos: list[tuple[float, str, ProjectAnalysis]] = []
    analyzed_count = 0
    filtered_count = 0
    failures: list[str] = []

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
                analyzed_count += 1
                if result is None:
                    filtered_count += 1
                else:
                    scored_repos.append(result)
            except Exception as e:
                print(f"  [GitHub] Analysis failed for {full_name}: {e}")
                failures.append(f"{full_name}: {e}")

    # Sort by score and take top N
    scored_repos.sort(key=lambda x: x[0], reverse=True)
    for _, name, analysis in scored_repos[:top_n]:
        analyses[name] = analysis

    return GitHubProjectAnalysisOutcome(
        analyses=analyses,
        source=source,
        candidate_count=len(enriched_data),
        analyzed_count=analyzed_count,
        filtered_count=filtered_count,
        failed_count=len(failures),
        failures=failures,
    )
