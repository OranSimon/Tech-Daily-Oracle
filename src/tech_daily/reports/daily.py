"""Report generation helpers for the daily brief."""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from tech_daily.llm.contracts import ModelRole
from tech_daily.llm.prompt_runner import PromptRunner
from tech_daily.pipeline.state import ReportInputState

if TYPE_CHECKING:
    from state import TechDailyState

ROOT_DIR = Path(__file__).resolve().parents[3]
ROOT = str(ROOT_DIR)
DEFAULT_DAILY_MODEL = ModelRole.DEFAULT

_GITHUB_SECTION_PATTERN = re.compile(
    r"^## 5\. GitHub Trending: Top 3 High-Signal Repos\s*$.*?(?=^## 6\. Papers & Research Frontiers\s*$)",
    flags=re.MULTILINE | re.DOTALL,
)

_GITHUB_EMPTY_SECTION_COPY = {
    "source_empty": "本期未获取到可分析的 GitHub 趋势候选，跳过此节。",
    "all_candidates_filtered": "本期 GitHub 趋势候选均未通过质量过滤，跳过此节。",
    "analysis_failed": "本期 GitHub 项目分析失败，结果不可用，跳过此节。",
    "no_watch_verdict": "本期 GitHub 候选仅达到 Track/Skip 级别，暂无 Watch 项目，跳过此节。",
}

__all__ = [
    "Any",
    "PromptRunner",
    "ReportInputState",
    "ROOT",
    "DEFAULT_DAILY_MODEL",
    "TechDailyState",
    "dataclasses",
    "build_daily_report_payload_from_input",
    "generate_daily_report",
    "generate_daily_report_from_input",
    "json",
    "os",
    "yaml",
]


def __getattr__(name: str) -> object:
    if name != "TechDailyState":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name = "st" + "ate"
    TechDailyState = importlib.import_module(module_name).TechDailyState

    return TechDailyState


def _load_config() -> Any:
    with (ROOT_DIR / "config.yml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_preferences() -> Any:
    prefs_path = ROOT_DIR / "data" / "user_preferences.yml"
    if prefs_path.exists():
        with prefs_path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    return {}


def _previous_reports_summary_from_input(input_state: ReportInputState) -> list[dict[str, Any]]:
    return [
        {
            "report_date": report.report_date,
            "type": report.report_type,
            "excerpt": report.content[:800],
        }
        for report in input_state.historical_context.previous_reports[-7:]
    ]


def _safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_safe_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _safe_dict(value) for key, value in obj.items()}
    return obj


def _github_report_status(input_state: ReportInputState, watch_projects: list[Any]) -> dict[str, Any]:
    status = dict(input_state.analysis.github_project_analysis_status)
    if watch_projects:
        status["reason"] = "watch_projects_available"
    elif input_state.analysis.github_project_analyses:
        status["reason"] = "no_watch_verdict"
    else:
        status.setdefault("reason", "source_empty")
    return status


def _replace_empty_github_section(report: str, status: dict[str, Any]) -> str:
    reason = status.get("reason", "source_empty")
    if reason == "watch_projects_available":
        return report

    copy = _GITHUB_EMPTY_SECTION_COPY.get(reason, _GITHUB_EMPTY_SECTION_COPY["source_empty"])
    replacement = f"## 5. GitHub Trending: Top 3 High-Signal Repos\n\n{copy}\n\n"
    return _GITHUB_SECTION_PATTERN.sub(replacement, report, count=1)


def _build_report_payload(state: TechDailyState) -> dict[str, Any]:
    return build_daily_report_payload_from_input(ReportInputState.from_tech_daily_state(state))


