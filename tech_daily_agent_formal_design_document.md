# Tech Daily Agent — Formal Design Document

> **Implementation Status Key**
> - ✅ Implemented and verified
> - ⚠️ Partially implemented — see notes
> - ❌ Not yet implemented (planned)

---

## 1. Project Overview

### 1.1 Project Name

**Tech Daily Agent**

### 1.2 Product Positioning

Tech Daily Agent is a personal technology intelligence system. It generates a daily Chinese-language technology intelligence memo for the user, while keeping company names, project names, paper titles, and technical terms in English.

The system focuses on global technology companies, AI, embodied AI, robotics, AI infrastructure, chips, GitHub trending projects, Hugging Face daily papers, major research papers, new unicorns, Big Tech changes, tech product launches, social media evaluations, and macro/geopolitical events that may affect technology companies.

It is not a generic newsletter. It is designed as a personal intelligence workflow with memory, prediction tracking, source validation, market signal analysis, and weekly/monthly review loops.

### 1.3 Target User

The report is for the user's personal use only.

This allows the report to be:

```text
- More judgment-oriented
- More direct
- More analytical
- More focused on technical trends, startup opportunities, watchlist companies, and strategic implications
- Less constrained by public newsletter tone
```

### 1.4 Output Language and Length

Confirmed defaults:

```text
Main language: Chinese
Company names, paper titles, project names, and technical terms: English
Daily report reading time: within 20 minutes
Weekly / Monthly reports: deep-dive format, no strict length limit
```

---

## 2. Core Goals ✅

The system should automatically perform the following tasks:

```text
1. ✅ Collect important technology-related information from the last 24 hours.
2. ✅ Analyze AI, robotics, embodied AI, AI infrastructure, chips, GitHub trending, papers, startups, Big Tech, and China Tech.
3. ✅ Identify high-signal GitHub repositories and filter out toy projects, thin wrappers, and low-maintenance repos.
4. ✅ Analyze important papers from Hugging Face Daily Papers, arXiv, Papers with Code, Semantic Scholar, OpenReview, and major CS conferences.
5. ✅ Track new hot startups and unicorns, including founder background, product, technical features, and why they are gaining attention.
6. ✅ Track major Big Tech and watchlist company changes, including earnings, layoffs, products, strategy shifts, and supply chain changes.
7. ✅ Analyze social media and community reaction only for already-hot products, projects, models, or devices.
8. ✅ Track macro/geopolitical events only when they have a clear transmission path to technology companies.
9. ✅ Maintain prediction logs for technology trends, company moves, open-source projects, research directions, and policy impacts.
10. ❌ Maintain a separate MarketSignalAgent for public-company stock trend analysis and buy/sell observation points. (Phase 4)
11. ✅ Produce weekly and monthly reviews to compress trends, evaluate predictions, and update long-term theses.
```

---

## 3. Scope and Priority ✅

### 3.1 First-Priority Topics: Covered Daily

```text
AI                                     ✅
Embodied AI / Robotics                 ✅
AI infrastructure / inference / chips  ✅
GitHub Trending                        ✅
Hugging Face Daily Papers              ✅
Big Tech major changes                 ✅
New hot startups / unicorns            ✅
```

### 3.2 Second-Priority Topics: Covered Only When Significant

```text
New technology devices                                ✅
Tech conferences and product events                   ✅
Social media evaluations                              ✅ (HN + web search; X API not connected)
Big Tech earnings / layoffs / product testing         ✅
International policy / war / trade / energy / minerals impact  ✅
```

### 3.3 Third-Priority Topics: Covered in Weekly / Monthly Reviews

```text
Long-term paper trends           ✅
Open-source ecosystem shifts     ✅
Global technology policy direction  ✅
Supply chain and industrial structure changes  ✅
```

---

## 4. Watchlists ✅

All watchlists are implemented as YAML files in `sources/`.

### 4.1 Global Big Tech ✅ `sources/company_watchlist.yml`

```text
Apple · Microsoft · Google / Alphabet · Amazon · Meta · Nvidia · Tesla
```

### 4.2 Global AI Labs / AI Product Companies ✅

```text
OpenAI · Anthropic · DeepMind · xAI · Mistral · Cohere · Perplexity
```

### 4.3 Global Robotics / Embodied AI ✅

```text
Figure AI · Physical Intelligence · Skild AI · Field AI
Agility Robotics · Boston Dynamics · Apptronik
```

### 4.4 Global AI Infrastructure ✅

```text
CoreWeave · Lambda · Crusoe · Together AI · Fireworks AI · Groq · Cerebras
```

### 4.5 Hardware / Devices / Spatial Computing ✅

