from __future__ import annotations

import html as html_mod
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
SCORING_VERSION = "2.2.0-ctr"

# Nominal CTR weights.  Per-keyword effective weights are renormalized
# when engagement data is unavailable for that keyword.
NOMINAL_CTR_WEIGHTS: dict[str, float] = {
    "intent": 0.55,
    "engagement": 0.20,
    "frequency": 0.25,
}

# Terms that signal outbound-click intent.
OUTBOUND_CLICK_TERMS = {
    "how to", "tips", "guide", "tutorial", "step by step",
    "best", "review", "comparison", "budget", "affordable",
    "fix", "solution", "recipe", "plan", "checklist", "easy", "small",
}

# Terms that signal Pinterest-internal engagement (saves / repins).
INTERNAL_ENGAGEMENT_TERMS = {
    "aesthetic", "vibes", "mood", "inspo", "gorgeous", "beautiful",
    "dreamy", "stunning", "inspiration", "look", "style", "design",
}

# Modifiers stripped from keywords before topic-family comparison.
# These change the specificity / framing of an article but not the
# core editorial intent.
TOPIC_FAMILY_MODIFIERS = {
    "free", "pattern", "patterns", "ideas", "idea", "easy", "simple",
    "best", "diy", "tutorial", "guide", "how", "to", "step",
    "project", "projects", "for", "beginners", "beginner", "kids",
    "adults", "advanced", "cheap", "budget", "affordable", "quick",
    "cute", "modern", "cozy", "beautiful", "cool", "unique",
    "creative", "fun", "stylish", "summer", "spring", "fall", "winter",
    "autumn", "seasonal", "holiday", "christmas", "new", "year",
}

DEFAULT_MIN_CLICK_SCORE = 0.01
DEFAULT_FAMILY_SIMILARITY_THRESHOLD = 0.5
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
    """Fraction of pins whose content signals outbound-click intent."""
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
    """Estimate confidence in the CTR estimate.

    Lower confidence when engagement data is missing — the estimate
    relies on fewer signals.
    """
    confidence = 0.3
    if engagement_available:
        confidence += 0.3
    else:
        confidence += 0.05  # small credit for having records at all
    if record_count >= 5:
        confidence += 0.2
    elif record_count >= 2:
        confidence += 0.1
    if outbound_intent > 0.2:
        confidence += 0.2
    return min(1.0, round(confidence, 4))


# ── Near-duplicate suppression ───────────────────────────────────────────


def _dedup_canonical_key(keyword: str) -> str:
    """Canonical key for exact / token-reorder / plural dedup.

    Uses ``_normalize_tokens`` (all tokens, stemmed, sorted) — NOT
    content-only tokens — so that modifier words still contribute to
    distinguishing genuinely different phrases.
    """
    return " ".join(sorted(_normalize_tokens(keyword)))


# ── Topic-family suppression ─────────────────────────────────────────────


def _topic_family_tokens(keyword: str) -> set[str]:
    """Content-bearing tokens for topic-family comparison.

    Delegates to ``_content_tokens`` so that within-run family suppression
    and WP overlap detection share the same normalization semantics.
    """
    return _content_tokens(keyword)


def _topic_family_key(keyword: str) -> str:
    """Deterministic family key from topic tokens (for artifact display)."""
    return " ".join(sorted(_topic_family_tokens(keyword))) or keyword.casefold().strip()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Shared normalization helpers ─────────────────────────────────────────


