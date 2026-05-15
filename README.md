# Tech Daily Oracle

A personal technology intelligence system that generates a structured daily brief covering AI models, robotics, chips, startups, Big Tech, China tech, GitHub trending, research papers, cross-domain science breakthroughs, market signals, and macro/geopolitical impacts. Output is in Chinese with English proper nouns preserved.

## What It Does

Every morning the system runs a 15-step pipeline:

1. Loads historical context (7 daily + 4 weekly + 3 monthly reports, 30-day topic trends, 90-day company mentions)
2. Collects from 27+ RSS feeds, Hacker News, Hugging Face, arXiv, GitHub Trending, and 15 Claude-powered web search queries
3. Collects live market data via yfinance/FRED for watchlist tickers (Phase 5 — optional, off by default)
4. Collects trending snapshots from OSSInsight (GitHub velocity data) and HuggingFace (daily papers + models)
5. Normalizes and deduplicates events (title-hash deduplication, topic tagging, cross-domain importance boost)
6. Analyzes topics, companies, papers, GitHub projects, social signals, and macro impact via Claude
7. Analyzes trending items — acceleration tracking, cross-list hit detection (GitHub ↔ HF models), LLM batch analysis for new entries
8. Runs MarketSignalAgent for triggered watchlist tickers (Phase 4 — prompt-only financial signal layer)
9. Updates open predictions with new evidence
10. Generates new falsifiable predictions with resolution criteria
11. Produces a structured ~20-minute read daily brief (18 sections, Chinese main text)
12. Saves report locally and optionally publishes to Notion

Weekly reviews synthesize topic trends and score predictions (Brier score). Monthly reviews update long-term technology theses. Both have data guards — weekly requires ≥3 daily reports in the current week; monthly requires ≥2 weekly reviews or ≥10 daily reports in the target month.

## Report Structure (Daily)

| # | Section | Trigger |
|---|---------|---------|
| 1 | 今日一句话判断 | Always |
| 2 | Executive Summary | Always |
| 3 | Top Developments | Always |
| 4 | Technology Radar | Always |
| 5 | GitHub Trending: Top 3 High-Signal Repos | If `github_project_analyses` is non-empty |
| 6 | Papers & Research Frontiers | Always |
| 7 | Startup / Unicorn Watch | If funding/launch signal present |
| 8 | Big Tech & Major Company Moves | If watchlist company event present |
| 9 | China Tech | Always |
| 10 | Social Media / Community Signal | If strong social heat detected |
| 11 | Macro & Geopolitical Impact on Tech | If qualifying macro event present |
| 12 | Cross-Domain Signals | If science/health/space/global event meets tech-implication gate (≤5 items) |
| 13 | Market Signal / Stock Watch | If `market_signal.enabled: true` and a watchlist ticker triggered |
| 14 | Open Prediction Updates | If open predictions exist |
| 15 | New Predictions | Always (3–5 per normal signal day) |
| 16 | Watchlist Changes | If additions recommended |
| 17 | Source Coverage & Confidence Notes | Always |
| 18 | Appendix: Source Links | Always |

## Implementation Status

| Phase | Status | What |
|-------|--------|------|
| 1 | ✅ Done | Core pipeline, all analyzers, report generation, prediction engine, storage |
| 2 | ✅ Done | Historical memory (weekly/monthly reviews, trend history), Notion publisher |
| 3 | ✅ Done | OSSInsight + HuggingFace trending engine; cross-domain topics (science, space, health); multi-provider AI fallback with auto-continuation; HN `general_interesting` topic; 15 web search queries |
| 4 | ✅ Done | MarketSignalAgent — prompt-only financial signal layer; per-ticker Claude calls gated by company event importance; pre-formatted `report_snippet` injected into Section 13 |
| 5 | ✅ Done | MarketSignalAgent with live market data (yfinance price/options, FRED macro); gated by `market_signal.live_data: true`; all failures non-fatal |
| 6 | ⚠️ Partial | GitHub Actions workflows done; OSSInsight retry + github.com/trending HTML fallback done; test suite and X/Twitter API not yet |

