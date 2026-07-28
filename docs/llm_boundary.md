# Provider-Neutral LLM Boundary

Business modules select a capability and neutral model role; they do not select
an SDK or provider-native model. Production adapters live in
`src/tech_daily/llm/providers/`:

- `anthropic.py` translates requests for Claude.
- `openai_compatible.py` translates requests for DeepSeek and OpenAI.
- `gemini.py` translates requests for Gemini through the maintained Google Gen
  AI SDK.
- `base.py` defines the adapter protocol.

Business modules must not import provider SDKs directly. Provider SDK imports,
request dialects, native tools, response parsing, and exception translation
belong in these adapters. The neutral contracts and router live in
`src/tech_daily/llm/contracts.py` and `src/tech_daily/llm/router.py`.
Claude-named functions and classes remain only as deprecated compatibility
wrappers.

## Configuration And Roles

`config.yml` defines provider order under `ai_providers.order`. The default is
DeepSeek, Claude, OpenAI, then Gemini. Each provider maps the neutral roles
`fast`, `default`, and `deep` to provider-native model IDs. Business code uses
`ModelRole`; legacy model-name arguments are converted at the compatibility
boundary.

A single configured provider can execute text generation, structured output,
web search, and continuation with one provider key, subject to model, account,
region, endpoint, and tool availability. Additional configured keys provide
fallback resilience.

## Capabilities And Fallback

`ProviderRouter` applies the same provider priority to:

- text generation;
- structured generation and schema validation;
- provider-native web search;
- continuation of truncated text.

Fallback is allowed for exactly seven normalized categories:

- `MissingCredential`;
- `AuthenticationFailure`;
- `RateLimited`;
- `QuotaExceeded`;
- `NetworkFailure`;
- `ProviderUnavailable`;
- `InvalidProviderResponse`.

Programming errors such as `TypeError` and `AttributeError`, malformed project
configuration, unknown providers, and unsupported internal capabilities
propagate immediately. Structured JSON is parsed and validated inside the
routing attempt. Empty output, refusal or safety termination without a valid
result, abnormal finish reasons, malformed structured output, schema mismatch,
and malformed search results become `InvalidProviderResponse`.

Continuation stays with the provider that produced the partial response. If an
eligible continuation failure occurs, routing restarts the complete logical
request on the next provider rather than appending another model's output.

## Safe Routing Telemetry

Attempt telemetry contains only capability, approved provider name, resolved
model when safe, attempt number, outcome, normalized error category, and
fallback reason. Generated content and credentials are never logged. Prompts
are never logged either.

For example:

```text
capability=search_web provider=deepseek attempt=1 outcome=failure error_category=rate_limited
capability=search_web provider=claude attempt=2 outcome=success error_category=None
```

## Business-Code Entry Points

Text and structured analysis should use `PromptRunner` or
`ProviderLLMClient`. Collection code should depend on `WebSearchClient`;
production uses `ProviderWebSearchClient`.

```python
from prompt_runner import PromptRunner

result = PromptRunner().run_text(
    prompt_path="daily_brief.md",
    payload=payload,
    max_tokens=8000,
)
```

```python
from web_search_client import WebSearchClient

def collect(web_search_client: WebSearchClient) -> list[RawEvent]:
    results = web_search_client.search(prompt, max_uses=3)
```

Do not call a legacy provider-named function from business modules. The guard
test `tests/test_migrated_analyzers_no_direct_claude.py` enforces the production
boundary.

## Provider Search Prerequisites

- DeepSeek uses its supported Anthropic-compatible web-search endpoint.
- Claude uses the Anthropic web-search tool.
- OpenAI uses the Responses API web-search tool.
- Gemini uses Google Search grounding through `google-genai`.

The selected provider/model must support its listed tool. Provider-side
entitlement, billing, regional, or model restrictions can still make a
capability unavailable and trigger an eligible fallback.

## Schema Semantics

LLM schemas should validate both shape and stable domain semantics where
downstream code relies on them. Probabilities must be in `[0.0, 1.0]`;
confidence/risk/status-like fields should use explicit literals only after
existing fixtures prove the allowed values.