```text
Humane · Rabbit · Brilliant Labs · Meta Reality Labs · Apple Vision Pro ecosystem
```

### 4.6 China Tech: Independent Section ✅

China Tech is analyzed as a separate section in the daily report.

```text
Huawei · ByteDance · Alibaba · Tencent · Baidu · Xiaomi
Unitree Robotics · Zhiyuan Robotics · DeepSeek · Moonshot AI
MiniMax · Zhipu AI · StepFun
```

Additional files:
- `sources/startup_watchlist.yml` ✅ — hot startups tracked separately
- `sources/conference_watchlist.yml` ✅ — AI/ML/robotics conferences
- `sources/influencer_watchlist.yml` ✅ — authority accounts for social signal weighting
- `sources/macro_watchlist.yml` ✅ — macro/geopolitical triggers and critical commodities

---

## 5. High-Level System Architecture

```text
Scheduler / Trigger Layer                ✅ GitHub Actions + manual
  ↓
Source Collector Layer                   ✅ RSS · HN · HuggingFace · arXiv · GitHub · Web Search
  ↓
Source Normalization & Deduplication     ✅ keyword tagging, title-hash dedup, scoring
  ↓
Topic & Sector Analysis Workflow         ✅ per-topic Claude call with cached system prompt
  ↓
Company / Startup Analysis Layer         ✅ watchlist-driven, category templates
  ↓
Paper / Research Analysis Layer          ✅ HF Daily Papers + arXiv, signal scoring
  ↓
GitHub Project Analysis Layer            ✅ top-3 filter, 6-dimension scoring
  ↓
Social Signal Analysis Layer             ✅ HN + web search; X API not connected
  ↓
Macro / Geopolitical Impact Layer        ✅ keyword filter + Claude analysis
  ↓
TechDailyState Blackboard                ✅ scripts/state.py
  ↓
Historical Memory Retrieval Layer        ✅ 7 daily + 4 weekly + 3 monthly + 30d trends + 90d mentions
  ↓
Prediction Update Engine                 ✅ scripts/update_predictions.py
  ↓
New Prediction Generation Engine         ✅ scripts/update_predictions.py
  ↓
Report Generation Layer                  ✅ scripts/generate_report.py
  ↓
Publishing & Storage Layer               ✅ GitHub (Markdown) · ✅ Notion (optional)
  ↓
Weekly / Monthly Review Layer            ✅ scripts/run_weekly_review.py · run_monthly_review.py
```

MarketSignalAgent — separate module:

```text
MarketSignalAgent                        ❌ Phase 4/5 — prompt template written, runner not implemented
  ← public company events
  ← market prices
  ← options / derivatives
  ← positioning / flows
  ← macro / liquidity signals
  → market scenario analysis
  → buy / sell observation points
  → market_signal_log.jsonl             ✅ stub file exists
  → market_signal_scorecard.csv         ✅ stub file exists
```

---

## 6. Repository Structure ✅

```text
tech-daily-agent/
  README.md                             ✅
  config.yml                            ✅
  requirements.txt                      ✅
  .gitignore                            ✅

  prompts/
    daily_brief.md                      ✅
    topic_analysis.md                   ✅
    company_analysis.md                 ✅
    paper_analysis.md                   ✅
    github_project_analysis.md          ✅
    social_signal_analysis.md           ✅
    macro_impact_analysis.md            ✅
    prediction_update.md                ✅
    new_prediction.md                   ✅
    market_signal.md                    ✅ (prompt written; runner not yet implemented)
    weekly_review.md                    ✅
    monthly_review.md                   ✅
    source_quality.md                   ✅

  sources/
    source_registry.yml                 ✅
    company_watchlist.yml               ✅
    startup_watchlist.yml               ✅
    conference_watchlist.yml            ✅
    paper_source_registry.yml           ✅
    github_trending_config.yml          ✅
    influencer_watchlist.yml            ✅
    macro_watchlist.yml                 ✅
    topic_taxonomy.yml                  ✅

  reports/
    daily/YYYY-MM-DD.md                 ✅ (populated at runtime)
    weekly/YYYY-Www.md                  ✅ (populated at runtime)
    monthly/YYYY-MM.md                  ✅ (populated at runtime)

  data/
    prediction_log.jsonl                ✅
    prediction_scorecard.csv            ✅
    market_signal_log.jsonl             ✅ (stub; populated by Phase 4)
    market_signal_scorecard.csv         ✅ (stub; populated by Phase 4)
    source_events.jsonl                 ✅
    company_mentions.jsonl              ✅
    project_mentions.jsonl              ✅
    paper_mentions.jsonl                ✅
    topic_trends.jsonl                  ✅
    social_signals.jsonl                ✅ (stub)
    macro_events.jsonl                  ✅ (stub)
    user_preferences.yml                ✅

  scripts/
    run_daily.py                        ✅ main orchestrator
    collect_sources.py                  ✅ async multi-source fetcher
    normalize_sources.py                ✅ dedup + tagging
    analyze_topics.py                   ✅
    analyze_companies.py                ✅
    analyze_papers.py                   ✅
    analyze_github_projects.py          ✅
    analyze_social_signals.py           ✅
    analyze_macro_impact.py             ✅
    update_predictions.py               ✅ update + generate
    generate_report.py                  ✅
    score_predictions.py                ✅ Brier score
    run_weekly_review.py                ✅
    run_monthly_review.py               ✅
    run_market_signal.py                ❌ Phase 4 — not yet written
    state.py                            ✅ TechDailyState blackboard
    storage.py                          ✅ all I/O and persistence
    claude_client.py                    ✅ Anthropic SDK wrapper with caching + web search
    publish_notion.py                   ✅ Markdown → Notion block converter + page creator

  workflows/
    daily_workflow.yml                  ✅ step-sequence documentation
    weekly_review_workflow.yml          ✅
    monthly_review_workflow.yml         ✅
    market_signal_workflow.yml          ✅ (planned; not executable yet)

  .github/workflows/
    daily.yml                           ✅ weekday 07:00 CST trigger
    weekly_review.yml                   ✅ Friday 18:00 CST trigger
    monthly_review.yml                  ✅ month-end trigger
```

