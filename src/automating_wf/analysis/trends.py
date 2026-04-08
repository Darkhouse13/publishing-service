from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from automating_wf.scrapers.file_parser import coerce_numeric, parse_tabular_export
from automating_wf.models.pinterest import TrendExportRecord, TrendKeywordCandidate


# Bump this when scoring logic changes to invalidate cached artifacts.
SCORING_VERSION = "2.2.0-reach"

# Qualification defaults — candidates below these floors are disqualified.
DEFAULT_MIN_REACH_HAT = 0.05
DEFAULT_MIN_SOURCE_COUNT = 1
DEFAULT_MIN_REACH_CONFIDENCE = 0.3

# Nominal reach-estimator weights.  Effective weights are dynamically
# redistributed at run time when a feature is flat or missing.
NOMINAL_REACH_WEIGHTS: dict[str, float] = {
    "trend_index": 0.55,
    "growth": 0.30,
    "consistency": 0.05,
    "source_count": 0.10,
}


TREND_INDEX_ALIASES = (
    "trend index",
    "interest",
    "search volume",
    "volume",
    "score",
    "popularity",
)

GROWTH_ALIASES = (
    "growth",
    "change",
    "trend change",
    "yoy",
    "mom",
    "year over year",
    "month over month",
    "variation",
    "variation hebdomadaire",
    "variation mensuelle",
    "variation annuelle",
)

KEYWORD_ALIASES = (
    "keyword",
    "trend",
    "tendance",
    "search term",
    "search query",
    "query",
    "term",
    "topic",
    "mot cle",
    "mots cles",
    "mot-cl",
)

SEED_MATCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "best",
    "cozy",
    "cute",
    "diy",
    "easy",
    "for",
    "home",
    "idea",
    "ideas",
    "in",
    "modern",
    "new",
    "of",
    "on",
    "small",
    "the",
    "to",
    "top",
    "your",
}


class TrendsAnalysisError(RuntimeError):
    """Raised when trends export analysis fails."""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_header(value: str) -> str:
    lowered = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> str:
    normalized_map = {_normalize_header(header): header for header in headers}
    for alias in aliases:
        alias_norm = _normalize_header(alias)
        for normalized, original in normalized_map.items():
            if alias_norm in normalized:
                return original
    return ""


def _extract_numeric_series(row: dict[str, Any], ignored_headers: set[str]) -> list[float]:
    values: list[float] = []
    for header, raw_value in row.items():
        if header in ignored_headers:
            continue
        header_norm = _normalize_header(header)
        if not header_norm:
            continue
        numeric = coerce_numeric(raw_value)
        if not math.isfinite(numeric):
            continue
        if abs(numeric) <= 0:
            continue
        values.append(float(numeric))
    return values


def _consistency_from_series(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return 1.0
    avg = mean(values)
    if avg <= 0:
        return 0.0
    deviation = pstdev(values)
    cv = deviation / avg if avg else 0.0
    nonzero_ratio = len([value for value in values if value > 0]) / len(values)
    return max(0.0, nonzero_ratio * (1.0 / (1.0 + cv)))


def _normalize_keyword(value: str) -> str:
    collapsed = " ".join(str(value or "").split()).strip().casefold()
    return re.sub(r"\s+", " ", collapsed)


def _tokenize_keyword(value: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9]+", str(value or "").casefold())
        if len(token) >= 3 and token not in SEED_MATCH_STOPWORDS
    }
    return tokens


def _keyword_matches_seed(keyword: str, seed_keyword: str) -> bool:
    keyword_tokens = _tokenize_keyword(keyword)
    seed_tokens = _tokenize_keyword(seed_keyword)
    if not keyword_tokens or not seed_tokens:
        return True
    return bool(keyword_tokens & seed_tokens)


def _is_usable_keyword(value: str) -> bool:
    normalized = _normalize_header(value)
    if not normalized:
        return False
    if len(normalized) < 2:
        return False
    if re.fullmatch(r"[0-9]+(?:[.][0-9]+)?", normalized):
        return False
    if not re.search(r"[a-z]", normalized):
        return False
    blocked = {
        "filtres selectionnes",
        "types de tendance",
        "periode",
        "centres d interet",
        "inclure des mots cles",
        "age",
        "identite de genre",
        "rang",
        "rank",
        "interest",
        "gender",
    }
    return normalized not in blocked


# ── Scrape-quality metadata ──────────────────────────────────────────────


def _read_export_metadata(export_file: str) -> dict[str, Any]:
    """Read trends_export_metadata.json from the same directory as *export_file*."""
    meta_path = Path(export_file).parent / "trends_export_metadata.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Dynamic weight redistribution ────────────────────────────────────────


