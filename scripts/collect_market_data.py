"""Market Data Collector — Phase 5.

Fetches price, volume, options, and macro data using yfinance (free, no API key)
and optionally FRED (free API key required) for macro series.

yfinance is not async-native; all calls use ThreadPoolExecutor so the rest of the
pipeline is not blocked.

Activation: config.market_signal.live_data must be true.
If yfinance is not installed, this module returns an empty dict gracefully rather
than crashing the pipeline.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Single-ticker fetch
# ---------------------------------------------------------------------------

def _fetch_ticker_data(ticker_symbol: str, history_days: int = 30) -> dict[str, Any]:
    """Fetch OHLCV history, key stats, and options chain for one ticker.

    Returns {} on any failure — market data is always non-fatal.
    """
    try:
        import yfinance as yf  # optional dependency
    except ImportError:
        return {}

    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period=f"{history_days}d")

        if hist.empty or len(hist) < 2:
            return {}

        current_price = float(hist["Close"].iloc[-1])

        # Serialize last 20 rows of OHLCV (enough context for the LLM)
        price_rows: list[dict] = []
        for idx, row in hist.tail(20).iterrows():
            price_rows.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]), 2),
                "high":   round(float(row["High"]), 2),
                "low":    round(float(row["Low"]), 2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        # Key stats
        high_52w = float(hist["High"].max())
        low_52w  = float(hist["Low"].min())
        # 20-day change (requires ≥21 rows)
        change_20d_pct = None
        if len(hist) >= 21:
            prev_close_20 = float(hist["Close"].iloc[-21])
            if prev_close_20 > 0:
                change_20d_pct = round((current_price / prev_close_20 - 1) * 100, 1)

        stats = {
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "distance_from_52w_high_pct": round(
                (current_price / high_52w - 1) * 100, 1
            ) if high_52w > 0 else None,
            "change_20d_pct": change_20d_pct,
        }

        # Options data (nearest expiry only) — optional, skip on any failure
        options_data: dict[str, Any] = {}
        try:
            expiries = t.options   # tuple of expiry date strings
            if expiries:
                chain = t.option_chain(expiries[0])
                calls_df = chain.calls
                puts_df  = chain.puts

                # ATM: strikes within ±5% of current price
                atm_calls = calls_df[
                    (calls_df["strike"] >= current_price * 0.95) &
                    (calls_df["strike"] <= current_price * 1.05)
                ]
                atm_puts = puts_df[
                    (puts_df["strike"] >= current_price * 0.95) &
                    (puts_df["strike"] <= current_price * 1.05)
                ]

                call_iv: float | None = None
                put_iv:  float | None = None
                if not atm_calls.empty:
                    raw_iv = atm_calls["impliedVolatility"].replace(0, float("nan")).dropna()
                    if not raw_iv.empty:
                        call_iv = float(raw_iv.mean())
                if not atm_puts.empty:
                    raw_iv = atm_puts["impliedVolatility"].replace(0, float("nan")).dropna()
                    if not raw_iv.empty:
                        put_iv = float(raw_iv.mean())

                call_oi = float(calls_df["openInterest"].sum())
                put_oi  = float(puts_df["openInterest"].sum())
                pc_ratio = round(put_oi / call_oi, 2) if call_oi > 0 else None

                options_data = {
                    "nearest_expiry": expiries[0],
                    "atm_call_iv_pct": round(call_iv * 100, 1) if call_iv is not None else None,
                    "atm_put_iv_pct":  round(put_iv  * 100, 1) if put_iv  is not None else None,
                    "put_call_oi_ratio": pc_ratio,
                    # Positive skew = puts more expensive than calls (bearish sentiment)
                    "skew_pct": round((put_iv - call_iv) * 100, 1)
                    if (put_iv is not None and call_iv is not None) else None,
                }
        except Exception:
            pass  # Options data is best-effort

        return {
            "current_price": round(current_price, 2),
            "price_data": price_rows,
            "stats": stats,
            "options_data": options_data,
        }

    except Exception as e:
        print(f"  [MarketData] {ticker_symbol} fetch failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Macro data (shared across all tickers)
# ---------------------------------------------------------------------------

_MACRO_SYMBOLS: dict[str, str] = {
    "vix":            "^VIX",
    "ten_year_yield": "^TNX",
    "dxy":            "DX-Y.NYB",
    "spx":            "^GSPC",
}


def _fetch_macro_data(macro_symbols: dict[str, str] | None = None) -> dict[str, Any]:
    """Fetch VIX, 10Y yield, DXY, SPX from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    symbols = macro_symbols or _MACRO_SYMBOLS
    macro: dict[str, Any] = {}

    for key, sym in symbols.items():
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="30d")
            if hist.empty:
                continue
            current = float(hist["Close"].iloc[-1])
            avg_20d = float(hist["Close"].tail(20).mean())
            change_pct = None
            if len(hist) >= 21:
                prev = float(hist["Close"].iloc[-21])
                if prev > 0:
                    change_pct = round((current / prev - 1) * 100, 1)
            macro[key] = {
                "current":    round(current, 2),
                "avg_20d":    round(avg_20d, 2),
                "change_pct": change_pct,
            }
        except Exception as e:
            print(f"  [MarketData] Macro {sym} ({key}) failed: {e}")

    return macro