MVP minimum (as specified):

```text
reports/daily/            ✅
data/prediction_log.jsonl ✅
data/prediction_scorecard.csv ✅
prompts/daily_brief.md    ✅
prompts/prediction_update.md ✅
sources/source_registry.yml  ✅
sources/company_watchlist.yml ✅
sources/topic_taxonomy.yml   ✅
config.yml                ✅
```

---

## 7. Core Workflow Details

## 7.1 Scheduler / Trigger Layer ✅

### Function

Decides when the system runs and which workflow mode should be executed.

### Trigger Types

```text
Daily schedule trigger       ✅ .github/workflows/daily.yml (weekdays 23:00 UTC = 07:00 CST)
Weekly review trigger        ✅ .github/workflows/weekly_review.yml (Friday 10:00 UTC)
Monthly strategic review     ✅ .github/workflows/monthly_review.yml (28th of month)
Manual trigger               ✅ workflow_dispatch in all three .github/workflows files
API webhook                  ❌ not implemented
GitHub event trigger         ❌ not implemented
Special event trigger        ❌ not implemented
```

### Recommended Schedule

```text
Daily: weekday morning       ✅ implemented (23:00 UTC / 07:00 CST)
Weekly: Friday evening       ✅ implemented (10:00 UTC / 18:00 CST)
Monthly: final working day   ⚠️ approximated to 28th; does not detect last working day exactly
Special: event-driven        ❌ not implemented
```

---

## 7.2 Source Collector Layer ✅

### Function ✅

Collects raw information from fixed high-quality sources and optional open web search.

### Principle ✅

```text
Fixed high-quality sources first.
Open search second.
Original source before media interpretation.
Technical evidence before social heat.
```

### Source Categories

```text
Company blogs and official newsroom pages    ✅ RSS feeds in source_registry.yml
AI labs and model release pages              ✅ RSS feeds
Paper sources                                ✅ HuggingFace Daily Papers API + arXiv API
GitHub and open-source sources               ✅ GitHub Search API (daily + weekly trending)
Startup and funding sources                  ✅ via RSS (TechCrunch, etc.) + web search
Big Tech financial and product sources       ✅ via RSS + web search
Technology conference sources                ✅ conference_watchlist.yml (static reference)
Social and community sources                 ✅ Hacker News public API
Macro/geopolitical sources                   ✅ via RSS (Reuters, Bloomberg, FT)
Market data sources for MarketSignalAgent    ❌ Phase 4
```

### Web Search ✅

Added in Phase 3 gap-fill. Uses the Anthropic built-in `web_search_20250305` tool (no additional API key required). Runs 10 targeted queries per day covering AI, robotics, chips, startups, Big Tech, and China Tech.

---

## 7.3 Source Normalization & Deduplication Layer ✅

### Function ✅

Converts raw items into standardized event objects and removes duplicate stories.

### Standard Event Fields ✅

