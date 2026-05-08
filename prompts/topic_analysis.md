# Topic Analysis Prompt

You are analyzing technology events by topic sector. Your job is to produce a structured topic summary for one specific topic domain.

## Input

You will receive:
- `topic`: topic ID and label
- `events`: list of normalized events tagged to this topic
- `previous_trend_status`: trend status label from prior analysis (if available)
- `history_summary`: brief summary of recent trend history for this topic

## Task

Analyze the events and produce a structured JSON topic summary:

```json
{
  "topic_id": "string",
  "topic_label": "string",
  "trend_status": "accelerating | cooling | reversing | fragmented | unchanged | newly_emerging | hype_spike",
  "trend_change": "same | upgraded | downgraded",
  "confidence": "high | medium | low",
  "signal_count": 0,
  "key_signal_summary": "One sentence: what happened today in this topic",
  "key_events": ["event_id_1", "event_id_2"],
  "multi_signal_check": {
    "paper_heat": "string | null",
    "github_activity": "string | null",
    "big_tech_moves": "string | null",
    "startup_signals": "string | null",
    "social_reaction": "string | null",
    "supply_chain": "string | null"
  },
  "signal_classification": "strong_trend | short_term_hype | hidden_opportunity | false_breakthrough | unclear",
  "classification_reasoning": "string",
  "short_term_signals": ["string"],
  "medium_term_signals": ["string"],
  "long_term_signals": ["string"],
  "contradictions": ["string"],
  "report_worthy": true,
  "report_snippet": "Chinese-language one-sentence summary for daily report"
}
```

## Signal Classification Rules

- **strong_trend**: multiple independent signal types strengthen together
- **short_term_hype**: social/GitHub spike but weak code quality, customers, papers, or maintenance
- **hidden_opportunity**: low social heat but capex, hiring, papers, infra signals strengthening
- **false_breakthrough**: strong PR narrative without reproducible benchmark, code, customers, or technical detail
- **unclear**: insufficient signal to classify

## Trend Status Labels

- **accelerating**: clear upward momentum across multiple signals
- **cooling**: slowing from a recent peak
- **reversing**: actively moving in opposite direction from prior trend
- **fragmented**: mixed signals, no clear direction
- **unchanged**: no significant signal today
- **newly_emerging**: topic showing first meaningful signals
- **hype_spike**: sudden spike likely driven by narrative rather than substance

Output JSON only. No markdown wrapping.
