"""AI client — DeepSeek primary with automatic Claude / OpenAI / Gemini fallback.

Provider order defaults to deepseek → claude → openai → gemini.
Override in config.yml under ai_providers.order.
Each provider is tried in turn; the first successful response is returned.
web_search is Claude-only (Anthropic built-in tool) and never falls back.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Singletons (lazy-initialised)
# ---------------------------------------------------------------------------

_anthropic_client: anthropic.Anthropic | None = None
_deepseek_client: Any = None     # openai.OpenAI with DeepSeek base_url — imported on demand
_openai_client: Any = None       # openai.OpenAI — imported on demand
_gemini_configured: bool = False  # google.generativeai — configured on demand

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_PROVIDER_ORDER = ["deepseek", "claude", "openai", "gemini"]

# Role → model name defaults for each provider
_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "deepseek": {
        "default": "deepseek-v4-flash",
        "fast":    "deepseek-v4-flash",
        "deep":    "deepseek-v4-pro",
    },
    "claude": {
        "default": "claude-sonnet-4-6",
        "fast":    "claude-haiku-4-5-20251001",
        "deep":    "claude-opus-4-7",
    },
    "openai": {
        "default": "gpt-4o",
        "fast":    "gpt-4o-mini",
        "deep":    "o1",
    },
    "gemini": {
        "default": "gemini-2.0-flash",
        "fast":    "gemini-2.0-flash-lite",
        "deep":    "gemini-2.5-pro-preview-06-05",
    },
}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_provider_config() -> tuple[list[str], dict[str, dict[str, str]]]:
    """Return (provider_order, models_map) from config.yml, falling back to defaults."""
    try:
        import yaml
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "config.yml")) as f:
            cfg = yaml.safe_load(f)
        ai_cfg = cfg.get("ai_providers", {})
        order: list[str] = ai_cfg.get("order", DEFAULT_PROVIDER_ORDER)
        models: dict[str, dict[str, str]] = {}
        for provider in ("deepseek", "claude", "openai", "gemini"):
            models[provider] = {**_DEFAULT_MODELS[provider], **ai_cfg.get(provider, {})}
        # Backward-compatible alias for older config/tests that still use "gpt".
        models["gpt"] = {**models["openai"], **ai_cfg.get("gpt", {})}
        return order, models
    except Exception:
        models = dict(_DEFAULT_MODELS)
        models["gpt"] = models["openai"]
        return DEFAULT_PROVIDER_ORDER, models


# ---------------------------------------------------------------------------
# Per-provider callers
# ---------------------------------------------------------------------------

def get_client() -> anthropic.Anthropic:
    """Return (and lazily create) the shared Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _anthropic_client


def _call_claude_direct(
    system: str, user: str, model: str, max_tokens: int, cache_system: bool
) -> tuple[str, str]:
    """Returns (text, stop_reason). stop_reason: 'end_turn' | 'max_tokens' | 'other'."""
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
    # Anthropic stop_reasons: end_turn, max_tokens, stop_sequence, tool_use
    raw_reason = getattr(response, "stop_reason", None) or "end_turn"
    normalized = "max_tokens" if raw_reason == "max_tokens" else "end_turn"
    return response.content[0].text, normalized


def _call_openai_compatible_direct(client: Any, system: str, user: str, model: str, max_tokens: int) -> tuple[str, str]:
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    finish_reason = getattr(response.choices[0], "finish_reason", "stop")
    normalized = "max_tokens" if finish_reason == "length" else "end_turn"
    return response.choices[0].message.content or "", normalized


def _call_deepseek_direct(system: str, user: str, model: str, max_tokens: int) -> tuple[str, str]:
    global _deepseek_client
    if _deepseek_client is None:
        import openai  # optional dependency; DeepSeek exposes an OpenAI-compatible API
        _deepseek_client = openai.OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    return _call_openai_compatible_direct(_deepseek_client, system, user, model, max_tokens)


def _call_gpt_direct(system: str, user: str, model: str, max_tokens: int) -> tuple[str, str]:
    return _call_openai_direct(system, user, model, max_tokens)


def _call_openai_direct(system: str, user: str, model: str, max_tokens: int) -> tuple[str, str]:
    global _openai_client
    if _openai_client is None:
        import openai  # optional dependency
        _openai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _call_openai_compatible_direct(_openai_client, system, user, model, max_tokens)


