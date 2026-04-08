from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from automating_wf.engine.config import (
    EngineRunOptions,
    GenerationResults,
    PINCLICKS_SKIP_REASON_UNKNOWN,
    PinClicksResults,
    TrendCandidates,
)
from automating_wf.config.blogs import (
    BLOG_CONFIGS,
    resolve_blog_config,
    resolve_blog_profile,
    resolve_prompt_type,
    suggest_primary_category,
)
from automating_wf.content.generators import (
    ArticleValidationError,
    GenerationError,
    generate_article,
    generate_image,
)
from automating_wf.content.validator import (
    ArticleValidationFinalError,
    ArticleValidatorError,
    load_repair_system_prompt,
    validate_article_with_repair,
)
from automating_wf.analysis.pinclicks import PinClicksAnalysisError, rank_pinclicks_keywords
from automating_wf.analysis.pinterest import AnalysisError, InsufficientSignalError, analyze_seed
from automating_wf.design.pinterest import ImageDesignError, generate_pinterest_image
from automating_wf.export.pinterest_csv import (
    DEFAULT_CADENCE_MINUTES,
    ExporterError,
    append_csv_row,
    csv_timezone_name,
    preview_publish_schedule,
    resolve_board_name,
    validate_board_mapping_for_blog,
)
from automating_wf.models.pinterest import CsvRow, PinRecord, RunManifestEntry, SeedScrapeResult
from automating_wf.scrapers.pinclicks import (
    PINCLICKS_SCRAPE_SOURCE_BRAVE,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
    SCRAPE_RETRY_ATTEMPTS,
    ScraperError,
    _classify_scrape_error,
    ensure_pinclicks_brave_session,
    scrape_seed,
)
from automating_wf.analysis.trends import (
    SCORING_VERSION as TRENDS_SCORING_VERSION,
    TrendsAnalysisError,
    analyze_trends_exports,
)
from automating_wf.scrapers.trends import TRENDS_RETRY_ATTEMPTS, TrendsScraperError, scrape_trends_exports
from automating_wf.wordpress.uploader import (
    WordPressUploadError,
    list_categories,
    publish_post,
    resolve_category_id,
    upload_media,
)


RUN_ROOT = Path("tmp") / "pinterest_engine"
MANIFEST_NAME = "manifest.jsonl"
SUMMARY_NAME = "run_summary.json"
RUN_OPTIONS_NAME = "run_options.json"
TRENDS_TOP_KEYWORDS_FILE = "trends_top_keywords.json"


def _run_csv_path(run_dir: Path, blog_suffix: str) -> Path:
    return run_dir / f"pinterest_bulk_upload_{blog_suffix.strip().lower()}.csv"
TERMINAL_WINNER_STATUSES = {
    "csv_appended",
    "wp_published",
    "csv_failed",
    "article_failed",
    "insufficient_signal",
    "analysis_failed",
    "image_failed",
    "wp_failed",
}
TERMINAL_PINCLICKS_CACHE_STATUSES = {
    "pinclicks_exported",
    "pinclicks_scraped",
    "pinclicks_ranked",
    "winner_processed",
    "wp_published",
    "csv_appended",
    "article_failed",
    "analysis_failed",
    "image_failed",
    "wp_failed",
    "insufficient_signal",
}
PINCLICKS_STATUS_SCRAPED = "pinclicks_scraped"


class EngineError(RuntimeError):
    """Raised when engine configuration is invalid."""


FULL_SUCCESS_STATUSES = {"csv_appended"}
PARTIAL_SUCCESS_STATUSES = {"csv_failed", "wp_published"}
FAILED_PRE_PUBLISH_STATUSES = {
    "article_failed",
    "analysis_failed",
    "image_failed",
    "wp_failed",
    "insufficient_signal",
    "generation_input",
    "pinclicks_cache_missing",
    "pinclicks_cache_parse",
}


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _running_in_streamlit() -> bool:
    """Detect whether code is currently running inside Streamlit runtime."""
    if "streamlit" not in sys.modules:
        return False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


