"""Typed normalization scoring policy."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventTypeRule:
    event_type: str
    keywords: list[str]


@dataclass(frozen=True)
class SourceReliabilityPolicy:
    source_reliability_by_priority: dict[int, float] = field(
        default_factory=lambda: {1: 0.95, 2: 0.75, 3: 0.55, 4: 0.35, 5: 0.15}
    )
    paper_reliability: float = 0.90
    github_reliability: float = 0.85
    default_reliability: float = 0.50


@dataclass(frozen=True)
class NormalizationScoringPolicy:
    baseline_importance: float = 0.3
    source_priority_weight: float = 0.1
    company_boost: float = 0.2
    high_priority_topic_boost: float = 0.1
    cross_domain_boost: float = 0.15
    hn_social_heat_thresholds: dict[int, float] = field(default_factory=lambda: {500: 0.3, 200: 0.2, 100: 0.1})
    source_reliability_by_priority: dict[int, float] = field(
        default_factory=lambda: {1: 0.95, 2: 0.75, 3: 0.55, 4: 0.35, 5: 0.15}
    )
    paper_reliability: float = 0.90
    github_reliability: float = 0.85
    default_reliability: float = 0.50
    event_type_rules: list[EventTypeRule] = field(
        default_factory=lambda: [
            EventTypeRule("funding", ["funding", "raises", "series", "unicorn", "valuation"]),
            EventTypeRule("layoffs", ["layoff", "laid off", "job cuts", "restructur"]),
            EventTypeRule("earnings", ["earnings", "revenue", "profit", "quarterly"]),
            EventTypeRule("product_launch", ["launch", "release", "announce", "introduce", "unveil"]),
            EventTypeRule("policy", ["policy", "regulation", "ban", "sanction", "tariff", "export"]),
        ]
    )

    @property
    def source_reliability_policy(self) -> SourceReliabilityPolicy:
        return SourceReliabilityPolicy(
            source_reliability_by_priority=self.source_reliability_by_priority,
            paper_reliability=self.paper_reliability,
            github_reliability=self.github_reliability,
            default_reliability=self.default_reliability,
        )
