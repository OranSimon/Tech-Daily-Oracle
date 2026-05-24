"""Notion Publisher — convert the daily Markdown report to Notion blocks and create a page."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


# ---------------------------------------------------------------------------
# Markdown → Notion block converter
# ---------------------------------------------------------------------------

def _rich_text(text: str) -> list[dict]:
    """Parse inline markdown (bold, italic, code) into Notion rich_text segments."""
    pattern = r"(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)"
    segments: list[dict] = []
    for part in re.split(pattern, text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            content, annotations = part[2:-2], {"bold": True}
        elif part.startswith("*") and part.endswith("*"):
            content, annotations = part[1:-1], {"italic": True}
        elif part.startswith("`") and part.endswith("`"):
            content, annotations = part[1:-1], {"code": True}
        else:
            content, annotations = part, {}
        # Notion max 2000 chars per segment
        while content:
            chunk, content = content[:2000], content[2000:]
            seg: dict[str, Any] = {"type": "text", "text": {"content": chunk}}
            if annotations:
                seg["annotations"] = annotations
            segments.append(seg)
    return segments or [{"type": "text", "text": {"content": ""}}]


def _heading(level: int, text: str) -> dict:
    htype = f"heading_{level}"
    return {"object": "block", "type": htype,
            htype: {"rich_text": _rich_text(text.strip())}}


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich_text(text)}}


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^\|[-| :]+\|$", stripped))


def md_to_notion_blocks(md: str) -> list[dict]:
    """Convert a Markdown string to a list of Notion block objects."""
    blocks: list[dict] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1

        if not line:
            continue

        if line.startswith("# "):
            blocks.append(_heading(1, line[2:]))
        elif line.startswith("## "):
            blocks.append(_heading(2, line[3:]))
        elif line.startswith("### "):
            blocks.append(_heading(3, line[4:]))
        elif line.startswith("#### "):
            # No heading_4 in Notion — render as bold paragraph
            blocks.append(_paragraph(f"**{line[5:]}**"))
        elif line in ("---", "***", "___"):
            blocks.append(_divider())
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(_bullet(line[2:]))
        elif line.startswith("  - ") or line.startswith("  * "):
            # Indented bullet — Notion doesn't nest easily, just add as bullet
            blocks.append(_bullet(line[4:]))
        elif line.startswith("|") and "|" in line[1:]:
            if _is_table_separator(line):
                pass  # skip separator rows
            else:
                # Render table rows as paragraph text
                cells = [c.strip() for c in line.strip("|").split("|")]
                blocks.append(_paragraph(" | ".join(cells)))
        elif line.startswith("```"):
            # Code block — collect until closing ```
            lang = line[3:].strip()
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_content = "\n".join(code_lines)
            # Notion code blocks max 2000 chars
            for chunk_start in range(0, max(len(code_content), 1), 1900):
                chunk = code_content[chunk_start:chunk_start + 1900]
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        "language": lang or "plain text",
                    },
                })
        elif line.startswith(">"):
            blocks.append(_paragraph(line[2:] if line.startswith("> ") else line[1:]))
        else:
            blocks.append(_paragraph(line))

    return blocks


# ---------------------------------------------------------------------------
# Notion API calls
# ---------------------------------------------------------------------------

def _notion_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _create_page(api_key: str, database_id: str, title: str,
                  run_date: str, blocks: list[dict]) -> str:
    headers = _notion_headers(api_key)
    title_property_name = os.environ.get("NOTION_TITLE_PROPERTY", "Name")
    properties: dict[str, Any] = {
        title_property_name: {
            "title": [{"text": {"content": title[:2000]}}]
        }
    }
    # Add a Date property if the database likely has one
    date_property_name = os.environ.get("NOTION_DATE_PROPERTY", "Date")
    if date_property_name:
        properties[date_property_name] = {"date": {"start": run_date}}

    body: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": blocks[:100],
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{NOTION_BASE}/pages", json=body, headers=headers)
        if resp.status_code == 400:
            # Date property may not exist — retry without it
            body["properties"] = {title_property_name: body["properties"][title_property_name]}
            resp = client.post(f"{NOTION_BASE}/pages", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        page_id = data["id"]
        page_url = data.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")

        # Append remaining blocks in batches of 100
        remaining = blocks[100:]
        while remaining:
            batch, remaining = remaining[:100], remaining[100:]
            patch_resp = client.patch(
                f"{NOTION_BASE}/blocks/{page_id}/children",
                json={"children": batch},
                headers=headers,
            )
            patch_resp.raise_for_status()

    return page_url


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def publish_to_notion(
    run_date: str,
    content: str,
    cfg: dict[str, Any],
    title: str | None = None,
) -> str | None:
    """Publish a Markdown report to a Notion database page.

    Args:
        run_date: ISO date string (YYYY-MM-DD) used for the Notion Date property.
        content:  Markdown content to convert and publish.
        cfg:      Loaded config.yml dict.
        title:    Page title override. Defaults to "Tech Daily Brief — {run_date}".

    Returns the Notion page URL on success, None on failure.
    Reads credentials from environment variables:
      NOTION_API_KEY, NOTION_DATABASE_ID (override config values)
    """
    api_key = os.environ.get("NOTION_API_KEY") or cfg.get("notion", {}).get("api_key", "")
    database_id = (
        os.environ.get("NOTION_DATABASE_ID")
        or cfg.get("notion", {}).get("database_id", "")
    )

    if not api_key or not database_id:
        print("  [Notion] Missing NOTION_API_KEY or NOTION_DATABASE_ID — skipping")
        return None

    if title is None:
        title = f"Tech Daily Brief — {run_date}"
    blocks = md_to_notion_blocks(content)
    print(f"  [Notion] Creating page '{title}' ({len(blocks)} blocks)...")
    url = _create_page(api_key, database_id, title, run_date, blocks)
    return url
