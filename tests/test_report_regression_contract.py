from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


DAILY_FIXTURES = [
    REPORTS / "daily" / "2026-05-15.md",
    REPORTS / "daily" / "2026-06-30.md",
    REPORTS / "daily" / "2026-07-02.md",
]
WEEKLY_FIXTURES = [
    REPORTS / "weekly" / "2026-W21.md",
    REPORTS / "weekly" / "2026-W26.md",
]
MONTHLY_FIXTURES = [
    REPORTS / "monthly" / "2026-05.md",
    REPORTS / "monthly" / "2026-06.md",
]


def _h2_sections(text: str) -> list[str]:
    return re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)


def test_report_files_follow_existing_naming_patterns() -> None:
    daily = sorted((REPORTS / "daily").glob("*.md"))
    weekly = sorted((REPORTS / "weekly").glob("*.md"))
    monthly = sorted((REPORTS / "monthly").glob("*.md"))

    assert daily
    assert weekly
    assert monthly
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name) for p in daily)
    assert all(re.fullmatch(r"\d{4}-W\d{2}\.md", p.name) for p in weekly)
    assert all(re.fullmatch(r"\d{4}-\d{2}\.md", p.name) for p in monthly)


def test_daily_golden_reports_keep_core_section_contract() -> None:
    expected_sections = [
        "1. 今日一句话判断",
        "2. Executive Summary",
        "3. Top Developments",
        "4. Technology Radar",
        "5. GitHub Trending: Top 3 High-Signal Repos",
        "6. Papers & Research Frontiers",
        "8. Big Tech & Major Company Moves",
        "9. China Tech",
        "14. Open Prediction Updates",
        "15. New Predictions",
        "17. Source Coverage & Confidence Notes",
        "18. Appendix: Source Links",
    ]

    for path in DAILY_FIXTURES:
        text = path.read_text(encoding="utf-8")
        date = path.stem

        assert text.startswith(f"# Tech Daily Brief — {date}")
        sections = _h2_sections(text)
        for section in expected_sections:
            assert section in sections, f"{path} missing {section}"
        assert len(re.findall(r"^###\s+\d+\.", text, flags=re.MULTILINE)) >= 3
        assert "---" in text
        assert "http" in text


def test_weekly_golden_reports_keep_core_section_contract() -> None:
    expected_sections = [
        "1. 本周主线",
        "2. 本周最重要技术趋势变化",
        "3. 本周 GitHub / Open-source 趋势",
        "4. 本周论文与研究前沿",
        "5. Startup / Unicorn 变化",
        "6. Big Tech 变化",
        "7. China Tech",
        "8. Macro / Policy Impact",
        "9. 本周预测更新总结",
        "10. 到期预测 Resolution",
        "11. Brier Score / Calibration",
        "14. 下周重点 Watchlist",
    ]

    for path in WEEKLY_FIXTURES:
        text = path.read_text(encoding="utf-8")
        week = path.stem

        assert text.startswith(f"# Tech Weekly Intelligence Review — {week}")
        sections = _h2_sections(text)
        for section in expected_sections:
            assert section in sections, f"{path} missing {section}"


def test_monthly_golden_reports_keep_core_section_contract() -> None:
    expected_sections = [
        "1. 月度科技主线",
        "2. Technology Momentum Ranking",
        "3. Startup / Unicorn Direction",
        "4. Big Tech Strategy Shifts",
        "5. China Tech Direction",
        "6. Research Frontier Shifts",
        "7. Open-source Ecosystem Shifts",
        "8. Macro / Geopolitical Impact",
        "9. Prediction Performance",
        "10. Strategic Theses Updated",
        "11. Opportunities for Startups / Investors",
    ]

    for path in MONTHLY_FIXTURES:
        text = path.read_text(encoding="utf-8")
        month = path.stem

        assert text.startswith(f"# Tech Monthly Strategic Review — {month}")
        sections = _h2_sections(text)
        for section in expected_sections:
            assert section in sections, f"{path} missing {section}"
        assert "| Rank | Technology Direction | Trend |" in text
