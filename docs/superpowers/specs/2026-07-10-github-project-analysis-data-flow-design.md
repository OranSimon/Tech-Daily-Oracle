# GitHub Project Analysis Data-Flow Repair

## Problem

The daily pipeline collects structured GitHub velocity data in a `TrendingSnapshot`, but the GitHub project-analysis step reads only normalized source events. Those events come from a separate GitHub Search collector and may be dominated by newly-created spam repositories or long-lived mega-repositories. A healthy OSSInsight collection can therefore coexist with an empty `github_project_analyses` result.

The current result also collapses distinct states into `{}`: no source candidates, every candidate filtered, and every candidate analysis failed. Per-repository exceptions are swallowed, so the pipeline can report success with zero records after an operational failure. Finally, the daily-report prompt can expose its internal `CRITICAL DATA-INTEGRITY RULE` label and uses the same fallback copy for every empty state.

## Considered Approaches

### 1. Snapshot-primary candidate flow with corpus fallback (selected)

Convert `TrendingSnapshot.github_items` into a small, typed repository-candidate representation. Analyze these candidates first and fall back to normalized GitHub events only when the snapshot contains no GitHub items. This preserves OSSInsight velocity and rank while retaining graceful degradation.

Advantages: fixes the broken boundary directly, preserves structured velocity data, and keeps the existing collector as a fallback. Disadvantage: requires an adapter and a richer analysis result.

### 2. Merge snapshot items into normalized events

Convert trending items into synthetic `NormalizedEvent` objects before all analysis steps.

Advantages: fewer signature changes. Disadvantages: pollutes the general event corpus, gives synthetic events misleading generic scores, and makes it harder to distinguish editorial events from velocity candidates.

### 3. Remove the GitHub Search collector and use OSSInsight exclusively

Advantages: eliminates duplicate sources. Disadvantages: loses a useful fallback when OSSInsight and the HTML scraper are unavailable and expands the scope beyond the observed defect.

## Selected Architecture

### Candidate boundary

Add a `GitHubRepoCandidate` dataclass in `scripts/analyze_github_projects.py`. It contains repository identity, URL, description, language, daily/weekly velocity, and source metadata. Two pure adapter functions produce candidates:

- snapshot adapter: `TrendingSnapshot.github_items` is the primary source;
- corpus adapter: normalized GitHub events are used only if the snapshot adapter returns no candidates.

Candidates are deduplicated by case-insensitive `owner/repo`. The configured `fetch.max_repos_to_analyze` controls the analysis pool instead of the current hard-coded limit of 30. GitHub REST enrichment continues to supply total stars, license, creation time, last push, topics, and issue counts.

### Pipeline boundary

`analyze_github_projects_state_action` accepts both `CorpusState` and the optional runtime snapshot. The daily step passes `rt.trending_snapshot`. Existing callers that provide only `CorpusState` remain valid and exercise the fallback path.

### Structured outcome and diagnostics

The analyzer returns a `GitHubProjectAnalysisOutcome` containing:

- accepted project analyses;
- source name;
- candidate, analyzed, filtered, and failed counts;
- per-candidate failure messages.

The pipeline stores only `outcome.analyses` in `AnalysisState`, preserving the existing state schema. It appends a confidence flag when every candidate fails analysis. Legitimate low-signal days remain successful and do not create an error flag. The run-step record count remains the number of accepted analyses.

### Report payload and deterministic empty rendering

The report payload continues to include only `Watch` projects, but it also includes a `github_project_analysis_status` object with accurate counts and a machine-readable reason:

- `source_empty`: no candidates from snapshot or fallback;
- `all_candidates_filtered`: candidates were analyzed successfully but none were accepted;
- `analysis_failed`: every attempted candidate failed;
- `no_watch_verdict`: accepted analyses exist but none has a `Watch` verdict;
- `watch_projects_available`: at least one Watch project is available.

After the LLM produces the report, Python deterministically replaces section 5 when no Watch project is available. The replacement contains one user-facing sentence appropriate to the reason and never contains internal prompt labels. When Watch projects exist, the LLM-rendered section is retained.

The prompt keeps the data-integrity prohibition against inventing repositories but removes displayable internal-rule wording and delegates empty-state copy to code.

## Error Handling

- A missing or empty snapshot activates the normalized-event fallback.
- Failure to enrich one repository does not abort other candidates; the base candidate fields are still analyzable.
- A failed LLM analysis increments `failed_count` and records a concise failure message.
- If all attempted analyses fail, the outcome reason is `analysis_failed` and the pipeline appends a confidence flag.
- Mixed success/failure runs retain successful analyses and expose counts without failing the complete daily report.

## Testing

Tests will prove:

1. snapshot candidates are preferred over normalized events and preserve `velocity_score` as daily stars;
2. normalized events remain the fallback when the snapshot is absent or empty;
3. candidate limits use `max_repos_to_analyze`;
4. all-analysis failure is distinguishable from all-filtered output;
5. orchestration passes the runtime snapshot and persists only the analyses mapping;
6. report payload status distinguishes source-empty, filtered, failed, no-Watch, and Watch-available states;
7. deterministic section rendering removes internal prompt labels and uses accurate copy;
8. the full existing test suite remains green.

## Non-Goals

- Removing the existing GitHub Search collector.
- Changing the LLM scoring rubric or Watch/Track thresholds.
- Rewriting the trending appendix.
- Adding a new external dependency.

## Acceptance Criteria

- A run with non-empty OSSInsight GitHub items analyzes those items instead of unrelated normalized GitHub Search results.
- A total analysis failure cannot be recorded as an indistinguishable successful empty result.
- Section 5 never contains `CRITICAL DATA-INTEGRITY RULE`.
- Empty-section copy truthfully reflects the observed reason.
- All tests pass, and the completed work is squash-merged to `main` as one commit.
