# LLM and Web Search Boundary

Business modules must not import or call `claude_client` directly. The legacy client stays available only behind adapter files so tests can use fakes and production behavior remains centralized.

Allowed direct Claude call sites:

- `scripts/claude_client.py`
- `scripts/llm_client.py`
- `scripts/web_search_client.py`

## JSON Analysis

Analyzer and prediction modules should use `PromptRunner.run_json(...)` with a Pydantic schema from `scripts/llm_schemas.py`.

Allowed:

```python
from prompt_runner import PromptRunner
from llm_schemas import TopicSummaryResponse

result = PromptRunner().run_json(
    prompt_path="topic_summary.md",
    payload=payload,
    schema=TopicSummaryResponse,
)
```

Forbidden:

```python
from claude_client import call_claude_json

result = call_claude_json(system, user)
```

## Markdown and Text Generation

Daily, weekly, monthly, and other Markdown/text generation should use `PromptRunner.run_text(...)`.

Allowed:

```python
from prompt_runner import PromptRunner

markdown = PromptRunner().run_text(
    prompt_path="daily_brief.md",
    payload=payload,
    max_tokens=8000,
)
```

Forbidden:

```python
from claude_client import call_claude

markdown = call_claude(system=system, user=user)
```

## Web Search Collection

Collection code that needs web search should depend on `WebSearchClient`. Production uses `ClaudeWebSearchClient`; tests should pass a fake client.

Allowed:

```python
from web_search_client import WebSearchClient

def collect(web_search_client: WebSearchClient) -> list[RawEvent]:
    results = web_search_client.search(prompt, max_uses=3)
```

Forbidden:

```python
from claude_client import call_claude_web_search

results = call_claude_web_search(prompt, max_uses=3)
```

The guard test `tests/test_migrated_analyzers_no_direct_claude.py` scans production scripts and fails if direct Claude usage appears outside the explicit boundary allowlist.
