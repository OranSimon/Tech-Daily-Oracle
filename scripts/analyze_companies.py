"""Company / Startup Analysis Layer (parallel)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yaml
from analyzer_helpers import schema_to_dataclass
from llm_schemas import CompanyAnalysisResponse
from prompt_runner import PromptRunner
from state import CompanyAnalysis, NormalizedEvent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_WORKERS = 5   # concurrent Claude calls


def _load_watchlist() -> dict[str, Any]:
    with open(os.path.join(ROOT, "sources", "company_watchlist.yml")) as f:
        return yaml.safe_load(f)


def _all_watched_companies(watchlist: dict[str, Any]) -> list[dict[str, Any]]:
    companies = []
    category_map = {
        "global_big_tech": "big_tech",
        "ai_labs": "ai_lab",
        "robotics_embodied_ai": "robotics",
        "ai_infrastructure": "infra",
        "hardware_devices": "hardware",
        "china_tech": "china_tech",
    }
    for section, cat in category_map.items():
        for c in watchlist.get(section, []):
            companies.append({"name": c["name"], "category": cat,
                               "ticker": c.get("ticker"), "domains": c.get("domains", [])})
    return companies


def _events_for_company(company_name: str, aliases: list[str],
                          events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    all_names = [company_name] + aliases
    matched = []
    for e in events:
        if company_name in e.companies:
            matched.append(e)
            continue
        text = f"{e.canonical_title} {e.summary}"
        if any(name in text for name in all_names):
            matched.append(e)
    return matched


def _analyze_one_company(
    company: dict[str, Any],
    events: list[NormalizedEvent],
    prompt_runner: PromptRunner,
) -> CompanyAnalysis | None:
    name = company["name"]
    cat = company["category"]
    aliases = company.get("domains", [])

    matched = _events_for_company(name, aliases, events)
    if not matched:
        return None

    payload = {
        "company": name,
        "category": cat,
        "ticker": company.get("ticker"),
        "events": [
            {
                "event_id": e.event_id,
                "title": e.canonical_title,
                "summary": e.summary,
                "source_type": e.source_type,
                "importance_score": e.importance_score,
                "source_urls": e.source_urls[:2],
            }
            for e in matched[:15]
        ],
        "history_summary": None,
    }

    result = prompt_runner.run_json(
        prompt_path="company_analysis.md",
        payload=payload,
        schema=CompanyAnalysisResponse,
        max_tokens=4096,
    )

    if not result.report_worthy:
        return None

    analysis = schema_to_dataclass(result, CompanyAnalysis, company=name)
    print(f"  [Companies] {name}: {analysis.significance} ({len(matched)} events)")
    return analysis


def analyze_companies(
    events: list[NormalizedEvent],
    prompt_runner: PromptRunner | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict[str, CompanyAnalysis]:
    watchlist = _load_watchlist()
    runner = prompt_runner or PromptRunner()
    watched = _all_watched_companies(watchlist)
    analyses: dict[str, CompanyAnalysis] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_one_company, company, events, runner): company["name"]
            for company in watched
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if result is not None:
                    analyses[name] = result
            except Exception as e:
                print(f"  [Companies] {name} analysis failed: {e}")

    return analyses
