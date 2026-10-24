"""Bounded API probes. Never print credentials, generated text, or balance amounts."""

from __future__ import annotations

import json
import os
import re
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


def probe(name: str, method: str, url: str, headers: dict, payload: dict | None = None) -> dict | None:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as client:
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
    main()
