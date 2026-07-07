"""Typed payloads for event artifact storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tech_daily.pipeline.state import (
    CompanyAnalysis,
    NormalizedEvent,
    PaperAnalysis,
    ProjectAnalysis,
    TopicSummary,
)

if TYPE_CHECKING:
    from tech_daily.pipeline.state import TechDailyState


@dataclass(frozen=True)
class EventStoragePayload:
    run_date: str
    run_id: str
    normalized_events: list[NormalizedEvent] = field(default_factory=list)
    topic_summaries: dict[str, TopicSummary] = field(default_factory=dict)
    company_analyses: dict[str, CompanyAnalysis] = field(default_factory=dict)
    paper_analyses: dict[str, PaperAnalysis] = field(default_factory=dict)
    github_project_analyses: dict[str, ProjectAnalysis] = field(default_factory=dict)

    @classmethod
    def from_state(cls, state: TechDailyState) -> EventStoragePayload:
        return cls(
            run_date=state.run_date,
            run_id=state.run_id,
            normalized_events=state.normalized_events,
            topic_summaries=state.topic_summaries,
            company_analyses=state.company_analyses,
            paper_analyses=state.paper_analyses,
            github_project_analyses=state.github_project_analyses,
        )
