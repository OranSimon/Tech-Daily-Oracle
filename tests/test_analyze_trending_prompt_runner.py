from __future__ import annotations

from pathlib import Path

import analyze_trending
import pytest
from prompt_runner import PromptRunner, PromptRunnerError
from state import TrendingAnalysis, TrendingItem, TrendingSnapshot
from test_prompt_runner import FakeLLMClient


def _github_item() -> TrendingItem:
    return TrendingItem(
        item_id="oransimon/fixture-trending",
        item_type="github_repo",
        source="ossinsight",
        title="fixture-trending",
        url="https://github.com/oransimon/fixture-trending",
        description="Fixture trending repository for analyzer tests.",
        period="daily",
        rank=1,
        velocity_score=1234.0,
        language="Python",
        topics=["devtools"],
        snapshot_date="2026-07-02",
        extra={"forks_increment": 12},
    )


def _snapshot() -> TrendingSnapshot:
    return TrendingSnapshot(
        snapshot_date="2026-07-02",
        period="daily",
        github_items=[_github_item()],
        hf_paper_items=[],
        hf_model_items=[],
    )


def _prompt_runner(tmp_path: Path, response: str) -> PromptRunner:
    (tmp_path / "trending_analysis.md").write_text("Trending prompt", encoding="utf-8")
    return PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)


VALID_TRENDING_JSON = """[
  {
    "item_id": "oransimon/fixture-trending",
    "why_trending": "It spiked on GitHub velocity lists.",
    "what_it_signals": "Developers are testing fixture automation tools.",
    "topics": ["devtools", "open_source"],
    "hype_risk": "low",
    "report_snippet": "**fixture-trending** (+1,234 ⭐)：Fixture trending snippet."
  }
]"""


def test_analyze_trending_accepts_fake_prompt_runner_plain_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, VALID_TRENDING_JSON)

    analysis = analyze_trending.analyze_trending(_snapshot(), history=[], top_n=1, prompt_runner=runner)

    assert isinstance(analysis, TrendingAnalysis)
    assert analysis.item_analyses == {
        "oransimon/fixture-trending": "**fixture-trending** (+1,234 ⭐)：Fixture trending snippet."
    }
    assert "Fixture trending snippet" in analysis.report_section
    assert analysis.top_github == [_github_item()]


def test_analyze_new_items_batch_accepts_fenced_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, f"```json\n{VALID_TRENDING_JSON}\n```")

    item_analyses = analyze_trending._analyze_new_items_batch([_github_item()], runner)

    assert item_analyses["oransimon/fixture-trending"].endswith("Fixture trending snippet.")


def test_analyze_new_items_batch_raises_prompt_runner_error_for_invalid_json(tmp_path: Path) -> None:
    runner = _prompt_runner(tmp_path, "not-json")

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_trending._analyze_new_items_batch([_github_item()], runner)

    assert exc_info.value.kind == "json_parse_error"


def test_analyze_new_items_batch_raises_prompt_runner_error_for_missing_required_fields(
    tmp_path: Path,
) -> None:
    runner = _prompt_runner(
        tmp_path,
        '[{"item_id": "oransimon/fixture-trending", "hype_risk": "low"}]',
    )

    with pytest.raises(PromptRunnerError) as exc_info:
        analyze_trending._analyze_new_items_batch([_github_item()], runner)

    assert exc_info.value.kind == "schema_validation_error"
    assert "report_snippet" in exc_info.value.message
