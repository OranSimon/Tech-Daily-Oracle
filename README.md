# Tech Daily Oracle

A personal technology intelligence system that generates a structured daily brief covering AI models, robotics, chips, startups, Big Tech, China tech, GitHub trending, research papers, and macro/geopolitical impacts. Output is in Chinese with English proper nouns preserved.

## What It Does

Every morning the system runs a 13-step pipeline:

1. Loads historical context (7 daily + 4 weekly + 3 monthly reports, 30-day topic trends, 90-day company mentions)
2. Collects from RSS feeds, Hacker News, Hugging Face, arXiv, GitHub Trending, and Claude-powered web search
3. Normalizes and deduplicates events (title-hash deduplication, metadata propagation)
4. Analyzes topics, companies, papers, GitHub projects, social signals, and macro impact via Claude
5. Updates open predictions with new evidence
6. Generates new falsifiable predictions with resolution criteria
7. Produces a structured ~20-minute read daily brief
8. Saves report locally and optionally publishes to Notion

Weekly reviews synthesize topic trends and score predictions (Brier score). Monthly reviews update long-term technology theses.

## Implementation Status

| Phase | Status | What |
|-------|--------|------|
| 1 | ✅ Done | Core pipeline, all analyzers, report generation, prediction engine, storage |
| 2 | ✅ Done | Historical memory (weekly/monthly reviews, trend history), Notion publisher |
| 3 | ✅ Done | Web search via Anthropic built-in tool, collect_sources async multi-source |
| 4 | ❌ Not started | MarketSignalAgent (prompt-only financial signal layer) |
| 5 | ❌ Not started | MarketSignalAgent with live market data APIs |
| 6 | ⚠️ Partial | GitHub Actions workflows done; test suite, retry logic, X API not yet |

## Repository Structure

```
config.yml                      # Main configuration
requirements.txt                # Python dependencies

prompts/                        # Claude prompt templates
  daily_brief.md                # Daily report structure and style guide
  topic_analysis.md             # Per-topic trend analysis
  company_analysis.md           # Company event analysis
  paper_analysis.md             # Research paper evaluation
  github_project_analysis.md    # GitHub repo signal scoring
  social_signal_analysis.md     # Social reaction analysis
  macro_impact_analysis.md      # Geopolitical/macro filtering
  prediction_update.md          # Open prediction update engine
  new_prediction.md             # New prediction generator
  weekly_review.md              # Weekly synthesis
  monthly_review.md             # Monthly strategic review
  source_quality.md             # Source reliability scoring

sources/                        # Watchlists and source registries
  source_registry.yml           # RSS feeds and API endpoints
  company_watchlist.yml         # Tracked companies by category
  startup_watchlist.yml         # Hot startups to track
  conference_watchlist.yml      # AI/ML/robotics conferences
  paper_source_registry.yml     # Paper source configuration
  github_trending_config.yml    # GitHub filtering rules
  influencer_watchlist.yml      # Authority accounts to track
  macro_watchlist.yml           # Macro/geopolitical triggers
  topic_taxonomy.yml            # Technology topic taxonomy

scripts/                        # Python orchestration (17 modules)
  run_daily.py                  # Main entry point (13-step orchestrator)
  run_weekly_review.py          # Weekly review runner
  run_monthly_review.py         # Monthly review runner
  collect_sources.py            # Async multi-source collector
  normalize_sources.py          # Normalization and deduplication
  analyze_topics.py             # Topic sector analysis
  analyze_companies.py          # Company event analysis
  analyze_papers.py             # Paper quality analysis
  analyze_github_projects.py    # GitHub project signal analysis
  analyze_social_signals.py     # Social signal analysis
  analyze_macro_impact.py       # Macro/geopolitical analysis
  update_predictions.py         # Prediction update engine
  score_predictions.py          # Brier score computation
  generate_report.py            # Report generation with history context
  storage.py                    # File I/O and persistence
  state.py                      # TechDailyState blackboard dataclass
  claude_client.py              # Anthropic SDK wrapper with prompt caching
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
  user_preferences.yml          # Personal configuration

workflows/                      # GitHub Actions YAML files
  daily.yml                     # Weekdays 23:00 UTC
  weekly_review.yml             # Fridays 10:00 UTC
  monthly_review.yml            # 28th of each month
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

**Required:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

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

### 4. Run manually

```bash
# Today's daily brief
python scripts/run_daily.py

# Specific date (useful for backfill)
python scripts/run_daily.py --date 2026-05-08

# Weekly review
python scripts/run_weekly_review.py

# Monthly review
python scripts/run_monthly_review.py --month 2026-05
```

Output: `reports/daily/YYYY-MM-DD.md`

---

## GitHub Actions (Automated)

Copy the three workflow files to `.github/workflows/`:

```bash
mkdir -p .github/workflows
cp workflows/*.yml .github/workflows/
```

Add these **Repository Secrets** (Settings → Secrets and variables → Actions):

| Secret | Required | Notes |
|--------|----------|-------|
| `ANTHROPIC_API_KEY` | Yes | Main AI engine |
| `HF_TOKEN` | Recommended | Hugging Face access |
| `NOTION_API_KEY` | Optional | If publishing to Notion |
| `NOTION_DATABASE_ID` | Optional | With above |

`GITHUB_TOKEN` is injected automatically by Actions — no manual secret needed.

**Schedule:**
- Daily brief: weekdays at 23:00 UTC (07:00 CST next day)
- Weekly review: Fridays at 10:00 UTC
- Monthly review: 28th of each month

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

## Claude Routine Setup

To run this via Claude's Routine feature (scheduled prompts in Claude.ai):

1. Set a Claude Routine to run daily at your preferred time
2. Include these environment variables in the routine configuration:
   - `ANTHROPIC_API_KEY` — required
   - `GITHUB_TOKEN`, `HF_TOKEN`, `NOTION_API_KEY`, `NOTION_DATABASE_ID` — as needed
3. The routine command: `python scripts/run_daily.py`

**Supplying API keys in Claude Routine context:** Claude Routine executes in your shell environment. Supply secrets via:
- Shell profile (`.zshrc` / `.bashrc`) — simplest for local machines
- A `.env` file loaded by a wrapper script
- System keychain accessed via a launcher script

The `ANTHROPIC_API_KEY` for Claude Routine itself and for the script's Claude API calls can be the same key.

---

## Design Principles

- **Fixed high-quality sources first.** Open web search fills gaps only — RSS/HN/HF/arXiv/GitHub are the primary signal layer.
- **Technical evidence before social heat.** Official announcements > media reports > social discussion.
- **No hype amplification.** Social signals only validate already-strong primary signals.
- **Every prediction must be falsifiable.** Specific horizon date, resolution criteria, and falsification condition required.
- **Multi-signal cross-validation.** Every topic classified as `strong_trend | short_term_hype | hidden_opportunity | false_breakthrough | unclear`.
- **Historical continuity.** Each daily report is generated with 7 prior reports, 4 weekly reviews, 3 monthly reviews, and 90 days of trend data as context.
- **Contradiction analysis.** Signal conflicts are information, not noise.
- **Prompt caching on all system prompts.** Reduces cost on daily repeated invocations.