def _call_gemini_direct(system: str, user: str, model: str, max_tokens: int) -> tuple[str, str]:
    global _gemini_configured
    import google.generativeai as genai  # optional dependency
    if not _gemini_configured:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        genai.configure(api_key=api_key)
        _gemini_configured = True
    gm = genai.GenerativeModel(model, system_instruction=system)
    response = gm.generate_content(
        user,
        generation_config={"max_output_tokens": max_tokens},
    )
    # Gemini finish_reasons: STOP, MAX_TOKENS, SAFETY, RECITATION, OTHER
    normalized = "end_turn"
    try:
        fr = response.candidates[0].finish_reason
        # finish_reason can be an enum or an int — check string form
        if "MAX_TOKENS" in str(fr).upper():
            normalized = "max_tokens"
    except (AttributeError, IndexError):
        pass
    return response.text, normalized


def _continue_claude_response(
    system: str, user: str, partial: str, model: str, max_tokens: int, cache_system: bool
) -> tuple[str, str]:
    """Ask Claude to continue a truncated response. Returns (new_text, stop_reason).

    Uses the standard assistant-message-prefill technique: append the partial response
    as an assistant turn, then ask the user to continue. Claude resumes seamlessly.
    """
    client = get_client()
    system_content: list[dict[str, Any]] = [{"type": "text", "text": system}]
    if cache_system:
        system_content[0]["cache_control"] = {"type": "ephemeral"}
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_content,
        messages=[
            {"role": "user", "content": user},
            {"role": "assistant", "content": partial},
            {"role": "user", "content": (
                "上一轮回复因 max_tokens 限制被截断。请从你上次停下的位置继续，"
                "不要重复任何已经输出的内容，不要添加任何引言或元说明。"
                "直接从被截断的位置继续写（可能是句子中间），完成剩余的报告。"
            )},
        ],
    )
    raw_reason = getattr(response, "stop_reason", None) or "end_turn"
    normalized = "max_tokens" if raw_reason == "max_tokens" else "end_turn"
    return response.content[0].text, normalized


# ---------------------------------------------------------------------------
# Model resolution — map a Claude model name to the equivalent role for
# another provider (fast / default / deep), then return that provider's model.
# ---------------------------------------------------------------------------

def _resolve_model(
    provider: str,
    model_hint: str,
    models: dict[str, dict[str, str]],
) -> str:
    """Return the best model name for *provider* given a Claude-style model hint."""
    pm = models.get(provider, _DEFAULT_MODELS.get(provider, {}))
    # If the hint already looks native to this provider, use it directly
    native_prefixes = {
        "deepseek": "deepseek",
        "claude": "claude",
        "gpt": ("gpt", "o1", "o3"),
        "openai": ("gpt", "o1", "o3"),
        "gemini": "gemini",
    }
    prefix = native_prefixes.get(provider, "")
    if isinstance(prefix, str) and model_hint.startswith(prefix):
        return model_hint
    if isinstance(prefix, tuple) and any(model_hint.startswith(p) for p in prefix):
        return model_hint
    # Infer role from hint
    claude_models = models.get("claude", _DEFAULT_MODELS["claude"])
    if model_hint == claude_models.get("fast") or any(k in model_hint for k in ("haiku", "mini", "lite", "flash-lite")):
        return pm.get("fast", pm.get("default", model_hint))
    if model_hint == claude_models.get("deep") or any(k in model_hint for k in ("opus", "o1", "pro")):
        return pm.get("deep", pm.get("default", model_hint))
    return pm.get("default", model_hint)


# ---------------------------------------------------------------------------
# Fallback orchestrator
# ---------------------------------------------------------------------------

