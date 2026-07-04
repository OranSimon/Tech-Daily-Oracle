from __future__ import annotations

import claude_client
import pytest


def test_call_claude_json_parses_plain_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_client, "call_claude", lambda *args, **kwargs: '{"ok": true}')

    assert claude_client.call_claude_json("system", "user") == {"ok": True}


def test_call_claude_json_parses_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        claude_client,
        "call_claude",
        lambda *args, **kwargs: '```json\n[{"id": "one"}]\n```',
    )

    assert claude_client.call_claude_json("system", "user") == [{"id": "one"}]


def test_call_claude_json_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_client, "call_claude", lambda *args, **kwargs: "not json")

    with pytest.raises(ValueError):
        claude_client.call_claude_json("system", "user")
