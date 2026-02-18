from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

from pinterest_analysis import score_keyword_candidates
from pinterest_models import PinClicksKeywordScore, SeedScrapeResult


INSPIRATION_TERMS = {
    "idea",
    "inspiration",
    "inspo",
    "style",
    "look",
    "design",
    "aesthetic",
}

PROBLEM_SOLVING_TERMS = {
    "how to",
    "tips",
    "guide",
    "best",
    "easy",
    "small",
    "budget",
    "solution",
    "fix",
}


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


def _intent_alignment_score(records: list[Any]) -> float:
    if not records:
        return 0.0
    hits = 0
    for record in records:
        text = f"{record.title} {record.description}".casefold()
        has_inspiration = any(term in text for term in INSPIRATION_TERMS)
        has_problem_solving = any(term in text for term in PROBLEM_SOLVING_TERMS)
        if has_inspiration or has_problem_solving:
            hits += 1
    return hits / len(records)


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if abs(max_value - min_value) < 1e-9:
        return [1.0 for _ in values]
    return [(value - min_value) / (max_value - min_value) for value in values]


def rank_pinclicks_keywords(
    *,
    scrape_results: list[SeedScrapeResult],
    run_dir: Path,
    top_n: int = 5,
    trend_rank_map: dict[str, int] | None = None,
) -> list[PinClicksKeywordScore]:
    _ensure_dir(run_dir)
    if not scrape_results:
        raise PinClicksAnalysisError("No PinClicks scrape results available for ranking.")

    trend_rank_map = trend_rank_map or {}
    raw_scores: list[dict[str, float | int | str]] = []

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
        intent_score = float(_intent_alignment_score(records))

        raw_scores.append(
            {
                "keyword": result.seed_keyword,
                "frequency_score": frequency_score,
                "engagement_score": engagement_score,
                "intent_score": intent_score,
                "record_count": len(records),
                "trend_rank": int(trend_rank_map.get(result.seed_keyword, 0)),
            }
        )

    if not raw_scores:
        raise PinClicksAnalysisError("No rankable PinClicks results after filtering empty records.")

    frequency_norm = _normalize([float(item["frequency_score"]) for item in raw_scores])
    engagement_norm = _normalize([float(item["engagement_score"]) for item in raw_scores])
    intent_norm = _normalize([float(item["intent_score"]) for item in raw_scores])

    candidates: list[PinClicksKeywordScore] = []
    for index, item in enumerate(raw_scores):
        total = (0.5 * frequency_norm[index]) + (0.35 * engagement_norm[index]) + (0.15 * intent_norm[index])
        candidates.append(
            PinClicksKeywordScore(
                keyword=str(item["keyword"]),
                total_score=round(total, 6),
                frequency_score=round(float(item["frequency_score"]), 6),
                engagement_score=round(float(item["engagement_score"]), 6),
                intent_score=round(float(item["intent_score"]), 6),
                record_count=int(item["record_count"]),
                trend_rank=int(item["trend_rank"]),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.total_score,
            -item.frequency_score,
            -item.engagement_score,
            item.trend_rank if item.trend_rank > 0 else 9999,
            item.keyword.casefold(),
        )
    )

    for rank, candidate in enumerate(candidates, start=1):
        candidate.pinclicks_rank = rank

    selected = candidates[: max(1, top_n)]
    _write_json(run_dir / "pinclicks_keyword_scores.json", [item.to_dict() for item in candidates])
    _write_json(run_dir / f"run_winners_top{max(1, top_n)}.json", [item.to_dict() for item in selected])
    return selected