def _is_feature_active(values: list[float]) -> tuple[bool, str]:
    """Check if a feature has meaningful variation across candidates.

    Returns ``(active, reason)`` where *reason* explains inactivity.
    A single-candidate run always reports features as active because
    there is nothing to redistribute.
    """
    if not values:
        return False, "no_values"
    if len(values) <= 1:
        return True, ""  # single candidate — use nominal weights
    if all(v == 0.0 for v in values):
        return False, "all_zero"
    unique = set(round(v, 8) for v in values)
    if len(unique) <= 1:
        return False, "constant"
    return True, ""


def _compute_effective_weights(
    feature_values: dict[str, list[float]],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Compute effective weights by redistributing from inactive features.

    Returns (effective_weights, feature_status) where feature_status maps
    each feature name to ``{"active": bool, "reason": str, "nominal": float,
    "effective": float}``.
    """
    feature_status: dict[str, dict[str, Any]] = {}
    active_nominal_sum = 0.0

    for name, values in feature_values.items():
        active, reason = _is_feature_active(values)
        feature_status[name] = {
            "active": active,
            "reason": reason,
            "nominal": NOMINAL_REACH_WEIGHTS.get(name, 0.0),
        }
        if active:
            active_nominal_sum += NOMINAL_REACH_WEIGHTS.get(name, 0.0)

    effective: dict[str, float] = {}

    if active_nominal_sum <= 0:
        # All features inactive — use equal weights as fallback
        n = max(len(feature_values), 1)
        for name in feature_values:
            effective[name] = 1.0 / n
            feature_status[name]["effective"] = round(1.0 / n, 6)
        return effective, feature_status

    for name in feature_values:
        if not feature_status[name]["active"]:
            effective[name] = 0.0
        else:
            effective[name] = NOMINAL_REACH_WEIGHTS.get(name, 0.0) / active_nominal_sum

    for name in feature_values:
        feature_status[name]["effective"] = round(effective[name], 6)

    return effective, feature_status


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


def _suppress_near_duplicates(
    candidates: list[TrendKeywordCandidate],
) -> list[TrendKeywordCandidate]:
    """Mark near-duplicate candidates, keeping the one with highest reach_hat.

    Mutates ``suppressed_by`` on dominated duplicates.  Returns the full
    list (caller filters).
    """
    canonical_groups: dict[str, list[int]] = defaultdict(list)
    for idx, c in enumerate(candidates):
        key = _dedup_canonical_key(c.keyword)
        canonical_groups[key].append(idx)

    for _key, indices in canonical_groups.items():
        if len(indices) <= 1:
            continue
        best_idx = indices[0]
        best_kw = candidates[best_idx].keyword
        for dup_idx in indices[1:]:
            if not candidates[dup_idx].suppressed_by:
                candidates[dup_idx].suppressed_by = best_kw
                candidates[dup_idx].qualified = False
                candidates[dup_idx].disqualification_reason = (
                    f"near-duplicate of '{best_kw}'"
                )
    return candidates


# ── Parsing ──────────────────────────────────────────────────────────────


def parse_trends_export_rows(
    *,
    rows: list[dict[str, Any]],
    seed_keyword: str,
    source_file: str,
    region: str,
    time_range: str,
    include_keyword_applied: bool = True,
) -> list[TrendExportRecord]:
    if not rows:
        return []
    headers = list(rows[0].keys())
    keyword_col = _find_column(headers, KEYWORD_ALIASES)
    trend_index_col = _find_column(headers, TREND_INDEX_ALIASES)
    growth_col = _find_column(headers, GROWTH_ALIASES)

    if not keyword_col:
        raise TrendsAnalysisError(
            f"Could not detect keyword column in trends export '{source_file}'."
        )

    parsed: list[TrendExportRecord] = []
    ignored = {keyword_col}
    if trend_index_col:
        ignored.add(trend_index_col)
    if growth_col:
        ignored.add(growth_col)

    for row in rows:
        keyword = str(row.get(keyword_col, "")).strip()
        if not keyword:
            continue
        if not _is_usable_keyword(keyword):
            continue
        if not _keyword_matches_seed(keyword, seed_keyword):
            continue
        trend_index = coerce_numeric(row.get(trend_index_col, 0)) if trend_index_col else 0.0
        growth_rate = coerce_numeric(row.get(growth_col, 0)) if growth_col else 0.0
        series = _extract_numeric_series(row, ignored_headers=ignored)
        consistency = _consistency_from_series(series)
        parsed.append(
            TrendExportRecord(
                seed_keyword=seed_keyword,
                keyword=keyword,
                trend_index=float(trend_index),
                growth_rate=float(growth_rate),
                consistency_score=float(consistency),
                region=region,
                time_range=time_range,
                source_file=source_file,
                include_keyword_applied=include_keyword_applied,
            )
        )
    return parsed


# ── Percentile-rank normalization ────────────────────────────────────────


def _percentile_ranks(values: list[float]) -> list[float]:
    """Percentile-rank normalization with tie handling.  Returns values in [0, 1].

    More robust than min-max across runs because it is insensitive to
    outliers and produces a uniform distribution regardless of the raw
    scale of the input.
    """
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


# ── Confidence ───────────────────────────────────────────────────────────


def _compute_reach_confidence(
    source_count: int,
    trend_index_raw: float,
    growth_rate_raw: float,
    include_keyword_ratio: float,
) -> float:
    """Estimate confidence in reach_hat based on data-quality signals."""
    confidence = 0.3
    if source_count >= 2:
        confidence += 0.15
    if source_count >= 3:
        confidence += 0.1
    if trend_index_raw > 0:
        confidence += 0.15
    if abs(growth_rate_raw) > 0:
        confidence += 0.1
    confidence += 0.2 * include_keyword_ratio
    return min(1.0, round(confidence, 4))


# ── Main entry point ─────────────────────────────────────────────────────


def analyze_trends_exports(
    *,
    export_files_by_seed: dict[str, list[str]],
    run_dir: Path,
    top_n: int = 20,
    region: str = "GLOBAL",
    time_range: str = "12m",
    min_reach_hat: float = DEFAULT_MIN_REACH_HAT,
    min_source_count: int = DEFAULT_MIN_SOURCE_COUNT,
    min_reach_confidence: float = DEFAULT_MIN_REACH_CONFIDENCE,
) -> list[TrendKeywordCandidate]:
    """Score trend keywords by estimated reach potential.

    Nominal reach-estimator weights:
      - 55% trend_index  (current volume)
      - 30% growth_rate  (expanding reach)
      - 10% source_count (cross-seed confirmation)
      -  5% consistency  (stability)

    If a feature is flat or missing for the entire run (all values zero,
    or no variation), its nominal weight is redistributed proportionally
    across the remaining active features.  Both nominal and effective
    weights are persisted in the run metadata.

    Qualification gates (applied in order):
      1. reach_hat >= min_reach_hat
      2. source_count >= min_source_count
      3. reach_confidence >= min_reach_confidence
      4. near-duplicate suppression (keeps highest-reach variant)
    """
    _ensure_dir(run_dir)
    all_records: list[TrendExportRecord] = []

    for seed_keyword, file_paths in export_files_by_seed.items():
        for file_path in file_paths:
            meta = _read_export_metadata(file_path)
            ik_applied = bool(meta.get("include_keyword_applied", True))

            rows = parse_tabular_export(Path(file_path))
            parsed = parse_trends_export_rows(
                rows=rows,
                seed_keyword=seed_keyword,
                source_file=file_path,
                region=region,
                time_range=time_range,
                include_keyword_applied=ik_applied,
            )
            all_records.extend(parsed)

    _write_json(run_dir / "trends_records.json", [record.to_dict() for record in all_records])
    if not all_records:
        raise TrendsAnalysisError("No trend records found after parsing export files.")

    # --- Group by normalized keyword and aggregate raw metrics ---
    grouped: dict[str, list[TrendExportRecord]] = defaultdict(list)
    canonical_keyword: dict[str, str] = {}
    for record in all_records:
        normalized = _normalize_keyword(record.keyword)
        if not normalized:
            continue
        grouped[normalized].append(record)
        canonical_keyword.setdefault(normalized, record.keyword.strip())

    aggregates: list[dict[str, Any]] = []
    for normalized, items in grouped.items():
        ik_count = sum(1 for r in items if r.include_keyword_applied)
        ik_ratio = ik_count / len(items) if items else 1.0
        aggregates.append(
            {
                "normalized_keyword": normalized,
                "keyword": canonical_keyword.get(normalized, normalized),
                "trend_index": float(mean([item.trend_index for item in items])),
                "growth": float(mean([item.growth_rate for item in items])),
                "consistency": float(mean([item.consistency_score for item in items])),
                "source_count": len(items),
                "include_keyword_ratio": float(ik_ratio),
            }
        )

    # --- Dynamic weight redistribution ---
    feature_values = {
        "trend_index": [a["trend_index"] for a in aggregates],
        "growth": [a["growth"] for a in aggregates],
        "consistency": [a["consistency"] for a in aggregates],
        "source_count": [float(a["source_count"]) for a in aggregates],
    }
    effective_weights, feature_status = _compute_effective_weights(feature_values)

    run_warnings: list[str] = []
    for name, status in feature_status.items():
        if not status["active"]:
            run_warnings.append(
                f"Stage 1 feature '{name}' is inactive ({status['reason']}); "
                f"nominal weight {status['nominal']:.0%} redistributed to active features."
            )

    # --- Percentile-rank normalize each dimension ---
    trend_pcts = _percentile_ranks(feature_values["trend_index"])
    growth_pcts = _percentile_ranks(feature_values["growth"])
    consistency_pcts = _percentile_ranks(feature_values["consistency"])
    source_pcts = _percentile_ranks(feature_values["source_count"])

    pct_map = {
        "trend_index": trend_pcts,
        "growth": growth_pcts,
        "consistency": consistency_pcts,
        "source_count": source_pcts,
    }

    # --- Compute reach_hat and apply qualification gates ---
    candidates: list[TrendKeywordCandidate] = []
    for index, agg in enumerate(aggregates):
        reach_hat = sum(
            effective_weights[feat] * pct_map[feat][index]
            for feat in effective_weights
        )
        reach_confidence = _compute_reach_confidence(
            source_count=agg["source_count"],
            trend_index_raw=agg["trend_index"],
            growth_rate_raw=agg["growth"],
            include_keyword_ratio=agg["include_keyword_ratio"],
        )

        qualified = True
        disqualification_reason = ""
        if reach_hat < min_reach_hat:
            qualified = False
            disqualification_reason = (
                f"reach_hat {reach_hat:.4f} below minimum {min_reach_hat}"
            )
        elif agg["source_count"] < min_source_count:
            qualified = False
            disqualification_reason = (
                f"source_count {agg['source_count']} below minimum {min_source_count}"
            )
        elif reach_confidence < min_reach_confidence:
            qualified = False
            disqualification_reason = (
                f"reach_confidence {reach_confidence:.4f} below minimum {min_reach_confidence}"
            )

        candidates.append(
            TrendKeywordCandidate(
                keyword=agg["keyword"],
                reach_hat=round(reach_hat, 6),
                reach_confidence=round(reach_confidence, 4),
                trend_index_raw=round(agg["trend_index"], 4),
                growth_rate_raw=round(agg["growth"], 4),
                consistency_raw=round(agg["consistency"], 4),
                source_count=int(agg["source_count"]),
                qualified=qualified,
                include_keyword_ratio=round(agg["include_keyword_ratio"], 4),
                disqualification_reason=disqualification_reason,
            )
        )

    # --- Sort by reach_hat descending so dedup keeps the best variant ---
    candidates.sort(
        key=lambda c: (
            -c.reach_hat,
            -c.reach_confidence,
            -c.source_count,
            c.keyword.casefold(),
        )
    )

    # --- Near-duplicate suppression ---
    _suppress_near_duplicates(candidates)

    # --- Rank qualified candidates by reach_hat ---
    qualified_candidates = [c for c in candidates if c.qualified]
    for rank, candidate in enumerate(qualified_candidates, start=1):
        candidate.rank = rank

    selected = qualified_candidates[: max(1, top_n)] if qualified_candidates else []

    # --- Persist artifacts ---
    _write_json(
        run_dir / "trends_keyword_candidates.json",
        [c.to_dict() for c in candidates],
    )
    _write_json(
        run_dir / "trends_top_keywords.json",
        [c.to_dict() for c in selected],
    )
    _write_json(
        run_dir / "trends_scoring_metadata.json",
        {
            "scoring_version": SCORING_VERSION,
            "top_n": top_n,
            "region": region,
            "time_range": time_range,
            "min_reach_hat": min_reach_hat,
            "min_source_count": min_source_count,
            "min_reach_confidence": min_reach_confidence,
            "nominal_weights": {k: round(v, 4) for k, v in NOMINAL_REACH_WEIGHTS.items()},
            "effective_weights": {k: round(v, 6) for k, v in effective_weights.items()},
            "feature_status": feature_status,
            "run_warnings": run_warnings,
            "record_count": len(all_records),
            "candidate_count": len(candidates),
            "qualified_count": len(qualified_candidates),
            "disqualified_count": len(candidates) - len(qualified_candidates),
            "suppressed_count": sum(1 for c in candidates if c.suppressed_by),
        },
    )
    return selected
