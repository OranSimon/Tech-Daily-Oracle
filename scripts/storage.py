"""Publishing & Storage Layer — save reports and update data files."""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from state import TechDailyState, Prediction, PredictionUpdate, Report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(ROOT, "reports")


def _ensure_dirs() -> None:
    for d in [DATA_DIR,
              os.path.join(REPORTS_DIR, "daily"),
              os.path.join(REPORTS_DIR, "weekly"),
              os.path.join(REPORTS_DIR, "monthly")]:
        os.makedirs(d, exist_ok=True)


def _safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_safe_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Report storage
# ---------------------------------------------------------------------------

def save_daily_report(run_date: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "daily", f"{run_date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Storage] Saved daily report: {path}")
    return path


def save_weekly_review(week: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "weekly", f"{week}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Storage] Saved weekly review: {path}")
    return path


def save_monthly_review(month: str, content: str) -> str:
    _ensure_dirs()
    path = os.path.join(REPORTS_DIR, "monthly", f"{month}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Storage] Saved monthly review: {path}")
    return path


# ---------------------------------------------------------------------------
# Prediction log
# ---------------------------------------------------------------------------

PREDICTION_LOG = os.path.join(DATA_DIR, "prediction_log.jsonl")


def load_open_predictions() -> list[Prediction]:
    predictions = []
    if not os.path.exists(PREDICTION_LOG):
        return []
    with open(PREDICTION_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("status") == "open":
                    predictions.append(Prediction(
                        prediction_id=d["prediction_id"],
                        created_date=d["created_date"],
                        prediction=d["prediction"],
                        topic_tags=d.get("topic_tags", []),
                        companies=d.get("companies", []),
                        time_horizon=d["time_horizon"],
                        horizon_date=d.get("horizon_date", ""),
                        probability=d["probability"],
                        evidence=d.get("evidence", ""),
                        resolution_criteria=d.get("resolution_criteria", ""),
                        falsification_condition=d.get("falsification_condition", ""),
                        signals_to_monitor=d.get("signals_to_monitor", []),
                        status=d["status"],
                        confidence=d.get("confidence", "medium"),
                        updates=d.get("updates", []),
                    ))
            except Exception as e:
                print(f"  [Storage] Failed to load prediction: {e}")
    return predictions


def save_predictions(new_predictions: list[Prediction],
                     updates: list[PredictionUpdate]) -> None:
    """Append new predictions and apply updates to the log."""
    _ensure_dirs()

    # Load all existing predictions
    all_predictions: dict[str, dict[str, Any]] = {}
    if os.path.exists(PREDICTION_LOG):
        with open(PREDICTION_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line)
                        all_predictions[d["prediction_id"]] = d
                    except Exception:
                        pass

    # Apply updates
    for update in updates:
        pid = update.prediction_id
        if pid in all_predictions:
            p = all_predictions[pid]
            p["probability"] = update.probability_after
            p.setdefault("updates", []).append(_safe_dict(update))
            if update.resolution.get("resolved"):
                outcome = update.resolution.get("resolved_as")
                p["status"] = f"resolved_{outcome}" if outcome else "resolved_unknown"
                p["resolution_reasoning"] = update.resolution.get("resolution_reasoning", "")

    # Add new predictions
    for pred in new_predictions:
        d = _safe_dict(pred)
        all_predictions[pred.prediction_id] = d

    # Rewrite log
    with open(PREDICTION_LOG, "w", encoding="utf-8") as f:
        for p in all_predictions.values():
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"  [Storage] Prediction log updated: "
          f"{len(new_predictions)} new, {len(updates)} updated")


# ---------------------------------------------------------------------------
# Event data files (append-only)
# ---------------------------------------------------------------------------