## Repository Structure

```
config.yml                      # Main configuration
requirements.txt                # Python dependencies

prompts/                        # Claude prompt templates
  daily_brief.md                # Daily report structure and style guide (18 sections)
  topic_analysis.md             # Per-topic trend analysis
  company_analysis.md           # Company event analysis
  paper_analysis.md             # Research paper evaluation
  github_project_analysis.md    # GitHub repo signal scoring
  social_signal_analysis.md     # Social reaction analysis
  macro_impact_analysis.md      # Geopolitical/macro filtering
  trending_analysis.md          # Trending item LLM analysis (batch, new entries only)
  market_signal.md              # MarketSignalAgent output format (Phase 4+)
  prediction_update.md          # Open prediction update engine
  new_prediction.md             # New prediction generator
  weekly_review.md              # Weekly synthesis (14 sections)
  monthly_review.md             # Monthly strategic review (11 sections)
  source_quality.md             # Source reliability scoring

sources/                        # Watchlists and source registries
  source_registry.yml           # 27+ RSS feeds and API endpoints
  topic_taxonomy.yml            # Technology topic taxonomy (20 topics)
  company_watchlist.yml         # Tracked companies by category
  startup_watchlist.yml         # Hot startups to track
  conference_watchlist.yml      # AI/ML/robotics conferences
  paper_source_registry.yml     # Paper source configuration
  github_trending_config.yml    # GitHub filtering rules
  influencer_watchlist.yml      # Authority accounts to track
  macro_watchlist.yml           # Macro/geopolitical triggers
  market_watchlist.yml          # Tickers tracked by MarketSignalAgent (Phase 4+)

scripts/                        # Python orchestration (22 modules)
  run_daily.py                  # Main entry point (15-step orchestrator)
  run_weekly_review.py          # Weekly review runner
  run_monthly_review.py         # Monthly review runner
  collect_sources.py            # Async multi-source collector (RSS/HN/HF/arXiv/GitHub)
  collect_trending.py           # OSSInsight + HuggingFace trending data collector
  collect_market_data.py        # yfinance price/options + FRED macro collector (Phase 5)
  normalize_sources.py          # Normalization, deduplication, topic/company tagging
  analyze_topics.py             # Topic sector analysis
  analyze_companies.py          # Company event analysis
  analyze_papers.py             # Paper quality analysis
  analyze_github_projects.py    # GitHub project signal analysis
  analyze_social_signals.py     # Social signal analysis
  analyze_macro_impact.py       # Macro/geopolitical analysis
  analyze_trending.py           # Trending analysis: acceleration, cross-list, LLM batch
  analyze_market_signals.py     # MarketSignalAgent: per-ticker financial signal (Phase 4+)
  update_predictions.py         # Prediction update engine
  score_predictions.py          # Brier score computation
  generate_report.py            # Report generation with history context
  storage.py                    # File I/O and persistence
  state.py                      # TechDailyState blackboard + domain dataclasses
  claude_client.py              # Multi-provider AI client (Claude/GPT/Gemini + auto-continuation)
  publish_notion.py             # Markdown → Notion blocks publisher

reports/
  daily/YYYY-MM-DD.md           # Daily briefs
  weekly/YYYY-Www.md            # Weekly reviews
  monthly/YYYY-MM.md            # Monthly strategic reviews

data/
  prediction_log.jsonl          # All predictions (open + resolved)
  prediction_scorecard.csv      # Brier score tracking
  source_events.jsonl           # Normalized event archive
  topic_trends.jsonl            # Daily topic trend history
  company_mentions.jsonl        # Company signal history
  paper_mentions.jsonl          # Paper signal history
  project_mentions.jsonl        # GitHub project history
  trending_snapshots.jsonl      # OSSInsight + HuggingFace trending history (acceleration tracking)
  market_signals.jsonl          # MarketSignalAgent outputs by ticker and date (Phase 4+)
  user_preferences.yml          # Personal configuration

.github/workflows/
  daily.yml                     # Mon–Thu 23:00 UTC (07:00 CST)
  weekly_review.yml             # Fri 23:00 UTC — runs daily brief first, then weekly review
  monthly_review.yml            # 1st of month 02:00 UTC (all prior month's data committed)
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

To use only Claude (no fallback providers):
```bash
pip install anthropic httpx pyyaml
```

### 2. Configure environment variables

**Required — at least one AI provider key:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Claude (primary by default)
export OPENAI_API_KEY=sk-...          # GPT (1st fallback by default)
export GEMINI_API_KEY=AIza...         # Gemini (2nd fallback by default)
```
The system tries providers in order. It skips any provider whose key is missing, so you only need the keys for providers you want active.