def _call_with_fallback(
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    cache_system: bool,
) -> tuple[str, str, str]:
    """Try each provider in config order. Returns (response_text, provider_used, stop_reason).

    stop_reason is normalized to 'end_turn' or 'max_tokens' across all providers,
    so the caller can detect truncation and continue regardless of which provider answered.
    """
    order, models = _load_provider_config()
    last_exc: Exception | None = None

    for provider in order:
        resolved = _resolve_model(provider, model, models)
        try:
            if provider == "deepseek":
                if not os.environ.get("DEEPSEEK_API_KEY"):
                    raise RuntimeError("DEEPSEEK_API_KEY not set")
                text, stop_reason = _call_deepseek_direct(system, user, resolved, max_tokens)
            elif provider == "claude":
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    raise RuntimeError("ANTHROPIC_API_KEY not set")
                text, stop_reason = _call_claude_direct(system, user, resolved, max_tokens, cache_system)
            elif provider in {"openai", "gpt"}:
                if not os.environ.get("OPENAI_API_KEY"):
                    raise RuntimeError("OPENAI_API_KEY not set")
                text, stop_reason = _call_openai_direct(system, user, resolved, max_tokens)
            elif provider == "gemini":
                if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
                    raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")
                text, stop_reason = _call_gemini_direct(system, user, resolved, max_tokens)
            else:
                print(f"  [AI] Unknown provider '{provider}' — skipping")
                continue

            if provider != order[0]:
                print(f"  [AI] Using fallback provider: {provider} ({resolved})")
            return text, provider, stop_reason

        except Exception as e:
            print(f"  [AI] {provider} ({resolved}) failed: {e}")
            last_exc = e

    raise RuntimeError(f"All AI providers exhausted. Last error: {last_exc}")


# ---------------------------------------------------------------------------
# Public API  (drop-in replacement for existing call_claude* calls)
# ---------------------------------------------------------------------------

MAX_CONTINUATIONS = 4  # safety cap: prevents infinite loops on adversarial prompts


def call_claude(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    cache_system: bool = True,
    auto_continue: bool = True,
) -> str:
    """Call the primary AI provider with automatic fallback and truncation recovery.

    Despite the name, this will transparently try GPT then Gemini if Claude
    is unavailable, following the order in config.yml ai_providers.order.

    If `auto_continue=True` (default) and the provider hit max_tokens, this will
    automatically issue continuation calls (up to MAX_CONTINUATIONS times) so the
    final returned text is never truncated mid-sentence — works for daily, weekly,
    and monthly reports regardless of length. Set to False for JSON-array calls
    where structural continuation isn't trivial (those should bump max_tokens instead).
    """
    text, provider, stop_reason = _call_with_fallback(
        system, user, model, max_tokens, cache_system
    )

    if not auto_continue or stop_reason != "max_tokens":
        return text

    # Truncation detected → automatically continue.
    # Claude provider supports clean continuation via assistant-message prefill;
    # for GPT/Gemini fallback we'd need provider-specific logic, so we only
    # auto-continue on the Claude path. (In practice Claude is the primary anyway.)
    if provider != "claude":
        print(f"  [AI] Response truncated (provider={provider}); auto-continue only supported on Claude")
        return text

    accumulated = text
    for attempt in range(1, MAX_CONTINUATIONS + 1):
        print(f"  [AI] Response hit max_tokens — continuing (attempt {attempt}/{MAX_CONTINUATIONS})")
        try:
            order, models = _load_provider_config()
            resolved = _resolve_model("claude", model, models)
            cont_text, cont_stop = _continue_claude_response(
                system, user, accumulated, resolved, max_tokens, cache_system
            )
        except Exception as e:
            print(f"  [AI] Continuation call failed: {e}")
            break
        if not cont_text:
            break
        accumulated += cont_text
        if cont_stop != "max_tokens":
            print(f"  [AI] Continuation completed cleanly after {attempt} extra call(s)")
            break
    else:
        print(f"  [AI] Reached MAX_CONTINUATIONS ({MAX_CONTINUATIONS}); returning best-effort output")
    return accumulated


def call_claude_web_search(
    prompt: str,
    max_uses: int = 5,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> list[dict]:
    """Call Claude with the built-in web_search tool.

    Claude-only — the web_search_20250305 tool is Anthropic-specific.
    No fallback to other providers.
    """
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break
    if not text:
        return []
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
    """Call AI (with fallback) and parse the JSON response. Raises on parse failure.

    Note: auto_continue is disabled for JSON because resuming mid-JSON is fragile
    (would require structural merging). For array-returning JSON calls, increase
    max_tokens directly — see update_predictions.py and analyze_trending.py.
    """
    raw = call_claude(system, user, model, max_tokens, cache_system, auto_continue=False)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Use .strip() on the last line so trailing whitespace doesn't prevent fence removal
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)
