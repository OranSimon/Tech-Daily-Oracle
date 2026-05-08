"""Shared Anthropic client with prompt caching support."""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

_client: anthropic.Anthropic | None = None

DEFAULT_MODEL = "claude-sonnet-4-6"


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def call_claude(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    cache_system: bool = True,
) -> str:
    """Call Claude with optional prompt caching on the system prompt."""
    client = get_client()

    system_content: list[dict[str, Any]] = [{"type": "text", "text": system}]
    if cache_system:
        system_content[0]["cache_control"] = {"type": "ephemeral"}

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_content,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def call_claude_web_search(
    prompt: str,
    max_uses: int = 5,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> list[dict]:
    """Call Claude with the built-in web_search tool. Returns a list of result dicts.

    The prompt should ask Claude to return a JSON array of items:
      [{"title": ..., "url": ..., "source": ..., "summary": ..., "published_at": ...}]
    """
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
        messages=[{"role": "user", "content": prompt}],
    )
    # Extract the text block that contains Claude's JSON output
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break
    if not text:
        return []
    # Strip markdown fences and parse JSON
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


def call_claude_json(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    cache_system: bool = True,
) -> Any:
    """Call Claude and parse JSON response. Returns parsed object or raises."""
    raw = call_claude(system, user, model, max_tokens, cache_system)
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(text)