def append_events(state: TechDailyState) -> None:
    """Append today's events to data log files."""
    _ensure_dirs()

    def _append_jsonl(path: str, records: list[dict[str, Any]]) -> None:
        with open(path, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # source_events.jsonl
    events_payload = [
        {
            "run_date": state.run_date,
            "run_id": state.run_id,
            **_safe_dict(e),
        }
        for e in state.normalized_events
    ]
    _append_jsonl(os.path.join(DATA_DIR, "source_events.jsonl"), events_payload)

    # topic_trends.jsonl
    topic_payload = [
        {
            "run_date": state.run_date,
            "topic_id": ts.topic_id,
            "trend_status": ts.trend_status,
            "signal_count": ts.signal_count,
            "signal_classification": ts.signal_classification,
        }
        for ts in state.topic_summaries.values()
    ]
    _append_jsonl(os.path.join(DATA_DIR, "topic_trends.jsonl"), topic_payload)

    # company_mentions.jsonl
    company_payload = [
        {
            "run_date": state.run_date,
            "company": name,
            "significance": a.significance,
            "summary": a.summary,
        }
        for name, a in state.company_analyses.items()
    ]
    if company_payload:
        _append_jsonl(os.path.join(DATA_DIR, "company_mentions.jsonl"), company_payload)

    # paper_mentions.jsonl
    paper_payload = [
        {
            "run_date": state.run_date,
            "title": p.title,
            "link": p.link,
            "signal_strength": p.signal_strength,
            "overall_score": p.overall_score,
        }
        for p in state.paper_analyses.values()
        if p.report_worthy
    ]
    if paper_payload:
        _append_jsonl(os.path.join(DATA_DIR, "paper_mentions.jsonl"), paper_payload)

    # project_mentions.jsonl
    project_payload = [
        {
            "run_date": state.run_date,
            "repo": p.repo,
            "url": p.url,
            "verdict": p.verdict,
            "stars_total": p.stars_total,
        }
        for p in state.github_project_analyses.values()
    ]
    if project_payload:
        _append_jsonl(os.path.join(DATA_DIR, "project_mentions.jsonl"), project_payload)

    print(f"  [Storage] Appended events to data logs")


# ---------------------------------------------------------------------------
# Historical context loading
# ---------------------------------------------------------------------------

def load_recent_reports(n: int = 7) -> list[Report]:
    daily_dir = os.path.join(REPORTS_DIR, "daily")
    if not os.path.exists(daily_dir):
        return []

    report_files = sorted([
        f for f in os.listdir(daily_dir) if f.endswith(".md")
    ], reverse=True)[:n]

    reports = []
    for fname in report_files:
        path = os.path.join(daily_dir, fname)
        report_date = fname.replace(".md", "")
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            reports.append(Report(
                report_type="daily",
                report_date=report_date,
                content=content,
            ))
        except Exception as e:
            print(f"  [Storage] Failed to load report {fname}: {e}")

    return reports


def load_recent_weekly_reviews(n: int = 4) -> list[Report]:
    weekly_dir = os.path.join(REPORTS_DIR, "weekly")
    if not os.path.exists(weekly_dir):
        return []
    files = sorted([f for f in os.listdir(weekly_dir) if f.endswith(".md")], reverse=True)[:n]
    reviews = []
    for fname in files:
        try:
            with open(os.path.join(weekly_dir, fname), encoding="utf-8") as f:
                content = f.read()
            reviews.append(Report(report_type="weekly",
                                  report_date=fname.replace(".md", ""),
                                  content=content))
        except Exception as e:
            print(f"  [Storage] Failed to load weekly review {fname}: {e}")
    return reviews


def load_recent_monthly_reviews(n: int = 3) -> list[Report]:
    monthly_dir = os.path.join(REPORTS_DIR, "monthly")
    if not os.path.exists(monthly_dir):
        return []
    files = sorted([f for f in os.listdir(monthly_dir) if f.endswith(".md")], reverse=True)[:n]
    reviews = []
    for fname in files:
        try:
            with open(os.path.join(monthly_dir, fname), encoding="utf-8") as f:
                content = f.read()
            reviews.append(Report(report_type="monthly",
                                  report_date=fname.replace(".md", ""),
                                  content=content))
        except Exception as e:
            print(f"  [Storage] Failed to load monthly review {fname}: {e}")
    return reviews


def _load_jsonl_since(path: str, days: int) -> list[dict]:
    if not os.path.exists(path):
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("run_date", "9999") >= cutoff:
                    records.append(d)
            except Exception:
                pass
    return records


def load_topic_trends_recent(days: int = 30) -> list[dict]:
    return _load_jsonl_since(os.path.join(DATA_DIR, "topic_trends.jsonl"), days)


def load_company_mentions_recent(days: int = 90) -> list[dict]:
    return _load_jsonl_since(os.path.join(DATA_DIR, "company_mentions.jsonl"), days)
