from __future__ import annotations

import run_monthly_review
import run_weekly_review


def test_iso_week_uses_two_digit_week_numbers() -> None:
    assert run_weekly_review._iso_week(__import__("datetime").date(2026, 1, 2)) == "2026-W01"


def test_monthly_week_overlap_guard_counts_weeks_touching_month() -> None:
    assert run_monthly_review._week_in_month("2026-W22", "2026-05")
    assert run_monthly_review._week_in_month("2026-W23", "2026-06")
    assert not run_monthly_review._week_in_month("2026-W10", "2026-06")


def test_weekly_review_skips_when_daily_guard_not_met(monkeypatch) -> None:
    monkeypatch.setattr(
        run_weekly_review,
        "_load_config",
        lambda: {"run": {"timezone": "Asia/Shanghai"}, "review_guards": {"min_daily_for_weekly": 3}},
    )
    monkeypatch.setattr(run_weekly_review, "_load_week_reports", lambda week: [{"date": "2026-06-22"}])

    assert run_weekly_review.run_weekly_review("2026-W26") == ""


def test_monthly_review_skips_when_monthly_guards_not_met(monkeypatch) -> None:
    monkeypatch.setattr(
        run_monthly_review,
        "_load_config",
        lambda: {
            "run": {"timezone": "Asia/Shanghai"},
            "review_guards": {"min_weekly_for_monthly": 2, "min_daily_for_monthly": 10},
        },
    )
    monkeypatch.setattr(run_monthly_review, "_load_weekly_reviews_for_month", lambda month: [])
    monkeypatch.setattr(run_monthly_review, "_load_daily_summaries_for_month", lambda month: [])

    assert run_monthly_review.run_monthly_review("2026-06") == ""
