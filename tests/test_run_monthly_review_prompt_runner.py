from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import run_monthly_review
import storage
from llm_client import LLMClient
from prompt_runner import PromptRunner
from state import Prediction


class FakeTextLLMClient:
    def __init__(self, response: str | BaseException) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
        auto_continue: bool = False,
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "max_tokens": max_tokens,
                "cache_system": cache_system,
                "auto_continue": auto_continue,
            }
        )
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def _fake_prediction() -> Prediction:
    return Prediction(
        prediction_id="pred-1",
        created_date="2026-06-01",
        prediction="Enterprise AI agents will expand in finance workflows.",
        topic_tags=["AI"],
        companies=["ExampleAI"],
        time_horizon="90d",
        horizon_date="2026-09-01",
        probability=0.68,
        evidence="Fixture evidence",
        resolution_criteria="Fixture criteria",
        falsification_condition="Fixture falsification",
        signals_to_monitor=["customer announcement"],
        status="open",
        confidence="medium",
        updates=[],
    )


def _patch_monthly_dependencies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(run_monthly_review, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "topic_trends.jsonl").write_text(
        json.dumps({"run_date": "2026-06-15", "topic": "AI"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "data" / "company_mentions.jsonl").write_text(
        json.dumps({"run_date": "2026-06-16", "company": "ExampleAI"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "data" / "prediction_log.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        run_monthly_review,
        "_load_config",
        lambda: {
            "run": {"timezone": "UTC"},
            "review_guards": {"min_weekly_for_monthly": 1, "min_daily_for_monthly": 10},
            "model": {"default": "fixture-model", "max_tokens_monthly": 3333},
            "trending": {"top_n": 3},
            "notion": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        run_monthly_review,
        "_load_weekly_reviews_for_month",
        lambda month: [{"week": "2026-W26", "content": "# Weekly 1"}],
    )
    monkeypatch.setattr(run_monthly_review, "_load_daily_summaries_for_month", lambda month: [])
    monkeypatch.setattr(run_monthly_review, "load_open_predictions", lambda: [_fake_prediction()])
    monkeypatch.setattr(run_monthly_review, "compute_scorecard", lambda: {"count": 1})
    monkeypatch.setattr(run_monthly_review, "collect_trending_snapshot", lambda period, run_date, cfg: {})
    monkeypatch.setattr(run_monthly_review, "load_trending_history", lambda days=90: [])
    monkeypatch.setattr(
        run_monthly_review,
        "analyze_trending",
        lambda snapshot, history, top_n=5: type(
            "TrendingResult",
            (),
            {"report_section": "## Monthly Trending\n\n- Fixture monthly trend"},
        )(),
    )
    monkeypatch.setattr(run_monthly_review, "load_market_signals_history", lambda days=95: [])


def test_monthly_review_uses_prompt_runner_and_saves_expected_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_monthly_dependencies(monkeypatch, tmp_path)
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "monthly_review.md").write_text("Monthly system prompt", encoding="utf-8")
    fake: LLMClient = FakeTextLLMClient(
        "# Tech Monthly Strategic Review - 2026-06\n\n## 1. Strategic Summary\n\nFixture report"
    )
    runner = PromptRunner(fake, prompt_root=prompt_dir)

    review = run_monthly_review.run_monthly_review("2026-06", prompt_runner=runner)

    assert review.startswith("# Tech Monthly Strategic Review")
    assert "## Monthly Trending" in review
    saved = tmp_path / "reports" / "monthly" / "2026-06.md"
    assert saved.read_text(encoding="utf-8") == review
    assert fake.calls[0]["system"] == "Monthly system prompt"
    assert fake.calls[0]["model"] == "fixture-model"
    assert fake.calls[0]["max_tokens"] == 3333
    assert fake.calls[0]["cache_system"] is True
    payload = json.loads(fake.calls[0]["user"])
    assert payload["month"] == "2026-06"
    assert payload["weekly_reviews"][0]["content"] == "# Weekly 1"
    assert payload["trending_monthly_summary"] == "## Monthly Trending\n\n- Fixture monthly trend"
    assert payload["open_predictions"][0]["prediction_id"] == "pred-1"


def test_monthly_review_surfaces_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_monthly_dependencies(monkeypatch, tmp_path)
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "monthly_review.md").write_text("Monthly system prompt", encoding="utf-8")
    runner = PromptRunner(FakeTextLLMClient(RuntimeError("llm unavailable")), prompt_root=prompt_dir)

    with pytest.raises(RuntimeError, match="llm unavailable"):
        run_monthly_review.run_monthly_review("2026-06", prompt_runner=runner)