```json
{
  "event_id": "event-YYYY-MM-DD-{hash12}",
  "canonical_title": "string",
  "summary": "string (first 500 chars of raw content)",
  "source_urls": ["string"],
  "primary_source_url": "string",
  "source_type": "company | paper | github | social | media | filing | conference | macro | market",
  "published_at": "datetime",
  "companies": ["string"],
  "projects": ["string"],
  "papers": ["string"],
  "people": ["string"],
  "topics": ["ai_models", "embodied_ai_robotics", ...],
  "geography": ["string"],
  "event_type": "product_launch | paper | github_trending | funding | ...",
  "importance_score": 0.0,
  "novelty_score": 0.0,
  "reliability_score": 0.0,
  "social_heat_score": 0.0,
  "metadata": {"source_name": "...", ...}
}
```

**Implementation notes:**
- Topic tagging is keyword-based (no Claude call) — fast and cheap
- Company tagging is keyword-based against `company_watchlist.yml` names and aliases
- Deduplication by title hash (MD5 of sorted tokens)
- `metadata` field carries source-specific data (HN score, GitHub stars, arXiv authors) downstream

### Source Priority ✅

```text
Official company / paper / filing / repository  → priority 1 → reliability 0.95
  > conference official page / reputable media  → priority 2 → reliability 0.75
  > specialist analyst / researcher comment     → priority 3 → reliability 0.55
  > social media discussion                     → priority 4 → reliability 0.35
  > aggregated blogs                            → priority 5 → reliability 0.15
```

---

## 7.4 Topic & Sector Analysis Workflow ✅

### Function ✅

Analyzes technology developments by topic rather than by raw news order.

### Topic Taxonomy ✅ `sources/topic_taxonomy.yml`

```text
AI Models / Foundation Models           ✅
AI Agents / Agentic Workflow            ✅
Embodied AI / Robotics                  ✅
Autonomous Systems / Drones             ✅
AI Infrastructure / Inference / Chips   ✅
Developer Tools / Open Source           ✅
Hardware / Devices / Wearables          ✅
Semiconductors / Compute Supply Chain   ✅
Big Tech Strategy                       ✅
Startups / Unicorns / Funding           ✅
Papers / Research Frontiers             ✅
GitHub Trending / Open-source Projects  ✅
Social Media Product Reviews            ✅
Macro / Geopolitical Impact on Tech     ✅
```

### Trend Status Labels ✅

```text
accelerating · cooling · reversing · fragmented · unchanged · newly_emerging · hype_spike
```

---

## 7.5 Company / Startup Analysis Layer ✅

All templates implemented in `prompts/company_analysis.md` and `scripts/analyze_companies.py`.

### New Hot Startup Template ✅
### Existing Unicorn / Mature Company Template ✅
### Big Tech Template ✅

---

## 7.6 Paper / Research Analysis Layer ✅

### Sources ✅

```text
Hugging Face Daily Papers   ✅ live API
arXiv cs.AI / cs.LG / cs.RO / cs.CV / cs.CL  ✅ live API (rate-limited politely)
Papers with Code trending   ⚠️ RSS feed only (not Papers with Code API)
Semantic Scholar trending   ❌ not fetched (API key optional, not yet integrated)
OpenReview conference pages ❌ not fetched
```

### Conference Watch ✅ `sources/conference_watchlist.yml`

All 15 conferences listed. Used as reference for paper context; conference pages not scraped.

### Selection Criteria ✅

Implemented in `prompts/paper_analysis.md` with novelty_score, impact_score, overall_score fields.

---

## 7.7 GitHub Project Analysis Layer ✅

### Confirmed Rule ✅

```text
Language unrestricted.              ✅
Only Top 3 high-signal repos.       ✅
Filter toy projects / thin wrappers.  ✅ 7-rule filter in prompts/github_project_analysis.md
```

### Ranking Criteria ✅

6-dimension scoring: pain_point, star_velocity, maintenance, documentation, authority_signals, topic_relevance.

### Filter-Out Rules ✅

All 7 filter-out rules implemented in the analysis prompt.

---

## 7.8 Social Signal Analysis Layer ⚠️

### Confirmed Rule ⚠️

```text
X + Hacker News first.              ⚠️ HN ✅; X API not connected (no X_BEARER_TOKEN)
Reddit / YouTube as supplements.    ❌ not integrated
Only analyze for already-hot items. ✅ trigger condition enforced
Do not force analysis for ordinary news.  ✅
```

### Trigger Conditions ✅

Implemented in `scripts/analyze_social_signals.py` — fires when HN score ≥ 200 or social_heat_score ≥ 0.5 or GitHub stars spike > 500/day.

### Output Dimensions ✅

positive_points, negative_points, controversies, authority_opinions, community_consensus, hype_risk.

---

## 7.9 Macro / Geopolitical Impact Layer ✅

### Confirmed Inclusion Criteria ✅