**Strongly recommended** (more sources, higher quality):
```bash
export GITHUB_TOKEN=github_pat_...   # GitHub Trending + API rate limits
export HF_TOKEN=hf_...               # Hugging Face authenticated access
```

**Optional — Notion publishing:**
```bash
export NOTION_API_KEY=secret_...
export NOTION_DATABASE_ID=...        # 32-char ID from your database URL
```

**Optional — Market signals (Phase 5 live data):**
```bash
export FRED_API_KEY=...              # Free key at fred.stlouisfed.org — CPI, rates, unemployment
```

**Optional — SEC filings:**
```bash
export SEC_USER_EMAIL=your@email.com
```

### 3. Configure `config.yml`

Key flags to set before first run:

```yaml
notion:
  enabled: true          # flip to true once NOTION_API_KEY is set
  database_id: ""        # or set NOTION_DATABASE_ID env var

output:
  push_github: true      # flip to true in production (GitHub Actions)
```

**To enable MarketSignalAgent (Phase 4 — prompt-only signals, no live data needed):**
```yaml
market_signal:
  enabled: true
```

**To add live yfinance/FRED price data (Phase 5):**
```bash
# 1. Uncomment in requirements.txt:
#   yfinance>=0.2.40
#   fredapi>=3.1.0
pip install yfinance fredapi

# 2. Set in config.yml:
market_signal:
  enabled: true
  live_data: true
```

### 4. Run manually

```bash
# Today's daily brief (defaults to yesterday in Asia/Shanghai timezone)
python3 scripts/run_daily.py

# Specific date (useful for backfill)
python3 scripts/run_daily.py --date 2026-05-08

# Force regenerate even if report already exists
python3 scripts/run_daily.py --force

# Weekly review
python3 scripts/run_weekly_review.py

# Monthly review
python3 scripts/run_monthly_review.py --month 2026-05
```

Output: `reports/daily/YYYY-MM-DD.md`

---

## Source Coverage

### RSS Feeds (27+)

| Category | Feeds |
|----------|-------|
| AI Labs | OpenAI Blog, Google DeepMind, Google AI Blog, Meta Engineering, Microsoft Research, NVIDIA Blog, AWS ML Blog, Hugging Face Blog |
| Tech Media | The Verge, TechCrunch, Wired, MIT Technology Review, IEEE Spectrum, Ars Technica |
| Startups / Funding | TechCrunch Startups |
| Open Source | GitHub Blog |
| Chips / Semiconductors | SemiAnalysis, Tom's Hardware |
| China Tech | South China Morning Post Tech |
| Macro / Geopolitical | NYT Technology, Bloomberg Technology, Financial Times Tech |
| Science / Health / Space | Nature News, Quanta Magazine, STAT News, SpaceNews, Science Magazine |

### APIs

| Source | What it provides |
|--------|-----------------|
| Hacker News | Top stories (min_score: 100), concurrent fetch |
| Hugging Face | Daily curated papers, trending models (internal ~7-day score) |
| arXiv | cs.AI, cs.LG, cs.RO, cs.CV, cs.CL (up to 20 papers per category, 2 days back) |
| GitHub Search API | Recent repos by star velocity (daily + weekly windows) |
| OSSInsight | GitHub velocity trending (daily / weekly / monthly), with HTML scrape fallback |
| Claude web search | 15 targeted queries per run (10 CS/AI beats + 5 cross-domain: science, health, space, disasters, materials) |
| yfinance | OHLCV price history, ATM options IV/put-call ratio/skew for watchlist tickers (Phase 5) |
| FRED | Fed funds rate, CPI YoY, unemployment rate (Phase 5) |

