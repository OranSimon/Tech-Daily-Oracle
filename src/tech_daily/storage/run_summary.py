"""Persistence for optional local run summaries."""

from __future__ import annotations

from tech_daily.pipeline.run_summary import RunSummary, run_summary_row
from tech_daily.storage._shared import storage_context as resolve_storage_context
from tech_daily.storage.context import StorageContext
from tech_daily.storage.io import append_jsonl_rows_safely


def save_run_summary(summary: RunSummary, *, storage_context: StorageContext | None = None) -> None:
    context = resolve_storage_context(storage_context)
    append_jsonl_rows_safely(
        context.run_summary_log_path(),
        [run_summary_row(summary)],
        ensure_ascii=False,
    )
