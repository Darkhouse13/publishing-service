from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from automating_wf.analysis.pinterest import score_keyword_candidates
from automating_wf.models.pinterest import PinClicksKeywordScore, SeedScrapeResult


# Bump when scoring logic changes to invalidate cached artifacts.
SCORING_VERSION = "2.1.0-ctr"

# Terms that signal a user is seeking actionable content and is likely to
# click through to a blog post (outbound click intent).
OUTBOUND_CLICK_TERMS = {
    "how to",
    "tips",
    "guide",
    "tutorial",
    "step by step",
    "best",
    "review",
    "comparison",
    "budget",
    "affordable",
    "fix",
    "solution",
    "recipe",
    "plan",
    "checklist",
    "easy",
    "small",
}

# Terms that signal Pinterest-internal engagement (saves / repins) but
# lower outbound-click propensity.
INTERNAL_ENGAGEMENT_TERMS = {
    "aesthetic",
    "vibes",
    "mood",
    "inspo",
    "gorgeous",
    "beautiful",
    "dreamy",
    "stunning",
    "inspiration",
    "look",
    "style",
    "design",
}

DEFAULT_MIN_CLICK_SCORE = 0.01
LOW_CONFIDENCE_THRESHOLD = 0.3


class PinClicksAnalysisError(RuntimeError):
    """Raised when PinClicks keyword ranking fails."""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_score_total(record: Any) -> float:
    engagement = getattr(record, "engagement", {}) or {}
    if isinstance(engagement.get("score_total"), (int, float)):
        return float(engagement["score_total"])
    values = [float(value) for value in engagement.values() if isinstance(value, (int, float))]
    return sum(values)


def _outbound_intent_score(records: list[Any]) -> float:
    """Fraction of pins whose content signals outbound-click intent.

    Problem-solving / actionable content drives users to click through to
    blog posts.  Pure-inspiration content mainly drives saves (internal to
    Pinterest), so a penalty is applied when inspiration dominates.
    """
    if not records:
        return 0.0
    outbound_hits = 0
    internal_hits = 0
    for record in records:
        text = f"{record.title} {record.description}".casefold()
        if any(term in text for term in OUTBOUND_CLICK_TERMS):
            outbound_hits += 1
        if any(term in text for term in INTERNAL_ENGAGEMENT_TERMS):
            internal_hits += 1
    outbound_ratio = outbound_hits / len(records)
    internal_ratio = internal_hits / len(records)
    return max(0.0, outbound_ratio - 0.3 * internal_ratio)


