"""Trending analysis module.

Responsibilities:
  1. Cross-list detection — same entity (owner/name) in both GitHub and HF model hub
  2. Acceleration tracking — rank + velocity trend across stored daily snapshots
  3. LLM analysis — batch call for items with no prior history (new entries)
  4. Report section assembly

Cross-list matching is intentionally conservative: only exact owner/name identity.
Topic-level fuzzy matching (paper ↔ implementation repo) is left as future work.

Acceleration is computed from data/trending_snapshots.jsonl entries:
  - velocity trend: recent 2 days vs. earlier average, threshold +15%
  - rank trend: lower number = better position; check if rank is improving
  - Combined verdict: both improving → "accelerating", both declining → "decelerating",
    mixed → "stable", first appearance → "new"
"""

from __future__ import annotations

import json
from typing import Any

from llm_schemas import TrendingAnalysisResponse
from prompt_runner import PromptRunner
from state import CrossListHit, TrendingAnalysis, TrendingItem, TrendingSnapshot

_ACCEL_EMOJI = {
    "accelerating": "📈",
    "stable": "➡️",
    "decelerating": "📉",
    "new": "🆕",
}


# ---------------------------------------------------------------------------
# Cross-list detection
# ---------------------------------------------------------------------------


def _norm_id(item_id: str) -> str:
    """Normalise to lowercase owner/name form for cross-list comparison."""
    parts = item_id.lower().strip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else item_id.lower()


def _find_cross_list_hits(
    github_items: list[TrendingItem],
    hf_model_items: list[TrendingItem],
    history: list[dict],
) -> list[CrossListHit]:
    """
    Find items appearing in both the GitHub and HuggingFace model hub lists.

    HF paper items are excluded from cross-list matching because paper arxiv IDs
    have no systematic relationship to GitHub repo paths.
    """
    hf_by_norm = {_norm_id(m.item_id): m for m in hf_model_items}
    hits: list[CrossListHit] = []

    for gh in github_items:
        norm = _norm_id(gh.item_id)
        if norm not in hf_by_norm:
            continue
        hf = hf_by_norm[norm]
        accel = _compute_acceleration(gh.item_id, "github_repo", history)
        hits.append(
            CrossListHit(
                item_id=gh.item_id,
                match_type="exact",
                github_item=gh,
                hf_item=hf,
                acceleration=accel["acceleration"],
                days_in_top_lists=accel["days_in_top"],
                rank_history=accel["rank_history"],
                velocity_history=accel["velocity_history"],
            )
        )
    return hits


# ---------------------------------------------------------------------------
# Acceleration computation
# ---------------------------------------------------------------------------


def _compute_acceleration(item_id: str, item_type: str, history: list[dict]) -> dict[str, Any]:
    """
    Compute acceleration from stored daily snapshots for a single item.

    Returns dict with keys: acceleration, days_in_top, rank_history, velocity_history.
    """
    item_hist = sorted(
        [h for h in history if h.get("item_id") == item_id and h.get("item_type") == item_type],
        key=lambda x: x.get("snapshot_date", ""),
    )

    ranks = [h.get("rank", 999) for h in item_hist]
    vels = [h.get("velocity_score", 0.0) for h in item_hist]

    if len(vels) < 2:
        return {
            "acceleration": "new",
            "days_in_top": len(item_hist),
            "rank_history": ranks,
            "velocity_history": vels,
        }

    # Compare recent 2 days vs. all earlier days
    recent_vel = sum(vels[-2:]) / 2
    older_vel = sum(vels[:-2]) / max(len(vels) - 2, 1)
    recent_rank = sum(ranks[-2:]) / 2
    older_rank = sum(ranks[:-2]) / max(len(ranks) - 2, 1)

    vel_up = recent_vel > older_vel * 1.15
    rank_up = recent_rank < older_rank  # lower number = higher position

    if vel_up and rank_up:
        accel = "accelerating"
    elif not vel_up and not rank_up:
        accel = "decelerating"
    else:
        accel = "stable"

    return {
        "acceleration": accel,
        "days_in_top": len(item_hist),
        "rank_history": ranks[-7:],
        "velocity_history": [round(v, 1) for v in vels[-7:]],
    }


# ---------------------------------------------------------------------------
# LLM analysis (batch, new items only)
# ---------------------------------------------------------------------------