def build_daily_report_payload_from_input(input_state: ReportInputState) -> dict[str, Any]:
    """Build the structured payload sent to the LLM for report generation."""

    top_events = sorted(input_state.corpus.normalized_events, key=lambda event: event.importance_score, reverse=True)[
        :30
    ]

    sorted_papers = sorted(
        input_state.analysis.paper_analyses.values(),
        key=lambda paper: paper.overall_score,
        reverse=True,
    )

    top_github = [
        verdict for verdict in input_state.analysis.github_project_analyses.values() if verdict.verdict == "Watch"
    ][:3]
    github_status = _github_report_status(input_state, top_github)

    sig_companies = {
        key: value
        for key, value in input_state.analysis.company_analyses.items()
        if value.significance in ("high", "medium")
    }

    return {
        "run_date": input_state.run_metadata.run_date,
        "normalized_events": [_safe_dict(event) for event in top_events],
        "topic_summaries": {
            key: _safe_dict(value) for key, value in input_state.analysis.topic_summaries.items() if value.report_worthy
        },
        "company_analyses": {key: _safe_dict(value) for key, value in sig_companies.items()},
        "paper_analyses": [_safe_dict(paper) for paper in sorted_papers[:8] if paper.report_worthy],
        "github_project_analyses": [_safe_dict(project) for project in top_github],
        "github_project_analysis_status": github_status,
        "social_signal_analyses": {
            key: _safe_dict(value)
            for key, value in input_state.analysis.social_signal_analyses.items()
            if value.report_worthy
        },
        "macro_impact_analyses": {
            key: _safe_dict(value)
            for key, value in input_state.analysis.macro_impact_analyses.items()
            if value.report_worthy
        },
        "open_predictions": [_safe_dict(prediction) for prediction in input_state.prediction.open_predictions],
        "prediction_updates": [_safe_dict(update) for update in input_state.prediction.prediction_updates],
        "new_predictions": [_safe_dict(prediction) for prediction in input_state.prediction.new_predictions],
        "previous_reports_summary": _previous_reports_summary_from_input(input_state),
        "history_context": {
            "weekly_reviews": [
                {"week": review.report_date, "excerpt": review.content[:1500]}
                for review in input_state.historical_context.weekly_reviews
            ],
            "monthly_reviews": [
                {"month": review.report_date, "excerpt": review.content[:2000]}
                for review in input_state.historical_context.monthly_reviews
            ],
            "topic_trend_30d": input_state.historical_context.recent_topic_trends[-90:],
            "company_mentions_90d": input_state.historical_context.recent_company_mentions[-120:],
        },
        "market_signal_analyses": [
            {"ticker": value.ticker, "company": value.company, "report_snippet": value.report_snippet}
            for value in input_state.analysis.market_signal_analyses.values()
        ],
        "source_warnings": input_state.diagnostics.source_warnings,
        "confidence_flags": input_state.diagnostics.confidence_flags,
        "user_preferences": _load_preferences(),
        "signal_level": input_state.run_metadata.signal_level,
    }


def generate_daily_report(
    state: TechDailyState,
    prompt_runner: PromptRunner | None = None,
) -> str:
    return generate_daily_report_from_input(ReportInputState.from_tech_daily_state(state), prompt_runner=prompt_runner)


def generate_daily_report_from_input(
    input_state: ReportInputState,
    prompt_runner: PromptRunner | None = None,
) -> str:
    cfg = _load_config()
    runner = prompt_runner or PromptRunner()
    max_tokens = cfg.get("model", {}).get("max_tokens_daily", 8000)
    model = cfg.get("model", {}).get("default", DEFAULT_DAILY_MODEL)

    payload = build_daily_report_payload_from_input(input_state)
    user_msg = json.dumps(payload, ensure_ascii=False)

    print(f"  [Report] Generating daily brief for {input_state.run_metadata.run_date}...")
    report = runner.run_text(
        prompt_path="daily_brief.md",
        payload=user_msg,
        model=model,
        max_tokens=max_tokens,
        cache_system=True,
    )
    report = _replace_empty_github_section(report, payload["github_project_analysis_status"])

    trending_analysis = input_state.analysis.trending_analysis
    if trending_analysis is not None and trending_analysis.report_section:
        report = report + "\n\n---\n" + trending_analysis.report_section

    print(f"  [Report] Generated {len(report)} characters")
    return report
