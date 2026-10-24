"""Bounded API probes. Never print credentials, generated text, or balance amounts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yml").read_text())
KEY_NAMES = ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
KEYS = {name: os.environ.get(name, "") for name in KEY_NAMES}


def clean(value: object) -> str:
    text = str(value)
    for key in KEYS.values():
        if key:
            text = text.replace(key, "[credential redacted]")
    text = re.sub(r"\b(?:sk-[\w-]+|AIza[\w-]+|org-[\w-]+|proj_[\w-]+)\b", "[redacted]", text)
    text = re.sub(r"projects/[\w-]+", "projects/[redacted]", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]+\b", "[email redacted]", text)
    text = re.sub(r"\b\d{10,}\b", "[identifier redacted]", text)
    return text[:1600]


def emit(probe: str, **fields: object) -> None:
    print(json.dumps({"probe": probe, **fields}, ensure_ascii=False), flush=True)


def probe(name: str, method: str, url: str, headers: dict, payload: dict | None = None, *, timeout: int = 120) -> dict | None:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(method, url, headers=headers, json=payload)
        try:
            data = response.json()
        except ValueError:
            emit(name, http_status=response.status_code, body_kind="non_json", body_bytes=len(response.content))
            return None
        fields = {"http_status": response.status_code, "seconds": round(time.monotonic() - start, 2)}
        if response.is_error:
            error = data.get("error", data)
            if isinstance(error, dict):
                fields["error"] = {key: clean(error[key]) for key in ("code", "type", "status", "message", "param") if key in error}
                details = error.get("details", [])
                fields["quota_violations"] = [
                    {key: clean(item[key]) for key in ("quotaMetric", "quotaId", "quotaValue") if key in item}
                    for detail in details if isinstance(detail, dict)
                    for item in detail.get("violations", []) if isinstance(item, dict)
                ]
            else:
                fields["error_kind"] = type(error).__name__
        elif name == "deepseek.balance":
            fields["balance_available_for_api"] = data.get("is_available")
        elif name == "deepseek.models":
            names = {item.get("id") for item in data.get("data", [])}
            fields["configured_names_listed"] = {model: model in names for model in ("deepseek-v4-flash", "deepseek-flash", "deepseek-v4-pro")}
        elif "choices" in data:
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message", {})
            fields.update(
                returned_model=data.get("model"), finish_reason=choice.get("finish_reason"),
                content_chars=len(message.get("content") or ""), reasoning_chars=len(message.get("reasoning_content") or ""),
                usage=data.get("usage"),
            )
        elif "candidates" in data:
            candidates = data.get("candidates") or [{}]
            fields.update(
                finish_reason=candidates[0].get("finishReason"),
                content_chars=sum(len(part.get("text", "")) for part in candidates[0].get("content", {}).get("parts", []) if not part.get("thought")),
                usage=data.get("usageMetadata"),
            )
        elif "content" in data:
            fields.update(stop_reason=data.get("stop_reason"), content_chars=sum(len(part.get("text", "")) for part in data.get("content", [])), usage=data.get("usage"))
        else:
            fields["response_top_level_fields"] = sorted(data)[:15]
        emit(name, **fields)
        return data if response.is_success else None
    except Exception as error:
        emit(name, exception=type(error).__name__, seconds=round(time.monotonic() - start, 2))
        return None


def jsonl(name: str, *, prior: bool = False) -> list[dict]:
    text = subprocess.check_output(["git", "show", f"eaccda984e04b71b9e5f1c19b443adbfbe4ab725:data/{name}.jsonl"], text=True) if prior else (ROOT / "data" / f"{name}.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def replay_report(*, compact: bool = False) -> None:
    """Rebuild stored portions of the failed request; original analyses were not retained."""
    date = "2026-10-23"
    events = [row for row in jsonl("source_events") if row.get("run_date") == date]
    opened = [row for row in jsonl("prediction_log", prior=True) if row.get("status") == "open"]
    current = jsonl("prediction_log")
    companies = [row for row in jsonl("company_mentions") if row.get("run_date") == date]
    topics = [row for row in jsonl("topic_trends") if row.get("run_date") == date]
    reports = sorted((ROOT / "reports/daily").glob("*.md"))
    payload = {
        "run_date": date,
        "normalized_events": sorted(events, key=lambda row: row.get("importance_score", 0), reverse=True)[:30],
        "topic_summaries": {row["topic_id"]: row for row in topics},
        "company_analyses": {row["company"]: row for row in companies if row.get("significance") in ("high", "medium")},
        "paper_analyses": [row for row in jsonl("paper_mentions") if row.get("run_date") == date][:8],
        "github_project_analyses": [row for row in jsonl("project_mentions") if row.get("run_date") == date and row.get("verdict") == "Watch"][:3],
        "github_project_analysis_status": {}, "social_signal_analyses": {}, "macro_impact_analyses": {},
        "open_predictions": opened,
        "prediction_updates": [update for row in current for update in row.get("updates", []) if update.get("update_date") == date],
        "new_predictions": [row for row in current if row.get("created_date") == date],
        "previous_reports_summary": [{"report_date": p.stem, "type": "daily", "excerpt": p.read_text()[:800]} for p in reports if p.stem < date][-7:],
        "history_context": {
            "weekly_reviews": [{"week": p.stem, "excerpt": p.read_text()[:1500]} for p in sorted((ROOT / "reports/weekly").glob("*.md"))][-4:],
            "monthly_reviews": [{"month": p.stem, "excerpt": p.read_text()[:2000]} for p in sorted((ROOT / "reports/monthly").glob("*.md"))][-3:],
            "topic_trend_30d": [row for row in jsonl("topic_trends", prior=True)][-90:],
            "company_mentions_90d": [row for row in jsonl("company_mentions", prior=True)][-120:],
        },
        "market_signal_analyses": [], "source_warnings": [], "confidence_flags": [],
        "user_preferences": yaml.safe_load((ROOT / "data/user_preferences.yml").read_text()), "signal_level": "high",
    }
    if compact:
        selected = sorted(opened, key=lambda row: row.get("created_date", ""), reverse=True)[:20]
        fields = ("prediction_id", "prediction", "probability", "horizon_date", "confidence", "companies", "topic_tags")
        payload["open_predictions"] = [{key: row[key] for key in fields if key in row} for row in selected]
    system = (ROOT / "prompts/daily_brief.md").read_text()
    user = json.dumps(payload, ensure_ascii=False)
    emit("report.reconstruction", exact_original_request=False, compact_predictions=compact, original_events=len(events), original_open_predictions=len(opened), selected_open_predictions=len(payload["open_predictions"]), open_prediction_chars=len(json.dumps(payload["open_predictions"], ensure_ascii=False)), request_chars=len(system) + len(user), missing_original_full_analyses=True)
    key = KEYS["DEEPSEEK_API_KEY"]
    if key:
        headers = {"Authorization": f"Bearer {key}"}
        request = {"model": CONFIG["ai_providers"]["deepseek"]["default"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": CONFIG["model"]["max_tokens_daily"]}
        data = probe("deepseek.report.default_thinking", "POST", "https://api.deepseek.com/chat/completions", headers, request, timeout=240)
        if data:
            choice = (data.get("choices") or [{}])[0]
            text = choice.get("message", {}).get("content") or ""
            emit("deepseek.report.production_validation", accepted_initial_response=bool(text.strip()) and choice.get("finish_reason") in ("stop", "length"), continuation_needed=choice.get("finish_reason") == "length")
            if choice.get("finish_reason") == "length" and text.strip():
                continuation = {**request, "messages": [*request["messages"], {"role": "assistant", "content": text}, {"role": "user", "content": "上一轮回复因输出上限被截断。请从停止位置继续，不重复已输出内容，不要添加引言或元说明。"}]}
                probe("deepseek.report.continuation", "POST", "https://api.deepseek.com/chat/completions", headers, continuation, timeout=240)
            if not text.strip() or choice.get("finish_reason") == "length":
                probe("deepseek.report.disabled_thinking", "POST", "https://api.deepseek.com/chat/completions", headers, {**request, "thinking": {"type": "disabled"}}, timeout=240)
    key = KEYS["GEMINI_API_KEY"]
    if key:
        model = CONFIG["ai_providers"]["gemini"]["default"]
        probe("gemini.report_input", "POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": key}, {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": {"maxOutputTokens": CONFIG["model"]["max_tokens_daily"] if compact else 128}}, timeout=240)


def main() -> None:
    emit("credentials", present={name: bool(value) for name, value in KEYS.items()})
    message = [{"role": "user", "content": "Reply with only the word OK."}]
    key = KEYS["DEEPSEEK_API_KEY"]
    if key:
        headers = {"Authorization": f"Bearer {key}"}
        probe("deepseek.balance", "GET", "https://api.deepseek.com/user/balance", headers)
        probe("deepseek.models", "GET", "https://api.deepseek.com/models", headers)
        model = CONFIG["ai_providers"]["deepseek"]["default"]
        original = {"model": model, "messages": message, "max_tokens": 128}
        probe("deepseek.text.default_thinking", "POST", "https://api.deepseek.com/chat/completions", headers, original)
        probe("deepseek.text.disabled_thinking", "POST", "https://api.deepseek.com/chat/completions", headers, {**original, "thinking": {"type": "disabled"}})
        probe("deepseek.text.report_budget", "POST", "https://api.deepseek.com/chat/completions", headers, {**original, "max_tokens": CONFIG["model"]["max_tokens_daily"]})
    key = KEYS["ANTHROPIC_API_KEY"]
    if key:
        probe("claude.text", "POST", "https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}, {"model": CONFIG["ai_providers"]["claude"]["default"], "messages": message, "max_tokens": 128})
    key = KEYS["OPENAI_API_KEY"]
    if key:
        probe("openai.text", "POST", "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}, {"model": CONFIG["ai_providers"]["openai"]["default"], "messages": message, "max_completion_tokens": 128})
    key = KEYS["GEMINI_API_KEY"]
    if key:
        model = CONFIG["ai_providers"]["gemini"]["default"]
        probe("gemini.text", "POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": key}, {"contents": [{"role": "user", "parts": [{"text": message[0]["content"]}]}], "generationConfig": {"maxOutputTokens": 128}})


if __name__ == "__main__":
    if "--compact-report" in sys.argv:
        replay_report(compact=True)
    elif "--replay-report" in sys.argv:
        replay_report()
    else:
        main()
