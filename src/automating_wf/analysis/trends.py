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
        # Weekly/temporal-like columns are often date labels; include numeric values broadly.
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


def parse_trends_export_rows(
    *,
    rows: list[dict[str, Any]],
    seed_keyword: str,
    source_file: str,
    region: str,
    time_range: str,
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
            )
        )
    return parsed


def _normalize_metric(values: list[float]) -> list[float]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if math.isclose(min_value, max_value):
        return [1.0 for _ in values]
    denominator = max_value - min_value
    return [(value - min_value) / denominator for value in values]


def analyze_trends_exports(
    *,
    export_files_by_seed: dict[str, list[str]],
    run_dir: Path,
    top_n: int = 20,
    region: str = "GLOBAL",
    time_range: str = "12m",
) -> list[TrendKeywordCandidate]:
    _ensure_dir(run_dir)
    all_records: list[TrendExportRecord] = []

    for seed_keyword, file_paths in export_files_by_seed.items():
        for file_path in file_paths:
            rows = parse_tabular_export(Path(file_path))
            parsed = parse_trends_export_rows(
                rows=rows,
                seed_keyword=seed_keyword,
                source_file=file_path,
                region=region,
                time_range=time_range,
            )
            all_records.extend(parsed)

    _write_json(run_dir / "trends_records.json", [record.to_dict() for record in all_records])
    if not all_records:
        raise TrendsAnalysisError("No trend records found after parsing export files.")

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
        trend_avg = mean([item.trend_index for item in items])
        growth_avg = mean([item.growth_rate for item in items])
        consistency_avg = mean([item.consistency_score for item in items])
        aggregates.append(
            {
                "normalized_keyword": normalized,
                "keyword": canonical_keyword.get(normalized, normalized),
                "trend_index": float(trend_avg),
                "growth": float(growth_avg),
                "consistency": float(consistency_avg),
                "source_count": len(items),
            }
        )

    trend_norm = _normalize_metric([item["trend_index"] for item in aggregates])
    growth_norm = _normalize_metric([item["growth"] for item in aggregates])
    consistency_norm = _normalize_metric([item["consistency"] for item in aggregates])

    candidates: list[TrendKeywordCandidate] = []
    for index, item in enumerate(aggregates):
        score = (0.5 * trend_norm[index]) + (0.3 * growth_norm[index]) + (0.2 * consistency_norm[index])
        candidates.append(
            TrendKeywordCandidate(
                keyword=item["keyword"],
                hybrid_score=round(score, 6),
                trend_index_norm=round(trend_norm[index], 6),
                growth_norm=round(growth_norm[index], 6),
                consistency_norm=round(consistency_norm[index], 6),
                source_count=int(item["source_count"]),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.hybrid_score,
            -item.trend_index_norm,
            -item.growth_norm,
            -item.source_count,
            item.keyword.casefold(),
        )
    )

    for rank, candidate in enumerate(candidates, start=1):
        candidate.rank = rank

    selected = candidates[: max(1, top_n)]
    _write_json(run_dir / "trends_keyword_candidates.json", [item.to_dict() for item in candidates])
    _write_json(run_dir / "trends_top_keywords.json", [item.to_dict() for item in selected])
    _write_json(
        run_dir / "trends_scoring_metadata.json",
        {
            "top_n": top_n,
            "region": region,
            "time_range": time_range,
            "record_count": len(all_records),
            "candidate_count": len(candidates),
        },
    )
    return selected
