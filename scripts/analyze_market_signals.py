"""Market Signal Analysis — Phase 4/5.

Phase 4: Qualitative signal per ticker using only events already in the
         daily pipeline (company_analyses, macro_impact_analyses, topic_summaries).
         No live market data. Activated by config.market_signal.enabled = true.

Phase 5: Adds yfinance price/options data and FRED macro data to the prompt.
         Activated by config.market_signal.live_data = true.

Architecture:
  - One LLM call per triggered ticker (not batched — each signal is independent)
  - Tickers are filtered by `only_on_event_day` and `min_importance_to_trigger`
  - Results are stored in TechDailyState.market_signal_analyses
  - A pre-formatted `report_snippet` is built from the validated JSON response
"""

from __future__ import annotations

import dataclasses
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yaml
from analyzer_helpers import schema_to_dataclass
from llm_schemas import MarketSignalAnalysisResponse
from pipeline_state import AnalysisState, CorpusState, MarketSignalInputState, RunMetadataState
from prompt_runner import PromptRunner
from state import MarketSignalAnalysis, TechDailyState

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _market_signal_input_from_state(state: TechDailyState) -> MarketSignalInputState:
    return MarketSignalInputState(
        run_metadata=RunMetadataState(
            run_id=getattr(state, "run_id", ""),
            run_date=state.run_date,
            time_window=getattr(state, "time_window", ""),
            signal_level=getattr(state, "signal_level", "normal"),
        ),
        corpus=CorpusState(normalized_events=state.normalized_events),
        analysis=AnalysisState(
            company_analyses=state.company_analyses,
            macro_impact_analyses=state.macro_impact_analyses,
            topic_summaries=state.topic_summaries,
        ),
    )


def _load_watchlist(config: dict) -> dict:
    watchlist_file = config.get("market_signal", {}).get("watchlist_file", "sources/market_watchlist.yml")
    path = os.path.join(ROOT, watchlist_file)
    with open(path) as f:
        return yaml.safe_load(f)


def _safe_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_safe_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Company name matching
# ---------------------------------------------------------------------------


def _find_company_analysis(watchlist_company: str, company_analyses: dict) -> Any | None:
    """Case-insensitive match of watchlist company name to company_analyses keys.

    Tries exact match first, then partial match as fallback
    (e.g. 'Google' matches 'Google' key even if analysis was tagged 'Google/Alphabet').
    """
    wl_lower = watchlist_company.lower()
    # Exact match (case-insensitive)
    for key, analysis in company_analyses.items():
        if key.lower() == wl_lower:
            return analysis
    # Partial match: watchlist name is substring of key or vice versa
    for key, analysis in company_analyses.items():
        if wl_lower in key.lower() or key.lower() in wl_lower:
            return analysis
    return None


def _find_related_events_from_input(
    watchlist_company: str,
    input_state: MarketSignalInputState,
    top_n: int = 5,
) -> list[dict]:
    """Return top normalized events that mention the company."""
    company_lower = watchlist_company.lower()
    related = [
        e
        for e in input_state.corpus.normalized_events
        if any(watchlist_company in c or company_lower in c.lower() for c in e.companies)
        or company_lower in e.canonical_title.lower()
    ]
    related.sort(key=lambda e: e.importance_score, reverse=True)
    return [
        {
            "title": e.canonical_title,
            "summary": e.summary[:300],
            "importance_score": round(e.importance_score, 2),
            "source_type": e.source_type,
            "event_type": e.event_type,
        }
        for e in related[:top_n]
    ]


def _find_related_events(watchlist_company: str, state: TechDailyState, top_n: int = 5) -> list[dict]:
    return _find_related_events_from_input(
        watchlist_company,
        _market_signal_input_from_state(state),
        top_n=top_n,
    )


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def _build_macro_context_from_input(input_state: MarketSignalInputState) -> dict:
    """Build a compact macro context dict from the pipeline's macro analyses."""
    macro_events = [
        {
            "title": a.event_title,
            "transmission": a.transmission_path,
            "affected_sectors": a.affected_sectors,
            "severity": a.severity,
            "time_dimension": a.time_dimension,
        }
        for a in input_state.analysis.macro_impact_analyses.values()
        if a.report_worthy
    ][:4]

    # Relevant tech topic summaries
    tech_trends = {
        k: {
            "status": v.trend_status,
            "summary": v.key_signal_summary,
            "classification": v.signal_classification,
        }
        for k, v in input_state.analysis.topic_summaries.items()
        if v.report_worthy
        and k
        in (
            "ai_models",
            "ai_infrastructure",
            "semiconductors",
            "embodied_ai_robotics",
            "big_tech_strategy",
            "startups_unicorns",
        )
    }

    return {
        "macro_events": macro_events,
        "tech_trends": tech_trends,
    }


def _build_macro_context(state: TechDailyState) -> dict:
    return _build_macro_context_from_input(_market_signal_input_from_state(state))


