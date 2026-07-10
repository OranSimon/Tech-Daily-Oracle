# GitHub Project Analysis Data-Flow Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed structured OSSInsight GitHub candidates into project analysis, expose accurate empty-result diagnostics, and prevent internal prompt text from appearing in daily reports.

**Architecture:** A typed candidate adapter and structured analysis outcome live at the analyzer boundary. The daily runtime passes its `TrendingSnapshot` into that boundary and stores accepted analyses plus status counters. Report generation uses the status to deterministically render section 5 when no Watch project is available.

**Tech Stack:** Python 3.11+, dataclasses, pytest, existing `PromptRunner`, existing pipeline state slices.

## Global Constraints

- Keep normalized GitHub events as a fallback.
- Do not change the LLM scoring rubric or Watch/Track thresholds.
- Add no external dependency.
- Preserve the `TechDailyState` compatibility shell.
- Squash-merge to `main` as one commit.

---

### Task 1: Structured GitHub candidates and outcomes

**Files:**
- Modify: `scripts/analyze_github_projects.py`
- Test: `tests/test_analyze_github_projects_prompt_runner.py`

**Interfaces:**
- Consumes: `list[NormalizedEvent]`, optional `TrendingSnapshot`, `fetch.max_repos_to_analyze`.
- Produces: `GitHubRepoCandidate`, `GitHubProjectAnalysisOutcome`, and the backward-compatible `analyze_github_projects(events, prompt_runner=None, max_workers=MAX_WORKERS, *, trending_snapshot=None) -> GitHubProjectAnalysisOutcome`.

- [ ] **Step 1: Write failing snapshot-priority and outcome tests**

```python
def test_snapshot_candidates_are_preferred_and_preserve_daily_velocity():
    snapshot = TrendingSnapshot(
        snapshot_date="2026-07-02",
        period="daily",
        github_items=[_github_trending_item(velocity_score=27)],
        hf_paper_items=[],
        hf_model_items=[],
    )
    candidates, source = analyze_github_projects._select_candidates([_event()], snapshot)
    assert source == "ossinsight"
    assert candidates[0].full_name == "snapshot-owner/snapshot-repo"
    assert candidates[0].stars_today == 27


def test_all_candidate_failures_are_distinct_from_filtered_results(monkeypatch):
    class FailingRunner:
        def run_json(self, **kwargs):
            raise PromptRunnerError(kind="json_parse_error", message="bad JSON")

    monkeypatch.setattr(
        analyze_github_projects,
        "_load_config",
        lambda: {"fetch": {"top_n_in_report": 3, "max_repos_to_analyze": 25}},
    )
    monkeypatch.setattr(analyze_github_projects, "_fetch_repo_details", _fake_fetch_repo_details)
    outcome = analyze_github_projects.analyze_github_projects(
        [_event()], prompt_runner=FailingRunner(), max_workers=1
    )
    assert outcome.reason == "analysis_failed"
    assert outcome.failed_count == 1
    assert outcome.filtered_count == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_analyze_github_projects_prompt_runner.py`

Expected: failures because `_select_candidates` and outcome types do not exist and the analyzer still returns a dictionary.

- [ ] **Step 3: Implement candidate adapters and structured outcome**

```python
@dataclass(frozen=True)
class GitHubRepoCandidate:
    full_name: str
    url: str
    description: str
    language: str
    stars_today: int
    stars_weekly: int
    metadata: dict[str, Any]


@dataclass
class GitHubProjectAnalysisOutcome:
    analyses: dict[str, ProjectAnalysis] = field(default_factory=dict)
    source: str = "none"
    candidate_count: int = 0
    analyzed_count: int = 0
    filtered_count: int = 0
    failed_count: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.analyses:
            return "accepted_projects_available"
        if self.candidate_count == 0:
            return "source_empty"
        if self.analyzed_count == 0 and self.failed_count:
            return "analysis_failed"
        return "all_candidates_filtered"
```

Implement snapshot and event adapters, case-insensitive deduplication, snapshot-primary selection, configuration-driven limiting, and enrichment from candidates. Count successful LLM responses separately from filtered and failed candidates.