All 8 inclusion criteria implemented as keyword filter + Claude analysis in `scripts/analyze_macro_impact.py`.

### Exclusion Criteria ✅

Implemented via Claude prompt in `prompts/macro_impact_analysis.md`.

### Required Questions ✅

All 4 required questions are fields in the analysis output schema.

---

## 7.10 TechDailyState Blackboard ✅

### Implementation ✅ `scripts/state.py`

```python
class TechDailyState:
    run_id: str
    run_date: str
    time_window: str

    raw_events: list[RawEvent]
    normalized_events: list[NormalizedEvent]

    topic_summaries: dict[str, TopicSummary]
    company_analyses: dict[str, CompanyAnalysis]
    paper_analyses: dict[str, PaperAnalysis]
    github_project_analyses: dict[str, ProjectAnalysis]
    social_signal_analyses: dict[str, SocialSignalAnalysis]
    macro_impact_analyses: dict[str, MacroImpactAnalysis]

    company_mentions: dict[str, list[EventID]]
    project_mentions: dict[str, list[EventID]]
    paper_mentions: dict[str, list[EventID]]

    previous_reports: list[Report]           # last 7 daily reports
    weekly_reviews: list[Report]             # last 4 weekly reviews ✅
    monthly_reviews: list[Report]            # last 3 monthly reviews ✅
    recent_topic_trends: list[dict]          # last 30 days ✅
    recent_company_mentions: list[dict]      # last 90 days ✅
    open_predictions: list[Prediction]

    prediction_updates: list[PredictionUpdate]
    new_predictions: list[Prediction]

    source_warnings: list[str]
    confidence_flags: list[str]
    signal_level: str                        # low | normal | high
    final_report: str
```

---

## 7.11 Historical Memory Retrieval Layer ✅

### Function ✅

Reads historical reports, prediction logs, weekly reviews, monthly reviews, watchlists, and market signal logs.

### Required Read Objects

```text
1.  Last 7 daily reports                    ✅
2.  Last 4–8 weekly reviews                 ✅ (4 loaded)
3.  Last 3–6 monthly strategic reviews      ✅ (3 loaded)
4.  Last 30 days of topic_trends            ✅
5.  Last 90 days of company mentions        ✅
6.  All open predictions                    ✅
7.  Recently resolved predictions           ⚠️ available in prediction_log.jsonl but not separately loaded into state
8.  Recent prediction performance           ⚠️ Brier score computed at review time, not loaded daily
9.  user_preferences.yml                    ✅ loaded at report generation
10. company_watchlist.yml                   ✅ loaded by analyze_companies.py
11. startup_watchlist.yml                   ⚠️ not explicitly loaded; startups covered via web search + RSS
12. project_watchlist.yml                   ⚠️ not yet created (GitHub tracking is event-driven)
13. paper/topic watchlist                   ✅ via topic_taxonomy.yml and paper_source_registry.yml
14. macro_watchlist.yml                     ✅ loaded by analyze_macro_impact.py
15. market_signal_log.jsonl                 ❌ Phase 4
```

### Memory Layers ✅

```text
Daily memory:    7 full daily reports + 30 days topic trends  ✅
Weekly memory:   4 weekly reviews                              ✅
Monthly memory:  3 monthly strategic reviews                   ✅
Prediction memory: all open predictions                        ✅
Market memory:   not loaded                                    ❌ Phase 4
```

---

## 7.12 Prediction Update Engine ✅

### Function ✅ `scripts/update_predictions.py`

Updates open predictions using new evidence. Signal level detection (low/normal/high) drives prediction count for the day.

### Prediction Focus ✅

All 8 focus areas implemented in `prompts/prediction_update.md`.

### Evidence Impact Labels ✅

```text
strengthens · weakens · neutral · contradicts · resolves_true · resolves_false · needs_more_data
```

---

## 7.13 New Prediction Generation Engine ✅

### Function ✅ `scripts/update_predictions.py`

### Rules ✅

```text
Generate 0–2 predictions on low-signal days.    ✅
Generate 3–5 predictions on normal days.        ✅
Generate 5–7 predictions on high-signal days.   ✅
Every prediction: time horizon, probability, evidence, resolution criteria, falsification condition.  ✅
```

---

## 7.14 Report Generation Layer ✅

### Daily Report Structure ✅ `prompts/daily_brief.md`