def _stem_token(token: str) -> str:
    """Strip a simple trailing 's' plural (not 'ss')."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _normalize_tokens(text: str) -> list[str]:
    """Casefold, tokenize into alphanumeric runs, stem.  Keeps all tokens."""
    return [_stem_token(t) for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) >= 2]


def _content_tokens(text: str) -> set[str]:
    """Content-bearing tokens after stripping topic modifiers.

    Shared by within-run family suppression and WP overlap detection so
    that the semantic comparison is consistent across both layers.
    """
    return {
        t for t in _normalize_tokens(text)
        if t not in TOPIC_FAMILY_MODIFIERS and len(t) >= 3
    }


# ── WordPress overlap detection ─────────────────────────────────────────

WP_OVERLAP_SUPPRESS_JACCARD = 0.7
WP_OVERLAP_WARN_JACCARD = 0.5


def _keyword_to_slug(keyword: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.casefold()).strip("-")
    return slug[:60]


def _strip_wp_numeric_suffix(slug: str) -> str:
    """'crochet-tank-top-5' → 'crochet-tank-top'."""
    return re.sub(r"-\d+$", "", slug)


def _slug_tokens(slug: str) -> set[str]:
    """Tokenize a WP slug (split on '-') and stem."""
    return {_stem_token(t) for t in _strip_wp_numeric_suffix(slug).split("-") if len(t) >= 2}


def _check_wp_overlap(
    keyword: str,
    existing_posts: list[dict[str, str]],
) -> dict[str, Any]:
    """Check a candidate keyword against existing WP posts.

    Signals checked (in priority order):
      1. **slug_match** — candidate slug == existing slug (after stripping ``-N``)
      2. **title_token_match** — content tokens of candidate == of title
      3. **token_jaccard** ≥ 0.7 on content tokens → suppress
      4. **containment** — candidate tokens ⊆ title tokens or vice versa (min 2 tokens)
      5. **token_jaccard** ≥ 0.5 on content tokens → warn only

    Returns a dict with keys: ``action`` (suppress/warn/none), ``signal``,
    ``matched_slug``, ``matched_title``, ``matched_url``, ``jaccard``.
    """
    candidate_slug_tokens = _slug_tokens(_keyword_to_slug(keyword))
    candidate_content = _content_tokens(keyword)

    best: dict[str, Any] = {
        "action": "none",
        "signal": "",
        "matched_slug": "",
        "matched_title": "",
        "matched_url": "",
        "jaccard": 0.0,
    }

    for post in existing_posts:
        slug = str(post.get("slug", ""))
        title = html_mod.unescape(str(post.get("title", "")))
        url = str(post.get("url", ""))

        def _result(action: str, signal: str, jac: float = 0.0) -> dict[str, Any]:
            return {
                "action": action,
                "signal": signal,
                "matched_slug": slug,
                "matched_title": title,
                "matched_url": url,
                "jaccard": round(jac, 4),
            }

        # Signal 1: slug match (after stripping -N suffix)
        post_slug_tokens = _slug_tokens(slug)
        if candidate_slug_tokens and candidate_slug_tokens == post_slug_tokens:
            return _result("suppress", "slug_match")

        # Signals 2-5 use content tokens from the post title
        post_content = _content_tokens(title) if title else set()
        if not candidate_content or not post_content:
            continue

        # Signal 2: exact content-token match
        if candidate_content == post_content:
            return _result("suppress", "title_token_match")

        # Signal 3 + 5: Jaccard similarity
        jac = _jaccard(candidate_content, post_content)

        if jac >= WP_OVERLAP_SUPPRESS_JACCARD:
            return _result("suppress", "token_jaccard", jac)

        # Signal 4: strict containment (one is a proper subset of the other)
        if len(candidate_content) >= 2 and len(post_content) >= 2:
            if candidate_content < post_content or post_content < candidate_content:
                return _result("suppress", "containment", jac)

        # Signal 5: moderate Jaccard → warn only
        if jac >= WP_OVERLAP_WARN_JACCARD and jac > best.get("jaccard", 0):
            best = _result("warn", "token_jaccard", jac)

    return best


# ── Pareto frontier ──────────────────────────────────────────────────────


def pareto_frontier_2d(
    items: list[dict[str, float]],
    key_x: str,
    key_y: str,
) -> list[int]:
    """Return indices of non-dominated items on a 2-D frontier (higher = better)."""
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
    family_similarity_threshold: float = DEFAULT_FAMILY_SIMILARITY_THRESHOLD,
    existing_wp_posts: list[dict[str, str]] | None = None,
) -> list[PinClicksKeywordScore]:
    """Rank keywords by expected outbound click score (reach x CTR proxy).

    CTR model runs in two modes per keyword:
      - **full** (engagement available): intent 55%, engagement 20%, frequency 25%
      - **no_engagement**: intent and frequency renormalized to sum to 1

    Selection pipeline:
      1. Qualification gates (min_click_score, low confidence)
      2. Near-duplicate suppression (token-canonical)
      3. Topic-family suppression (Jaccard on modifier-stripped tokens)
      4. WordPress overlap check (slug + title + Jaccard if existing_wp_posts provided)
      5. Pareto frontier on (reach_hat, ctr_hat)
      6. Winner selection: frontier first, backfill if needed
    """
    _ensure_dir(run_dir)
    if not scrape_results:
        raise PinClicksAnalysisError("No PinClicks scrape results available for ranking.")

    trend_rank_map = trend_rank_map or {}
    reach_hat_map = reach_hat_map or {}
    reach_confidence_map = reach_confidence_map or {}
    existing_wp_posts = existing_wp_posts or []

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

    # --- Percentile-rank normalise always-available CTR components ---
    intent_pcts = _percentile_ranks([float(s["outbound_intent_score"]) for s in raw_scores])
    frequency_pcts = _percentile_ranks([float(s["frequency_score"]) for s in raw_scores])

    # Engagement percentile computed ONLY among keywords that have data.
    # Missing engagement is not zero — it is absent.
    engagement_indices = [i for i, s in enumerate(raw_scores) if s["engagement_available"]]
    engagement_pct_map: dict[int, float] = {}
    if engagement_indices:
        eng_values = [float(raw_scores[i]["engagement_score"]) for i in engagement_indices]
        eng_pcts = _percentile_ranks(eng_values)
        for j, idx in enumerate(engagement_indices):
            engagement_pct_map[idx] = eng_pcts[j]

    engagement_coverage = len(engagement_indices) / len(raw_scores) if raw_scores else 0.0

    # --- Build scored candidates with per-keyword CTR model ---
    scored: list[dict[str, Any]] = []
    for index, item in enumerate(raw_scores):
        if item["engagement_available"] and index in engagement_pct_map:
            # Full model: all three components
            ctr_hat = (
                NOMINAL_CTR_WEIGHTS["intent"] * intent_pcts[index]
                + NOMINAL_CTR_WEIGHTS["engagement"] * engagement_pct_map[index]
                + NOMINAL_CTR_WEIGHTS["frequency"] * frequency_pcts[index]
            )
            ctr_model = "full"
        else:
            # Fallback: exclude engagement, renormalize intent + frequency
            active_sum = NOMINAL_CTR_WEIGHTS["intent"] + NOMINAL_CTR_WEIGHTS["frequency"]
            ctr_hat = (
                (NOMINAL_CTR_WEIGHTS["intent"] / active_sum) * intent_pcts[index]
                + (NOMINAL_CTR_WEIGHTS["frequency"] / active_sum) * frequency_pcts[index]
            )
            ctr_model = "no_engagement"

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
                "ctr_model": ctr_model,
                "reach_hat": round(reach_hat, 6),
                "click_score": round(click_score, 6),
                "combined_confidence": round(combined_confidence, 4),
                "outbound_intent_score": round(float(item["outbound_intent_score"]), 6),
                "engagement_score": round(float(item["engagement_score"]), 6),
                "frequency_score": round(float(item["frequency_score"]), 6),
                "record_count": int(item["record_count"]),
                "engagement_available": bool(item["engagement_available"]),
                "trend_rank": int(item["trend_rank"]),
                "topic_family_key": _topic_family_key(item["keyword"]),
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

    # ── Step 2: Near-duplicate suppression (token-canonical) ─────────────

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
    suppressed_dedup = [s for idx, s in enumerate(qualified) if idx in suppressed_indices]

    # ── Step 3: Topic-family suppression (Jaccard) ───────────────────────
    #
    # Greedy: iterate by click_score descending.  A candidate is suppressed
    # if its topic tokens have Jaccard >= threshold with any already-accepted
    # candidate.

    accepted_families: list[tuple[str, set[str]]] = []  # (keyword, topic_tokens)
    family_suppressed: list[dict[str, Any]] = []
    family_active: list[dict[str, Any]] = []

    for item in active:
        tokens = _topic_family_tokens(item["keyword"])
        suppressed_by_family = ""
        for accepted_kw, accepted_tokens in accepted_families:
            if _jaccard(tokens, accepted_tokens) >= family_similarity_threshold:
                suppressed_by_family = accepted_kw
                break
        if suppressed_by_family:
            item["qualified"] = False
            item["disqualification_reason"] = f"topic-family of '{suppressed_by_family}'"
            family_suppressed.append(item)
        else:
            accepted_families.append((item["keyword"], tokens))
            family_active.append(item)

    # ── Step 4: WordPress overlap (slug + title + Jaccard) ─────────────

    wp_suppressed: list[dict[str, Any]] = []
    wp_warned: list[dict[str, Any]] = []
    wp_active: list[dict[str, Any]] = []

    if existing_wp_posts:
        for item in family_active:
            overlap = _check_wp_overlap(item["keyword"], existing_wp_posts)
            detail = ""
            if overlap["matched_slug"]:
                detail_parts = [f"{overlap['signal']}"]
                if overlap["jaccard"] > 0:
                    detail_parts.append(f"jaccard={overlap['jaccard']:.2f}")
                detail_parts.append(f"slug='{overlap['matched_slug']}'")
                if overlap["matched_title"]:
                    detail_parts.append(f"title='{overlap['matched_title'][:60]}'")
                detail = "; ".join(detail_parts)
            item["wp_overlap_detail"] = detail

            if overlap["action"] == "suppress":
                item["qualified"] = False
                item["disqualification_reason"] = f"wp_overlap: {detail}"
                wp_suppressed.append(item)
            elif overlap["action"] == "warn":
                wp_warned.append(item)
                wp_active.append(item)
            else:
                wp_active.append(item)
    else:
        wp_active = family_active

    # ── Step 5: Pareto frontier ──────────────────────────────────────────

    frontier_indices = set(pareto_frontier_2d(wp_active, "reach_hat", "ctr_hat"))

    for idx, item in enumerate(wp_active):
        item["is_pareto_efficient"] = idx in frontier_indices

    # ── Step 6: Deterministic winner selection ───────────────────────────

    wp_active.sort(
        key=lambda s: (
            not s["is_pareto_efficient"],
            -s["click_score"],
            -s["combined_confidence"],
            s["keyword"].casefold(),
        )
    )

    desired = max(1, top_n)
    for idx, item in enumerate(wp_active):
        if idx < desired:
            item["selection_reason"] = (
                "pareto_frontier" if item["is_pareto_efficient"] else "backfill"
            )
        else:
            item["selection_reason"] = ""

    # ── Build final candidate objects ────────────────────────────────────

    all_items = wp_active + family_suppressed + wp_suppressed + suppressed_dedup + disqualified
    all_candidates: list[PinClicksKeywordScore] = []
    for item in all_items:
        selection = str(item.get("selection_reason", ""))
        suppressed_by = ""
        dq = str(item.get("disqualification_reason", ""))

        if dq.startswith("near-duplicate of"):
            suppressed_by = dq.replace("near-duplicate of ", "").strip("'")
            selection = "suppressed_duplicate"
        elif dq.startswith("topic-family of"):
            suppressed_by = dq.replace("topic-family of ", "").strip("'")
            selection = "suppressed_family"
        elif dq.startswith("wp_overlap:"):
            selection = "suppressed_wp_overlap"
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
                topic_family_key=str(item.get("topic_family_key", "")),
                ctr_model=str(item.get("ctr_model", "full")),
                wp_overlap_detail=str(item.get("wp_overlap_detail", "")),
            )
        )

    for rank, candidate in enumerate(all_candidates, start=1):
        candidate.pinclicks_rank = rank

    selected = [c for c in all_candidates if c.selection_reason in ("pareto_frontier", "backfill")]

    # --- Run-level warnings ---
    run_warnings: list[str] = []
    if engagement_coverage < 0.25:
        run_warnings.append(
            f"Engagement data available for only {engagement_coverage:.0%} of keywords. "
            "CTR estimates for most candidates use the no_engagement fallback model."
        )
    if not existing_wp_posts:
        run_warnings.append(
            "WordPress post lookup unavailable — WP overlap suppression was skipped."
        )

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
            "nominal_ctr_weights": NOMINAL_CTR_WEIGHTS,
            "min_click_score": min_click_score,
            "family_similarity_threshold": family_similarity_threshold,
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "engagement_coverage_ratio": round(engagement_coverage, 4),
            "ctr_model_partial": engagement_coverage < 1.0,
            "engagement_signal_available": any(c.engagement_available for c in all_candidates),
            "pareto_frontier_size": sum(1 for c in all_candidates if c.is_pareto_efficient),
            "total_candidates": len(all_candidates),
            "qualified_count": len(wp_active),
            "disqualified_count": len(disqualified),
            "suppressed_duplicate_count": len(suppressed_dedup),
            "suppressed_family_count": len(family_suppressed),
            "suppressed_wp_overlap_count": len(wp_suppressed),
            "selected_count": len(selected),
            "backfill_count": sum(1 for c in selected if c.selection_reason == "backfill"),
            "full_ctr_model_count": sum(1 for c in all_candidates if c.ctr_model == "full"),
            "no_engagement_ctr_model_count": sum(1 for c in all_candidates if c.ctr_model == "no_engagement"),
            "wp_overlap_warning_count": len(wp_warned),
            "run_warnings": run_warnings,
            "wp_posts_checked": len(existing_wp_posts),
            "keywords_with_engagement": [c.keyword for c in all_candidates if c.engagement_available],
            "keywords_without_engagement": [c.keyword for c in all_candidates if not c.engagement_available],
        },
    )
    return selected
