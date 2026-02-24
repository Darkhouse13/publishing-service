"""Shared runtime configuration and phase result models for the bulk engine."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from typing import Any

from dotenv import load_dotenv


PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND = "search_input_not_found"
PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED = "search_input_rejected"
PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED = "direct_top_pins_navigation_failed"
PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED = "export_download_failed"
PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED = "no_records_extracted"
PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED = "captcha_checkpoint_required"
PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED = "authentication_failed"
PINCLICKS_SKIP_REASON_UNKNOWN = "unknown_scrape_failure"


def _read_positive_int(value: Any, default: int) -> int:
    """Parse a positive int and fallback to the provided default."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _read_bool(value: Any, default: bool = False) -> bool:
    """Parse common truthy/falsey strings into bool with fallback default."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_keywords(value: Any) -> list[str]:
    """Normalize keyword input from list/text into deduplicated ordered values."""
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value or "")
        raw_items = [part for line in text.splitlines() for part in line.split(",")]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        keyword = str(item or "").strip()
        if not keyword:
            continue
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        cleaned.append(keyword)
    return cleaned


def _load_seed_map() -> dict[str, list[str]]:
    """Load and normalize PINTEREST_SEED_MAP_JSON from environment."""
    load_dotenv()
    raw = os.getenv("PINTEREST_SEED_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for suffix, seeds in payload.items():
        if not isinstance(suffix, str) or not isinstance(seeds, list):
            continue
        normalized[suffix.strip().upper()] = _parse_keywords(seeds)
    return normalized


@dataclass
class EngineRunOptions:
    """Runtime options used to execute the bulk Pinterest engine."""

    # Target WordPress/blog environment suffix (maps to WP_URL_<SUFFIX> keys).
    blog_suffix: str
    # Seed keywords for Trends collection; defaults from PINTEREST_SEED_MAP_JSON for blog suffix.
    seed_keywords: list[str]
    # Trends region filter; defaults from PINTEREST_TRENDS_REGION/PINTEREST_TRENDS_FILTER_REGION.
    trends_region: str
    # Trends time range filter; defaults from PINTEREST_TRENDS_RANGE/PINTEREST_TRENDS_FILTER_RANGE.
    trends_range: str
    # Number of top trend keywords kept after ranking; defaults from PINTEREST_TRENDS_TOP_N/PINTEREST_TRENDS_TOP_KEYWORDS.
    trends_top_n: int
    # Explicit trends selected by UI; empty means use all ranked trends (current CLI behavior).
    selected_trend_keywords: list[str]
    # Max pin records scraped per keyword in PinClicks; defaults to current hardcoded behavior (25).
    pinclicks_max_records: int
    # Number of winner keywords/articles to process; defaults from PINTEREST_PINCLICKS_WINNERS_PER_RUN.
    winners_count: int
    # WordPress publish status passed to uploader; defaults from WP_POST_STATUS then "draft".
    publish_status: str
    # Whether scraping runs in headed browser mode; defaults False.
    headed: bool
    # Optional run id/path to resume from existing artifacts; defaults None.
    resume_run_id: str | None

    @classmethod
    def from_env(cls, blog_suffix: str) -> "EngineRunOptions":
        """Build options from environment values, preserving current CLI defaults."""
        load_dotenv()
        suffix = str(blog_suffix or "").strip().upper()
        seed_map = _load_seed_map()

        region = (
            os.getenv("PINTEREST_TRENDS_REGION", "").strip()
            or os.getenv("PINTEREST_TRENDS_FILTER_REGION", "").strip()
            or "GLOBAL"
        )
        time_range = (
            os.getenv("PINTEREST_TRENDS_RANGE", "").strip()
            or os.getenv("PINTEREST_TRENDS_FILTER_RANGE", "").strip()
            or "12m"
        )
        top_n = _read_positive_int(
            os.getenv("PINTEREST_TRENDS_TOP_N", "").strip()
            or os.getenv("PINTEREST_TRENDS_TOP_KEYWORDS", "").strip(),
            20,
        )
        winners_count = _read_positive_int(
            os.getenv("PINTEREST_PINCLICKS_WINNERS_PER_RUN", "").strip(),
            5,
        )
        publish_status = os.getenv("WP_POST_STATUS", "draft").strip() or "draft"
        seed_keywords = seed_map.get(suffix, [])

        return cls(
            blog_suffix=suffix,
            seed_keywords=seed_keywords,
            trends_region=region,
            trends_range=time_range,
            trends_top_n=top_n,
            selected_trend_keywords=[],
            pinclicks_max_records=25,
            winners_count=winners_count,
            publish_status=publish_status,
            headed=False,
            resume_run_id=None,
        )

    @classmethod
    def from_ui(cls, form_data: dict[str, Any]) -> "EngineRunOptions":
        """Build options from UI values, falling back to environment defaults per blog."""
        if "blog_suffix" not in form_data:
            raise ValueError("blog_suffix is required in form_data")

        blog_suffix = str(form_data.get("blog_suffix", "")).strip().upper()
        defaults = cls.from_env(blog_suffix)
        field_names = {item.name for item in fields(cls)}

        overrides: dict[str, Any] = {}
        for key, value in form_data.items():
            if key not in field_names or value is None:
                continue
            overrides[key] = value

        if "seed_keywords" in overrides:
            overrides["seed_keywords"] = _parse_keywords(overrides["seed_keywords"])
        if "selected_trend_keywords" in overrides:
            overrides["selected_trend_keywords"] = _parse_keywords(overrides["selected_trend_keywords"])
        if "trends_top_n" in overrides:
            overrides["trends_top_n"] = _read_positive_int(overrides["trends_top_n"], defaults.trends_top_n)
        if "pinclicks_max_records" in overrides:
            overrides["pinclicks_max_records"] = _read_positive_int(
                overrides["pinclicks_max_records"],
                defaults.pinclicks_max_records,
            )
        if "winners_count" in overrides:
            overrides["winners_count"] = _read_positive_int(overrides["winners_count"], defaults.winners_count)
        if "headed" in overrides:
            overrides["headed"] = _read_bool(overrides["headed"], defaults.headed)
        if "resume_run_id" in overrides:
            resume = str(overrides["resume_run_id"] or "").strip()
            overrides["resume_run_id"] = resume or None
        if "publish_status" in overrides:
            publish_status = str(overrides["publish_status"] or "").strip()
            overrides["publish_status"] = publish_status or defaults.publish_status
        if "blog_suffix" in overrides:
            overrides["blog_suffix"] = str(overrides["blog_suffix"] or "").strip().upper() or defaults.blog_suffix
        if "trends_region" in overrides:
            overrides["trends_region"] = str(overrides["trends_region"] or "").strip() or defaults.trends_region
        if "trends_range" in overrides:
            overrides["trends_range"] = str(overrides["trends_range"] or "").strip() or defaults.trends_range

        return cls(
            blog_suffix=overrides.get("blog_suffix", defaults.blog_suffix),
            seed_keywords=overrides.get("seed_keywords", defaults.seed_keywords),
            trends_region=overrides.get("trends_region", defaults.trends_region),
            trends_range=overrides.get("trends_range", defaults.trends_range),
            trends_top_n=overrides.get("trends_top_n", defaults.trends_top_n),
            selected_trend_keywords=overrides.get(
                "selected_trend_keywords",
                defaults.selected_trend_keywords,
            ),
            pinclicks_max_records=overrides.get(
                "pinclicks_max_records",
                defaults.pinclicks_max_records,
            ),
            winners_count=overrides.get("winners_count", defaults.winners_count),
            publish_status=overrides.get("publish_status", defaults.publish_status),
            headed=overrides.get("headed", defaults.headed),
            resume_run_id=overrides.get("resume_run_id", defaults.resume_run_id),
        )


@dataclass
class TrendCandidates:
    """Phase 1 result with ranked trend keywords for the current run."""

    # Unique run identifier shared across all phases.
    run_id: str
    # Absolute/relative path to the run directory that stores artifacts.
    run_dir: str
    # Ranked trend candidates including keyword and score metadata.
    ranked_keywords: list[dict[str, Any]]
    # Count of parsed trend records prior to top-N selection.
    raw_trends_count: int


@dataclass
class PinClicksResults:
    """Phase 2 result with ranked winners and scrape failures."""

    # Unique run identifier shared across all phases.
    run_id: str
    # Absolute/relative path to the run directory that stores artifacts.
    run_dir: str
    # Winner rows selected for article generation.
    winners: list[dict[str, Any]]
    # Keywords skipped due to scrape/rank failures.
    # Expected normalized shape per item:
    # {
    #   "keyword": str,
    #   "reason": str,
    #   "error": str,
    #   "attempts": int,
    #   "used_headed_fallback": bool,
    #   "source_stage": "pinclicks"
    # }
    skipped: list[dict[str, Any]]


@dataclass
class GenerationResults:
    """Phase 3 result with per-article completion/failure outcomes."""

    # Unique run identifier shared across all phases.
    run_id: str
    # Absolute/relative path to the run directory that stores artifacts.
    run_dir: str
    # Successfully processed winners with publish/csv details.
    completed: list[dict[str, Any]]
    # Partially successful winners (for example, published to WordPress but CSV append failed).
    partial: list[dict[str, Any]]
    # Failures that happened before WordPress publish succeeded.
    failed_pre_publish: list[dict[str, Any]]
    # Failed winners with error details.
    failed: list[dict[str, Any]]
    # Manifest file generated for the run.
    manifest_path: str
    # Optional CSV output path for Pinterest bulk upload file.
    csv_path: str = ""