def _fetch_fred_macro(fred_api_key: str) -> dict[str, Any]:
    """Fetch macro series from FRED. Optional — complements yfinance macro data.

    Requires: pip install fredapi  and  FRED_API_KEY env var or config.
    Returns {} gracefully if fredapi is not installed or key is missing.
    """
    if not fred_api_key:
        return {}
    try:
        from fredapi import Fred  # optional dependency
    except ImportError:
        return {}

    series_map = {
        "fed_funds_rate": "FEDFUNDS",
        "cpi_yoy":        "CPIAUCSL",
        "unemployment":   "UNRATE",
    }
    result: dict[str, Any] = {}

    try:
        fred = Fred(api_key=fred_api_key)
        for key, series_id in series_map.items():
            try:
                series = fred.get_series_latest_release(series_id)
                if series is not None and len(series) > 0:
                    result[key] = round(float(series.iloc[-1]), 2)
            except Exception:
                pass
    except Exception as e:
        print(f"  [MarketData] FRED connection failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def collect_market_data(tickers: list[str], config: dict) -> dict[str, Any]:
    """Collect price, options, and macro data for all tracked tickers.

    Returns:
        {
          "per_ticker": {
              "NVDA": {"current_price": 950.0, "price_data": [...], "stats": {...}, "options_data": {...}},
              ...
          },
          "macro": {
              "vix":            {"current": 18.5, "avg_20d": 17.2, "change_pct": 7.6},
              "ten_year_yield": {...},
              "dxy":            {...},
              "spx":            {...},
              "fed_funds_rate": 5.33,   # FRED, if key provided
              ...
          }
        }

    All failures are non-fatal — partial results or empty dict returned rather
    than raising exceptions.
    """
    ms_cfg = config.get("market_signal", {})
    history_days: int = ms_cfg.get("price_history_days", 30)
    fred_api_key: str = ms_cfg.get("fred_api_key") or os.environ.get("FRED_API_KEY", "")
    macro_symbols: dict | None = ms_cfg.get("macro_tickers")  # None → use defaults

    if not tickers:
        return {"per_ticker": {}, "macro": {}}

    # -----------------------------------------------------------------------
    # Per-ticker fetches — parallel (yfinance is thread-safe)
    # -----------------------------------------------------------------------
    per_ticker: dict[str, Any] = {}
    workers = min(len(tickers), 5)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_ticker_data, sym, history_days): sym
            for sym in tickers
        }
        for future in as_completed(futures):
            sym = futures[future]
            try:
                data = future.result()
                if data:
                    per_ticker[sym] = data
            except Exception as e:
                print(f"  [MarketData] {sym} future failed: {e}")

    # -----------------------------------------------------------------------
    # Macro data — one batch call
    # -----------------------------------------------------------------------
    macro = _fetch_macro_data(macro_symbols)
    if fred_api_key:
        fred_data = _fetch_fred_macro(fred_api_key)
        macro.update(fred_data)

    print(
        f"  [MarketData] Fetched {len(per_ticker)}/{len(tickers)} tickers; "
        f"macro keys: {list(macro.keys())}"
    )
    return {"per_ticker": per_ticker, "macro": macro}