```markdown
# Tech Daily Brief — YYYY-MM-DD

## 1.  今日一句话判断          ✅
## 2.  Executive Summary       ✅
## 3.  Top Developments        ✅
## 4.  Technology Radar        ✅
## 5.  GitHub Trending         ✅
## 6.  Papers & Research       ✅
## 7.  Startup / Unicorn Watch ✅
## 8.  Big Tech Moves          ✅
## 9.  China Tech              ✅
## 10. Social Media Signal     ✅
## 11. Macro & Geopolitical    ✅
## 12. Market Signal           ⚠️ section defined; content skipped until Phase 4
## 13. Open Prediction Updates ✅
## 14. New Predictions         ✅
## 15. Watchlist Changes       ✅
## 16. Source Coverage Notes   ✅
## 17. Appendix: Source Links  ✅
```

### Reporting Style ✅

Conclusion → direct reason → key evidence → uncertainty → signals to monitor.

---

## 8. Digital Oracle-Inspired Internal Reasoning Principles ✅

All four reasoning principles are embedded in the analysis prompts:

```text
8.1 Signal Routing              ✅ in topic_analysis.md and company_analysis.md
8.2 Multi-Signal Cross-Validation  ✅ signal_classification field (strong_trend / short_term_hype / hidden_opportunity / false_breakthrough)
8.3 Time Stratification         ✅ short/medium/long term signal fields in topic summaries
8.4 Contradiction Analysis      ✅ contradictions field in TopicSummary
8.5 Signals to Monitor          ✅ signals_to_monitor field in predictions and GitHub analyses
```

---

## 9. MarketSignalAgent Design ❌ Phase 4/5

## 9.1 Purpose ❌

Not implemented. The prompt template (`prompts/market_signal.md`) is written and documents the full Sensor Fusion design. The data stub files exist. The runner script (`scripts/run_market_signal.py`) has not been created.

## 9.2 Implementation Priority

```text
Phase 1: Complete core Tech Daily report and historical storage.  ✅ Done
Phase 2: Complete prediction_log and weekly/monthly review.       ✅ Done
Phase 3: Add prompt-only MarketSignalAgent.                       ← Next step for market work
Phase 4: Add provider-based market data fetching and scorecard.   ❌
```

## 9.3–9.7 Sensor Fusion Model, Sensors, Workflow, Output Format, Schema

All documented in this file and in `prompts/market_signal.md`. Not yet implemented in code.

---

## 10. API and Token Strategy

## 10.1 Design Principle ✅

Staged implementation:

```text
Stage 1: Low-friction sources and connectors.                     ✅
Stage 2: Read-only API tokens for stability and rate limits.      ✅ (GITHUB_TOKEN, HF_TOKEN)
Stage 3: Paid APIs only after the module proves useful.           ❌ (planned)
```

---

## 10.2 No API or Optional API Sources ✅

```text
Company websites / blogs / newsroom pages    ✅ RSS feeds
Big Tech official announcements              ✅ RSS feeds
AI lab blogs                                 ✅ RSS feeds
Tech conference websites                     ✅ reference data (conference_watchlist.yml)
General news websites                        ✅ RSS feeds
arXiv basic queries                          ✅ public API, polite rate limiting
GitHub public repository pages               ✅ Search API with GITHUB_TOKEN
Hugging Face public pages                    ✅ Daily Papers API with HF_TOKEN
SEC EDGAR basic queries                      ⚠️ User-Agent header set; no active queries yet
World Bank / US Treasury / central banks     ❌ not fetched
Hacker News public API                       ✅
```

### Notes ✅

```text
arXiv: rate-limited (0.5s between requests)  ✅
SEC EDGAR: User-Agent header uses SEC_USER_EMAIL env var  ✅
```

---

## 10.3 Strongly Recommended APIs / Tokens

### GitHub ✅

```text
GITHUB_TOKEN  ✅ read public repos for trending; write to this repo for committing reports
```

Permission recommendation (implemented):

```text
Read public repos + Contents write on Tech-Daily-Oracle repo only
```

### Hugging Face ✅

```text
HF_TOKEN  ✅ read-only; used for Daily Papers API
```

### Notion ✅

```text
NOTION_API_KEY      ✅ implemented in scripts/publish_notion.py
NOTION_DATABASE_ID  ✅ configurable via env var or config.yml

Enabled by setting config.notion.enabled: true
Page title property name configurable via NOTION_TITLE_PROPERTY env var (default: "Name")
Date property name configurable via NOTION_DATE_PROPERTY env var (default: "Date")
```

### Email ❌

```text
Not implemented. config.yml has a placeholder for future notification output.
```

---

## 10.4 APIs Usually Needed Later or Paid

### X / Twitter ⚠️

```text
X_API_KEY / X_BEARER_TOKEN  ❌ not connected
Social signals currently come from HN + web search only.
```

### Reddit ❌

```text
Not integrated. Planned as supplement in Phase 3.
```

### YouTube Data API ❌