### Topic Taxonomy (20 topics)

**Core CS / AI:**
`ai_models` · `ai_agents` · `embodied_ai_robotics` · `autonomous_systems` · `ai_infrastructure` · `developer_tools` · `hardware_devices` · `semiconductors` · `big_tech_strategy` · `startups_unicorns` · `papers_research` · `github_opensource` · `social_signals` · `macro_geopolitical`

**Cross-Domain:**
`general_interesting` (HN ≥300 score, non-tech) · `science_breakthrough` · `health_biotech` · `global_events` · `astronomy_space` · `materials_science`

Cross-domain importance boost: events tagged with both a core tech topic **and** a science/global topic get +0.15 importance score — these rare intersections (e.g. AI + drug discovery, space + compute demand) are prioritized.

---

## MarketSignalAgent (Phase 4/5)

The MarketSignalAgent generates qualitative per-ticker signals using a "sensor fusion" philosophy — it combines public events, market price behavior, options signals, and macro context, rather than relying on price charts alone.

**Phase 4 (prompt-only, default):**
- Triggers when a watchlist ticker's company appears in today's `company_analyses` with medium+ significance
- One Claude call per triggered ticker (up to `max_tickers_per_run: 5`)
- Output: conclusion, base/bull/bear cases, observation points, signals table — pre-formatted as `report_snippet` for Section 13

**Phase 5 (live data, opt-in):**
- Adds yfinance OHLCV history (30d), ATM options IV/put-call/skew, 52w stats
- Adds FRED macro series (fed funds, CPI, unemployment)
- Gate: `market_signal.live_data: true` + `pip install yfinance fredapi`

**Watchlist:** `sources/market_watchlist.yml` — 10 default tickers (NVDA, TSM, AMD, ASML, MSFT, GOOGL, META, AAPL, AMZN, PLTR). Edit to add/remove tickers or change horizons.

**Signal history:** Each triggered signal is logged (without the verbose `report_snippet`) to `data/market_signals.jsonl` for accuracy review in weekly/monthly reports.

---

## AI Provider Fallback

The system uses a provider chain: **Claude → GPT → Gemini** by default. On any API error, rate-limit, or missing key the next provider is tried transparently:

```
[AI] claude (claude-sonnet-4-6) failed: 529 overloaded
[AI] Using fallback provider: gpt (gpt-4o)
```

**Auto-continuation on truncation:** If any report response hits `max_tokens`, Claude automatically resumes via assistant-message prefill (up to 4 continuations), ensuring reports are never cut mid-sentence. This applies to all markdown reports (daily, weekly, monthly). JSON calls (topic analysis, market signals) do not auto-continue — they use a 4096-token budget which is sufficient for structured outputs.

**Model role mapping:** Roles (fast / default / deep) are preserved across providers — a fast Claude call becomes a fast GPT call, not a full-cost one. Models are configured in `config.yml` under `ai_providers`.

**`web_search` is Claude-only** — the `web_search_20250305` built-in tool is Anthropic-specific. If Claude is unavailable when web search runs, those queries are skipped; the rest of the pipeline continues normally with the fallback provider.

**Changing the provider order** — edit `config.yml`:

```yaml
ai_providers:
  order: ["gpt", "claude", "gemini"]   # make GPT primary
```

**Disabling a provider:**

```yaml
ai_providers:
  order: ["claude"]   # Claude only, no fallback
```

---

## Trending Engine

The trending pipeline runs in parallel with source collection on every daily run:

**GitHub velocity data (OSSInsight):**
- `GET /v1/repos/trending?period=past_24_hours` — real star velocity (not total stars)
- 3× retry with exponential backoff (1s, 2s) on transient 5xx errors
- Falls back to scraping `github.com/trending` HTML (stars-today velocity) if OSSInsight is unavailable