def _build_ticker_payload(
    ticker_cfg: dict,
    company_analysis: Any | None,
    related_events: list[dict],
    macro_context: dict,
    run_date: str,
    market_data: dict | None,
    prior_signal: dict | None,
) -> dict:
    """Build the JSON payload sent to the MarketSignalAgent for one ticker."""
    # Company events (structured)
    pub_info = []
    if company_analysis is not None:
        pub_info.append(
            {
                "significance": company_analysis.significance,
                "summary": company_analysis.summary,
                "confidence": company_analysis.confidence,
                "analysis_by_category": company_analysis.analysis_by_category,
            }
        )

    # Phase 5 market data slices
    per_ticker_data = (market_data or {}).get("per_ticker", {})
    ticker_sym = ticker_cfg["ticker"]
    price_data = per_ticker_data.get(ticker_sym, {}).get("price_data") or None
    options_data = per_ticker_data.get(ticker_sym, {}).get("options_data") or None
    price_stats = per_ticker_data.get(ticker_sym, {}).get("stats") or None
    current_price = per_ticker_data.get(ticker_sym, {}).get("current_price")
    macro_market = (market_data or {}).get("macro") or None

    return {
        "ticker": ticker_sym,
        "company": ticker_cfg["company"],
        "time_horizon": ticker_cfg.get("horizon", "2–8 weeks"),
        "why_tracked": ticker_cfg.get("why_tracked", ""),
        "date": run_date,
        "public_info_events": pub_info,
        "related_normalized_events": related_events,
        "macro_context": macro_context,
        # Phase 5 fields (None if live_data=false)
        "current_price": current_price,
        "price_data": price_data,
        "price_stats": price_stats,
        "options_data": options_data,
        "macro_market_data": macro_market,
        "previous_signal": prior_signal,
    }


# ---------------------------------------------------------------------------
# Report snippet builder
# ---------------------------------------------------------------------------