```text
Not integrated. Planned as supplement for hardware reviews.
```

### Market Data APIs ❌ Phase 4/5

```text
POLYGON_API_KEY / FINNHUB_API_KEY / ALPHA_VANTAGE_API_KEY  ❌
yfinance (free, unofficial): can be added in Phase 4 without a key
```

### Startup / Funding Data APIs ❌

```text
Crunchbase / PitchBook / CB Insights  ❌ not integrated
Startup signals come from RSS (TechCrunch, etc.) + web search.
```

---

## 10.5 Minimum Recommended Credentials by Stage

### Stage 1: Tech Daily MVP ✅

```text
ANTHROPIC_API_KEY     ✅ required
GITHUB_TOKEN          ✅ strongly recommended
HF_TOKEN              ✅ strongly recommended
NOTION_API_KEY        ✅ optional; publisher implemented
NOTION_DATABASE_ID    ✅ optional; publisher implemented
SEC_USER_EMAIL        ✅ optional; used in User-Agent header
```

### Stage 2: Stable Research and Source Monitoring ✅

```text
SEMANTIC_SCHOLAR_API_KEY  ❌ not yet integrated
GITHUB_TOKEN (higher read stability)  ✅
RSS source registry  ✅ sources/source_registry.yml
```

### Stage 3: SocialSignalAgent ❌

```text
X_BEARER_TOKEN         ❌ not connected
REDDIT_CLIENT_ID/SECRET  ❌ not integrated
YOUTUBE_API_KEY        ❌ not integrated
```

### Stage 4: MarketSignalAgent ❌

```text
POLYGON_API_KEY or equivalent  ❌
Options data provider  ❌
SEC_USER_EMAIL  ✅
```

### Stage 5: Startup Intelligence Expansion ❌

```text
Crunchbase / Dealroom / PitchBook  ❌
```

---

## 10.6 Connector Permission Policy ✅

```text
GitHub repository:  ✅ read public + write to this repo only
Notion:             ✅ integrated via one database (not workspace-wide)
Google Drive:       ❌ not connected
Email:              ❌ not connected
Canva:              ❌ not needed
```

---

## 11. Publishing and Storage

### Required Storage ✅

```text
GitHub repository  ✅
  Daily reports      ✅ reports/daily/YYYY-MM-DD.md
  Weekly reviews     ✅ reports/weekly/YYYY-Www.md
  Monthly reviews    ✅ reports/monthly/YYYY-MM.md
  Prediction logs    ✅ data/prediction_log.jsonl
  Market signal logs ⚠️ stub file exists; Phase 4
  Scorecards         ✅ data/prediction_scorecard.csv
  Source registry    ✅ sources/
  Prompt templates   ✅ prompts/
  Configuration      ✅ config.yml
```

### Recommended Reading Output ✅

```text
Notion  ✅ scripts/publish_notion.py
  Daily report reading page  ✅
  Weekly and monthly review pages  ⚠️ run_weekly/monthly_review.py do not call publish_notion yet
  Report database with tags  ⚠️ basic title + date properties; no topic tags yet
```

### Optional Notification Output ❌

```text
Email or Slack  ❌ not implemented
```

---

## 12. Weekly and Monthly Review ✅

### Weekly Review ✅ `prompts/weekly_review.md` + `scripts/run_weekly_review.py`

All 13 sections implemented in the prompt template.

### Monthly Review ✅ `prompts/monthly_review.md` + `scripts/run_monthly_review.py`

All 11 sections implemented in the prompt template.

**Known gap:** Weekly and monthly review outputs are not yet published to Notion automatically. Only daily reports call `publish_to_notion`.

---

## 13. Implementation Roadmap

### Phase 1: Core Daily MVP ✅ Complete

```text
✅ GitHub Actions schedule
✅ Source registry (25+ RSS feeds, HN, HF, arXiv, GitHub)
✅ Daily report prompt (17 sections)
✅ GitHub storage (Markdown reports committed)
✅ Notion output (scripts/publish_notion.py; enable in config.yml)
✅ Basic prediction_log (JSONL, append-only)
```

### Phase 2: Historical Memory and Reviews ✅ Complete

```text
✅ Daily report memory (last 7 reports loaded into state)
✅ Weekly review (run_weekly_review.py + prompt)
✅ Monthly review (run_monthly_review.py + prompt)
✅ Prediction update workflow (update + generate in one script)
✅ Prediction scorecard (Brier score in score_predictions.py)
✅ Weekly/monthly history loaded into state (4 weekly + 3 monthly + 30d trends + 90d mentions)
```

### Phase 3: Structured Source Pipelines ✅ Complete

