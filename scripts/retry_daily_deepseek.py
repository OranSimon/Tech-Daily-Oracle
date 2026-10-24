"""Retry the archived 2026-10-23 daily corpus using DeepSeek alone."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
import openai
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "retry-output"
OUT.mkdir(exist_ok=True)
LOCK = threading.Lock()
PHASE = "setup"
HISTORY_REF = "eaccda984e04b71b9e5f1c19b443adbfbe4ab725"
RUN_DATE = "2026-10-23"


def record(**fields: object) -> None:
    row = {"time": datetime.now(UTC).isoformat(), "phase": PHASE, **fields}
    line = json.dumps(row, ensure_ascii=False)
    with LOCK:
        with (OUT / "deepseek-attempts.jsonl").open("a") as handle:
            handle.write(line + "\n")
        print("[DeepSeekTrace] " + line, flush=True)


def inspect_response(response: httpx.Response) -> None:
    """Record response structure and usage without generated content or credentials."""
    try:
        response.read()
        data = response.json()
        fields = {"http_status": response.status_code}
        if response.is_error:
            error = data.get("error", {})
            fields["error"] = {name: error[name] for name in ("code", "type") if name in error}
        else:
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message", {})
            fields.update(model=data.get("model"), finish_reason=choice.get("finish_reason"),
                          content_chars=len(message.get("content") or ""),
                          reasoning_chars=len(message.get("reasoning_content") or ""), usage=data.get("usage"))
        record(**fields)
    except Exception as error:
        record(trace_error_type=type(error).__name__)


def main() -> None:
    global PHASE
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is required")
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ.pop(name, None)
    source_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_rows = [json.loads(line) for line in (ROOT / "data/source_events.jsonl").open() if line.strip()]
    source_rows = [row for row in source_rows if row.get("run_date") == RUN_DATE]
    if len(source_rows) != 395:
        raise RuntimeError(f"Expected the 395 archived events, found {len(source_rows)}")
    # The runner checkout is disposable. Restore history from before the failed run
    # so its existing predictions and later review cannot leak into the retry.
    subprocess.run(["git", "restore", "--source=" + HISTORY_REF, "--", "data", "reports"], check=True)
    cfg_path = ROOT / "config.yml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["ai_providers"]["order"] = ["deepseek"]
    cfg["notion"]["enabled"] = False
    cfg["output"]["publish_notion"] = False
    cfg["output"]["push_github"] = False
    cfg["market_signal"]["live_data"] = False
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))

    original_client = openai.OpenAI

    def traced_client(*args, **kwargs):
        if str(kwargs.get("base_url", "")).rstrip("/") != "https://api.deepseek.com":
            raise RuntimeError("This retry only permits DeepSeek LLM requests")
        kwargs["http_client"] = httpx.Client(timeout=600, event_hooks={"response": [inspect_response]})
        return original_client(*args, **kwargs)

    openai.OpenAI = traced_client
    from state import NormalizedEvent, TechDailyState, new_run_id
    import analyze_github_projects
    import tech_daily.pipeline.daily as daily
    from tech_daily.pipeline.policy import StepId
    from tech_daily.runtime.run_context import AppConfig, RunContext
    from tech_daily.runtime.run_logging import RunLogger

    # Archived normalized events retain the repository metadata used at collection.
    # Do not replace those measurements with the repository's present-day values.
    async def archived_repo_details(*_args, **_kwargs):
        return {}

    analyze_github_projects._fetch_repo_details = archived_repo_details
    event_fields = {item.name for item in dataclasses.fields(NormalizedEvent)}
    events = [NormalizedEvent(**{key: value for key, value in row.items() if key in event_fields}) for row in source_rows]
    context = RunContext.from_config(run_date=RUN_DATE, run_id=new_run_id(), root_dir=ROOT, config=cfg)
    state = TechDailyState(run_id=context.run_id, run_date=RUN_DATE, time_window=context.time_window)
    state.normalized_events = events
    state.source_warnings.append("本次重生成使用2026-10-23归档的395条事件；未重新采集新闻、实时行情或实时趋势。")
    state.confidence_flags.append("原运行的实时行情与完整趋势快照未保存，本次不补入后续日期数据。")
    runtime = daily.DailyPipelineRuntime(state=state, context=context, cfg=cfg, app_config=AppConfig(cfg),
                                         logger=RunLogger(context), root_dir=str(ROOT))
    original_definitions = daily.build_daily_step_definitions
    skipped = {StepId.COLLECT_SOURCES, StepId.COLLECT_MARKET_DATA, StepId.COLLECT_TRENDING_SNAPSHOT,
               StepId.NORMALIZE_EVENTS, StepId.PUBLISH_TO_NOTION}
    daily.build_daily_step_definitions = lambda rt: [definition for definition in original_definitions(rt)
                                                     if definition.step_id not in skipped]

    def heading(name: str) -> None:
        global PHASE
        PHASE = name
        print("\nSTEP: " + name, flush=True)

    record(event="retry_start", provider_order=["deepseek"], archived_events=len(events), history_ref=HISTORY_REF)
    result = daily.execute_daily_pipeline(runtime, step_printer=heading)
    report = state.final_report
    success = len(report) > 2000 and "[Report generation failed:" not in report
    (OUT / f"{RUN_DATE}.md").write_text(report, encoding="utf-8")
    manifest = {"run_date": RUN_DATE, "run_id": context.run_id, "success": success,
                "provider_order": ["deepseek"], "archived_events": len(events),
                "history_ref": HISTORY_REF, "runner_ref": source_ref, "report_chars": len(report),
                "report_headings": [line for line in report.splitlines() if line.startswith("## ")],
                "source_warnings": state.source_warnings, "confidence_flags": state.confidence_flags,
                "steps": [{"name": step.name, "success": step.success, "error": step.error}
                          for step in result.step_results]}
    (OUT / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    record(event="retry_result", success=success, report_chars=len(report), headings=len(manifest["report_headings"]))
    if not success:
        raise RuntimeError("DeepSeek-only retry did not produce a valid daily report; inspect trace artifact")


if __name__ == "__main__":
    main()