def _percentile_ranks(values: list[float]) -> list[float]:
    """Percentile-rank normalization with tie handling.  Returns [0, 1]."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and math.isclose(
            values[indexed[j]], values[indexed[i]], rel_tol=1e-9, abs_tol=1e-12
        ):
            j += 1
        avg_rank = (i + j - 1) / 2.0
        for k in range(i, j):
            ranks[indexed[k]] = avg_rank / max(n - 1, 1)
        i = j
    return ranks


def _compute_ctr_confidence(
    engagement_available: bool,
    record_count: int,
    outbound_intent: float,
) -> float:
    """Estimate confidence in the CTR estimate based on signal quality."""
    confidence = 0.3
    if engagement_available:
        confidence += 0.3
    if record_count >= 5:
        confidence += 0.2
    elif record_count >= 2:
        confidence += 0.1
    if outbound_intent > 0.2:
        confidence += 0.2
    return min(1.0, round(confidence, 4))


# ── Near-duplicate / cannibalization suppression ─────────────────────────


def _dedup_canonical_key(keyword: str) -> str:
    """Create a canonical key for near-duplicate detection.

    Handles: casefold, whitespace, simple plural (trailing 's'),
    token-order variants.
    """
    tokens = re.findall(r"[a-z0-9]+", keyword.casefold())
    stemmed = []
    for t in tokens:
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            stemmed.append(t[:-1])
        else:
            stemmed.append(t)
    return " ".join(sorted(stemmed))


# ── Pareto frontier ──────────────────────────────────────────────────────


def pareto_frontier_2d(
    items: list[dict[str, float]],
    key_x: str,
    key_y: str,
) -> list[int]:
    """Return indices of non-dominated items on a 2-D frontier (higher = better).

    A candidate *i* is dominated when another candidate *j* satisfies
    ``x_j >= x_i`` and ``y_j >= y_i`` with at least one strict inequality.
    Only non-dominated indices are returned.
    """
    n = len(items)
    if n == 0:
        return []
    dominated: set[int] = set()
    for i in range(n):
        if i in dominated:
            continue
        xi, yi = items[i][key_x], items[i][key_y]
        for j in range(n):
            if i == j or j in dominated:
                continue
            xj, yj = items[j][key_x], items[j][key_y]
            if xj >= xi and yj >= yi and (xj > xi or yj > yi):
                dominated.add(i)
                break
    return [i for i in range(n) if i not in dominated]


# ── Main ranking entry point ─────────────────────────────────────────────


def rank_pinclicks_keywords(
    *,
    scrape_results: list[SeedScrapeResult],
    run_dir: Path,
    top_n: int = 5,
    trend_rank_map: dict[str, int] | None = None,
    reach_hat_map: dict[str, float] | None = None,
    reach_confidence_map: dict[str, float] | None = None,
    min_click_score: float = DEFAULT_MIN_CLICK_SCORE,
) -> list[PinClicksKeywordScore]:
    """Rank keywords by expected outbound click score (reach x CTR proxy).

    ``click_score`` = ``reach_hat * ctr_hat``.  This is a *relative*
    ranking proxy, not a literal predicted click count.

    CTR estimator weights (percentile-rank normalised):
      - 55% outbound intent  (problem-solving content drives clicks)
      - 20% engagement        (engagement as click proxy, reduced to avoid
                               over-indexing on-platform satisfaction)
      - 25% frequency         (content-market validation)

    Final selection logic (deterministic):
      1. Disqualify candidates with click_score < min_click_score
      2. Disqualify candidates with very low combined confidence
      3. Suppress near-duplicate keywords
      4. Compute Pareto frontier on (reach_hat, ctr_hat)
      5. If frontier covers top_n, winners = top_n from frontier by click_score
      6. Otherwise, backfill from non-frontier candidates by click_score
      7. Each candidate is tagged with selection_reason
    """
    _ensure_dir(run_dir)
    if not scrape_results:
        raise PinClicksAnalysisError("No PinClicks scrape results available for ranking.")

    trend_rank_map = trend_rank_map or {}
    reach_hat_map = reach_hat_map or {}
    reach_confidence_map = reach_confidence_map or {}

    raw_scores: list[dict[str, Any]] = []

    for result in scrape_results:
        records = result.records
        if not records:
            continue

        frequency_candidates = score_keyword_candidates(records, min_frequency=1)
        if frequency_candidates:
            top_candidate = frequency_candidates[0]
            frequency_score = float(top_candidate.weighted_score + top_candidate.frequency)
        else:
            frequency_score = 0.0

        engagement_values = [_record_score_total(record) for record in records]
        engagement_score = float(mean(engagement_values)) if engagement_values else 0.0
        engagement_available = any(value > 0.0 for value in engagement_values)
        outbound_intent = float(_outbound_intent_score(records))

        raw_scores.append(
            {
                "keyword": result.seed_keyword,
                "frequency_score": frequency_score,
                "engagement_score": engagement_score,
                "outbound_intent_score": outbound_intent,
                "record_count": len(records),
                "engagement_available": engagement_available,
                "trend_rank": int(trend_rank_map.get(result.seed_keyword, 0)),
                "reach_hat": float(reach_hat_map.get(result.seed_keyword, 0.5)),
                "reach_confidence": float(reach_confidence_map.get(result.seed_keyword, 0.5)),
            }
        )

    if not raw_scores:
        raise PinClicksAnalysisError("No rankable PinClicks results after filtering empty records.")

    # --- Percentile-rank normalise CTR components ---
    intent_pcts = _percentile_ranks([float(s["outbound_intent_score"]) for s in raw_scores])
    engagement_pcts = _percentile_ranks([float(s["engagement_score"]) for s in raw_scores])
    frequency_pcts = _percentile_ranks([float(s["frequency_score"]) for s in raw_scores])

    # --- Build scored candidates ---
    scored: list[dict[str, Any]] = []
    for index, item in enumerate(raw_scores):
        # CTR estimator: outbound-intent dominant, engagement reduced
        ctr_hat = (
            0.55 * intent_pcts[index]
            + 0.20 * engagement_pcts[index]
            + 0.25 * frequency_pcts[index]
        )
        ctr_confidence = _compute_ctr_confidence(
            engagement_available=bool(item["engagement_available"]),
            record_count=int(item["record_count"]),
            outbound_intent=float(item["outbound_intent_score"]),
        )
        reach_hat = float(item["reach_hat"])
        reach_conf = float(item["reach_confidence"])
        click_score = reach_hat * ctr_hat
        combined_confidence = math.sqrt(reach_conf * ctr_confidence)

        scored.append(
            {
                "keyword": item["keyword"],
                "ctr_hat": round(ctr_hat, 6),
                "ctr_confidence": round(ctr_confidence, 4),
                "reach_hat": round(reach_hat, 6),
                "click_score": round(click_score, 6),
                "combined_confidence": round(combined_confidence, 4),
                "outbound_intent_score": round(float(item["outbound_intent_score"]), 6),
                "engagement_score": round(float(item["engagement_score"]), 6),
                "frequency_score": round(float(item["frequency_score"]), 6),
                "record_count": int(item["record_count"]),
                "engagement_available": bool(item["engagement_available"]),
                "trend_rank": int(item["trend_rank"]),
            }
        )

    # ── Step 1: Qualification gates ──────────────────────────────────────

    for item in scored:
        item["qualified"] = True
        item["disqualification_reason"] = ""

        if item["click_score"] < min_click_score:
            item["qualified"] = False
            item["disqualification_reason"] = (
                f"click_score {item['click_score']:.4f} below minimum {min_click_score}"
            )
        elif item["combined_confidence"] < LOW_CONFIDENCE_THRESHOLD:
            item["qualified"] = False
            item["disqualification_reason"] = (
                f"combined_confidence {item['combined_confidence']:.4f} below {LOW_CONFIDENCE_THRESHOLD}"
            )

    qualified = [s for s in scored if s["qualified"]]
    disqualified = [s for s in scored if not s["qualified"]]

    # ── Step 2: Near-duplicate suppression ────────────────────────────────

    # Sort qualified by click_score desc so dedup keeps the best variant
    qualified.sort(key=lambda s: -s["click_score"])
    canonical_groups: dict[str, list[int]] = defaultdict(list)
    for idx, item in enumerate(qualified):
        key = _dedup_canonical_key(item["keyword"])
        canonical_groups[key].append(idx)

    suppressed_indices: set[int] = set()
    for _key, indices in canonical_groups.items():
        if len(indices) <= 1:
            continue
        best_kw = qualified[indices[0]]["keyword"]
        for dup_idx in indices[1:]:
            suppressed_indices.add(dup_idx)
            qualified[dup_idx]["qualified"] = False
            qualified[dup_idx]["disqualification_reason"] = f"near-duplicate of '{best_kw}'"

    active = [s for idx, s in enumerate(qualified) if idx not in suppressed_indices]
    suppressed = [s for idx, s in enumerate(qualified) if idx in suppressed_indices]

    # ── Step 3: Pareto frontier on (reach_hat, ctr_hat) ──────────────────

    frontier_indices = set(pareto_frontier_2d(active, "reach_hat", "ctr_hat"))

    # ── Step 4: Deterministic winner selection ───────────────────────────
    #
    # Sort active candidates by click_score descending, using confidence
    # as tiebreaker.  Assign selection_reason to each:
    #   - "pareto_frontier"       if on the frontier
    #   - "backfill"              if not on frontier but needed to fill top_n
    #   - ""                      if not selected as winner

    for idx, item in enumerate(active):
        item["is_pareto_efficient"] = idx in frontier_indices

    # Rank: Pareto-efficient first (by click_score desc), then rest
    active.sort(
        key=lambda s: (
            not s["is_pareto_efficient"],
            -s["click_score"],
            -s["combined_confidence"],
            s["keyword"].casefold(),
        )
    )

    desired = max(1, top_n)
    for idx, item in enumerate(active):
        if idx < desired:
            if item["is_pareto_efficient"]:
                item["selection_reason"] = "pareto_frontier"
            else:
                item["selection_reason"] = "backfill"
        else:
            item["selection_reason"] = ""

    # ── Step 5: Build final candidate objects ────────────────────────────

    all_items = active + suppressed + disqualified
    all_candidates: list[PinClicksKeywordScore] = []
    for item in all_items:
        selection = str(item.get("selection_reason", ""))
        suppressed_by = ""
        dq = str(item.get("disqualification_reason", ""))
        if dq.startswith("near-duplicate of"):
            suppressed_by = dq.replace("near-duplicate of ", "").strip("'")
            selection = "suppressed_duplicate"
        elif not item.get("qualified", True) and not selection:
            selection = "disqualified"

        all_candidates.append(
            PinClicksKeywordScore(
                keyword=str(item["keyword"]),
                ctr_hat=item["ctr_hat"],
                ctr_confidence=item["ctr_confidence"],
                reach_hat=item["reach_hat"],
                click_score=item["click_score"],
                is_pareto_efficient=bool(item.get("is_pareto_efficient", False)),
                outbound_intent_score=item["outbound_intent_score"],
                engagement_score=item["engagement_score"],
                frequency_score=item["frequency_score"],
                record_count=item["record_count"],
                engagement_available=item["engagement_available"],
                trend_rank=item["trend_rank"],
                selection_reason=selection,
                suppressed_by=suppressed_by,
            )
        )

    # Assign pinclicks_rank across all candidates (winners first)
    for rank, candidate in enumerate(all_candidates, start=1):
        candidate.pinclicks_rank = rank

    selected = [c for c in all_candidates if c.selection_reason in ("pareto_frontier", "backfill")]
    pareto_winners = [c for c in all_candidates if c.is_pareto_efficient and c.selection_reason]

    # --- Persist artifacts ---
    _write_json(
        run_dir / "pinclicks_keyword_scores.json",
        [c.to_dict() for c in all_candidates],
    )
    _write_json(
        run_dir / f"run_winners_top{desired}.json",
        [c.to_dict() for c in selected],
    )
    _write_json(
        run_dir / "pinclicks_ranking_metadata.json",
        {
            "scoring_version": SCORING_VERSION,
            "min_click_score": min_click_score,
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "engagement_signal_available": any(c.engagement_available for c in all_candidates),
            "pareto_frontier_size": sum(1 for c in all_candidates if c.is_pareto_efficient),
            "total_candidates": len(all_candidates),
            "qualified_count": len(active),
            "disqualified_count": len(disqualified),
            "suppressed_count": len(suppressed),
            "selected_count": len(selected),
            "backfill_count": sum(1 for c in selected if c.selection_reason == "backfill"),
            "keywords_with_engagement": [c.keyword for c in all_candidates if c.engagement_available],
            "keywords_without_engagement": [c.keyword for c in all_candidates if not c.engagement_available],
        },
    )
    return selected