```text
✅ GitHub project analyzer (6-dimension scoring, top-3 filter)
✅ Paper analyzer (novelty + impact scoring, HF Daily Papers + arXiv)
✅ Company / startup analyzer (4 category templates)
✅ Macro impact analyzer (keyword filter + transmission path analysis)
✅ Social signal analyzer (HN-driven; limited mode — X not connected)
✅ Web search (Anthropic built-in web_search tool, 10 queries/day)
```

### Phase 4: MarketSignalAgent MVP ❌

```text
❌ Prompt-only stock watch section (prompt written; runner not created)
❌ Public information + basic price / options data
❌ market_signal_log.jsonl (stub exists; not populated)
```

**To implement Phase 4:**
1. Write `scripts/run_market_signal.py`
2. Add `yfinance` to requirements.txt for basic price data
3. Hook into `run_daily.py` after report generation
4. Populate market_signal_log.jsonl and market_signal_scorecard.csv

### Phase 5: MarketSignalAgent Advanced ❌

```text
❌ Market data APIs (Polygon, Finnhub, or similar)
❌ Options analytics (IV, put/call, skew)
❌ Positioning and flow data
❌ Market signal scorecard backtesting
❌ Buy/sell observation point tracking
```

### Phase 6: Production Hardening ⚠️ Partial

```text
✅ Structured schemas (dataclasses in state.py)
✅ Parallel fetching (asyncio.gather in collect_sources.py)
✅ Source coverage warnings (state.source_warnings, state.confidence_flags)
⚠️ Provider abstraction (claude_client.py wraps SDK; no fallback providers)
⚠️ Partial failure tolerance (try/except on each pipeline step; no retry logic)
❌ CI tests (no test files)
❌ Parser maintenance via Codex Automations
❌ Retry with exponential backoff on network errors
❌ Weekly/monthly Notion publish integration
❌ X API social signal integration
```

---

## 14. Tooling Recommendation

### Claude API ✅

Used for all analysis and generation. Model: `claude-sonnet-4-6` (default). Prompt caching enabled on all system prompts via `cache_control: ephemeral`. Web search via built-in `web_search_20250305` tool.

### GitHub Repository ✅

Used for long-term memory, version control, prediction logs, prompt templates, and configuration.

### Notion ✅

Used for reading-friendly daily report output. Publisher implemented in `scripts/publish_notion.py`.

### GitHub Actions ✅

Used for scheduled automation. Three workflow files cover daily, weekly, and monthly runs.

### Codex Automations ❌

Planned for Phase 6: parser maintenance, source registry updates, CI failures, schema consistency checks.

---

## 15. Boundaries and Risk Controls

### Do Not Do in MVP ✅

```text
Automated trading             ✅ enforced (MarketSignalAgent not implemented)
Definitive personal financial advice  ✅ enforced
Stock price certainty claims  ✅ enforced
Unverified social media rumor amplification  ✅ enforced (social_heat_score separated from factual evidence)
Macro news without tech path  ✅ enforced (macro keyword filter + transmission path requirement)
Large-scale scraping          ✅ enforced (RSS + public APIs only; rate limiting on arXiv)
```

### Risk Controls ✅

```text
Source reliability score       ✅ reliability_score on NormalizedEvent
Social signal vs factual       ✅ social_heat_score is separate field
Official source priority       ✅ source priority tiers 1–5
Prediction resolution criteria ✅ required field on every prediction
Brier Score                    ✅ score_predictions.py
Weekly bad prediction review   ✅ weekly_review.md section 12
MarketSignalAgent separated    ✅ (not yet implemented; separation by design)
Source coverage warning        ✅ state.source_warnings
Minimum connector permissions  ✅ GITHUB_TOKEN scoped to this repo only
```

---

## 16. Final Design Summary ✅

Tech Daily Agent has been built as:

```text
✅ Personal technology intelligence memo
✅ + technology radar
✅ + GitHub / paper / startup / Big Tech monitor
✅ + China Tech independent section
✅ + social signal analyzer (HN; X pending)
✅ + macro impact filter
✅ + prediction memory and review system
❌ + optional MarketSignalAgent based on Sensor Fusion (Phase 4)
```

The most important design principle:

> The system should not merely summarize technology news. It should convert technology news, papers, open-source projects, company moves, social evaluation, macro events, and market signals into trackable judgments that can be reviewed and corrected over time.

**This principle is enforced through:**
- Every topic analysis producing a `signal_classification` (not just a summary)
- Every prediction requiring `resolution_criteria` and `falsification_condition`
- Weekly reviews including `错误类型分析` (error type analysis)
- Brier score tracking on all predictions
- `contradictions` field on every topic summary
