from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import analyze_market_signals
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import CompanyAnalysis, MarketSignalAnalysis, NormalizedEvent
from test_prompt_runner import FakeLLMClient


def _event() -> NormalizedEvent:
    published = datetime(2026, 7, 2, tzinfo=UTC).isoformat()
    return NormalizedEvent(
        event_id="event-2026-07-02-market",
        canonical_title="Nvidia announces fixture AI accelerator demand",
        summary="Nvidia reports fixture demand for AI accelerators.",
        source_urls=["https://example.com/nvidia"],
        primary_source_url="https://example.com/nvidia",
        source_type="company",
        published_at=published,
        companies=["Nvidia"],
        projects=[],
        papers=[],
        people=[],
        topics=["semiconductors", "ai_infrastructure"],
        geography=[],
        event_type="earnings",
        importance_score=0.92,
        novelty_score=0.8,
        reliability_score=0.95,
        social_heat_score=0.0,
        raw_event_ids=["raw-market-1"],
        metadata={},
    )


def _company_analysis() -> CompanyAnalysis:
    return CompanyAnalysis(
        company="Nvidia",
        category="semiconductors",
        report_worthy=True,
        significance="high",
        event_ids=["event-2026-07-02-market"],
        summary="Fixture Nvidia company signal.",
        analysis_by_category={"product": "accelerator demand"},
        confidence="high",
        source_quality="official",
        watchlist_action="monitor",
        watchlist_notes=None,
    )


def _state() -> Any:
    return SimpleNamespace(
        run_date="2026-07-02",
        normalized_events=[_event()],
        company_analyses={"Nvidia": _company_analysis()},
        macro_impact_analyses={},
        topic_summaries={},
    )


def _ticker_cfg() -> dict:
    return {
        "ticker": "NVDA",
        "company": "Nvidia",
        "horizon": "2-8 weeks",
        "why_tracked": "AI accelerator bellwether",
    }


def _payload() -> dict:
    return analyze_market_signals._build_ticker_payload(
        ticker_cfg=_ticker_cfg(),
        company_analysis=_company_analysis(),
        related_events=[
            {
                "title": "Nvidia fixture demand",
                "summary": "Fixture event.",
                "importance_score": 0.92,
                "source_type": "company",
                "event_type": "earnings",
            }
        ],
        macro_context={"macro_events": [], "tech_trends": {}},
        run_date="2026-07-02",
        market_data=None,
        prior_signal=None,
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "market_signal.md").write_text("Market prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_MARKET_SIGNAL_JSON = """{
  "date": "2026-07-02",
  "ticker": "NVDA",
  "company": "Nvidia",
  "time_horizon": "2-8 weeks",
  "event_context": ["event-2026-07-02-market"],
  "conclusion": "Fixture medium-term thesis.",
  "conclusion_zh": "Fixture 中文结论。",
  "reasoning_zh": "Fixture 中文原因。",
  "base_case": "Demand remains firm.",
  "bull_case": "Supply expands faster than expected.",
  "bear_case": "Demand normalizes.",
  "buy_observation_point": "Watch pullbacks on volume.",
  "sell_reduce_observation_point": "Reduce if demand indicators weaken.",
  "invalidation_condition": "Major order cancellations.",
  "risk_level": "medium",
  "confidence": "high",
  "signals_to_monitor": [
    {
      "signal": "Datacenter demand",
      "current": "strong",
      "threshold": "weakening",
      "meaning": "Demand inflection"
    }
  ],
  "source_events": ["event-2026-07-02-market"]
}"""


def test_analyze_market_signals_accepts_fake_prompt_runner_plain_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        analyze_market_signals,
        "_load_watchlist",
        lambda config: {
            "tickers": [_ticker_cfg()],
            "settings": {
                "only_on_event_day": True,
                "min_importance_to_trigger": 0.55,
                "max_tickers_per_run": 1,
            },
        },
    )
    runner = _prompt_runner(tmp_path, VALID_MARKET_SIGNAL_JSON)

    analyses = analyze_market_signals.analyze_market_signals(
        _state(),
        market_data=None,
        prior_signals={},
        config={"market_signal": {"enabled": True}},
        prompt_runner=runner,
    )

    assert list(analyses) == ["NVDA"]
    assert isinstance(analyses["NVDA"], MarketSignalAnalysis)
    assert analyses["NVDA"].confidence == "high"
    assert analyses["NVDA"].has_price_data is False
    assert "Fixture 中文结论" in analyses["NVDA"].report_snippet


def test_analyze_one_ticker_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_MARKET_SIGNAL_JSON}\n```")

    analysis = analyze_market_signals._analyze_one_ticker(_ticker_cfg(), _payload(), False, runner)

    assert analysis is not None
    assert analysis.ticker == "NVDA"
    assert analysis.company == "Nvidia"
    assert analysis.signals_to_monitor[0]["signal"] == "Datacenter demand"


def test_analyze_one_ticker_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_market_signals._analyze_one_ticker(_ticker_cfg(), _payload(), False, runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_one_ticker_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(tmp_path, '{"ticker": "NVDA", "company": "Nvidia"}')

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_market_signals._analyze_one_ticker(_ticker_cfg(), _payload(), False, runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "risk_level" in exc_info.value.message
