from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import generate_report
from prompt_runner import PromptRunner
from state import TechDailyState
from test_prompt_runner import FakeLLMClient


def test_build_report_payload_contains_existing_report_generation_contract() -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")

    payload = generate_report._build_report_payload(state)

    assert payload["run_date"] == "2026-07-02"
    assert payload["normalized_events"] == []
    assert payload["topic_summaries"] == {}
    assert payload["open_predictions"] == []
    assert payload["history_context"] == {
        "weekly_reviews": [],
        "monthly_reviews": [],
        "topic_trend_30d": [],
        "company_mentions_90d": [],
    }
    assert payload["signal_level"] == "normal"


def test_generate_daily_report_uses_fake_prompt_runner_and_appends_trending_section(
    monkeypatch, tmp_path: Path
) -> None:
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    state.trending_analysis = SimpleNamespace(report_section="## 🔥 趋势榜单 — 今日 (2026-07-02)")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    fake = FakeLLMClient("# Tech Daily Brief — 2026-07-02\n\n## 1. 今日一句话判断\n")
    runner = PromptRunner(fake, prompt_root=tmp_path)

    monkeypatch.setattr(
        generate_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100, "default": "model"}}
    )
    monkeypatch.setattr(generate_report, "_load_preferences", lambda: {})

    report = generate_report.generate_daily_report(state, prompt_runner=runner)

    assert report.startswith("# Tech Daily Brief — 2026-07-02")
    assert "---\n## 🔥 趋势榜单 — 今日 (2026-07-02)" in report
    assert fake.calls[0]["system"] == "Daily prompt"
    assert fake.calls[0]["model"] == "model"
    assert fake.calls[0]["max_tokens"] == 100


def test_generate_daily_report_surfaces_fake_llm_failure(monkeypatch, tmp_path: Path) -> None:
    class FailingLLMClient:
        def generate_text(self, **kwargs):
            raise RuntimeError("fake LLM failure")

    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    runner = PromptRunner(FailingLLMClient(), prompt_root=tmp_path)
    monkeypatch.setattr(generate_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100}})
    monkeypatch.setattr(generate_report, "_load_preferences", lambda: {})

    try:
        generate_report.generate_daily_report(state, prompt_runner=runner)
    except RuntimeError as exc:
        assert "fake LLM failure" in str(exc)
    else:
        raise AssertionError("Expected fake LLM failure to surface")
