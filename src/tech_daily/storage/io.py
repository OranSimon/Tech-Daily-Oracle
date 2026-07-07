"""Low-level storage I/O helpers."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TextIO


def atomic_replace(temp_path: str | os.PathLike[str], target_path: str | os.PathLike[str]) -> None:
    """Atomically replace target_path with temp_path."""
    os.replace(temp_path, target_path)


def _atomic_write(path: str | os.PathLike[str], writer: Any, *, encoding: str = "utf-8") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        atomic_replace(temp_path, target)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def atomic_write_text(path: str | os.PathLike[str], content: str, *, encoding: str = "utf-8") -> None:
    """Write text through a same-directory temp file, then atomically replace."""

    def write_text(handle: TextIO) -> None:
        handle.write(content)

    _atomic_write(path, write_text, encoding=encoding)


def atomic_write_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    encoding: str = "utf-8",
) -> None:
    """Write JSON through a same-directory temp file, then atomically replace."""

    def write_json(handle: TextIO) -> None:
        json.dump(data, handle, ensure_ascii=ensure_ascii, indent=indent)

    _atomic_write(path, write_json, encoding=encoding)


def atomic_write_jsonl(
    path: str | os.PathLike[str],
    rows: Iterable[dict[str, Any]],
    *,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
) -> None:
    """Write JSONL rows through a same-directory temp file, then atomically replace."""

    def write_jsonl(handle: TextIO) -> None:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=ensure_ascii) + "\n")

    _atomic_write(path, write_jsonl, encoding=encoding)


def append_jsonl_rows_safely(
    path: str | os.PathLike[str],
    rows: Iterable[dict[str, Any]],
    *,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
) -> None:
    """Append JSONL rows with explicit flush/fsync semantics.

    This preserves append-only artifact formats while making the write policy
    explicit for callers that should not rewrite the whole file.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized_rows = [json.dumps(row, ensure_ascii=ensure_ascii) + "\n" for row in rows]
    with open(target, "a", encoding=encoding) as handle:
        for serialized_row in serialized_rows:
            handle.write(serialized_row)
        handle.flush()
        os.fsync(handle.fileno())


def quarantine_jsonl_row(
    artifact_path: str | os.PathLike[str],
    *,
    line_number: int,
    raw_value: str,
    message: str,
    quarantine_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Record a malformed persisted JSONL row in a local quarantine artifact."""
    artifact = Path(artifact_path)
    root = Path(quarantine_root) if quarantine_root is not None else artifact.parent / "quarantine"
    quarantine_path = root / f"{artifact.stem}.quarantine.jsonl"
    append_jsonl_rows_safely(
        quarantine_path,
        [
            {
                "artifact": str(artifact),
                "line_number": line_number,
                "message": message,
                "raw_value": raw_value,
            }
        ],
        ensure_ascii=False,
    )
    return quarantine_path