**HuggingFace rolling window:**
- Daily papers: aggregates N days of `/api/daily_papers` calls; rank = days_appeared × upvote_sum
- Models: `/api/models?sort=trending` — HF's internal ~7-day sliding trending score

**Acceleration tracking:**
- Every trending item is compared to its history in `data/trending_snapshots.jsonl`
- Verdict: `accelerating | stable | decelerating | new`
- Cross-list detection: exact owner/name match between GitHub and HF model hub → "两个平台同时上榜"

**LLM batch analysis:** New entries (no prior history) are analyzed in a single batched Claude call — one snippet per item, in Chinese. Returning items get programmatic snippets (no API cost).

---

## GitHub Actions (Automated)

Copy the three workflow files to `.github/workflows/`:

```bash
mkdir -p .github/workflows
cp .github/workflows/*.yml .github/workflows/
```

Add these **Repository Secrets** (Settings → Secrets and variables → Actions):

| Secret | Required | Notes |
|--------|----------|-------|
| `ANTHROPIC_API_KEY` | Recommended | Claude — primary provider |
| `OPENAI_API_KEY` | Recommended | GPT — 1st fallback |
| `GEMINI_API_KEY` | Optional | Gemini — 2nd fallback |
| `HF_TOKEN` | Recommended | Hugging Face access |
| `NOTION_API_KEY` | Optional | If publishing to Notion |
| `NOTION_DATABASE_ID` | Optional | With above |
| `FRED_API_KEY` | Optional | Phase 5 macro data (free at fred.stlouisfed.org) |

`GITHUB_TOKEN` is injected automatically by Actions — no manual secret needed.

**Schedule:**
- Daily brief: Mon–Thu at 23:00 UTC (07:00 CST next morning)
- Weekly review: Friday at 23:00 UTC — runs daily brief **then** weekly review in sequence
- Monthly review: 1st of month at 02:00 UTC — all prior month's data is committed by then

**Review guards** (prevents wasted runs when data is insufficient):
- Weekly skips if fewer than 3 daily reports exist in the current week
- Monthly skips if fewer than 2 weekly reviews **and** fewer than 10 daily reports exist in the target month

---

## Notion Setup

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) and create an integration
2. Copy the **Internal Integration Token** → set as `NOTION_API_KEY`
3. Create a database in Notion with at minimum a **Name** (title) property and a **Date** property
4. Open the database, click `...` → **Connections** → connect your integration
5. Copy the database ID from the URL: `notion.so/.../{DATABASE_ID}?v=...`
6. Set `NOTION_DATABASE_ID` or add it to `config.yml`
7. Set `notion.enabled: true` in `config.yml`

The publisher converts the full Markdown report to Notion blocks and handles the 100-block-per-request limit automatically.

---

## Design Principles

- **Fixed high-quality sources first.** Open web search fills gaps — RSS/HN/HF/arXiv/GitHub/OSSInsight are the primary signal layer.
- **Technical evidence before social heat.** Official announcements > media reports > social discussion.
- **No hype amplification.** Social signals only validate already-strong primary signals.
- **Every prediction must be falsifiable.** Specific horizon date, resolution criteria, and falsification condition required.
- **Multi-signal cross-validation.** Every topic classified as `strong_trend | short_term_hype | hidden_opportunity | false_breakthrough | unclear`.
- **Historical continuity.** Each daily report is generated with 7 prior reports, 4 weekly reviews, 3 monthly reviews, and 90 days of trend data as context.
- **Velocity over popularity.** GitHub trending uses stars-today (OSSInsight velocity), not total stars. A 50-star repo gaining 30 stars today outranks a 50k-star repo gaining 5.
- **Contradiction analysis.** Signal conflicts are information, not noise.
- **Prompt caching on all system prompts.** Reduces cost on daily repeated invocations.
- **Idempotency.** Running the same date twice returns the cached report. Use `--force` to regenerate.
- **Graceful degradation.** Every external data source (yfinance, FRED, OSSInsight, HuggingFace) fails non-fatally — the pipeline continues and the report notes the missing coverage.
