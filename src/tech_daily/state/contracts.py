"""Typed helper contracts for nested state dictionaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictionResolution:
    resolved: bool
    resolved_as: str | None = None
    resolution_reasoning: str | None = None

    def to_persisted_dict(self) -> dict[str, object]:
        return {
            "resolved": self.resolved,
            "resolved_as": self.resolved_as,
            "resolution_reasoning": self.resolution_reasoning,
        }


@dataclass(frozen=True)
class SignalToMonitor:
    signal: str
    threshold: str
    meaning: str
    current: str | None = None

    def to_persisted_dict(self) -> dict[str, str]:
        persisted = {
            "signal": self.signal,
            "threshold": self.threshold,
            "meaning": self.meaning,
        }
        if self.current is not None:
            persisted["current"] = self.current
        return persisted