def _analyze_new_items_batch(
    items: list[TrendingItem],
    prompt_runner: PromptRunner,
) -> dict[str, str]:
    """Send a batch of new trending items to the LLM. Returns item_id → snippet."""
    if not items:
        return {}

    payload = [
        {
            "item_id": item.item_id,
            "item_type": item.item_type,
            "title": item.title,
            "description": item.description[:300],
            "url": item.url,
            "rank": item.rank,
            "velocity_score": round(item.velocity_score, 1),
            "language": item.language,
            "extra": {
                k: v
                for k, v in item.extra.items()
                if k
                in ("collection_names", "authors", "days_appeared", "avg_upvotes", "pipeline_tag", "forks_increment")
            },
        }
        for item in items
    ]

    # Returns an ARRAY of {item_id, report_snippet} — output scales with
    # batch size. Daily uses top_n=5 across 3 sources (up to 15 items),
    # weekly/monthly may pass more. Each snippet is ~150-300 tokens, so
    # 15 items × 250 = 3750 tokens — 4096 is tight, 8192 is comfortable.
    results = prompt_runner.run_json(
        prompt_path="trending_analysis.md",
        payload=json.dumps({"trending_items": payload}, ensure_ascii=False),
        schema=TrendingAnalysisResponse,
        max_tokens=8192,
    )
    return {item.item_id: item.report_snippet for item in results.root}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_trending(
    snapshot: TrendingSnapshot,
    history: list[dict],
    top_n: int = 5,
    prompt_runner: PromptRunner | None = None,
) -> TrendingAnalysis:
    """
    Analyse a trending snapshot.

    Steps:
      1. Find cross-list hits (GitHub ↔ HF models, exact owner/name match)
      2. Compute acceleration for all items using stored history
      3. LLM batch analysis for items with no prior history (new entries)
      4. Programmatic snippets for returning items (no LLM cost)
      5. Assemble formatted report section
    """
    runner = prompt_runner or PromptRunner()

    # 1. Cross-list detection
    cross_hits = _find_cross_list_hits(
        snapshot.github_items,
        snapshot.hf_model_items,
        history,
    )
    cross_ids = {h.item_id for h in cross_hits}

    # 2. Classify all non-cross-list items as new vs. returning
    all_items = snapshot.github_items[:top_n] + snapshot.hf_paper_items[:top_n] + snapshot.hf_model_items[:top_n]
    new_items: list[TrendingItem] = []
    returning: list[tuple[TrendingItem, dict]] = []

    for item in all_items:
        if item.item_id in cross_ids:
            continue
        accel = _compute_acceleration(item.item_id, item.item_type, history)
        if accel["days_in_top"] == 0:
            new_items.append(item)
        else:
            returning.append((item, accel))

    # 3. LLM analysis for new items (single batched call)
    try:
        item_analyses = _analyze_new_items_batch(new_items, runner)
    except Exception as e:
        print(f"  [Trending] LLM analysis failed: {e}")
        item_analyses = {}
    print(f"  [Trending] {len(new_items)} new, {len(returning)} returning, {len(cross_hits)} cross-list")

    # 4. Programmatic snippets for returning items
    for item, accel in returning:
        emoji = _ACCEL_EMOJI.get(accel["acceleration"], "")
        days = accel["days_in_top"]
        vel = item.velocity_score
        item_analyses[item.item_id] = (
            f"{emoji} **{item.title}** — {accel['acceleration']} (day {days + 1} in trending, velocity: {vel:,.0f})"
        )

    # 5. Assemble report section (Chinese headers, English proper nouns)
    period_zh = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(snapshot.period, snapshot.period)
    lines: list[str] = [f"\n## 🔥 趋势榜单 — {period_zh} ({snapshot.snapshot_date})\n"]

    if cross_hits:
        lines.append("### ↔️ 跨平台动量（GitHub + HuggingFace 同时上榜）\n")
        accel_zh = {
            "accelerating": "加速",
            "stable": "平稳",
            "decelerating": "减速",
            "new": "首次出现",
        }
        for hit in cross_hits:
            emoji = _ACCEL_EMOJI.get(hit.acceleration, "")
            status = accel_zh.get(hit.acceleration, hit.acceleration)
            gh_vel = hit.github_item.velocity_score if hit.github_item else 0
            lines.append(
                f"- {emoji} **{hit.item_id}** — 两个平台同时{status} "
                f"(GitHub +{gh_vel:,.0f} ⭐, 上榜第 {hit.days_in_top_lists + 1} 天)"
            )
        lines.append("")

    if snapshot.github_items[:top_n]:
        lines.append("### 🐙 GitHub 趋势 (OSSInsight 速度数据)\n")
        for item in snapshot.github_items[:top_n]:
            if item.item_id in cross_ids:
                continue
            snippet = item_analyses.get(item.item_id, f"**{item.title}** (+{item.velocity_score:,.0f} ⭐)")
            lines.append(f"- {snippet}")
        lines.append("")

    if snapshot.hf_paper_items[:top_n]:
        lines.append("### 📄 HuggingFace 论文\n")
        for item in snapshot.hf_paper_items[:top_n]:
            days = item.extra.get("days_appeared", 1)
            days_note = f" · 连续上榜 {days} 天" if days > 1 else ""
            # Fallback snippet — show "(just posted)" if no upvotes yet
            upvote_note = "(just posted)" if item.velocity_score == 0 else f"(👍 {int(item.velocity_score)})"
            snippet = item_analyses.get(item.item_id, f"**{item.title}** {upvote_note}{days_note}")
            lines.append(f"- {snippet}")
        lines.append("")

    if snapshot.hf_model_items[:top_n]:
        lines.append("### 🤗 HuggingFace 模型\n")
        for item in snapshot.hf_model_items[:top_n]:
            if item.item_id in cross_ids:
                continue
            snippet = item_analyses.get(item.item_id, f"**{item.title}**")
            lines.append(f"- {snippet}")
        lines.append("")

    return TrendingAnalysis(
        snapshot_date=snapshot.snapshot_date,
        period=snapshot.period,
        top_github=snapshot.github_items[:top_n],
        top_hf_papers=snapshot.hf_paper_items[:top_n],
        top_hf_models=snapshot.hf_model_items[:top_n],
        cross_list_hits=cross_hits,
        item_analyses=item_analyses,
        report_section="\n".join(lines),
    )