- [ ] **Step 4: Run analyzer tests and verify GREEN**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_analyze_github_projects_prompt_runner.py`

Expected: all analyzer tests pass.

- [ ] **Step 5: Commit task**

```bash
git add scripts/analyze_github_projects.py tests/test_analyze_github_projects_prompt_runner.py
git commit -m "fix: analyze structured GitHub trending candidates"
```

### Task 2: Retain a larger GitHub candidate pool

**Files:**
- Modify: `config.yml`
- Modify: `scripts/collect_trending.py`
- Test: `tests/test_collector_modules.py`

**Interfaces:**
- Consumes: `trending.top_n` and new `trending.github_candidate_pool_size`.
- Produces: up to `github_candidate_pool_size` GitHub items while HF lists remain limited to `top_n`.

- [ ] **Step 1: Write a failing retention test with all fetchers stubbed**

```python
def test_daily_snapshot_retains_github_analysis_pool(monkeypatch):
    config = {"trending": {"top_n": 5, "github_candidate_pool_size": 25}}
    snapshot = asyncio.run(collect_trending._collect_async("daily", "2026-07-02", config))
    assert len(snapshot.github_items) == 25
    assert len(snapshot.hf_paper_items) == 5
    assert len(snapshot.hf_model_items) == 5
```

- [ ] **Step 2: Run focused test and verify RED**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_collector_modules.py -k github_analysis_pool`

Expected: snapshot retains only five GitHub items.

- [ ] **Step 3: Implement separate GitHub pool size**

```python
top_n = int(tcfg.get("top_n", 5))
github_pool_size = int(tcfg.get("github_candidate_pool_size", 25))
github_fetch_size = max(top_n * 2, github_pool_size)
```

Fetch and retain `github_pool_size` GitHub items, keep HF retention at `top_n`, and add `github_candidate_pool_size: 25` to `config.yml`.

- [ ] **Step 4: Run collector tests and verify GREEN**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_collector_modules.py`

Expected: all collector module tests pass.

- [ ] **Step 5: Commit task**

```bash
git add config.yml scripts/collect_trending.py tests/test_collector_modules.py
git commit -m "fix: retain GitHub analysis candidate pool"
```

### Task 3: Pipeline state and orchestration wiring

**Files:**
- Modify: `scripts/state.py`
- Modify: `src/tech_daily/pipeline/state.py`
- Modify: `src/tech_daily/pipeline/actions.py`
- Modify: `src/tech_daily/pipeline/daily.py`
- Test: `tests/test_pipeline_state.py`
- Test: `tests/test_daily_step_actions.py`
- Test: `tests/test_daily_orchestration_wrapping.py`

**Interfaces:**
- Consumes: `GitHubProjectAnalysisOutcome` and runtime `trending_snapshot`.
- Produces: `github_project_analysis_status: dict[str, Any]` plus the existing accepted-analysis mapping.

- [ ] **Step 1: Write failing state and orchestration tests**

```python
def test_github_analysis_state_action_receives_snapshot(monkeypatch):
    corpus = CorpusState(normalized_events=[_normalized_event()])
    snapshot = object()
    expected = object()
    captured = {}

    def fake_analyze(events, trending_snapshot=None):
        captured["snapshot"] = trending_snapshot
        return expected

    monkeypatch.setattr(actions, "analyze_github_projects", fake_analyze)
    result = actions.analyze_github_projects_state_action(corpus, snapshot)

    assert result is expected
    assert captured["snapshot"] is snapshot


def test_all_github_analysis_failures_add_confidence_flag(tmp_path):
    runtime = _runtime(tmp_path)
    outcome = GitHubProjectAnalysisOutcome(
        source="ossinsight", candidate_count=1, failed_count=1,
        failures=["owner/repo: parse error"],
    )
    result = PipelineStepResult(
        name="Analyzing GitHub projects",
        success=True,
        duration_seconds=0.1,
        value=outcome,
        record_count=0,
    )
    daily_pipeline._after_analyze_github_projects(runtime, result)

    assert runtime.state.github_project_analysis_status["reason"] == "analysis_failed"
    assert runtime.state.confidence_flags == ["GitHub analysis failed for all 1 candidates"]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_pipeline_state.py tests/test_daily_step_actions.py tests/test_daily_orchestration_wrapping.py`

Expected: failures because snapshot and status are not wired.

- [ ] **Step 3: Add status state and apply helper**

Add `github_project_analysis_status` with a source-empty default to both state layers. Extend conversion/apply methods. Add a helper that writes `outcome.analyses` and `outcome.to_status_dict()`.

- [ ] **Step 4: Wire snapshot and outcome through the daily step**

```python
action=lambda rt: actions.analyze_github_projects_state_action(
    pipeline_state.get_corpus_state(rt.state), rt.trending_snapshot
),
fallback=None,
record_count=lambda outcome: len(outcome.analyses) if outcome is not None else 0,
```

Update `_after_analyze_github_projects` to persist the outcome and append an all-failed confidence flag. Preserve step-level fallback behavior.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_pipeline_state.py tests/test_daily_step_actions.py tests/test_daily_orchestration_wrapping.py`

