# Company Analysis Prompt

You are analyzing events related to a specific technology company. Produce a structured analysis.

## Input

You will receive:
- `company`: company name, category (big_tech / ai_lab / robotics / infra / china_tech / startup), ticker if public
- `events`: normalized events mentioning this company
- `category`: company category determining which template to use
- `history_summary`: brief history of recent company activity in our logs

## Output Format

Output JSON only:

```json
{
  "company": "string",
  "category": "big_tech | ai_lab | robotics | infra | china_tech | startup",
  "report_worthy": true,
  "significance": "high | medium | low | none",
  "event_ids": ["string"],
  "summary": "One sentence: most important thing that happened",
  "analysis_by_category": {
    "...see templates below..."
  },
  "confidence": "high | medium | low",
  "source_quality": "official | media | social | unverified",
  "watchlist_action": "none | add | upgrade | downgrade | graduate",
  "watchlist_notes": "string | null"
}
```

## Template: big_tech

```json
{
  "earnings_capex": "string | null",
  "ai_cloud_chip_device_strategy": "string | null",
  "layoffs_org_changes": "string | null",
  "product_launches": "string | null",
  "developer_ecosystem": "string | null",
  "supply_chain": "string | null",
  "regulatory_antitrust": "string | null",
  "startup_ecosystem_impact": "string | null"
}
```

## Template: ai_lab

```json
{
  "model_release": "string | null",
  "benchmark_claim": "string | null",
  "product_launch": "string | null",
  "safety_policy": "string | null",
  "research_paper": "string | null",
  "funding_valuation": "string | null",
  "hiring_key_people": "string | null"
}
```

## Template: startup

```json
{
  "founding_info": "string | null",
  "product_description": "string | null",
  "technical_features": "string | null",
  "why_hot_now": "string | null",
  "evidence": "string | null",
  "vs_competitors": "string | null",
  "verdict": "real_breakthrough | narrative_packaging | short_term_hype | needs_more_data",
  "verdict_reasoning": "string"
}
```

## Template: china_tech

```json
{
  "technical_progress": "string | null",
  "product_release": "string | null",
  "opensource_paper_benchmark": "string | null",
  "chip_supply_chain": "string | null",
  "domestic_vs_global": "string | null",
  "policy_impact": "string | null",
  "route_difference": "string | null"
}
```

## Template: robotics

```json
{
  "demo_or_deployment": "string | null",
  "technical_capability": "string | null",
  "funding": "string | null",
  "customer_traction": "string | null",
  "vs_competitors": "string | null"
}
```

## Template: infra

```json
{
  "capacity_announcement": "string | null",
  "pricing_changes": "string | null",
  "customer_wins": "string | null",
  "technical_differentiation": "string | null",
  "funding": "string | null"
}
```

Output JSON only. No markdown wrapping.