def _build_report_snippet(raw: dict) -> str:
    """Convert the validated JSON response into a formatted markdown snippet."""
    ticker = raw.get("ticker", "?")
    company = raw.get("company", "")
    conclusion_zh = raw.get("conclusion_zh") or raw.get("conclusion", "")
    reasoning_zh = raw.get("reasoning_zh", "")
    base_case = raw.get("base_case", "")
    bull_case = raw.get("bull_case", "")
    bear_case = raw.get("bear_case", "")
    buy_pt = raw.get("buy_observation_point", "")
    sell_pt = raw.get("sell_reduce_observation_point", "")
    inval = raw.get("invalidation_condition", "")
    risk = raw.get("risk_level", "—")
    conf = raw.get("confidence", "—")

    lines = [f"### {ticker} — {company}"]
    if conclusion_zh:
        lines.append(f"\n**结论：** {conclusion_zh}")
    if reasoning_zh:
        lines.append(f"\n**直白原因：** {reasoning_zh}")
    if base_case:
        lines.append(f"\n**Base case：** {base_case}")
    if bull_case:
        lines.append(f"\n**Bull case：** {bull_case}")
    if bear_case:
        lines.append(f"\n**Bear case：** {bear_case}")
    if buy_pt:
        lines.append(f"\n**Buy observation point：** {buy_pt}")
    if sell_pt:
        lines.append(f"\n**Sell / reduce observation point：** {sell_pt}")
    if inval:
        lines.append(f"\n**Invalidation：** {inval}")

    monitors = raw.get("signals_to_monitor") or []
    if monitors:
        lines.append("\n**Signals to monitor：**")
        lines.append("| Signal | Current | Threshold | Meaning |")
        lines.append("|--------|---------|-----------|---------|")
        for m in monitors:
            if not isinstance(m, dict):
                continue
            sig = m.get("signal", "")
            curr = m.get("current", "—")
            thresh = m.get("threshold", "—")
            meaning = m.get("meaning", "")
            lines.append(f"| {sig} | {curr} | {thresh} | {meaning} |")

    lines.append(f"\n*风险等级：{risk} · 信心：{conf}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-ticker analysis call
# ---------------------------------------------------------------------------


def _analyze_one_ticker(
    ticker_cfg: dict,
    payload: dict,
    has_price_data: bool,
    prompt_runner: PromptRunner,
) -> MarketSignalAnalysis | None:
    """Call MarketSignalAgent for a single ticker."""
    ticker = ticker_cfg["ticker"]

    result = prompt_runner.run_json(
        prompt_path="market_signal.md",
        payload=json.dumps(payload, ensure_ascii=False),
        schema=MarketSignalAnalysisResponse,
        max_tokens=4096,
        cache_system=True,
    )
    raw = result.model_dump()
    snippet = _build_report_snippet(raw)

    return schema_to_dataclass(
        result,
        MarketSignalAnalysis,
        ticker=result.ticker or ticker,
        company=result.company or ticker_cfg["company"],
        date=result.date or payload["date"],
        time_horizon=result.time_horizon or ticker_cfg.get("horizon", ""),
        has_price_data=has_price_data,
        report_snippet=snippet,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_market_signals(
    state: TechDailyState,
    market_data: dict | None,
    prior_signals: dict[str, dict],
    config: dict,
    prompt_runner: PromptRunner | None = None,
) -> dict[str, MarketSignalAnalysis]:
    return analyze_market_signals_from_input(
        _market_signal_input_from_state(state),
        market_data=market_data,
        prior_signals=prior_signals,
        config=config,
        prompt_runner=prompt_runner,
    )


def analyze_market_signals_from_input(
    input_state: MarketSignalInputState,
    *,
    market_data: dict | None,
    prior_signals: dict[str, dict],
    config: dict,
    prompt_runner: PromptRunner | None = None,
) -> dict[str, MarketSignalAnalysis]:
    """Run MarketSignalAgent for triggered tickers.

    Steps:
      1. Load watchlist + settings
      2. Filter: which tickers have a company event today (if only_on_event_day)
      3. Sort by company analysis importance; cap at max_tickers_per_run
      4. Build payloads (events + macro context + optional price data)
      5. Run per-ticker LLM calls in parallel (ThreadPoolExecutor)
      6. Return dict of ticker → MarketSignalAnalysis
    """
    ms_cfg = config.get("market_signal", {})
    only_on_event_day: bool = ms_cfg.get("only_on_event_day", True)
    min_importance: float = ms_cfg.get("min_importance_to_trigger", 0.55)
    max_tickers: int = ms_cfg.get("max_tickers_per_run", 5)

    try:
        watchlist = _load_watchlist(config)
    except Exception as e:
        print(f"  [MarketSignal] Failed to load watchlist: {e}")
        return {}

    all_tickers: list[dict] = watchlist.get("tickers", [])
    # Merge watchlist settings with config (watchlist settings act as per-ticker overrides)
    wl_settings = watchlist.get("settings", {})
    only_on_event_day = wl_settings.get("only_on_event_day", only_on_event_day)
    min_importance = wl_settings.get("min_importance_to_trigger", min_importance)
    max_tickers = wl_settings.get("max_tickers_per_run", max_tickers)

    runner = prompt_runner or PromptRunner()
    macro_context = _build_macro_context_from_input(input_state)

    # -----------------------------------------------------------------------
    # Identify triggered tickers
    # -----------------------------------------------------------------------
    triggered: list[tuple[dict, Any, float]] = []  # (ticker_cfg, company_analysis, importance)

    for ticker_cfg in all_tickers:
        company_analysis = _find_company_analysis(ticker_cfg["company"], input_state.analysis.company_analyses)
        if only_on_event_day:
            if company_analysis is None:
                continue
            importance = getattr(company_analysis, "significance", "low")
            # Convert significance string to numeric for sorting
            importance_num = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(importance, 0.4)
            if importance_num < min_importance:
                continue
        else:
            importance_num = 0.5  # uniform when not gating

        triggered.append((ticker_cfg, company_analysis, importance_num))

    # Sort highest importance first, then cap
    triggered.sort(key=lambda x: x[2], reverse=True)
    triggered = triggered[:max_tickers]

    if not triggered:
        print(f"  [MarketSignal] No tickers triggered today (only_on_event_day={only_on_event_day})")
        return {}

    has_price_data = bool(market_data and market_data.get("per_ticker"))
    print(
        f"  [MarketSignal] {len(triggered)} tickers triggered; "
        f"price_data={'yes' if has_price_data else 'no (Phase 4 mode)'}"
    )

    # -----------------------------------------------------------------------
    # Build payloads
    # -----------------------------------------------------------------------
    jobs: list[tuple[dict, dict, bool]] = []  # (ticker_cfg, payload, has_price_data)
    for ticker_cfg, company_analysis, _ in triggered:
        related_events = _find_related_events_from_input(ticker_cfg["company"], input_state)
        prior_signal = prior_signals.get(ticker_cfg["ticker"])
        payload = _build_ticker_payload(
            ticker_cfg=ticker_cfg,
            company_analysis=company_analysis,
            related_events=related_events,
            macro_context=macro_context,
            run_date=input_state.run_metadata.run_date,
            market_data=market_data,
            prior_signal=prior_signal,
        )
        # Only mark as having price data if this specific ticker's data was fetched
        ticker_has_data = has_price_data and ticker_cfg["ticker"] in (market_data or {}).get("per_ticker", {})
        jobs.append((ticker_cfg, payload, ticker_has_data))

    # -----------------------------------------------------------------------
    # Run calls in parallel (each ticker is one independent API call)
    # -----------------------------------------------------------------------
    results: dict[str, MarketSignalAnalysis] = {}
    workers = min(len(jobs), 3)  # cap parallelism to avoid rate-limit bursts

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_analyze_one_ticker, tc, pl, hpd, runner): tc["ticker"] for tc, pl, hpd in jobs}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                analysis = future.result()
                if analysis is not None:
                    results[ticker] = analysis
                    print(f"  [MarketSignal] {ticker}: risk={analysis.risk_level}, confidence={analysis.confidence}")
            except Exception as e:
                print(f"  [MarketSignal] {ticker} future failed: {e}")

    print(f"  [MarketSignal] Completed {len(results)}/{len(jobs)} ticker analyses")
    return results