Expected: all focused pipeline tests pass.

- [ ] **Step 6: Commit task**

```bash
git add scripts/state.py src/tech_daily/pipeline/state.py src/tech_daily/pipeline/actions.py src/tech_daily/pipeline/daily.py tests/test_pipeline_state.py tests/test_daily_step_actions.py tests/test_daily_orchestration_wrapping.py
git commit -m "fix: wire GitHub snapshot analysis into daily pipeline"
```

### Task 4: Accurate report status and deterministic section 5

**Files:**
- Modify: `src/tech_daily/reports/daily.py`
- Modify: `prompts/daily_brief.md`
- Test: `tests/test_report_rendering.py`

**Interfaces:**
- Consumes: accepted analyses and `github_project_analysis_status`.
- Produces: normalized status in the report payload and deterministic section-5 fallback copy.

- [ ] **Step 1: Write failing payload and rendering tests**

```python
def test_report_payload_distinguishes_no_watch_from_source_empty():
    state.github_project_analyses = {"owner/repo": _track_project()}
    state.github_project_analysis_status = {"reason": "accepted_projects_available"}
    payload = daily_report._build_report_payload(state)
    assert payload["github_project_analysis_status"]["reason"] == "no_watch_verdict"


def test_empty_github_section_is_replaced_without_internal_prompt_text(monkeypatch, tmp_path):
    state = TechDailyState(run_id="run-test", run_date="2026-07-02", time_window="last_24h")
    (tmp_path / "daily_brief.md").write_text("Daily prompt", encoding="utf-8")
    response = (
        "## 5. GitHub Trending: Top 3 High-Signal Repos\n\n"
        "**CRITICAL DATA-INTEGRITY RULE:** leaked\n\n"
        "## 6. Papers & Research Frontiers\n"
    )
    runner = PromptRunner(FakeLLMClient(response), prompt_root=tmp_path)
    monkeypatch.setattr(daily_report, "_load_config", lambda: {"model": {"max_tokens_daily": 100}})
    monkeypatch.setattr(daily_report, "_load_preferences", lambda: {})

    report = daily_report.generate_daily_report(state, prompt_runner=runner)
    assert "CRITICAL DATA-INTEGRITY RULE" not in report
    assert "未获取到可分析的 GitHub 趋势候选" in report
```

- [ ] **Step 2: Run report tests and verify RED**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_report_rendering.py`

Expected: payload lacks status and leaked prompt text remains.

- [ ] **Step 3: Implement status normalization and section replacement**

Add `_github_report_status` and `_replace_empty_github_section` with copy for `source_empty`, `all_candidates_filtered`, `analysis_failed`, and `no_watch_verdict`. Retain LLM section 5 only for `watch_projects_available`.

- [ ] **Step 4: Remove displayable internal prompt labels**

Replace the `CRITICAL DATA-INTEGRITY RULE` block with a concise instruction that repositories must come only from `github_project_analyses` and the application renders empty states.

- [ ] **Step 5: Run report tests and verify GREEN**

Run: `/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q tests/test_report_rendering.py`

Expected: all report tests pass and generated empty sections contain no internal label.

- [ ] **Step 6: Commit task**

```bash
git add src/tech_daily/reports/daily.py prompts/daily_brief.md tests/test_report_rendering.py
git commit -m "fix: render truthful GitHub report empty states"
```

### Task 5: Full verification and squash delivery

**Files:**
- Modify only if verification exposes a defect.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified branch and one new commit on `main`.

- [ ] **Step 1: Run lint, type checks, and full tests**

```bash
/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m ruff check .
/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m mypy src scripts
/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q
```

Expected: zero lint errors, zero type errors, and all tests pass.

- [ ] **Step 2: Inspect scope and diff quality**

```bash
git diff --check main...HEAD
git status --short
git diff --stat main...HEAD
```

Expected: no whitespace errors, no unintended files, and a clean worktree.

- [ ] **Step 3: Squash merge from the main checkout**

```bash
git merge --squash codex/fix-github-analysis-data-flow
git commit -m "fix: repair GitHub project analysis data flow"
```

- [ ] **Step 4: Verify main after merge**

```bash
/Users/oransimon/Tech-Daily-Oracle/.venv/bin/python -m pytest -q
git log --oneline -2
git status --short
```

Expected: full tests pass, exactly one new commit is above `d37d28b`, and main is clean.

- [ ] **Step 5: Remove completed worktree and branch**

```bash
git worktree remove .worktrees/fix-github-analysis-data-flow
git branch -d codex/fix-github-analysis-data-flow
```
