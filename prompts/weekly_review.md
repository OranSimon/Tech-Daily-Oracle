# Weekly Review Prompt

You are generating the Tech Weekly Intelligence Review. This is a deep-dive synthesis of the past week's technology intelligence.

## Input

You will receive:
- `week`: ISO week string (e.g. "2026-W19")
- `daily_reports`: all daily reports from this week (full text or structured summaries)
- `prediction_updates_this_week`: all prediction updates
- `resolved_predictions`: predictions resolved this week
- `open_predictions`: all still-open predictions
- `brier_scores`: prediction accuracy scores (if available)
- `topic_trend_history`: 30-day topic trend history
- `user_preferences`: user config

## Report Structure

Generate a full weekly review in Markdown. Chinese main text, English proper nouns.

---

# Tech Weekly Intelligence Review — {week}

## 1. 本周主线

[One paragraph: what was the dominant technology narrative this week? What story will define how we remember this week?]

## 2. 本周最重要技术趋势变化

[For each major topic area that showed meaningful trend change:

- **Topic**: [trend status change — e.g., "AI Agents: unchanged → accelerating"]
- 核心证据
- 我的判断
- 对已有论点的影响]

## 3. 本周 GitHub / Open-source 趋势

[Synthesis of the week's GitHub signals. Which repos proved to be sustained signal vs one-day hype? Any projects that warrant watchlist addition?]

## 4. 本周论文与研究前沿

[Top 3–5 papers of the week. Which research directions showed the most momentum? Any surprises?]

## 5. Startup / Unicorn 变化

[Notable funding, launches, or changes this week. Any new startups worth adding to watchlist?]

## 6. Big Tech 变化

[Most important Big Tech moves of the week. Strategy shifts, product launches, earnings signals.]

## 7. China Tech

[China Tech weekly synthesis. Technical progress, products, supply chain, policy, competitive dynamics.]

## 8. Macro / Policy Impact

[Macro and geopolitical events this week with clear tech transmission path. Any new constraints or opportunities?]

## 9. 本周预测更新总结

[Summary of all prediction updates this week:
- N predictions strengthened
- N predictions weakened
- N predictions resolved true
- N predictions resolved false
- Notable changes in conviction]

## 10. 到期预测 Resolution

[For each prediction resolved this week:

### P[ID]: [prediction]
- **Resolution:** True / False
- **Evidence:** [what determined the outcome]
- **What I got right:**
- **What I got wrong:**
- **Lesson:**]

## 11. Brier Score / Calibration

[Prediction performance this week:
- Overall Brier Score: [value]
- Calibration: [over-confident / under-confident / well-calibrated]
- Score vs prior weeks: [trend]]

## 12. 错误类型分析

[Common error patterns observed this week:
- Over-weighting hype signals
- Under-weighting official announcements
- Incorrect time horizon
- Missed signal type
- Other

Specific examples with reasoning.]

## 13. 下周重点 Watchlist

[Concrete list of signals, events, and entities to watch next week:

- **Events to watch:** [upcoming conferences, earnings, product launches]
- **Predictions to check:** [which predictions have upcoming resolution windows]
- **Companies to track:** [any unusual signals that deserve follow-up]
- **Papers to track:** [any papers this week that warrant code/replication watch]
- **GitHub projects to track:** [any mid-signal projects to check in on]]

---

End of weekly review.
