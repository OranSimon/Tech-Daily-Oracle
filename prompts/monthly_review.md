# Monthly Review Prompt

You are generating the Tech Monthly Strategic Review. This is a high-level strategic synthesis for long-term technology intelligence.

## Input

You will receive:
- `month`: YYYY-MM string
- `weekly_reviews`: all weekly reviews from this month
- `daily_summaries`: brief daily summaries for context
- `topic_trend_history`: 90-day topic trend history
- `prediction_performance`: monthly prediction performance summary
- `company_mention_trends`: company mention frequency and sentiment trends
- `user_preferences`: user config

## Report Structure

---

# Tech Monthly Strategic Review — {month}

## 1. 月度科技主线

[2–3 paragraphs: what were the dominant technology themes this month? What story defines this month in technology? What shifted vs last month?]

## 2. Technology Momentum Ranking

[Rank the major technology directions by momentum this month:

| Rank | Technology Direction | Trend | Change vs Last Month | Key Evidence |
|------|----------------------|-------|----------------------|--------------|
| 1    | ...                  | accelerating | ↑ | ... |
| ...  | ...                  | ...   | ...                  | ... |

Analysis: which directions are gaining vs losing momentum? Why?]

## 3. Startup / Unicorn Direction

[Monthly synthesis of startup activity:
- Active new startups that emerged this month
- Funding themes: which sectors attracted capital?
- Any notable failures or pivots?
- Competitive dynamics vs established players
- Early signals for next emerging cohort]

## 4. Big Tech Strategy Shifts

[For each major Big Tech company with significant signals this month:
- What strategic direction is becoming clearer?
- Capex and investment signals
- Product and platform moves
- Developer ecosystem changes]

## 5. China Tech Direction

[Monthly China Tech synthesis:
- Most important technical progress
- Open-source / model / benchmark activity
- Supply chain and chip status
- Competitive dynamics globally
- Policy environment changes
- Route divergence from global technology]

## 6. Research Frontier Shifts

[Which research directions showed the most momentum this month?
- Top papers of the month
- Emerging research themes
- Directions cooling
- Lab/institution moves]

## 7. Open-source Ecosystem Shifts

[GitHub and open-source trends this month:
- Projects that sustained signal beyond initial spike
- New tool categories emerging
- Platform/ecosystem shifts]

## 8. Macro / Geopolitical Impact

[Monthly macro and policy synthesis:
- Most important policy changes affecting tech
- Supply chain and trade developments
- Energy and compute access signals
- Geopolitical risk trajectory]

## 9. Prediction Performance

[Monthly prediction performance:
- Predictions opened this month: N
- Predictions resolved this month: N true, N false
- Brier Score: [value]
- Calibration trend: [improving / stable / degrading]
- Main error types this month
- Updated calibration notes for future predictions

### Market Signal Accuracy (Phase 5)

[Render only if `market_signal_performance` in the payload is non-empty.

If empty: output one line → "本月 MarketSignalAgent 未启用或无历史信号数据。"

If non-empty, summarise per ticker across the month:
- How many times each ticker was triggered
- Most common risk_level and confidence distributions
- Whether the stated conclusions (conclusion_zh) were consistent across the month
- Signals to monitor: which thresholds were repeatedly flagged

Note: Quantitative accuracy (direction correct/incorrect vs realised price moves) requires
≥4 weeks of signal history. Once available, compare `buy_observation_point` / `sell_reduce_observation_point` from stored signals against subsequent yfinance price data.]

## 10. Strategic Theses Updated

[Review of long-term technology theses:

For each major thesis:
- **Thesis:** [statement]
- **Status:** [strengthened / weakened / unchanged / refined]
- **Evidence this month:** [what happened]
- **Updated conviction:** [%]
- **Horizon:** [unchanged / moved forward / moved back]

New theses worth tracking:]

## 11. Opportunities for Startups / Investors

[Based on this month's signals, what opportunities are emerging?

Format each as:
- **Opportunity:** [description]
- **Evidence:** [signals supporting this]
- **Time window:** [when this window might close]
- **Risks:** [what could prevent this]
- **Key players to watch:** [companies or people]]

---

End of monthly strategic review.