def _run_scraper_subprocess(payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    """Run Playwright scraper work in a child process and return parsed JSON data."""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    src_dir = str(Path(__file__).resolve().parents[3])
    python_path = env.get("PYTHONPATH", "")
    if src_dir not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = src_dir + (os.pathsep + python_path if python_path else "")
    result = subprocess.run(
        [sys.executable, "-m", "automating_wf.scrapers.subprocess_runner"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr_msg = result.stderr.strip() or result.stdout.strip() or "Unknown subprocess error."
        raise RuntimeError(
            f"Scraper subprocess failed (exit {result.returncode}): {stderr_msg}"
        )

    stdout_text = result.stdout.strip()
    if not stdout_text:
        raise RuntimeError("Scraper subprocess returned empty output.")

    try:
        response = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid scraper subprocess JSON output: {stdout_text[:500]}") from exc

    if not isinstance(response, dict):
        raise RuntimeError("Scraper subprocess returned non-object JSON.")
    if not response.get("ok"):
        error_message = str(response.get("error", "unknown")).strip() or repr(response)
        raise RuntimeError(f"Scraper error: {error_message}")

    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Scraper subprocess response is missing object data.")
    return data


def _seed_scrape_result_from_dict(payload: dict[str, Any]) -> SeedScrapeResult:
    """Rebuild SeedScrapeResult model from JSON payload returned by subprocess."""
    records: list[PinRecord] = []
    for item in payload.get("records", []):
        if not isinstance(item, dict):
            continue
        try:
            rank = int(item.get("rank", 0) or 0)
        except Exception:
            rank = 0
        engagement = item.get("engagement", {})
        tags = item.get("tags", [])
        records.append(
            PinRecord(
                seed_keyword=str(item.get("seed_keyword", "")),
                rank=rank,
                pin_url=str(item.get("pin_url", "")),
                pin_id=str(item.get("pin_id", "")),
                title=str(item.get("title", "")),
                description=str(item.get("description", "")),
                tags=[str(tag) for tag in tags] if isinstance(tags, list) else [],
                engagement=dict(engagement) if isinstance(engagement, dict) else {},
                scraped_at=str(item.get("scraped_at", "")),
            )
        )
    return SeedScrapeResult(
        blog_suffix=str(payload.get("blog_suffix", "")),
        seed_keyword=str(payload.get("seed_keyword", "")),
        source_url=str(payload.get("source_url", "")),
        source_file=str(payload.get("source_file", "")),
        records=records,
        scraped_at=str(payload.get("scraped_at", "")),
        scrape_mode=str(payload.get("scrape_mode", "")).strip()
        or ("export" if str(payload.get("source_file", "")).strip() else "visible_rows"),
        diagnostics=dict(payload.get("diagnostics", {})) if isinstance(payload.get("diagnostics"), dict) else {},
    )


def _scrape_trends_exports_bridge(
    *,
    seed_keywords: list[str],
    run_dir: Path,
    headed: bool,
    max_attempts: int,
    region: str,
    date_range: str,
) -> dict[str, list[str]]:
    """Bridge trends scraping through subprocess only when in Streamlit runtime."""
    if _running_in_streamlit():
        raw_result = _run_scraper_subprocess(
            {
                "action": "scrape_trends",
                "seed_keywords": seed_keywords,
                "run_dir": str(run_dir),
                "headed": headed,
                "max_attempts": max_attempts,
                "region": region,
                "date_range": date_range,
            }
        )
        export_files_by_seed: dict[str, list[str]] = {}
        for seed, files in raw_result.items():
            seed_keyword = str(seed or "").strip()
            if not seed_keyword:
                continue
            if isinstance(files, list):
                export_files_by_seed[seed_keyword] = [
                    str(file_path).strip()
                    for file_path in files
                    if str(file_path).strip()
                ]
            elif str(files).strip():
                export_files_by_seed[seed_keyword] = [str(files).strip()]
        return export_files_by_seed

    return scrape_trends_exports(
        seed_keywords=seed_keywords,
        run_dir=run_dir,
        headed=headed,
        max_attempts=max_attempts,
    )


def _scrape_seed_bridge(
    *,
    seed_keyword: str,
    blog_suffix: str,
    run_dir: Path,
    headed: bool,
    max_records: int,
    max_attempts: int,
) -> SeedScrapeResult:
    """Run PinClicks scrape_seed, routing through subprocess when in Streamlit."""
    if _running_in_streamlit():
        raw = _run_scraper_subprocess(
            {
                "action": "scrape_pinclicks",
                "seed_keyword": seed_keyword,
                "blog_suffix": blog_suffix,
                "run_dir": str(run_dir),
                "headed": headed,
                "max_records": max_records,
                "max_attempts": max_attempts,
            }
        )
        return _seed_scrape_result_from_dict(raw)

    return scrape_seed(
        seed_keyword=seed_keyword,
        blog_suffix=blog_suffix,
        run_dir=run_dir,
        headed=headed,
        max_records=max_records,
        max_attempts=max_attempts,
    )


def _bootstrap_pinclicks_session_bridge(
    *,
    headed: bool,
    allow_manual_setup: bool,
    setup_timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Validate or bootstrap the PinClicks Brave session, using subprocess in Streamlit."""
    if _running_in_streamlit():
        return _run_scraper_subprocess(
            {
                "action": "bootstrap_pinclicks_session",
                "headed": headed,
                "allow_manual_setup": allow_manual_setup,
                "setup_timeout_seconds": setup_timeout_seconds,
            }
        )

    return ensure_pinclicks_brave_session(
        headed=headed,
        allow_manual_setup=allow_manual_setup,
        setup_timeout_seconds=setup_timeout_seconds,
    )


def _seed_slug(seed_keyword: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", seed_keyword.strip().lower()).strip("_")
    return normalized or "seed"


def _build_csv_keywords(primary_keyword: str, supporting_terms: list[str] | None) -> str:
    ordered_terms = [str(primary_keyword or "").strip(), *[str(item).strip() for item in (supporting_terms or [])]]
    deduped: list[str] = []
    seen: set[str] = set()
    for term in ordered_terms:
        if not term:
            continue
        normalized = " ".join(term.replace(",", " ").split())
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return ", ".join(deduped)


def _is_valid_trend_keyword(keyword: str) -> bool:
    text = str(keyword or "").strip()
    if len(text) < 2:
        return False
    if re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", text):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", text))


def _load_json_env(name: str) -> dict[str, Any]:
    load_dotenv()
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EngineError(f"{name} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise EngineError(f"{name} must be a JSON object.")
    return payload


def _load_seed_map() -> dict[str, list[str]]:
    raw_map = _load_json_env("PINTEREST_SEED_MAP_JSON")
    normalized: dict[str, list[str]] = {}
    for suffix, seeds in raw_map.items():
        if not isinstance(suffix, str):
            continue
        if not isinstance(seeds, list):
            continue
        cleaned = [str(item).strip() for item in seeds if str(item).strip()]
        if not cleaned:
            continue
        normalized[suffix.strip().upper()] = cleaned
    return normalized


def _resolve_blog_name_from_suffix(suffix: str) -> str:
    normalized = (suffix or "").strip().upper()
    for blog_name, config in BLOG_CONFIGS.items():
        if str(config.get("wp_env_suffix", "")).strip().upper() == normalized:
            return blog_name
    raise EngineError(f"Unknown blog suffix '{suffix}'. Check app.BLOG_CONFIGS.")


def _manifest_path(run_dir: Path) -> Path:
    return run_dir / MANIFEST_NAME


def _run_options_path(run_dir: Path) -> Path:
    return run_dir / RUN_OPTIONS_NAME


def _append_manifest(run_dir: Path, entry: RunManifestEntry) -> None:
    manifest = _manifest_path(run_dir)
    _ensure_dir(manifest.parent)
    with manifest.open("a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


def _write_run_options(run_dir: Path, opts: EngineRunOptions, *, overwrite: bool = False) -> None:
    path = _run_options_path(run_dir)
    if path.exists() and not overwrite:
        return
    seed_keywords = getattr(opts, "seed_keywords", [])
    if isinstance(seed_keywords, list):
        serialized_seed_keywords = [str(item).strip() for item in seed_keywords if str(item).strip()]
    else:
        serialized_seed_keywords = []

    selected_trend_keywords = getattr(opts, "selected_trend_keywords", [])
    if isinstance(selected_trend_keywords, list):
        serialized_selected_keywords = [str(item).strip() for item in selected_trend_keywords if str(item).strip()]
    else:
        serialized_selected_keywords = []
    payload = {
        "blog_suffix": str(getattr(opts, "blog_suffix", "")).strip(),
        "seed_keywords": serialized_seed_keywords,
        "trends_region": str(getattr(opts, "trends_region", "")).strip(),
        "trends_range": str(getattr(opts, "trends_range", "")).strip(),
        "trends_top_n": int(getattr(opts, "trends_top_n", 0) or 0),
        "selected_trend_keywords": serialized_selected_keywords,
        "pinclicks_max_records": int(getattr(opts, "pinclicks_max_records", 0) or 0),
        "winners_count": int(getattr(opts, "winners_count", 0) or 0),
        "publish_status": str(getattr(opts, "publish_status", "")).strip(),
        "csv_first_publish_at": str(getattr(opts, "csv_first_publish_at", "")).strip() or None,
        "csv_cadence_minutes": int(getattr(opts, "csv_cadence_minutes", DEFAULT_CADENCE_MINUTES) or DEFAULT_CADENCE_MINUTES),
        "csv_timezone": csv_timezone_name(),
        "csv_preview_slots": preview_publish_schedule(
            first_publish_at=str(getattr(opts, "csv_first_publish_at", "")).strip() or None,
            cadence_minutes=int(getattr(opts, "csv_cadence_minutes", DEFAULT_CADENCE_MINUTES) or DEFAULT_CADENCE_MINUTES),
            count=min(5, max(1, int(getattr(opts, "winners_count", 1) or 1))),
        ),
        "headed": bool(getattr(opts, "headed", False)),
        "resume_run_id": str(getattr(opts, "resume_run_id", "")).strip() or None,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_run_options(run_dir: Path) -> dict[str, Any]:
    path = _run_options_path(run_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_manifest_entries(run_dir: Path) -> list[dict[str, Any]]:
    manifest = _manifest_path(run_dir)
    if not manifest.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_status_by_seed(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        seed = str(entry.get("seed_keyword", "")).strip()
        if not seed:
            continue
        latest[seed] = entry
    return latest


def build_public_permalink(*, blog_suffix: str, post_slug: str) -> str:
    if not post_slug.strip():
        raise EngineError("post_slug is required to build public permalink.")
    load_dotenv()
    normalized = blog_suffix.strip().upper()
    custom_template = os.getenv(f"WP_PUBLIC_POST_URL_TEMPLATE_{normalized}", "").strip()
    site_url = os.getenv(f"WP_URL_{normalized}", "").strip().rstrip("/")
    if not site_url:
        raise EngineError(f"Missing WP_URL_{normalized} in environment.")

    slug = post_slug.strip().strip("/")
    if custom_template:
        try:
            return custom_template.format(site_url=site_url, slug=slug)
        except KeyError as exc:
            raise EngineError(
                f"WP_PUBLIC_POST_URL_TEMPLATE_{normalized} supports only {{site_url}} and {{slug}} placeholders."
            ) from exc
    return f"{site_url}/{slug}/"


def _resolve_category_id_for_article(
    *,
    target_suffix: str,
    blog_name: str,
    article_payload: dict[str, str],
) -> int | None:
    blog_config = resolve_blog_config(blog_name)
    categories = list_categories(target_suffix=target_suffix)
    category_names = [str(item.get("name", "")).strip() for item in categories if str(item.get("name", "")).strip()]
    if not category_names:
        return None
    suggested = suggest_primary_category(
        title=str(article_payload.get("title", "")),
        content_markdown=str(
            article_payload.get("article_markdown", article_payload.get("content_markdown", ""))
        ),
        category_names=category_names,
        fallback_category=str(blog_config.get("fallback_category", "")),
        deprioritized_category=str(blog_config.get("deprioritized_category", "")),
        category_keywords=dict(blog_config.get("category_keywords", {})),
    )
    if not suggested:
        return None
    return resolve_category_id(
        selected_name=suggested,
        typed_new_name="",
        target_suffix=target_suffix,
    )


def _new_run_dir(run_id: str) -> Path:
    run_dir = RUN_ROOT / run_id
    _ensure_dir(run_dir)
    return run_dir


def _resolve_run_dir(resume: str | None) -> tuple[str, Path]:
    if resume:
        candidate = Path(resume)
        if candidate.exists():
            run_dir = candidate
            run_id = run_dir.name
        else:
            run_dir = RUN_ROOT / resume
            run_id = resume
        if not run_dir.exists():
            raise EngineError(f"Resume path not found: {run_dir}")
        return run_id, run_dir

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = _new_run_dir(run_id)
    return run_id, run_dir


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _load_seed_scrape_result(path: Path) -> SeedScrapeResult:
    payload = json.loads(path.read_text(encoding="utf-8"))

    records = [
        PinRecord(
            seed_keyword=str(item.get("seed_keyword", "")),
            rank=int(item.get("rank", 0)),
            pin_url=str(item.get("pin_url", "")),
            pin_id=str(item.get("pin_id", "")),
            title=str(item.get("title", "")),
            description=str(item.get("description", "")),
            tags=[str(tag) for tag in item.get("tags", [])],
            engagement=dict(item.get("engagement", {})),
            scraped_at=str(item.get("scraped_at", "")),
        )
        for item in payload.get("records", [])
        if isinstance(item, dict)
    ]
    return SeedScrapeResult(
        blog_suffix=str(payload.get("blog_suffix", "")),
        seed_keyword=str(payload.get("seed_keyword", "")),
        source_url=str(payload.get("source_url", "")),
        source_file=str(payload.get("source_file", "")),
        records=records,
        scraped_at=str(payload.get("scraped_at", "")),
        scrape_mode=str(payload.get("scrape_mode", "")).strip()
        or ("export" if str(payload.get("source_file", "")).strip() else "visible_rows"),
        diagnostics=dict(payload.get("diagnostics", {})) if isinstance(payload.get("diagnostics"), dict) else {},
    )


def _synthesize_scrape_result(keyword: str, blog_suffix: str) -> SeedScrapeResult:
    """Create minimal SeedScrapeResult when PinClicks was skipped."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = [
        PinRecord(
            seed_keyword=keyword,
            rank=i,
            pin_url="",
            pin_id=f"synth_{i}",
            title=keyword,
            description=keyword,
            tags=[keyword],
            engagement={},
            scraped_at=now,
        )
        for i in range(1, 6)
    ]
    return SeedScrapeResult(
        blog_suffix=blog_suffix,
        seed_keyword=keyword,
        source_url="",
        records=records,
        scraped_at=now,
        source_file="synthesized",
        scrape_mode="visible_rows",
        diagnostics={"scrape_mode": "visible_rows", "engagement_available": False},
    )


def _replay_pending_csv(
    *,
    run_id: str,
    run_dir: Path,
    blog_suffix: str,
    latest_by_seed: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cadence_minutes = _int_env("PINTEREST_CSV_CADENCE_MINUTES", DEFAULT_CADENCE_MINUTES)
    replayed = 0
    failed = 0
    skipped = 0
    for seed_keyword, latest in latest_by_seed.items():
        if str(latest.get("status", "")).strip() != "csv_failed":
            continue
        replayed += 1
        details = latest.get("details")
        if not isinstance(details, dict):
            skipped += 1
            continue
        pending_row = details.get("pending_csv_row")
        if not isinstance(pending_row, dict):
            skipped += 1
            continue
        csv_path_raw = details.get("csv_path")
        csv_path = Path(str(csv_path_raw)) if isinstance(csv_path_raw, str) and csv_path_raw.strip() else _run_csv_path(run_dir, blog_suffix)
        csv_first_publish_at = str(details.get("csv_first_publish_at", "")).strip() or None
        csv_cadence_minutes = int(details.get("csv_cadence_minutes", cadence_minutes) or cadence_minutes)
        pending_board = str(pending_row.get("Pinterest board", pending_row.get("Pinterest Board", ""))).strip()
        if not pending_board:
            supporting_terms = [
                term.strip()
                for term in str(pending_row.get("Keywords", "")).split(",")
                if term and term.strip()
            ]
            primary_keyword = str(latest.get("primary_keyword", "")).strip()
            if not primary_keyword and supporting_terms:
                primary_keyword = supporting_terms[0]
            if not primary_keyword:
                primary_keyword = str(pending_row.get("Title", "")).strip()
            pending_board = resolve_board_name(
                blog_suffix=blog_suffix,
                primary_keyword=primary_keyword,
                supporting_terms=supporting_terms,
            )
        row = CsvRow(
            title=str(pending_row.get("Title", "")),
            description=str(pending_row.get("Description", "")),
            link=str(pending_row.get("Link", "")),
            image_url=str(pending_row.get("Media URL", pending_row.get("Image URL", ""))),
            pinterest_board=pending_board,
            publish_date=str(pending_row.get("Publish date", pending_row.get("Publish Date", ""))),
            thumbnail=str(pending_row.get("Thumbnail", "")),
            keywords=str(pending_row.get("Keywords", "")),
        )
        try:
            result = append_csv_row(
                row=row,
                csv_path=csv_path,
                cadence_minutes=csv_cadence_minutes,
                initial_publish_date=csv_first_publish_at,
            )
        except Exception as exc:
            failed += 1
            _append_manifest(
                run_dir,
                RunManifestEntry.create(
                    run_id=run_id,
                    blog_suffix=blog_suffix,
                    seed_keyword=seed_keyword,
                    status="csv_failed",
                    failure_stage="csv_failed",
                    source_stage="csv",
                    details={
                        "replay_error": str(exc),
                        "pending_csv_row": row.to_dict(),
                        "csv_path": str(csv_path),
                        "csv_first_publish_at": csv_first_publish_at or "",
                        "csv_cadence_minutes": int(csv_cadence_minutes),
                        "csv_timezone": csv_timezone_name(),
                    },
                ),
            )
            continue

        publish_date = str(result.get("publish_date", "")).strip()
        replay_status = str(result.get("status", "")).strip()
        if replay_status in {"appended", "skipped_duplicate"}:
            # For duplicate links/titles, mark as recovered to avoid perpetual csv_failed state.
            pass
        else:
            skipped += 1
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="csv_appended",
                primary_keyword=str(latest.get("primary_keyword", "")),
                idempotency_key=str(latest.get("idempotency_key", "")),
                public_permalink=str(row.link),
                requires_wp_publish_before=publish_date,
                source_stage="csv",
                details={
                    "csv_result": result,
                    "replayed": True,
                    "csv_first_publish_at": csv_first_publish_at or "",
                    "csv_cadence_minutes": int(csv_cadence_minutes),
                    "csv_timezone": csv_timezone_name(),
                },
            ),
        )
    return {
        "replayed": replayed,
        "failed": failed,
        "skipped": skipped,
    }


def _build_summary(run_dir: Path, *, blog_suffix: str | None = None) -> dict[str, Any]:
    entries = _load_manifest_entries(run_dir)
    run_options = _read_run_options(run_dir)
    status_counts: dict[str, int] = {}
    publish_checklist: list[dict[str, str]] = []
    stage3_scrape_modes: dict[str, int] = {}
    stage3_quality = {
        "keywords_succeeded": 0,
        "raw_rows": 0,
        "rejected_rows": 0,
        "kept_rows": 0,
        "engagement_available_keywords": 0,
        "engagement_unavailable_keywords": 0,
    }
    for entry in entries:
        status = str(entry.get("status", "")).strip()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        details = entry.get("details", {})
        if not isinstance(details, dict):
            details = {}
        if status in {"pinclicks_exported", PINCLICKS_STATUS_SCRAPED}:
            scrape_mode = str(details.get("scrape_mode", "")).strip() or (
                "export" if str(entry.get("source_file", "")).strip() else "visible_rows"
            )
            stage3_scrape_modes[scrape_mode] = stage3_scrape_modes.get(scrape_mode, 0) + 1
            stage3_quality["keywords_succeeded"] += 1
            stage3_quality["raw_rows"] += int(details.get("raw_item_count", 0) or 0)
            stage3_quality["rejected_rows"] += int(details.get("rejected_item_count", 0) or 0)
            stage3_quality["kept_rows"] += int(details.get("final_record_count", details.get("record_count", 0)) or 0)
            if bool(details.get("engagement_available", False)):
                stage3_quality["engagement_available_keywords"] += 1
            else:
                stage3_quality["engagement_unavailable_keywords"] += 1
        publish_before = str(entry.get("requires_wp_publish_before", "")).strip()
        permalink = str(entry.get("public_permalink", "")).strip()
        if status == "csv_appended" and publish_before and permalink:
            publish_checklist.append(
                {
                    "seed_keyword": str(entry.get("seed_keyword", "")),
                    "permalink": permalink,
                    "publish_before": publish_before,
                }
            )
    suffix = (blog_suffix or "").strip().upper()
    if not suffix:
        for entry in reversed(entries):
            candidate = str(entry.get("blog_suffix", "")).strip().upper()
            if candidate:
                suffix = candidate
                break
    csv_path = str(_run_csv_path(run_dir, suffix)) if suffix else ""
    csv_cadence_minutes = int(run_options.get("csv_cadence_minutes", DEFAULT_CADENCE_MINUTES) or DEFAULT_CADENCE_MINUTES)
    csv_first_publish_at = str(run_options.get("csv_first_publish_at", "") or "").strip() or None
    preview_slots = run_options.get("csv_preview_slots")
    if not isinstance(preview_slots, list):
        preview_slots = preview_publish_schedule(
            first_publish_at=csv_first_publish_at,
            cadence_minutes=csv_cadence_minutes,
            count=5,
        )
    csv_schedule = {
        "first_publish_at": csv_first_publish_at,
        "cadence_minutes": csv_cadence_minutes,
        "timezone": str(run_options.get("csv_timezone", "")).strip() or csv_timezone_name(),
        "preview_slots": preview_slots,
    }
    return {
        "run_dir": str(run_dir),
        "status_counts": status_counts,
        "stage3_scrape_modes": stage3_scrape_modes,
        "stage3_quality": stage3_quality,
        "csv_schedule": csv_schedule,
        "publish_checklist": publish_checklist,
        "csv_path": csv_path,
    }


def _write_summary(run_dir: Path, *, blog_suffix: str | None = None) -> dict[str, Any]:
    summary = _build_summary(run_dir, blog_suffix=blog_suffix)
    (run_dir / SUMMARY_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _result_title_from_entry_details(details: dict[str, Any]) -> str:
    title = str(details.get("title", "")).strip()
    if title:
        return title
    publish_result = details.get("publish_result", {})
    if isinstance(publish_result, dict):
        title = str(publish_result.get("title", "")).strip()
        if title:
            return title
    pending_row = details.get("pending_csv_row", {})
    if isinstance(pending_row, dict):
        return str(pending_row.get("Title", "")).strip()
    return ""


def build_generation_result_from_manifest_entry(
    *,
    seed_keyword: str,
    entry: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize latest manifest state for one winner into GenerationResults row shape."""
    status = str(entry.get("status", "")).strip()
    if not status:
        return None

    details = entry.get("details", {})
    if not isinstance(details, dict):
        details = {}
    publish_result = details.get("publish_result", {})
    if not isinstance(publish_result, dict):
        publish_result = {}

    common: dict[str, Any] = {
        "keyword": seed_keyword,
        "title": _result_title_from_entry_details(details),
        "post_url": str(entry.get("public_permalink", "")).strip(),
        "publish_status": str(publish_result.get("status", "")).strip(),
        "failure_stage": status,
        "error": str(details.get("error", status)).strip() or status,
    }

    if status in FULL_SUCCESS_STATUSES:
        common["status"] = "completed"
        return common
    if status in PARTIAL_SUCCESS_STATUSES:
        common["status"] = "partial"
        return common
    if status in FAILED_PRE_PUBLISH_STATUSES:
        common["status"] = "failed_pre_publish"
        return common
    return None


def _split_generation_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    completed: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    failed_pre_publish: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in results:
        status = str(item.get("status", "")).strip()
        if status == "completed":
            completed.append(item)
            continue
        if status == "partial":
            partial.append(item)
            failed.append(item)
            continue
        failed_pre_publish.append(item)
        failed.append(item)
    return completed, partial, failed_pre_publish, failed


def replay_pending_csv_sync(*, run_id: str, blog_suffix: str) -> dict[str, Any]:
    """Replay pending csv_failed rows for a run after config fixes."""
    suffix = str(blog_suffix or "").strip().upper()
    if not suffix:
        raise EngineError("blog_suffix is required for CSV replay.")
    validate_board_mapping_for_blog(suffix)

    run_dir = _resolve_phase_run_dir(run_id)
    before_latest = _latest_status_by_seed(_load_manifest_entries(run_dir))
    pending_before = {
        seed
        for seed, entry in before_latest.items()
        if str(entry.get("status", "")).strip() == "csv_failed"
    }
    replay_stats = _replay_pending_csv(
        run_id=run_id,
        run_dir=run_dir,
        blog_suffix=suffix,
        latest_by_seed=before_latest,
    )
    after_latest = _latest_status_by_seed(_load_manifest_entries(run_dir))
    recovered_keywords: list[str] = []
    failed_keywords: list[str] = []
    for seed in sorted(pending_before):
        latest = after_latest.get(seed, {})
        latest_status = str(latest.get("status", "")).strip()
        if latest_status == "csv_appended":
            recovered_keywords.append(seed)
        elif latest_status == "csv_failed":
            failed_keywords.append(seed)

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "csv_path": str(_run_csv_path(run_dir, suffix)),
        "pending_before": len(pending_before),
        "recovered_count": len(recovered_keywords),
        "failed_count": len(failed_keywords),
        "remaining_pending": len(
            [seed for seed, entry in after_latest.items() if str(entry.get("status", "")).strip() == "csv_failed"]
        ),
        "recovered_keywords": recovered_keywords,
        "failed_keywords": failed_keywords,
        "replay_stats": replay_stats,
    }


def _process_winner(
    *,
    run_id: str,
    run_dir: Path,
    blog_suffix: str,
    blog_name: str,
    scrape_result: SeedScrapeResult,
    trend_rank: int,
    pinclicks_rank: int,
    repair_system_prompt: str,
    publish_status: str = "draft",
    csv_first_publish_at: str | None = None,
    csv_cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
) -> dict[str, Any]:
    seed_keyword = scrape_result.seed_keyword
    seed_dir = run_dir / "winners" / _seed_slug(seed_keyword)
    analysis_dir = seed_dir / "analysis"
    pin_dir = seed_dir / "pin"
    writer_dir = seed_dir / "writer"
    for path in (seed_dir, analysis_dir, pin_dir, writer_dir):
        _ensure_dir(path)

    _append_manifest(
        run_dir,
        RunManifestEntry.create(
            run_id=run_id,
            blog_suffix=blog_suffix,
            seed_keyword=seed_keyword,
            status="winner_processed",
            source_stage="generation",
            source_file=scrape_result.source_file,
            keyword_rank_trends=trend_rank,
            keyword_rank_pinclicks=pinclicks_rank,
        ),
    )

    try:
        brain_output = analyze_seed(
            scrape_result=scrape_result,
            blog_suffix=blog_suffix,
            run_dir=analysis_dir,
        )
    except InsufficientSignalError as exc:
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="insufficient_signal",
                failure_stage="analysis_failed",
                source_stage="generation",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details={"error": str(exc)},
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": str(exc),
            "failure_stage": "analysis_failed",
        }
    except Exception as exc:
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="analysis_failed",
                failure_stage="analysis_failed",
                source_stage="generation",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details={"error": str(exc)},
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": str(exc),
            "failure_stage": "analysis_failed",
        }

    def _article_failed_result(
        *,
        error: str,
        generation_errors: list[str] | None = None,
        validator_attempts: list[dict[str, Any]] | None = None,
        validator_errors: list[str] | None = None,
    ) -> dict[str, Any]:
        details = {
            "error": str(error or "").strip() or "article_failed",
            "generation_errors": list(generation_errors or []),
            "validator_attempts": list(validator_attempts or []),
            "validator_errors": list(validator_errors or []),
        }
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="article_failed",
                primary_keyword=brain_output.primary_keyword,
                idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
                failure_stage="article_failed",
                source_stage="generation",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details=details,
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": details["error"],
            "failure_stage": "article_failed",
            "primary_keyword": brain_output.primary_keyword,
            "generation_errors": details["generation_errors"],
            "validator_attempts": details["validator_attempts"],
            "validator_errors": details["validator_errors"],
        }

    try:
        blog_profile = resolve_blog_profile(blog_name)
    except Exception as exc:
        return _article_failed_result(error=str(exc))

    article_payload: dict[str, str] | None = None
    generation_errors: list[str] = []
    try:
        article_payload = generate_article(
            topic=brain_output.primary_keyword,
            vibe=brain_output.cluster_label,
            blog_profile=blog_profile,
            focus_keyword=brain_output.primary_keyword,
            prompt_type=resolve_prompt_type(blog_name),
        )
    except ArticleValidationError as exc:
        generation_errors = list(exc.errors or [])
        payload = exc.payload if isinstance(exc.payload, dict) else None
        if payload is None:
            return _article_failed_result(
                error=str(exc),
                generation_errors=generation_errors,
            )
        article_payload = payload
    except Exception as exc:
        return _article_failed_result(error=str(exc))

    try:
        validator_result = validate_article_with_repair(
            article_payload=article_payload,
            focus_keyword=brain_output.primary_keyword,
            blog_profile=blog_profile,
            repair_system_prompt=repair_system_prompt,
            artifact_dir=writer_dir / "validator",
        )
        article_payload = validator_result.article_payload
    except ArticleValidationFinalError as exc:
        validator_errors = list(exc.errors or [])
        if not validator_errors:
            validator_errors = [str(exc)]
        return _article_failed_result(
            error=str(exc),
            generation_errors=generation_errors,
            validator_attempts=list(getattr(exc, "attempts", []) or []),
            validator_errors=validator_errors,
        )
    except ArticleValidatorError as exc:
        return _article_failed_result(
            error=str(exc),
            generation_errors=generation_errors,
            validator_errors=[str(exc)],
        )
    except Exception as exc:
        return _article_failed_result(
            error=str(exc),
            generation_errors=generation_errors,
            validator_errors=[str(exc)],
        )

    try:
        pin_image_path = generate_pinterest_image(
            brain_output=brain_output,
            blog_suffix=blog_suffix,
            blog_name=blog_name,
            run_dir=pin_dir,
            max_attempts=2,
        )
    except Exception as exc:
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="image_failed",
                primary_keyword=brain_output.primary_keyword,
                idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
                failure_stage="image_failed",
                source_stage="generation",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details={"error": str(exc)},
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": str(exc),
            "failure_stage": "image_failed",
            "primary_keyword": brain_output.primary_keyword,
        }

    try:
        hero_path = generate_image(
            prompt=article_payload["hero_image_prompt"],
            image_kind="hero",
            out_dir=writer_dir,
        )
        detail_path = generate_image(
            prompt=article_payload["detail_image_prompt"],
            image_kind="detail",
            out_dir=writer_dir,
        )

        category_id = _resolve_category_id_for_article(
            target_suffix=blog_suffix,
            blog_name=blog_name,
            article_payload=article_payload,
        )
        publish_result = publish_post(
            title=article_payload["title"],
            content_markdown=article_payload.get("article_markdown", article_payload["content_markdown"]),
            hero_path=hero_path,
            detail_path=detail_path,
            target_suffix=blog_suffix,
            focus_keyword=article_payload["focus_keyword"],
            meta_description=article_payload["meta_description"],
            seo_title=article_payload["seo_title"],
            status=publish_status,
            category_id=category_id,
        )

        pin_media = upload_media(
            pin_image_path,
            alt_text=f"{article_payload['title']} Pinterest image",
            target_suffix=blog_suffix,
        )
        post_slug = str(publish_result.get("post_slug", "")).strip()
        public_permalink = build_public_permalink(blog_suffix=blog_suffix, post_slug=post_slug)
    except Exception as exc:
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="wp_failed",
                primary_keyword=brain_output.primary_keyword,
                idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
                failure_stage="wp_failed",
                source_stage="wordpress",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details={"error": str(exc)},
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": str(exc),
            "failure_stage": "wp_failed",
            "primary_keyword": brain_output.primary_keyword,
        }

    _append_manifest(
        run_dir,
        RunManifestEntry.create(
            run_id=run_id,
            blog_suffix=blog_suffix,
            seed_keyword=seed_keyword,
            status="wp_published",
            primary_keyword=brain_output.primary_keyword,
            idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
            public_permalink=public_permalink,
            source_stage="wordpress",
            source_file=scrape_result.source_file,
            keyword_rank_trends=trend_rank,
            keyword_rank_pinclicks=pinclicks_rank,
            details={
                "title": article_payload["title"],
                "publish_result": publish_result,
                "pin_media_url": pin_media["source_url"],
                "pin_media_id": pin_media["id"],
                "category_id": category_id,
            },
        ),
    )

    board_name = resolve_board_name(
        blog_suffix=blog_suffix,
        primary_keyword=brain_output.primary_keyword,
        supporting_terms=brain_output.supporting_terms,
    )
    csv_row = CsvRow(
        title=brain_output.pin_title,
        description=brain_output.pin_description,
        link=public_permalink,
        image_url=str(pin_media["source_url"]),
        pinterest_board=board_name,
        publish_date="",
        thumbnail="",
        keywords=_build_csv_keywords(
            primary_keyword=brain_output.primary_keyword,
            supporting_terms=brain_output.supporting_terms,
        ),
    )
    csv_path = _run_csv_path(run_dir, blog_suffix)
    try:
        csv_result = append_csv_row(
            row=csv_row,
            csv_path=csv_path,
            cadence_minutes=max(1, int(csv_cadence_minutes)),
            initial_publish_date=csv_first_publish_at,
        )
    except Exception as exc:
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                status="csv_failed",
                primary_keyword=brain_output.primary_keyword,
                idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
                public_permalink=public_permalink,
                failure_stage="csv_failed",
                source_stage="csv",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank,
                keyword_rank_pinclicks=pinclicks_rank,
                details={
                    "error": str(exc),
                    "pending_csv_row": csv_row.to_dict(),
                    "csv_path": str(csv_path),
                    "csv_first_publish_at": csv_first_publish_at or "",
                    "csv_cadence_minutes": int(csv_cadence_minutes),
                    "csv_timezone": csv_timezone_name(),
                },
            ),
        )
        return {
            "keyword": seed_keyword,
            "status": "failed",
            "error": str(exc),
            "failure_stage": "csv_failed",
            "primary_keyword": brain_output.primary_keyword,
            "title": article_payload["title"],
            "post_url": public_permalink,
            "csv_path": str(csv_path),
        }

    publish_date = str(csv_result.get("publish_date", "")).strip()
    _append_manifest(
        run_dir,
        RunManifestEntry.create(
            run_id=run_id,
            blog_suffix=blog_suffix,
            seed_keyword=seed_keyword,
            status="csv_appended",
            primary_keyword=brain_output.primary_keyword,
            idempotency_key=f"{blog_suffix}|{seed_keyword}|{brain_output.primary_keyword}",
            public_permalink=public_permalink,
            requires_wp_publish_before=publish_date,
            source_stage="csv",
            source_file=scrape_result.source_file,
            keyword_rank_trends=trend_rank,
            keyword_rank_pinclicks=pinclicks_rank,
            details={
                "csv_result": csv_result,
                "csv_first_publish_at": csv_first_publish_at or "",
                "csv_cadence_minutes": int(csv_cadence_minutes),
                "csv_timezone": csv_timezone_name(),
            },
        ),
    )
    return {
        "keyword": seed_keyword,
        "status": "completed",
        "primary_keyword": brain_output.primary_keyword,
        "title": article_payload["title"],
        "post_url": public_permalink,
        "publish_status": str(publish_result.get("status", "")),
        "publish_result": publish_result,
        "csv_publish_date": publish_date,
        "csv_path": str(csv_path),
    }


def _load_cached_top_keywords(run_dir: Path) -> list[dict[str, Any]]:
    file_path = run_dir / "trends_analysis" / TRENDS_TOP_KEYWORDS_FILE
    if not file_path.exists():
        return []

    # Cache invalidation: reject artifacts produced by an older scoring version.
    metadata_path = run_dir / "trends_analysis" / "trends_scoring_metadata.json"
    if metadata_path.exists():
        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            cached_version = str(meta.get("scoring_version", "")).strip()
            if cached_version and cached_version != TRENDS_SCORING_VERSION:
                return []
        except Exception:
            pass

    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    valid_items: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword", "")).strip()
        if not _is_valid_trend_keyword(keyword):
            continue
        normalized = dict(item)
        normalized["keyword"] = keyword
        valid_items.append(normalized)
    return valid_items


def _read_raw_trends_count(trends_analysis_dir: Path) -> int:
    """Read count of parsed trend records from cached trends analysis artifacts."""
    records_path = trends_analysis_dir / "trends_records.json"
    if not records_path.exists():
        return 0
    try:
        payload = json.loads(records_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def _resolve_phase_run_dir(run_id: str) -> Path:
    """Resolve a run_id to its run directory and fail fast when missing."""
    run_dir = RUN_ROOT / run_id
    if run_dir.exists():
        return run_dir
    raise EngineError(f"Run path not found for run_id '{run_id}'.")


def _safe_winner_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize winner payload values into stable serializable types."""
    return {
        "keyword": str(item.get("keyword", "")).strip(),
        "reach_hat": float(item.get("reach_hat", 0.0) or 0.0),
        "ctr_hat": float(item.get("ctr_hat", 0.0) or 0.0),
        "click_score": float(item.get("click_score", 0.0) or 0.0),
        "is_pareto_efficient": bool(item.get("is_pareto_efficient", False)),
        "selection_reason": str(item.get("selection_reason", "")).strip(),
        "outbound_intent_score": float(item.get("outbound_intent_score", 0.0) or 0.0),
        "engagement_score": float(item.get("engagement_score", 0.0) or 0.0),
        "frequency_score": float(item.get("frequency_score", 0.0) or 0.0),
        "record_count": int(item.get("record_count", 0) or 0),
        "engagement_available": bool(item.get("engagement_available", True)),
        "trend_rank": int(item.get("trend_rank", 0) or 0),
        "pinclicks_rank": int(item.get("pinclicks_rank", 0) or 0),
        "scrape_source": str(item.get("scrape_source", "")).strip(),
    }


def _clean_keyword_list(items: list[str]) -> list[str]:
    """Normalize and deduplicate keyword lists while preserving order."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        keyword = str(item or "").strip()
        if not keyword:
            continue
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        cleaned.append(keyword)
    return cleaned


def _collect_trends_candidates_sync(opts: EngineRunOptions) -> TrendCandidates:
    """Phase 1 sync implementation: scrape/analyze trends and return ranked keywords."""
    suffix = opts.blog_suffix.strip().upper()
    if not opts.seed_keywords:
        raise EngineError(
            f"No seed list configured for '{suffix}' in PINTEREST_SEED_MAP_JSON."
        )
    validate_board_mapping_for_blog(suffix)

    run_id, run_dir = _resolve_run_dir(resume=opts.resume_run_id)
    _write_run_options(run_dir, opts)
    entries = _load_manifest_entries(run_dir)
    latest_by_seed = _latest_status_by_seed(entries)
    _replay_pending_csv(
        run_id=run_id,
        run_dir=run_dir,
        blog_suffix=suffix,
        latest_by_seed=latest_by_seed,
    )

    trends_exports_dir = run_dir / "trends_exports"
    trends_analysis_dir = run_dir / "trends_analysis"
    _ensure_dir(trends_exports_dir)
    _ensure_dir(trends_analysis_dir)

    top_keywords_payload = _load_cached_top_keywords(run_dir)
    if not top_keywords_payload:
        export_files_by_seed = _scrape_trends_exports_bridge(
            seed_keywords=opts.seed_keywords,
            run_dir=trends_exports_dir,
            headed=opts.headed,
            max_attempts=TRENDS_RETRY_ATTEMPTS,
            region=opts.trends_region,
            date_range=opts.trends_range,
        )
        for seed_keyword, files in export_files_by_seed.items():
            _append_manifest(
                run_dir,
                RunManifestEntry.create(
                    run_id=run_id,
                    blog_suffix=suffix,
                    seed_keyword=seed_keyword,
                    status="trends_scraped",
                    source_stage="pinterest_trends",
                    source_file=";".join(files),
                    details={"export_files": files},
                ),
            )

        top_candidates = analyze_trends_exports(
            export_files_by_seed=export_files_by_seed,
            run_dir=trends_analysis_dir,
            top_n=opts.trends_top_n,
            region=opts.trends_region,
            time_range=opts.trends_range,
            min_reach_hat=opts.min_reach_hat,
            min_source_count=opts.min_source_count,
        )
        top_keywords_payload = [item.to_dict() for item in top_candidates]
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=suffix,
                seed_keyword="__TRENDS__",
                status="trends_analyzed",
                source_stage="pinterest_trends",
                details={
                    "top_keyword_count": len(top_keywords_payload),
                    "region": opts.trends_region,
                    "time_range": opts.trends_range,
                },
            ),
        )

    ranked_keywords: list[dict[str, Any]] = []
    for item in top_keywords_payload:
        keyword = str(item.get("keyword", "")).strip()
        if not _is_valid_trend_keyword(keyword):
            continue
        ranked_keywords.append(
            {
                "keyword": keyword,
                "rank": int(item.get("rank", 0) or 0),
                "reach_hat": float(item.get("reach_hat", 0.0) or 0.0),
                "reach_confidence": float(item.get("reach_confidence", 0.0) or 0.0),
                "trend_index_raw": float(item.get("trend_index_raw", 0.0) or 0.0),
                "growth_rate_raw": float(item.get("growth_rate_raw", 0.0) or 0.0),
                "source_count": int(item.get("source_count", 0) or 0),
                "qualified": bool(item.get("qualified", True)),
            }
        )

    raw_trends_count = _read_raw_trends_count(trends_analysis_dir)
    result = TrendCandidates(
        run_id=run_id,
        run_dir=str(run_dir),
        ranked_keywords=ranked_keywords,
        raw_trends_count=raw_trends_count,
    )
    _write_summary(run_dir, blog_suffix=suffix)
    return result


async def collect_trends_candidates(opts: EngineRunOptions) -> TrendCandidates:
    """Phase 1: Collect, score, and return ranked Pinterest Trends candidates."""
    return _collect_trends_candidates_sync(opts)


def collect_trends_candidates_sync(opts: EngineRunOptions) -> TrendCandidates:
    """Sync wrapper for Phase 1 (safe for Streamlit reruns and CLI)."""
    return _collect_trends_candidates_sync(opts)


def _collect_pinclicks_data_sync(
    opts: EngineRunOptions,
    selected_keywords: list[str],
    run_id: str,
) -> PinClicksResults:
    """Phase 2 sync implementation: scrape/rank PinClicks data for selected keywords."""
    run_dir = _resolve_phase_run_dir(run_id)
    suffix = opts.blog_suffix.strip().upper()
    _write_run_options(run_dir, opts)
    entries = _load_manifest_entries(run_dir)
    latest_by_seed = _latest_status_by_seed(entries)

    trends_payload = _load_cached_top_keywords(run_dir)
    trend_rank_map: dict[str, int] = {}
    reach_hat_map: dict[str, float] = {}
    reach_confidence_map: dict[str, float] = {}
    for item in trends_payload:
        keyword = str(item.get("keyword", "")).strip()
        if not _is_valid_trend_keyword(keyword):
            continue
        trend_rank_map[keyword] = int(item.get("rank", 0))
        reach_hat_map[keyword] = float(item.get("reach_hat", 0.5) or 0.5)
        reach_confidence_map[keyword] = float(item.get("reach_confidence", 0.5) or 0.5)

    candidate_keywords = _clean_keyword_list(selected_keywords)
    if not candidate_keywords:
        candidate_keywords = list(trend_rank_map.keys())
    if not candidate_keywords:
        raise TrendsAnalysisError(
            "No valid textual keywords were found in Pinterest Trends output."
        )

    pinclicks_results: dict[str, SeedScrapeResult] = {}
    skipped: list[dict[str, Any]] = []
    pinclicks_exports_dir = run_dir / "pinclicks_exports"
    _ensure_dir(pinclicks_exports_dir)
    # --- Session preflight ---
    try:
        session_status = _bootstrap_pinclicks_session_bridge(
            headed=opts.headed,
            allow_manual_setup=False,
            setup_timeout_seconds=30,
        )
        if not bool(session_status.get("authenticated", False)):
            skipped.append(
                {
                    "keyword": "__preflight__",
                    "reason": PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
                    "error": str(session_status.get("message", "")).strip()
                    or "PinClicks Stage 3 setup is required before scraping.",
                    "session_expired": bool(session_status.get("session_expired", False)),
                    "expired_cookies": session_status.get("expired_cookies", []),
                    "expired_at": session_status.get("expired_at", {}),
                    "attempts": 0,
                    "used_headed_fallback": False,
                    "source_stage": "pinclicks",
                }
            )
            result = PinClicksResults(
                run_id=run_id,
                run_dir=str(run_dir),
                winners=[],
                skipped=skipped,
            )
            _write_summary(run_dir, blog_suffix=suffix)
            return result
    except Exception as exc:
        skipped.append(
            {
                "keyword": "__preflight__",
                "reason": _classify_scrape_error(exc),
                "error": str(exc),
                "attempts": 0,
                "used_headed_fallback": False,
                "source_stage": "pinclicks",
            }
        )
        result = PinClicksResults(
            run_id=run_id,
            run_dir=str(run_dir),
            winners=[],
            skipped=skipped,
        )
        _write_summary(run_dir, blog_suffix=suffix)
        return result

    # --- Circuit breaker state ---
    _CB_AUTH_REASONS = {
        "authentication_failed",
        PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
    }
    consecutive_failures = 0
    consecutive_auth_failures = 0

    for idx, keyword in enumerate(candidate_keywords):
        if idx > 0:
            time.sleep(random.uniform(0.5, 1.2))

        keyword_slug = _seed_slug(keyword)
        cached_path = pinclicks_exports_dir / keyword_slug / "seed_scrape_result.json"
        latest = latest_by_seed.get(keyword)
        if cached_path.exists() and isinstance(latest, dict):
            latest_status = str(latest.get("status", "")).strip()
            if latest_status in TERMINAL_PINCLICKS_CACHE_STATUSES:
                try:
                    pinclicks_results[keyword] = _load_seed_scrape_result(cached_path)
                    consecutive_failures = 0
                    consecutive_auth_failures = 0
                    continue
                except Exception:
                    pass

        try:
            scrape_result = _scrape_seed_bridge(
                seed_keyword=keyword,
                blog_suffix=suffix,
                run_dir=pinclicks_exports_dir,
                headed=opts.headed,
                max_records=opts.pinclicks_max_records,
                max_attempts=SCRAPE_RETRY_ATTEMPTS,
            )
        except Exception as exc:
            error_text = str(exc)
            reason = _classify_scrape_error(exc)
            attempts = int(getattr(exc, "attempts", SCRAPE_RETRY_ATTEMPTS) or SCRAPE_RETRY_ATTEMPTS)
            used_headed_fallback = bool(getattr(exc, "used_headed_fallback", False))
            _append_manifest(
                run_dir,
                RunManifestEntry.create(
                    run_id=run_id,
                    blog_suffix=suffix,
                    seed_keyword=keyword,
                    status="scrape_failed",
                    failure_stage="scrape_failed",
                    source_stage="pinclicks",
                    keyword_rank_trends=trend_rank_map.get(keyword, 0),
                    details={
                        "error": error_text,
                        "reason": reason,
                        "attempts": attempts,
                        "used_headed_fallback": used_headed_fallback,
                    },
                ),
            )
            skipped.append(
                {
                    "keyword": keyword,
                    "reason": reason or PINCLICKS_SKIP_REASON_UNKNOWN,
                    "error": error_text,
                    "attempts": attempts,
                    "used_headed_fallback": used_headed_fallback,
                    "source_stage": "pinclicks",
                }
            )

            # Circuit breaker tracking (3a)
            consecutive_failures += 1
            if reason in _CB_AUTH_REASONS:
                consecutive_auth_failures += 1
            else:
                consecutive_auth_failures = 0

            if consecutive_auth_failures >= 2 or consecutive_failures >= 3:
                remaining = candidate_keywords[idx + 1:]
                for aborted_kw in remaining:
                    skipped.append({
                        "keyword": aborted_kw,
                        "reason": "circuit_breaker_tripped",
                        "error": f"Aborted after {consecutive_failures} consecutive failures (last: {reason})",
                        "attempts": 0,
                        "used_headed_fallback": False,
                        "source_stage": "pinclicks",
                    })
                break

            continue

        consecutive_failures = 0
        consecutive_auth_failures = 0
        pinclicks_results[keyword] = scrape_result
        scrape_mode = str(scrape_result.scrape_mode or "").strip() or (
            "export" if scrape_result.source_file else "visible_rows"
        )
        diagnostics = dict(scrape_result.diagnostics or {})
        success_status = "pinclicks_exported" if scrape_mode == "export" else PINCLICKS_STATUS_SCRAPED
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=suffix,
                seed_keyword=keyword,
                status=success_status,
                source_stage="pinclicks",
                source_file=scrape_result.source_file,
                keyword_rank_trends=trend_rank_map.get(keyword, 0),
                details={
                    "record_count": len(scrape_result.records),
                    "source_url": scrape_result.source_url,
                    "source_file": scrape_result.source_file,
                    "scrape_mode": scrape_mode,
                    "raw_item_count": int(diagnostics.get("raw_item_count", 0) or 0),
                    "rejected_item_count": int(diagnostics.get("rejected_item_count", 0) or 0),
                    "kept_item_count": int(diagnostics.get("kept_item_count", len(scrape_result.records)) or 0),
                    "final_record_count": int(diagnostics.get("final_record_count", len(scrape_result.records)) or 0),
                    "engagement_available": bool(diagnostics.get("engagement_available", False)),
                },
            ),
        )
        entries = _load_manifest_entries(run_dir)
        latest_by_seed = _latest_status_by_seed(entries)

    pinclicks_analysis_dir = run_dir / "pinclicks_analysis"
    _ensure_dir(pinclicks_analysis_dir)
    try:
        winners = rank_pinclicks_keywords(
            scrape_results=list(pinclicks_results.values()),
            run_dir=pinclicks_analysis_dir,
            top_n=opts.winners_count,
            trend_rank_map=trend_rank_map,
            reach_hat_map=reach_hat_map,
            reach_confidence_map=reach_confidence_map,
            min_click_score=opts.min_click_score,
        )
    except PinClicksAnalysisError:
        winners = []

    normalized_winners: list[dict[str, Any]] = []
    for winner in winners:
        winner_payload = winner.to_dict()
        winner_payload["scrape_source"] = PINCLICKS_SCRAPE_SOURCE_BRAVE
        normalized_winners.append(_safe_winner_dict(winner_payload))
        _append_manifest(
            run_dir,
            RunManifestEntry.create(
                run_id=run_id,
                blog_suffix=suffix,
                seed_keyword=winner.keyword,
                status="pinclicks_ranked",
                source_stage="pinclicks",
                keyword_rank_trends=winner.trend_rank,
                keyword_rank_pinclicks=winner.pinclicks_rank,
                details=winner_payload,
            ),
        )

    result = PinClicksResults(
        run_id=run_id,
        run_dir=str(run_dir),
        winners=normalized_winners,
        skipped=skipped,
    )
    _write_summary(run_dir, blog_suffix=suffix)
    return result


async def collect_pinclicks_data(
    opts: EngineRunOptions,
    selected_keywords: list[str],
    run_id: str,
) -> PinClicksResults:
    """Phase 2: Scrape/score PinClicks data for selected trend keywords."""
    return _collect_pinclicks_data_sync(opts=opts, selected_keywords=selected_keywords, run_id=run_id)


def collect_pinclicks_data_sync(
    opts: EngineRunOptions,
    selected_keywords: list[str],
    run_id: str,
) -> PinClicksResults:
    """Sync wrapper for Phase 2 (safe for Streamlit reruns and CLI)."""
    return _collect_pinclicks_data_sync(opts=opts, selected_keywords=selected_keywords, run_id=run_id)


def bootstrap_pinclicks_session_sync(
    *,
    headed: bool = True,
    allow_manual_setup: bool = True,
    setup_timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Sync wrapper for Stage 3 Brave session bootstrap/setup."""
    return _bootstrap_pinclicks_session_bridge(
        headed=headed,
        allow_manual_setup=allow_manual_setup,
        setup_timeout_seconds=setup_timeout_seconds,
    )


def _run_winner_generation_sync(
    opts: EngineRunOptions,
    winners: list[dict[str, Any]],
    run_id: str,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> GenerationResults:
    """Phase 3 sync implementation: generate, publish, and append CSV for winners."""
    run_dir = _resolve_phase_run_dir(run_id)
    suffix = opts.blog_suffix.strip().upper()
    _write_run_options(run_dir, opts)
    validate_board_mapping_for_blog(suffix)
    blog_name = _resolve_blog_name_from_suffix(suffix)
    normalized_results: list[dict[str, Any]] = []

    entries = _load_manifest_entries(run_dir)
    latest_by_seed = _latest_status_by_seed(entries)
    bounded_winners = winners[: max(0, opts.winners_count)]
    total_count = len(bounded_winners)
    repair_system_prompt: str | None = None

    for index, winner in enumerate(bounded_winners, start=1):
        keyword = str(winner.get("keyword", "")).strip()
        if not keyword:
            result = {
                "keyword": "",
                "status": "failed_pre_publish",
                "error": "Winner item is missing keyword.",
                "failure_stage": "generation_input",
            }
            normalized_results.append(result)
            if on_progress:
                on_progress(index, total_count, result)
            continue

        latest = latest_by_seed.get(keyword, {})
        latest_status = str(latest.get("status", "")).strip()
        if latest_status in TERMINAL_WINNER_STATUSES:
            result = build_generation_result_from_manifest_entry(seed_keyword=keyword, entry=latest)
            if result is None:
                result = {
                    "keyword": keyword,
                    "status": "failed_pre_publish",
                    "error": f"Already terminal: {latest_status}",
                    "failure_stage": latest_status,
                }
            normalized_results.append(result)
            if on_progress:
                on_progress(index, total_count, result)
            continue

        cached_path = run_dir / "pinclicks_exports" / _seed_slug(keyword) / "seed_scrape_result.json"
        if cached_path.exists():
            try:
                scrape_result = _load_seed_scrape_result(cached_path)
            except Exception as exc:
                result = {
                    "keyword": keyword,
                    "status": "failed_pre_publish",
                    "error": str(exc),
                    "failure_stage": "pinclicks_cache_parse",
                }
                normalized_results.append(result)
                if on_progress:
                    on_progress(index, total_count, result)
                continue
        else:
            scrape_source = str(winner.get("scrape_source", "")).strip().lower()
            if scrape_source in {"cloudflare_crawl", PINCLICKS_SCRAPE_SOURCE_BRAVE}:
                result = {
                    "keyword": keyword,
                    "status": "failed_pre_publish",
                    "error": "Missing cached Stage 3 scrape result for Brave-backed winner.",
                    "failure_stage": "pinclicks_cache_missing",
                }
                normalized_results.append(result)
                if on_progress:
                    on_progress(index, total_count, result)
                continue
            scrape_result = _synthesize_scrape_result(keyword, suffix)

        if repair_system_prompt is None:
            repair_system_prompt = load_repair_system_prompt()

        result = _process_winner(
            run_id=run_id,
            run_dir=run_dir,
            blog_suffix=suffix,
            blog_name=blog_name,
            scrape_result=scrape_result,
            trend_rank=int(winner.get("trend_rank", 0) or 0),
            pinclicks_rank=int(winner.get("pinclicks_rank", 0) or 0),
            repair_system_prompt=repair_system_prompt,
            publish_status=opts.publish_status,
            csv_first_publish_at=opts.csv_first_publish_at,
            csv_cadence_minutes=opts.csv_cadence_minutes,
        )
        result_status = str(result.get("status", "")).strip()
        failure_stage = str(result.get("failure_stage", "")).strip()
        if result_status == "completed":
            normalized = dict(result)
            normalized["status"] = "completed"
            normalized_results.append(normalized)
        elif failure_stage in PARTIAL_SUCCESS_STATUSES:
            normalized = dict(result)
            normalized["status"] = "partial"
            normalized_results.append(normalized)
        else:
            normalized = dict(result)
            normalized["status"] = "failed_pre_publish"
            normalized_results.append(normalized)

        if on_progress:
            on_progress(index, total_count, normalized)

        entries = _load_manifest_entries(run_dir)
        latest_by_seed = _latest_status_by_seed(entries)

    completed, partial, failed_pre_publish, failed = _split_generation_results(normalized_results)

    result = GenerationResults(
        run_id=run_id,
        run_dir=str(run_dir),
        completed=completed,
        partial=partial,
        failed_pre_publish=failed_pre_publish,
        failed=failed,
        manifest_path=str(_manifest_path(run_dir)),
        csv_path=str(_run_csv_path(run_dir, suffix)),
    )
    _write_summary(run_dir, blog_suffix=suffix)
    return result


async def run_winner_generation(
    opts: EngineRunOptions,
    winners: list[dict[str, Any]],
    run_id: str,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> GenerationResults:
    """Phase 3: Generate/publish winners and append Pinterest CSV rows."""
    return _run_winner_generation_sync(
        opts=opts,
        winners=winners,
        run_id=run_id,
        on_progress=on_progress,
    )


def run_winner_generation_sync(
    opts: EngineRunOptions,
    winners: list[dict[str, Any]],
    run_id: str,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> GenerationResults:
    """Sync wrapper for Phase 3 (safe for Streamlit reruns and CLI)."""
    return _run_winner_generation_sync(
        opts=opts,
        winners=winners,
        run_id=run_id,
        on_progress=on_progress,
    )


def run_engine(*, blog_suffix: str, resume: str | None, max_seeds: int | None, headed: bool) -> dict[str, Any]:
    """Backward-compatible CLI wrapper that runs phase 1 -> phase 2 -> phase 3."""
    load_dotenv()
    opts = EngineRunOptions.from_env(blog_suffix)
    opts.resume_run_id = resume
    opts.headed = bool(headed)
    if max_seeds is not None:
        opts.seed_keywords = opts.seed_keywords[: max(0, max_seeds)]

    trends_result = collect_trends_candidates_sync(opts)
    selected_keywords = [
        str(item.get("keyword", "")).strip()
        for item in trends_result.ranked_keywords
        if str(item.get("keyword", "")).strip()
    ]
    pinclicks_result = collect_pinclicks_data_sync(
        opts=opts,
        selected_keywords=selected_keywords,
        run_id=trends_result.run_id,
    )
    run_winner_generation_sync(
        opts=opts,
        winners=pinclicks_result.winners,
        run_id=pinclicks_result.run_id,
    )

    run_dir = Path(trends_result.run_dir)
    return _write_summary(run_dir, blog_suffix=opts.blog_suffix)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autonomous Pinterest Trends + PinClicks to WordPress + Pinterest CSV engine.",
    )
    parser.add_argument("--blog", required=True, help="Blog suffix (e.g. THE_SUNDAY_PATIO)")
    parser.add_argument("--resume", default=None, help="Run ID or run folder path to resume")
    parser.add_argument("--max-seeds", type=int, default=None, help="Limit initial trends seed keywords for this run")
    parser.add_argument("--headed", action="store_true", help="Force headed browser for scraping")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        summary = run_engine(
            blog_suffix=str(args.blog),
            resume=args.resume,
            max_seeds=args.max_seeds,
            headed=bool(args.headed),
        )
    except (
        EngineError,
        TrendsScraperError,
        TrendsAnalysisError,
        ScraperError,
        PinClicksAnalysisError,
        AnalysisError,
        ImageDesignError,
        GenerationError,
        ArticleValidatorError,
        WordPressUploadError,
        ExporterError,
    ) as exc:
        print(f"[pinterest_engine] failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
