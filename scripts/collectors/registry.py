"""Explicit registry and config mapping for source collectors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from state import RawEvent
from web_search_client import WebSearchClient

from collectors.arxiv import fetch_arxiv
from collectors.github import fetch_github_trending
from collectors.hackernews import fetch_hn
from collectors.huggingface import fetch_hf_daily_papers
from collectors.rss import fetch_rss
from collectors.telemetry import CollectorWarning
from collectors.web_search import WEB_SEARCH_QUERIES, fetch_web_search_sync

AsyncTaskBuilder = Callable[..., list[Awaitable[list[RawEvent]]]]
WebSearchRunner = Callable[..., list[RawEvent]]
EnabledResolver = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class AsyncCollectorRegistration:
    name: str
    config_key: str
    build_tasks: AsyncTaskBuilder
    enabled: EnabledResolver


@dataclass(frozen=True)
class WebSearchCollectorRegistration:
    name: str
    config_key: str
    run: WebSearchRunner


@dataclass(frozen=True)
class CollectorTaskGroup:
    name: str
    tasks: list[Awaitable[list[RawEvent]]]
    skipped_reason: str | None = None
    warnings: list[CollectorWarning] | None = None


def _enabled(source_cfg: dict[str, Any], config_key: str) -> bool:
    return source_cfg.get(config_key, {}).get("enabled", True)


def _source_enabled(config_key: str) -> EnabledResolver:
    return lambda source_cfg: _enabled(source_cfg, config_key)


def _hugging_face_enabled(source_cfg: dict[str, Any]) -> bool:
    return _enabled(source_cfg, "hugging_face") and source_cfg.get("hugging_face", {}).get("daily_papers", True)


def _build_rss_tasks(
    *,
    source_cfg: dict[str, Any],
    source_registry: dict[str, Any],
    client: Any,
    cutoff: datetime,
    warnings: list[CollectorWarning],
    **_: Any,
) -> list[Awaitable[list[RawEvent]]]:
    return [fetch_rss(client, feed, cutoff, warnings) for feed in source_registry.get("rss_feeds", [])]


def _build_hacker_news_tasks(
    *,
    source_cfg: dict[str, Any],
    client: Any,
    warnings: list[CollectorWarning],
    **_: Any,
) -> list[Awaitable[list[RawEvent]]]:
    hn_cfg = source_cfg.get("hacker_news", {})
    return [fetch_hn(client, hn_cfg.get("top_stories", 50), hn_cfg.get("min_score", 100), warnings)]


def _build_hugging_face_tasks(
    *,
    source_cfg: dict[str, Any],
    client: Any,
    hf_token: str | None,
    warnings: list[CollectorWarning],
    **_: Any,
) -> list[Awaitable[list[RawEvent]]]:
    return [fetch_hf_daily_papers(client, hf_token, warnings)]


def _build_arxiv_tasks(
    *,
    source_cfg: dict[str, Any],
    client: Any,
    warnings: list[CollectorWarning],
    **_: Any,
) -> list[Awaitable[list[RawEvent]]]:
    arxiv_cfg = source_cfg.get("arxiv", {})
    return [
        fetch_arxiv(
            client,
            arxiv_cfg.get("categories", ["cs.AI", "cs.LG", "cs.RO", "cs.CV", "cs.CL"]),
            arxiv_cfg.get("max_results_per_category", 20),
            arxiv_cfg.get("days_back", 2),
            warnings,
        )
    ]


def _build_github_tasks(
    *,
    source_cfg: dict[str, Any],
    client: Any,
    github_token: str | None,
    warnings: list[CollectorWarning],
    **_: Any,
) -> list[Awaitable[list[RawEvent]]]:
    gh_cfg = source_cfg.get("github_trending", {})
    return [fetch_github_trending(client, github_token, gh_cfg.get("top_n", 25), warnings)]


def _run_web_search(
    *,
    source_cfg: dict[str, Any],
    date_str: str,
    web_search_client: WebSearchClient | None,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    ws_cfg = source_cfg.get("web_search", {})
    n_queries = ws_cfg.get("queries_per_run", 10)
    queries = WEB_SEARCH_QUERIES[:n_queries]
    if warnings is None:
        return fetch_web_search_sync(queries, date_str, web_search_client)
    return fetch_web_search_sync(queries, date_str, web_search_client, warnings=warnings)


ASYNC_COLLECTORS = [
    AsyncCollectorRegistration("rss", "rss", _build_rss_tasks, _source_enabled("rss")),
    AsyncCollectorRegistration("hacker_news", "hacker_news", _build_hacker_news_tasks, _source_enabled("hacker_news")),
    AsyncCollectorRegistration("hugging_face", "hugging_face", _build_hugging_face_tasks, _hugging_face_enabled),
    AsyncCollectorRegistration("arxiv", "arxiv", _build_arxiv_tasks, _source_enabled("arxiv")),
    AsyncCollectorRegistration(
        "github_trending",
        "github_trending",
        _build_github_tasks,
        _source_enabled("github_trending"),
    ),
]

WEB_SEARCH_COLLECTOR = WebSearchCollectorRegistration("web_search", "web_search", _run_web_search)


def build_async_collector_task_groups(
    *,
    source_cfg: dict[str, Any],
    source_registry: dict[str, Any],
    client: Any,
    cutoff: datetime,
    github_token: str | None,
    hf_token: str | None,
) -> list[CollectorTaskGroup]:
    context = {
        "source_cfg": source_cfg,
        "source_registry": source_registry,
        "client": client,
        "cutoff": cutoff,
        "github_token": github_token,
        "hf_token": hf_token,
    }
    groups: list[CollectorTaskGroup] = []
    for collector in ASYNC_COLLECTORS:
        if not collector.enabled(source_cfg):
            groups.append(CollectorTaskGroup(collector.name, [], skipped_reason="disabled"))
            continue
        warnings: list[CollectorWarning] = []
        tasks = collector.build_tasks(**context, warnings=warnings)
        if not tasks:
            groups.append(CollectorTaskGroup(collector.name, [], skipped_reason="no tasks"))
            continue
        groups.append(CollectorTaskGroup(collector.name, tasks, warnings=warnings))
    return groups


def build_async_collector_tasks(
    *,
    source_cfg: dict[str, Any],
    source_registry: dict[str, Any],
    client: Any,
    cutoff: datetime,
    github_token: str | None,
    hf_token: str | None,
) -> list[Awaitable[list[RawEvent]]]:
    return [
        task
        for group in build_async_collector_task_groups(
            source_cfg=source_cfg,
            source_registry=source_registry,
            client=client,
            cutoff=cutoff,
            github_token=github_token,
            hf_token=hf_token,
        )
        if group.skipped_reason is None
        for task in group.tasks
    ]


def is_web_search_enabled(source_cfg: dict[str, Any]) -> bool:
    return _enabled(source_cfg, WEB_SEARCH_COLLECTOR.config_key)


def run_web_search_collector(
    *,
    source_cfg: dict[str, Any],
    date_str: str,
    web_search_client: WebSearchClient | None,
    warnings: list[CollectorWarning] | None = None,
) -> list[RawEvent]:
    return WEB_SEARCH_COLLECTOR.run(
        source_cfg=source_cfg,
        date_str=date_str,
        web_search_client=web_search_client,
        warnings=warnings,
    )
