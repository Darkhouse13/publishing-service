from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv
import requests

from automating_wf.scrapers.file_parser import coerce_numeric, parse_tabular_export
from automating_wf.models.pinterest import PinRecord, SeedScrapeResult


PINCLICKS_DEFAULT_BASE_URL = "https://app.pinclicks.com"
TOP_PIN_TARGET = 25
MAX_SCROLL_ATTEMPTS = 36
MAX_DUPLICATE_SCROLLS = 5
SCRAPE_RETRY_ATTEMPTS = 3
NAVIGATION_DELAY_RANGE = (2.0, 5.0)
ACTION_DELAY_RANGE = (0.8, 1.8)
LOGIN_SETTLE_DELAY_RANGE = (4.0, 7.0)
EXPORT_DOWNLOAD_TIMEOUT_MS = 5000
CLOUDFLARE_BROWSER_RENDERING_BASE_URL = "https://api.cloudflare.com/client/v4/accounts"
CLOUDFLARE_CRAWL_POLL_INTERVAL_SECONDS = 2.0
CLOUDFLARE_CRAWL_TIMEOUT_SECONDS = 180
CLOUDFLARE_CRAWL_REQUEST_TIMEOUT_SECONDS = 30
CLOUDFLARE_CRAWL_DEFAULT_MAX_PAGES = 3

PINCLICKS_BROWSER_MODE_ENV = "PINCLICKS_BROWSER_MODE"
PINCLICKS_BROWSER_MODE_BRAVE = "brave_persistent"
PINCLICKS_BROWSER_MODE_CAMOUFOX = "camoufox"
PINCLICKS_BROWSER_MODE_DEFAULT = PINCLICKS_BROWSER_MODE_BRAVE
PINCLICKS_SCRAPE_SOURCE_BRAVE = PINCLICKS_BROWSER_MODE_BRAVE

CAPTCHA_MARKERS = (
    "captcha",
    "verify you are human",
    "unusual traffic",
    "cloudflare",
    "challenge",
)

LOGIN_INPUT_SELECTORS = (
    "input[name='email']",
    "input[type='email']",
    "input[name='username']",
    "input[autocomplete='username']",
    "#email",
    "input[placeholder*='email' i]",
)

PASSWORD_INPUT_SELECTORS = (
    "input[name='password']",
    "input[type='password']",
    "input[autocomplete='current-password']",
    "#password",
    "input[placeholder*='password' i]",
)

LOGIN_BUTTON_SELECTORS = (
    "button[type='submit']",
    "button:has-text('Log in')",
    "button:has-text('Sign in')",
    "[role='button']:has-text('Log in')",
    "[role='button']:has-text('Sign in')",
    "button:has-text('Login')",
)

EXPORT_BUTTON_SELECTORS = (
    "button:has-text('Export')",
    "button:has-text('Download')",
    "[role='button']:has-text('Export')",
    "[aria-label*='Export']",
    "[data-testid*='export']",
    "button:has-text('CSV')",
    "a:has-text('Export')",
    "a:has-text('Download')",
)

PINCLICKS_PINS_SEARCH_INPUT_SELECTORS = (
    "input[placeholder*='search any keyword or topic to see top pins' i]",
    "input[aria-label*='search any keyword or topic to see top pins' i]",
    "input[placeholder*='keyword or topic' i]",
    "input[aria-label*='keyword or topic' i]",
    "input[placeholder*='search' i][type='text']",
    "[role='search'] input",
    "form input[type='search']",
)

PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND = "search_input_not_found"
PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED = "search_input_rejected"
PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED = "direct_top_pins_navigation_failed"
PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE = "invalid_results_page"
PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED = "export_download_failed"
PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED = "no_records_extracted"
PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED = "captcha_checkpoint_required"
PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED = "authentication_failed"
PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED = "authentication_setup_required"
PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED = "cloudflare_request_failed"
PINCLICKS_SKIP_REASON_CLOUDFLARE_RESPONSE_PARSE_FAILED = "cloudflare_response_parse_failed"
PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED = "cloudflare_bot_blocked"
PINCLICKS_SKIP_REASON_UNKNOWN = "unknown_scrape_failure"

PINCLICKS_SKIP_REASONS = {
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND,
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
    PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
    PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE,
    PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
    PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
    PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
    PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED,
    PINCLICKS_SKIP_REASON_CLOUDFLARE_RESPONSE_PARSE_FAILED,
    PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED,
    PINCLICKS_SKIP_REASON_UNKNOWN,
}


class ScraperError(RuntimeError):
    """Raised when PinClicks scraping cannot continue."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = PINCLICKS_SKIP_REASON_UNKNOWN,
        attempts: int = 1,
        used_headed_fallback: bool = False,
    ) -> None:
        super().__init__(message)
        normalized_reason = str(reason or "").strip()
        self.reason = (
            normalized_reason
            if normalized_reason in PINCLICKS_SKIP_REASONS
            else PINCLICKS_SKIP_REASON_UNKNOWN
        )
        self.attempts = int(attempts) if int(attempts) > 0 else 1
        self.used_headed_fallback = bool(used_headed_fallback)


class CaptchaCheckpointRequired(ScraperError):
    """Raised when a human checkpoint is required."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason=PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED)


def _classify_scrape_error(error: Exception) -> str:
    if isinstance(error, ScraperError) and error.reason in PINCLICKS_SKIP_REASONS:
        return error.reason

    text = str(error or "").strip().casefold()
    if not text:
        return PINCLICKS_SKIP_REASON_UNKNOWN
    if "search box" in text or "keyword" in text and "enter" in text:
        return PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED
    if ("404" in text or "not found" in text) and (
        "pinclicks" in text or "results page" in text or "top pins" in text
    ):
        return PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE
    if "export" in text and ("download" in text or "trigger" in text):
        return PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED
    if "captcha" in text or "challenge" in text or "verify you are human" in text:
        if "cloudflare" in text or "crawl" in text or "browser rendering" in text:
            return PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED
        return PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED
    if "access denied" in text or "forbidden" in text or "bot" in text and "cloudflare" in text:
        return PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED
    if "cloudflare" in text and ("parse" in text or "schema" in text or "record" in text):
        return PINCLICKS_SKIP_REASON_CLOUDFLARE_RESPONSE_PARSE_FAILED
    if "cloudflare" in text and ("request" in text or "crawl" in text or "http" in text):
        return PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED
    if "setup" in text and "pinclicks" in text:
        return PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED
    if "login" in text or "unauthenticated" in text or "authentication" in text:
        return PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED
    if "no pin records" in text or "no records" in text:
        return PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED
    return PINCLICKS_SKIP_REASON_UNKNOWN


def _should_retry_brave_error(error: Exception) -> bool:
    """Return False for Brave failures that are unlikely to succeed on retry."""
    if isinstance(error, ScraperError):
        if error.reason in {
            PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
            PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE,
        }:
            return False

    text = str(error or "").strip().casefold()
    if "playwright sync api inside the asyncio loop" in text:
        return False
    return True


def _sleep_random(delay_range: tuple[float, float]) -> None:
    time.sleep(random.uniform(*delay_range))


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_compact_number(raw_value: str) -> float:
    cleaned = raw_value.strip().lower().replace(",", "")
    multiplier = 1.0
    if cleaned.endswith("k"):
        multiplier = 1000.0
        cleaned = cleaned[:-1]
    elif cleaned.endswith("m"):
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


def _extract_engagement(metric_text: str) -> dict[str, float]:
    lowered = metric_text.lower()
    patterns = {
        "saves": r"(\d[\d.,]*[km]?)\s*saves?",
        "clicks": r"(\d[\d.,]*[km]?)\s*clicks?",
        "impressions": r"(\d[\d.,]*[km]?)\s*(?:impressions?|views?)",
        "comments": r"(\d[\d.,]*[km]?)\s*comments?",
        "outbound": r"(\d[\d.,]*[km]?)\s*outbound(?:\s*clicks?)?",
    }
    parsed: dict[str, float] = {}
    for metric_name, pattern in patterns.items():
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        parsed[metric_name] = _parse_compact_number(match.group(1))
    parsed["score_total"] = float(sum(parsed.values()))
    return parsed


def _extract_pin_id(pin_url: str) -> str:
    match = re.search(r"/pin/(\d+)", pin_url)
    if match:
        return match.group(1)
    return ""


_MOJIBAKE_HINTS = ("\u00c3", "\u00e2", "\u00c2")
_MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u2018": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u00a6": "...",
    "\u00c2\u00a0": " ",
}
_TEXT_REPLACEMENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u00a0": " ",
}
_UI_NOISE_MARKERS = (
    "select/deselect item",
    "select deselect item",
    "save to board",
    "copy link",
    "more ideas",
)
_UI_NOISE_PREFIXES = (
    "pin by ",
    "posted by ",
    "shared by ",
)
_TAG_NOISE_TERMS = {
    "pin",
    "pins",
    "pin by",
    "www",
    "com",
    "select",
    "deselect",
}


def _repair_mojibake(value: str) -> str:
    repaired = value
    if any(marker in value for marker in _MOJIBAKE_HINTS):
        for encoding in ("cp1252", "latin-1"):
            try:
                candidate = value.encode(encoding, errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                continue
            if candidate and sum(candidate.count(marker) for marker in _MOJIBAKE_HINTS) < sum(
                value.count(marker) for marker in _MOJIBAKE_HINTS
            ):
                repaired = candidate
                break
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(bad, good)
    return repaired


def _normalize_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = _repair_mojibake(text)
    for bad, good in _TEXT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("|,;:/")
    return text


def _looks_like_domain_or_url(value: str) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    if " " in text:
        return False
    stripped = re.sub(r"^https?://", "", text).strip("/ ")
    return bool(re.fullmatch(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[\w./%+-]*)?", stripped))


def _strip_domain_only_description(value: str) -> str:
    return "" if _looks_like_domain_or_url(value) else value


def _is_ui_noise_text(*values: str) -> bool:
    combined = " ".join(part for part in values if part).casefold()
    if not combined:
        return False
    if any(marker in combined for marker in _UI_NOISE_MARKERS):
        return True
    return any(combined.startswith(prefix) for prefix in _UI_NOISE_PREFIXES)


def _is_pinterest_pin_url(pin_url: str) -> bool:
    if not pin_url:
        return False
    parsed = urlparse(pin_url)
    host = parsed.netloc.casefold()
    return "pinterest." in host and "/pin/" in parsed.path.casefold()


def _has_strong_fallback_identifier(*, title: str, description: str) -> bool:
    if _is_ui_noise_text(title, description):
        return False
    text = " ".join(part for part in (title, description) if part).strip()
    if len(text) < 24:
        return False
    if _looks_like_domain_or_url(text):
        return False
    return len(title.split()) >= 2 or len(description.split()) >= 4


def _clean_tags(tags: list[str], *, title: str, description: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    title_key = title.casefold()
    description_key = description.casefold()
    for tag in tags:
        normalized = _normalize_text(tag).lstrip("#")
        if not normalized:
            continue
        lowered = normalized.casefold()
        if lowered in seen:
            continue
        if lowered in _TAG_NOISE_TERMS:
            continue
        if re.fullmatch(r"[_\W]+", normalized):
            continue
        if "http" in lowered or "www." in lowered or _looks_like_domain_or_url(lowered):
            continue
        if lowered == title_key or lowered == description_key:
            continue
        seen.add(lowered)
        cleaned.append(normalized)
        if len(cleaned) >= 12:
            break
    return cleaned


def _normalize_record_candidates(
    *,
    seed_keyword: str,
    items: list[dict[str, Any]],
    max_records: int,
    scrape_mode: str,
) -> tuple[list[PinRecord], dict[str, Any], list[dict[str, Any]]]:
    records: list[PinRecord] = []
    rejected: list[dict[str, Any]] = []
    rejected_count = 0
    seen_keys: set[str] = set()
    now = _now_utc_iso()

    for raw_item in items:
        pin_url = _normalize_text(raw_item.get("pin_url", ""))
        if pin_url and not _is_pinterest_pin_url(pin_url):
            pin_url = ""
        title = _normalize_text(raw_item.get("title", ""))
        description = _strip_domain_only_description(_normalize_text(raw_item.get("description", "")))
        tags_raw = raw_item.get("tags", [])
        tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
        metric_text_parts = [_normalize_text(raw_item.get("metric_text", ""))]
        metric_fragments = raw_item.get("metric_fragments", [])
        if isinstance(metric_fragments, list):
            metric_text_parts.extend(_normalize_text(item) for item in metric_fragments)
        metric_text = " | ".join(part for part in metric_text_parts if part)

        if not title and not description and metric_text:
            fragments = [part.strip() for part in re.split(r"[|\n]+", metric_text) if part.strip()]
            if fragments:
                title = fragments[0]
                description = " ".join(fragments[1:]).strip()
                description = _strip_domain_only_description(description)
        if not tags and metric_text:
            tags = [match.group(1) for match in re.finditer(r"#([a-z0-9_]+)", metric_text.lower())]
        tags = _clean_tags(tags, title=title, description=description)

        engagement_raw = raw_item.get("engagement")
        engagement = dict(engagement_raw) if isinstance(engagement_raw, dict) else _extract_engagement(metric_text)
        if "score_total" not in engagement:
            engagement["score_total"] = float(
                sum(float(value) for key, value in engagement.items() if key != "score_total" and isinstance(value, (int, float)))
            )

        pin_id = _extract_pin_id(pin_url) or _normalize_text(raw_item.get("pin_id", ""))
        dedupe_key = pin_id or pin_url or f"{title}|{description}"
        reject_reason = ""
        if not title and not description:
            reject_reason = "missing_text"
        elif _is_ui_noise_text(title, description):
            reject_reason = "ui_noise"
        elif not pin_id and not pin_url and not _has_strong_fallback_identifier(title=title, description=description):
            reject_reason = "missing_identity"
        elif dedupe_key in seen_keys:
            reject_reason = "duplicate"

        if reject_reason:
            rejected_count += 1
            if len(rejected) < 25:
                rejected.append(
                    {
                        "reason": reject_reason,
                        "pin_url": pin_url,
                        "pin_id": pin_id,
                        "title": title,
                        "description": description,
                        "tags": tags,
                        "metric_text": metric_text,
                    }
                )
            continue

        seen_keys.add(dedupe_key)
        records.append(
            PinRecord(
                seed_keyword=seed_keyword,
                rank=len(records) + 1,
                pin_url=pin_url,
                pin_id=pin_id,
                title=title,
                description=description,
                tags=tags,
                engagement=engagement,
                scraped_at=now,
            )
        )
        if len(records) >= max_records:
            break

    diagnostics = {
        "scrape_mode": scrape_mode,
        "raw_item_count": len(items),
        "rejected_item_count": rejected_count,
        "kept_item_count": len(records),
        "final_record_count": len(records),
        "engagement_available": any(
            float(record.engagement.get("score_total", 0.0) or 0.0) > 0.0 for record in records
        ),
    }
    return records, diagnostics, rejected


def _safe_storage_state_path() -> Path:
    load_dotenv()
    configured = os.getenv("PINCLICKS_STORAGE_STATE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # Legacy compatibility with previous key.
    legacy = os.getenv("PINTEREST_STORAGE_STATE_PATH", "").strip()
    if legacy:
        return Path(legacy).expanduser().resolve()
    default = Path.home() / ".codex" / "secrets" / "pinclicks_state.json"
    return default


def _check_session_health(storage_state_path: Path) -> dict[str, Any]:
    """Inspect stored cookies and classify session health."""
    result: dict[str, Any] = {
        "healthy": False,
        "cf_valid": False,
        "needs_reauth": True,
        "expired_critical": [],
    }
    if not storage_state_path.exists():
        return result

    try:
        state = json.loads(storage_state_path.read_text(encoding="utf-8"))
    except Exception:
        return result

    cookies = state.get("cookies", [])
    if not isinstance(cookies, list):
        return result

    now = time.time()
    critical_names = {"pinclicks_session", "XSRF-TOKEN"}
    cf_names = {"cf_clearance"}
    critical_valid = set()

    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name", "")).strip()
        expires = cookie.get("expires", 0)
        try:
            exp_ts = float(expires)
        except (TypeError, ValueError):
            exp_ts = 0.0
        # expires == -1 or 0 means session cookie (no expiry)
        is_expired = exp_ts > 0 and exp_ts < now

        if name in critical_names:
            if is_expired:
                result["expired_critical"].append(name)
            else:
                critical_valid.add(name)
        elif name in cf_names:
            result["cf_valid"] = not is_expired

    if critical_valid >= critical_names:
        result["needs_reauth"] = False
        result["healthy"] = True
    elif critical_valid:
        # Partial — some critical cookies still valid
        result["needs_reauth"] = True
        result["healthy"] = False
    else:
        result["needs_reauth"] = True
        result["healthy"] = False

    return result


def _check_brave_session_health() -> dict[str, Any]:
    """Inspect Brave PinFlow profile cookies and classify session health.

    Reads the Chromium Cookies SQLite DB directly (read-only) without
    launching the browser.  Returns the same shape as ``_check_session_health``
    plus an ``expired_at`` mapping of cookie-name to human-readable expiry.
    """
    import sqlite3

    from automating_wf.scrapers.brave_browser import pinflow_profile_dir

    result: dict[str, Any] = {
        "healthy": False,
        "cf_valid": False,
        "needs_reauth": True,
        "expired_critical": [],
        "expired_at": {},
    }

    profile = pinflow_profile_dir()
    if not profile:
        return result

    cookies_db = Path(profile) / "Default" / "Network" / "Cookies"
    if not cookies_db.exists():
        return result

    # Chromium stores timestamps as microseconds since 1601-01-01 00:00:00 UTC.
    _WEBKIT_EPOCH_OFFSET = 11_644_473_600

    try:
        conn = sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name, expires_utc, has_expires "
                "FROM cookies "
                "WHERE host_key LIKE '%pinclicks%' "
                "AND name IN ('pinclicks_session', 'XSRF-TOKEN', 'cf_clearance')",
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return result

    now = time.time()
    critical_names = {"pinclicks_session", "XSRF-TOKEN"}
    critical_valid: set[str] = set()

    for name, expires_webkit, has_expires in rows:
        if has_expires and expires_webkit > 0:
            expires_unix = (expires_webkit / 1_000_000) - _WEBKIT_EPOCH_OFFSET
            is_expired = expires_unix < now
            if is_expired:
                exp_dt = datetime.fromtimestamp(expires_unix, tz=timezone.utc)
                result["expired_at"][name] = exp_dt.strftime("%b %d, %Y")
        else:
            is_expired = False

        if name in critical_names:
            if is_expired:
                result["expired_critical"].append(name)
            else:
                critical_valid.add(name)
        elif name == "cf_clearance":
            result["cf_valid"] = not is_expired

    if critical_valid >= critical_names:
        result["needs_reauth"] = False
        result["healthy"] = True

    return result


def _cloudflare_account_id() -> str:
    load_dotenv()
    return os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()


def _cloudflare_api_token() -> str:
    load_dotenv()
    return os.getenv("CLOUDFLARE_API_TOKEN", "").strip()


def _cloudflare_base_url() -> str:
    load_dotenv()
    configured = os.getenv("CLOUDFLARE_BROWSER_RENDERING_BASE_URL", "").strip().rstrip("/")
    return configured or CLOUDFLARE_BROWSER_RENDERING_BASE_URL


def _cloudflare_crawl_max_pages() -> int:
    load_dotenv()
    raw = os.getenv("PINCLICKS_CRAWL_MAX_PAGES", "").strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = CLOUDFLARE_CRAWL_DEFAULT_MAX_PAGES
    return max(1, parsed)


def _load_storage_state(storage_state_path: Path) -> dict[str, Any]:
    if not storage_state_path.exists():
        raise ScraperError(
            f"PinClicks storage state was not found at {storage_state_path}.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )
    try:
        payload = json.loads(storage_state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ScraperError(
            f"Could not parse PinClicks storage state: {exc}",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        ) from exc
    if not isinstance(payload, dict):
        raise ScraperError(
            "PinClicks storage state must be a JSON object.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )
    return payload


def _cookie_matches_host(cookie: dict[str, Any], host: str) -> bool:
    domain = str(cookie.get("domain", "")).strip().lstrip(".").lower()
    if not domain:
        return True
    host = host.strip().lower()
    return host == domain or host.endswith(f".{domain}")


def _cookie_header_for_host(storage_state_path: Path, host: str) -> tuple[str, str]:
    state = _load_storage_state(storage_state_path)
    cookies = state.get("cookies", [])
    if not isinstance(cookies, list):
        raise ScraperError(
            "PinClicks storage state cookies are malformed.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    now = time.time()
    header_parts: list[str] = []
    xsrf_token = ""
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", "")).strip()
        if not name or not value:
            continue
        if not _cookie_matches_host(cookie, host):
            continue
        try:
            expires = float(cookie.get("expires", 0) or 0)
        except (TypeError, ValueError):
            expires = 0.0
        if expires > 0 and expires < now:
            continue
        header_parts.append(f"{name}={value}")
        if name == "XSRF-TOKEN":
            xsrf_token = value

    if not header_parts:
        raise ScraperError(
            f"No valid PinClicks cookies found for host '{host}'.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )
    return "; ".join(header_parts), xsrf_token


def _cloudflare_request_headers(*, start_url: str, cookie_header: str, xsrf_token: str) -> dict[str, str]:
    parsed = urlparse(start_url)
    host = parsed.netloc.strip()
    headers = {
        "Cookie": cookie_header,
        "Referer": start_url,
        "Origin": f"{parsed.scheme}://{host}" if parsed.scheme and host else start_url,
    }
    if xsrf_token:
        headers["X-XSRF-TOKEN"] = xsrf_token
    return headers


def _build_cloudflare_crawl_payload(*, start_url: str, cookie_header: str, xsrf_token: str) -> dict[str, Any]:
    parsed = urlparse(start_url)
    host = parsed.netloc.strip()
    return {
        "url": start_url,
        "maxPages": _cloudflare_crawl_max_pages(),
        "crawlerOptions": {
            "limit": _cloudflare_crawl_max_pages(),
            "maxRequestsPerCrawl": _cloudflare_crawl_max_pages(),
            "allowSubdomains": False,
        },
        "contentOptions": {
            "outputFormats": ["html", "markdown"],
        },
        "sessionOptions": {
            "extraHTTPHeaders": _cloudflare_request_headers(
                start_url=start_url,
                cookie_header=cookie_header,
                xsrf_token=xsrf_token,
            ),
        },
        "includeHosts": [host] if host else [],
    }


def _cloudflare_api_request(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = CLOUDFLARE_CRAWL_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    account_id = _cloudflare_account_id()
    token = _cloudflare_api_token()
    if not account_id or not token:
        raise ScraperError(
            "Missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN for PinClicks crawl.",
            reason=PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED,
        )
    url = f"{_cloudflare_base_url().rstrip('/')}/{account_id}/browser-rendering{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ScraperError(
            f"Cloudflare crawl request failed: {exc}",
            reason=PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED,
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ScraperError(
            f"Cloudflare crawl returned non-JSON response (HTTP {response.status_code}).",
            reason=PINCLICKS_SKIP_REASON_CLOUDFLARE_RESPONSE_PARSE_FAILED,
        ) from exc

    if response.status_code >= 400 or body.get("success") is False:
        error_text = ""
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            error_text = "; ".join(str(item.get("message", "")).strip() for item in errors if isinstance(item, dict))
        error_text = error_text or str(body.get("message", "")).strip() or f"HTTP {response.status_code}"
        raise ScraperError(
            f"Cloudflare crawl API error: {error_text}",
            reason=_classify_scrape_error(RuntimeError(error_text)),
        )
    return body


def _cloudflare_result_object(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", {})
    return result if isinstance(result, dict) else {}


def _cloudflare_job_id(payload: dict[str, Any]) -> str:
    result = _cloudflare_result_object(payload)
    for key in ("jobId", "job_id", "id"):
        value = str(result.get(key, "")).strip()
        if value:
            return value
    raise ScraperError(
        "Cloudflare crawl response did not include a job id.",
        reason=PINCLICKS_SKIP_REASON_CLOUDFLARE_RESPONSE_PARSE_FAILED,
    )


def _cloudflare_job_status(payload: dict[str, Any]) -> str:
    result = _cloudflare_result_object(payload)
    for key in ("status", "state"):
        value = str(result.get(key, "")).strip().lower()
        if value:
            return value
    return ""


def _cloudflare_terminal_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = _cloudflare_result_object(payload)
    for key in ("records", "pages", "results", "data"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _cloudflare_poll_job(job_id: str, *, artifacts_dir: Path) -> dict[str, Any]:
    deadline = time.time() + CLOUDFLARE_CRAWL_TIMEOUT_SECONDS
    attempts = 0
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        attempts += 1
        payload = _cloudflare_api_request(method="GET", path=f"/crawl/{job_id}")
        last_payload = payload
        _write_json(artifacts_dir / "cloudflare_crawl_poll.json", payload)
        status = _cloudflare_job_status(payload)
        if status in {"completed", "complete", "done", "success"}:
            return payload
        if status in {"failed", "error", "cancelled", "canceled"}:
            message = json.dumps(payload, ensure_ascii=False)
            raise ScraperError(
                f"Cloudflare crawl job failed: {message}",
                reason=_classify_scrape_error(RuntimeError(message)),
            )
        time.sleep(CLOUDFLARE_CRAWL_POLL_INTERVAL_SECONDS)

    raise ScraperError(
        f"Cloudflare crawl job '{job_id}' timed out after {attempts} polls.",
        reason=PINCLICKS_SKIP_REASON_CLOUDFLARE_REQUEST_FAILED,
    )


def _ensure_browser_context(browser_or_context: Any) -> tuple[Any, bool]:
    """Normalize Camoufox return value into a BrowserContext."""
    if hasattr(browser_or_context, "storage_state") and hasattr(browser_or_context, "new_page"):
        return browser_or_context, False
    if hasattr(browser_or_context, "new_context"):
        return browser_or_context.new_context(), True
    raise ScraperError(
        "Camoufox returned an unsupported browser handle; could not create a browser context.",
        reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
    )


def _clean_html_text(raw_html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _pin_record_from_match(*, seed_keyword: str, rank: int, pin_url: str, title: str, snippet: str) -> PinRecord:
    normalized_title = re.sub(r"\s+", " ", unescape(title or "")).strip() or seed_keyword
    normalized_snippet = re.sub(r"\s+", " ", unescape(snippet or "")).strip() or normalized_title
    tags = [tag.lstrip("#") for tag in re.findall(r"#([A-Za-z0-9_]+)", normalized_snippet)]
    return PinRecord(
        seed_keyword=seed_keyword,
        rank=rank,
        pin_url=pin_url,
        pin_id=_extract_pin_id(pin_url),
        title=normalized_title[:280],
        description=normalized_snippet[:500],
        tags=tags[:12],
        engagement=_extract_engagement(normalized_snippet),
        scraped_at=_now_utc_iso(),
    )


def _records_from_html_content(*, seed_keyword: str, html_content: str, max_records: int) -> list[PinRecord]:
    records: list[PinRecord] = []
    seen: set[str] = set()
    anchor_pattern = re.compile(
        r"""<a[^>]+href=["'](?P<href>https?://[^"']*/pin/\d+/?[^"']*|/pin/\d+/?[^"']*)["'][^>]*>(?P<label>.*?)</a>""",
        re.IGNORECASE | re.DOTALL,
    )
    for match in anchor_pattern.finditer(html_content):
        href = match.group("href").strip()
        if href.startswith("/"):
            href = f"https://www.pinterest.com{href}"
        pin_id = _extract_pin_id(href)
        if not pin_id or pin_id in seen:
            continue
        seen.add(pin_id)
        label_html = match.group("label")
        label = _clean_html_text(label_html)
        start = max(0, match.start() - 240)
        end = min(len(html_content), match.end() + 320)
        snippet = _clean_html_text(html_content[start:end])
        records.append(
            _pin_record_from_match(
                seed_keyword=seed_keyword,
                rank=len(records) + 1,
                pin_url=href,
                title=label,
                snippet=snippet,
            )
        )
        if len(records) >= max_records:
            break
    return records


def _records_from_markdown_content(*, seed_keyword: str, markdown_content: str, max_records: int) -> list[PinRecord]:
    records: list[PinRecord] = []
    seen: set[str] = set()
    pattern = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<href>https?://[^)]+/pin/\d+/?[^)]*)\)", re.IGNORECASE)
    for match in pattern.finditer(markdown_content):
        href = match.group("href").strip()
        pin_id = _extract_pin_id(href)
        if not pin_id or pin_id in seen:
            continue
        seen.add(pin_id)
        start = max(0, match.start() - 240)
        end = min(len(markdown_content), match.end() + 320)
        snippet = markdown_content[start:end]
        records.append(
            _pin_record_from_match(
                seed_keyword=seed_keyword,
                rank=len(records) + 1,
                pin_url=href,
                title=match.group("label"),
                snippet=snippet,
            )
        )
        if len(records) >= max_records:
            break
    return records


def _records_from_crawl_payload(
    *,
    seed_keyword: str,
    payload: dict[str, Any],
    max_records: int,
) -> list[PinRecord]:
    documents = _cloudflare_terminal_records(payload)
    extracted: list[PinRecord] = []
    seen: set[str] = set()
    for document in documents:
        html_content = str(document.get("html", "") or "")
        markdown_content = str(document.get("markdown", "") or document.get("md", "") or "")
        document_records = _records_from_html_content(
            seed_keyword=seed_keyword,
            html_content=html_content,
            max_records=max_records,
        )
        if not document_records and markdown_content:
            document_records = _records_from_markdown_content(
                seed_keyword=seed_keyword,
                markdown_content=markdown_content,
                max_records=max_records,
            )
        for record in document_records:
            dedupe_key = record.pin_id or record.pin_url
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            record.rank = len(extracted) + 1
            extracted.append(record)
            if len(extracted) >= max_records:
                return extracted
    return extracted


def _refresh_session(*, storage_state_path: Path, headed: bool) -> None:
    """Re-authenticate using existing cookies if possible."""
    health = _check_session_health(storage_state_path)
    if health["healthy"]:
        return

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        return

    import nest_asyncio
    nest_asyncio.apply()

    load_dotenv()
    app_base_url = os.getenv("PINCLICKS_APP_BASE_URL", PINCLICKS_DEFAULT_BASE_URL).strip()

    kwargs = _camoufox_kwargs(headed=headed, storage_state_path=storage_state_path)
    try:
        with Camoufox(**kwargs) as browser_or_context:
            context, owns_context = _ensure_browser_context(browser_or_context)
            page = context.new_page()

            try:
                if not health["cf_valid"]:
                    # Navigate to trigger CF challenge — Camoufox handles it automatically
                    page.goto(app_base_url, wait_until="load", timeout=60_000)
                    _sleep_random((3.0, 6.0))
                    if _contains_captcha(page):
                        if headed:
                            print("Cloudflare challenge detected. Solve it in the browser window...", file=sys.stderr)
                            _wait_for_captcha_solved(page)
                        else:
                            raise CaptchaCheckpointRequired(
                                "cf_clearance expired and Camoufox headless bypass failed; retry in headed mode."
                            )

                _perform_login(
                    page=page,
                    context=context,
                    app_base_url=app_base_url,
                    headed=headed,
                )
            finally:
                if owns_context and hasattr(context, "close"):
                    context.close()
    except TypeError as exc:
        raise ScraperError(
            "Camoufox/Playwright launch option mismatch during PinClicks session refresh: "
            f"{exc}",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        ) from exc


def _get_pinclicks_credentials() -> tuple[str, str]:
    load_dotenv()
    username = os.getenv("PINCLICKS_USERNAME", "").strip()
    password = os.getenv("PINCLICKS_PASSWORD", "").strip()
    if username and password:
        return username, password

    # Backward compatibility only.
    legacy_username = os.getenv("PINTEREST_USERNAME", "").strip()
    legacy_password = os.getenv("PINTEREST_PASSWORD", "").strip()
    return legacy_username, legacy_password


def _has_pinclicks_credentials() -> bool:
    username, password = _get_pinclicks_credentials()
    return bool(username and password)


def build_top_pins_url(seed_keyword: str) -> str:
    load_dotenv()
    template = os.getenv("PINCLICKS_TOP_PINS_URL_TEMPLATE", "").strip()
    if not template:
        raise ScraperError("Missing PINCLICKS_TOP_PINS_URL_TEMPLATE in environment.")
    if "{keyword}" not in template and "{raw_keyword}" not in template:
        raise ScraperError(
            "PINCLICKS_TOP_PINS_URL_TEMPLATE must include {keyword} or {raw_keyword} placeholder."
        )
    try:
        return template.format(keyword=quote_plus(seed_keyword), raw_keyword=seed_keyword)
    except KeyError as exc:
        raise ScraperError(
            "PINCLICKS_TOP_PINS_URL_TEMPLATE has unsupported placeholders. "
            "Use {keyword} or {raw_keyword}."
        ) from exc


def _build_pins_url(app_base_url: str) -> str:
    return f"{app_base_url.rstrip('/')}/pins"


def _body_text(page: Any) -> str:
    try:
        body = page.locator("body")
        if body.count() == 0:
            return ""
        return str(body.inner_text(timeout=5000)).strip().lower()
    except Exception:
        return ""


def _page_title(page: Any) -> str:
    try:
        return str(page.title()).strip().lower()
    except Exception:
        return ""


def _page_contains_not_found(page: Any) -> bool:
    title = _page_title(page)
    body = _body_text(page)
    if title == "not found":
        return True
    if "404" in body and "not found" in body:
        return True
    return False


def _has_results_page_signals(page: Any) -> bool:
    if _first_existing_selector(page, PINCLICKS_PINS_SEARCH_INPUT_SELECTORS):
        return True
    if _first_existing_selector(page, EXPORT_BUTTON_SELECTORS):
        return True
    candidate_selectors = (
        "a[href*='/pin/']",
        "table tbody tr",
        "[data-testid*='pin-row']",
        "[data-testid*='top-pin']",
        ".pin-card",
        ".result-row",
    )
    for selector in candidate_selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    body = _body_text(page)
    return any(
        marker in body
        for marker in (
            "top pins",
            "search any keyword or topic to see top pins",
            "keyword or topic",
        )
    )


def _results_page_issue(page: Any) -> str:
    if _page_contains_not_found(page):
        return PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE
    if not _has_results_page_signals(page):
        return PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED
    return ""


def _ensure_valid_results_page(page: Any, seed_keyword: str, artifacts_dir: Path) -> None:
    issue = _results_page_issue(page)
    if not issue:
        return
    label = "invalid_results" if issue == PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE else "search_failed"
    _dump_page_diagnostics(page, artifacts_dir, label)
    if issue == PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE:
        raise ScraperError(
            f"PinClicks results page for seed '{seed_keyword}' resolved to an invalid route or 404 page.",
            reason=issue,
        )
    raise ScraperError(
        f"Could not locate a valid PinClicks results page for seed '{seed_keyword}'.",
        reason=issue,
    )


def _contains_captcha(page: Any) -> bool:
    body_text = _body_text(page)
    if not body_text:
        return False
    return any(marker in body_text for marker in CAPTCHA_MARKERS)


def _wait_for_captcha_solved(page: Any, timeout: float = 300.0) -> None:
    """Poll the page until the CAPTCHA disappears or timeout is reached."""
    deadline = time.time() + timeout
    while _contains_captcha(page):
        if time.time() > deadline:
            raise CaptchaCheckpointRequired(
                f"CAPTCHA was not solved within {int(timeout)}s."
            )
        page.wait_for_timeout(2000)


def _dismiss_pinclicks_popups(page: Any) -> None:
    """Remove Livewire error overlays and dismiss modal popups on PinClicks."""
    try:
        page.evaluate("""() => {
            const lwError = document.getElementById("livewire-error");
            if (lwError) lwError.remove();

            document.querySelectorAll('[wire\\\\:id]').forEach(el => {
                if (el.style && (el.style.position === 'fixed' || el.style.position === 'absolute')) {
                    const text = (el.innerText || '').toLowerCase();
                    if (text.includes('error') || text.includes('went wrong') || text.includes('page expired')) {
                        el.remove();
                    }
                }
            });

            document.querySelectorAll('.modal-backdrop, .overlay, [class*="livewire-error"]')
                .forEach(el => el.remove());

            document.querySelectorAll('button').forEach(btn => {
                const txt = (btn.innerText || '').toLowerCase().trim();
                if (['ok', 'dismiss', 'close', 'got it', 'retry'].includes(txt)) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) btn.click();
                }
            });
        }""")
    except Exception:
        pass


def _wait_for_results_loaded(page: Any, timeout: float = 20.0) -> None:
    """Poll until PinClicks results finish loading."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = _body_text(page)
        if "Loading..." not in body:
            return
        page.wait_for_timeout(1000)


def _first_existing_selector(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return selector
        except Exception:
            continue
    return ""


def _is_authenticated(page: Any, app_base_url: str) -> bool:
    page.goto(app_base_url, wait_until="load", timeout=60_000)
    _sleep_random(NAVIGATION_DELAY_RANGE)
    password_selector = _first_existing_selector(page, PASSWORD_INPUT_SELECTORS)
    if password_selector:
        return False
    login_button_selector = _first_existing_selector(page, LOGIN_BUTTON_SELECTORS)
    if login_button_selector:
        body = _body_text(page)
        if "log in" in body or "sign in" in body:
            return False
    return True


def _has_authenticated_session_cookies(context: Any, app_base_url: str) -> bool:
    try:
        cookies = context.cookies([app_base_url])
    except Exception:
        return False
    required = {"pinclicks_session", "XSRF-TOKEN"}
    found = {str(cookie.get("name", "")).strip() for cookie in cookies if isinstance(cookie, dict)}
    return required.issubset(found)


def _wait_for_manual_login(
    *,
    context: Any,
    app_base_url: str,
    page: Any,
    timeout_seconds: int,
) -> bool:
    deadline = time.time() + max(0, timeout_seconds)
    while time.time() < deadline:
        if _has_authenticated_session_cookies(context, app_base_url):
            try:
                return _is_authenticated(page, app_base_url)
            except Exception:
                return True
        page.wait_for_timeout(2000)
    return False


def _persist_storage_state(context: Any, storage_state_path: Path) -> None:
    """Legacy compatibility no-op for deprecated storage_state flows."""
    return None


def _perform_login(
    *,
    page: Any,
    context: Any,
    app_base_url: str,
    headed: bool,
) -> None:
    username, password = _get_pinclicks_credentials()
    if not username or not password:
        raise ScraperError(
            "PinClicks authentication required but PINCLICKS_USERNAME/PINCLICKS_PASSWORD are missing.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    page.goto(f"{app_base_url.rstrip('/')}/login", wait_until="load", timeout=60_000)
    _sleep_random(NAVIGATION_DELAY_RANGE)
    _dismiss_pinclicks_popups(page)

    username_selector = _first_existing_selector(page, LOGIN_INPUT_SELECTORS)
    password_selector = _first_existing_selector(page, PASSWORD_INPUT_SELECTORS)
    login_button_selector = _first_existing_selector(page, LOGIN_BUTTON_SELECTORS)

    if not username_selector or not password_selector or not login_button_selector:
        raise ScraperError(
            "Could not locate PinClicks login form fields/selectors.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    page.fill(username_selector, username)
    _sleep_random(ACTION_DELAY_RANGE)
    page.fill(password_selector, password)
    _sleep_random(ACTION_DELAY_RANGE)
    page.click(login_button_selector)
    _sleep_random(LOGIN_SETTLE_DELAY_RANGE)

    if _contains_captcha(page):
        if headed:
            print("PinClicks challenge detected. Solve it in the browser window...", file=sys.stderr)
            _wait_for_captcha_solved(page)
        else:
            raise CaptchaCheckpointRequired(
                "PinClicks challenge encountered during headless login; retry in headed mode."
            )

    if not _is_authenticated(page, app_base_url):
        raise ScraperError(
            "PinClicks login failed; session is still unauthenticated.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )


def ensure_pinclicks_brave_session(
    *,
    headed: bool,
    allow_manual_setup: bool,
    setup_timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Validate or bootstrap the PinFlow Brave session for PinClicks."""
    from automating_wf.scrapers.brave_browser import (
        BravePersistentBrowser,
        is_available as brave_available,
        pinflow_profile_dir,
    )

    load_dotenv()
    app_base_url = os.getenv("PINCLICKS_APP_BASE_URL", PINCLICKS_DEFAULT_BASE_URL).strip()
    profile_dir = pinflow_profile_dir() or ""
    if not brave_available():
        raise ScraperError(
            "Brave browser is required for Stage 3. Install Brave and retry PinClicks setup.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
        )

    # --- Early cookie expiration check (avoids unnecessary browser launch) ---
    _brave_health = _check_brave_session_health()
    _json_health = _check_session_health(_safe_storage_state_path())
    # Merge expired cookies from both sources (Brave DB + JSON state file).
    _all_expired = list(
        dict.fromkeys(
            _brave_health.get("expired_critical", [])
            + _json_health.get("expired_critical", [])
        )
    )
    _all_expired_at: dict[str, str] = {**_brave_health.get("expired_at", {})}
    _session_expired = bool(_all_expired)

    if _session_expired and not _has_pinclicks_credentials() and not allow_manual_setup:
        expired_names = ", ".join(sorted(_all_expired))
        date_parts = sorted(_all_expired_at.values()) if _all_expired_at else []
        date_suffix = f" on {date_parts[0]}" if date_parts else ""
        return {
            "authenticated": False,
            "setup_required": True,
            "session_expired": True,
            "expired_cookies": _all_expired,
            "expired_at": _all_expired_at,
            "used_env_login": False,
            "manual_setup_completed": False,
            "message": (
                f"PinClicks session cookies expired{date_suffix} ({expired_names}). "
                "Re-login is required to refresh the session."
            ),
            "profile_dir": profile_dir,
            "browser_mode": PINCLICKS_SCRAPE_SOURCE_BRAVE,
        }

    # --- Fast-success: trust healthy Brave cookies without launching browser ---
    if _brave_health["healthy"]:
        return {
            "authenticated": True,
            "setup_required": False,
            "session_expired": False,
            "expired_cookies": [],
            "expired_at": {},
            "used_env_login": False,
            "manual_setup_completed": False,
            "message": "PinClicks session cookies are valid in Brave profile.",
            "profile_dir": profile_dir,
            "browser_mode": PINCLICKS_SCRAPE_SOURCE_BRAVE,
        }

    if _session_expired:
        expired_names = ", ".join(sorted(_all_expired))
        date_parts = sorted(_all_expired_at.values()) if _all_expired_at else []
        date_suffix = f" on {date_parts[0]}" if date_parts else ""
        setup_message = (
            f"PinClicks session cookies expired{date_suffix} ({expired_names}). "
            "Re-login is required to refresh the session."
        )
    else:
        setup_message = (
            "PinClicks session is not ready in the PinFlow Brave profile. "
            "Run the Stage 3 setup, log into PinClicks in the opened Brave window, then retry."
        )
    result: dict[str, Any] = {
        "authenticated": False,
        "setup_required": True,
        "session_expired": _session_expired,
        "expired_cookies": _all_expired,
        "expired_at": _all_expired_at,
        "used_env_login": False,
        "manual_setup_completed": False,
        "message": setup_message,
        "profile_dir": profile_dir,
        "browser_mode": PINCLICKS_SCRAPE_SOURCE_BRAVE,
    }

    with BravePersistentBrowser(headed=headed) as context:
        page = context.new_page()
        try:
            if _is_authenticated(page, app_base_url):
                result.update(
                    {
                        "authenticated": True,
                        "setup_required": False,
                        "message": "PinClicks session is ready in the PinFlow Brave profile.",
                    }
                )
                return result

            if _has_pinclicks_credentials():
                try:
                    _perform_login(
                        page=page,
                        context=context,
                        app_base_url=app_base_url,
                        headed=headed,
                    )
                    result.update(
                        {
                            "authenticated": True,
                            "setup_required": False,
                            "used_env_login": True,
                            "message": "PinClicks session was refreshed using configured credentials.",
                        }
                    )
                    return result
                except ScraperError:
                    if not allow_manual_setup:
                        raise

            if not allow_manual_setup:
                return result

            login_url = f"{app_base_url.rstrip('/')}/login"
            page.goto(login_url, wait_until="load", timeout=60_000)
            _sleep_random(NAVIGATION_DELAY_RANGE)
            _dismiss_pinclicks_popups(page)
            print(
                "PinClicks setup: log into PinClicks in the opened Brave window. "
                "The session will be reused automatically in future Stage 3 runs.",
                file=sys.stderr,
            )
            if _wait_for_manual_login(
                context=context,
                app_base_url=app_base_url,
                page=page,
                timeout_seconds=setup_timeout_seconds,
            ):
                result.update(
                    {
                        "authenticated": True,
                        "setup_required": False,
                        "manual_setup_completed": True,
                        "message": "PinClicks session setup completed successfully.",
                    }
                )
                return result
            return result
        finally:
            page.close()


def _extract_card_payloads(page: Any) -> list[dict[str, Any]]:
    script = r"""
() => {
  const selectors = [
    "[data-testid*='pin-row']",
    "[data-testid*='top-pin']",
    "table tbody tr",
    ".pin-card",
    ".result-row",
    ".grid > div"
  ];
  const seen = new Set();
  const output = [];
  const metricPattern = /\b\d[\d.,]*\s*[km]?\s*(?:saves?|clicks?|impressions?|views?|comments?|outbound(?:\s*clicks?)?)\b/i;
  const collectMetricFragments = (node) => {
    const fragments = [];
    const seenText = new Set();
    const candidates = node.querySelectorAll("[aria-label], [title], [data-testid], span, small, strong, div, td");
    for (const candidate of candidates) {
      if (!candidate) continue;
      const parts = [
        candidate.getAttribute("aria-label") || "",
        candidate.getAttribute("title") || "",
        candidate.textContent || ""
      ];
      for (const part of parts) {
        const text = (part || "").replace(/\s+/g, " ").trim();
        if (!text || text.length < 2) continue;
        if (!metricPattern.test(text)) continue;
        if (seenText.has(text)) continue;
        seenText.add(text);
        fragments.push(text);
        if (fragments.length >= 12) return fragments;
      }
    }
    return fragments;
  };
  for (const selector of selectors) {
    const nodes = document.querySelectorAll(selector);
    for (const node of nodes) {
      if (!node) continue;
      const text = (node.innerText || "").trim();
      if (!text || text.length < 10) continue;
      const hrefNode =
        node.querySelector("a[href*='/pin/']") ||
        node.querySelector("a[href*='pinterest.com/pin']") ||
        node.querySelector("a[href]");
      const pinUrl = hrefNode ? hrefNode.href : "";
      const titleNode =
        node.querySelector("h1, h2, h3, .title, [data-testid*='title']") ||
        node.querySelector("strong");
      const descriptionNode =
        node.querySelector("p, .description, [data-testid*='description']") ||
        node.querySelector("span");
      const tagNodes = node.querySelectorAll(
        ".tag, [data-testid*='tag'], a[href*='keyword'], a[href*='tag'], a[href*='/topics/']"
      );
      const tags = [];
      for (const item of tagNodes) {
        const value = (item.textContent || "").trim();
        if (!value) continue;
        tags.push(value);
        if (tags.length >= 12) break;
      }
      const key = pinUrl || text.slice(0, 120);
      if (seen.has(key)) continue;
      seen.add(key);
      const metricFragments = collectMetricFragments(node);
      output.push({
        pin_url: pinUrl,
        title: titleNode ? (titleNode.textContent || "").trim() : "",
        description: descriptionNode ? (descriptionNode.textContent || "").trim() : "",
        tags,
        metric_text: text.slice(0, 2500),
        metric_fragments: metricFragments
      });
      if (output.length >= 300) return output;
    }
  }
  if (output.length === 0) {
    const pinLinks = document.querySelectorAll('a[href*="/pin/"]');
    for (const link of pinLinks) {
      const container = link.closest('div, tr, li, article') || link.parentElement;
      if (!container) continue;
      const text = (container.innerText || "").trim();
      if (!text || text.length < 10) continue;
      const pinUrl = link.href || "";
      const key = pinUrl || text.slice(0, 120);
      if (seen.has(key)) continue;
      seen.add(key);
      const titleNode = container.querySelector("h1, h2, h3, .title, strong");
      const descNode = container.querySelector("p, .description, span");
      const metricFragments = collectMetricFragments(container);
      output.push({
        pin_url: pinUrl,
        title: titleNode ? (titleNode.textContent || "").trim() : "",
        description: descNode ? (descNode.textContent || "").trim() : "",
        tags: [],
        metric_text: text.slice(0, 2500),
        metric_fragments: metricFragments
      });
      if (output.length >= 300) return output;
    }
  }
  return output;
}
"""
    payload = page.evaluate(script)
    if not isinstance(payload, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        pin_url = str(item.get("pin_url", "")).strip()
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        tags_raw = item.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(value).strip() for value in tags_raw if str(value).strip()]
        metric_text = str(item.get("metric_text", "")).strip()
        metric_fragments_raw = item.get("metric_fragments")
        metric_fragments = (
            [str(value).strip() for value in metric_fragments_raw if str(value).strip()]
            if isinstance(metric_fragments_raw, list)
            else []
        )
        if not title and not description:
            combined = metric_text.splitlines()
            if combined:
                title = combined[0].strip()
                description = " ".join(combined[1:]).strip()
        if not tags and metric_text:
            tags = [match.group(1) for match in re.finditer(r"#([a-z0-9_]+)", metric_text.lower())]
        if not title and not description:
            continue
        normalized.append(
            {
                "pin_url": pin_url,
                "title": title,
                "description": description,
                "tags": tags[:12],
                "metric_text": metric_text,
                "metric_fragments": metric_fragments[:12],
            }
        )
    return normalized


def _split_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, list):
        return [str(item).strip() for item in raw_tags if str(item).strip()]
    value = str(raw_tags or "").strip()
    if not value:
        return []
    if "#" in value:
        matches = re.findall(r"#([A-Za-z0-9_]+)", value)
        if matches:
            return [match.strip() for match in matches if match.strip()]
    parts = [item.strip() for item in re.split(r"[|,;/]+", value) if item.strip()]
    return parts


def _first_existing_key(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    lowered = {str(key).strip().casefold(): str(key) for key in row.keys()}
    for alias in aliases:
        alias_norm = alias.strip().casefold()
        for key_norm, original in lowered.items():
            if alias_norm in key_norm:
                return original
    return ""


def _engagement_from_export_row(row: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    metric_aliases = {
        "saves": ("save", "saves"),
        "clicks": ("click", "clicks"),
        "impressions": ("impression", "impressions", "view"),
        "comments": ("comment", "comments"),
        "outbound": ("outbound", "outbound clicks"),
    }
    for metric_name, aliases in metric_aliases.items():
        key = _first_existing_key(row, aliases)
        if key:
            metrics[metric_name] = coerce_numeric(row.get(key))
    if not metrics:
        row_text = " ".join(str(item) for item in row.values())
        metrics = _extract_engagement(row_text)
    metrics["score_total"] = float(sum(value for key, value in metrics.items() if key != "score_total"))
    return metrics


def _records_from_export_rows(
    *,
    seed_keyword: str,
    rows: list[dict[str, Any]],
    source_file: Path,
    source_url: str,
    max_records: int,
) -> tuple[list[PinRecord], dict[str, Any], list[dict[str, Any]]]:
    normalized_rows: list[dict[str, Any]] = []
    pin_url_aliases = ("pin url", "url", "link", "pin link")
    title_aliases = ("pin title", "title", "headline")
    description_aliases = ("description", "pin description", "desc")
    tags_aliases = ("tags", "keywords", "tag")

    for row in rows:
        if not isinstance(row, dict):
            continue
        title_key = _first_existing_key(row, title_aliases)
        description_key = _first_existing_key(row, description_aliases)
        tags_key = _first_existing_key(row, tags_aliases)
        pin_url_key = _first_existing_key(row, pin_url_aliases)

        title = str(row.get(title_key, "")).strip() if title_key else ""
        description = str(row.get(description_key, "")).strip() if description_key else ""
        tags = _split_tags(row.get(tags_key, "")) if tags_key else []
        pin_url = str(row.get(pin_url_key, "")).strip() if pin_url_key else ""

        if not title and not description and not pin_url:
            continue

        normalized_rows.append(
            {
                "pin_url": pin_url,
                "pin_id": _extract_pin_id(pin_url),
                "title": title,
                "description": description,
                "tags": tags[:12],
                "engagement": _engagement_from_export_row(row),
                "metric_text": " ".join(str(item) for item in row.values()),
                "source_url": source_url,
                "source_file": str(source_file),
            }
        )

    return _normalize_record_candidates(
        seed_keyword=seed_keyword,
        items=normalized_rows,
        max_records=max_records,
        scrape_mode="export",
    )


def _records_from_payload(
    seed_keyword: str,
    payload: list[dict[str, Any]],
    max_records: int,
) -> tuple[list[PinRecord], dict[str, Any], list[dict[str, Any]]]:
    return _normalize_record_candidates(
        seed_keyword=seed_keyword,
        items=payload,
        max_records=max_records,
        scrape_mode="visible_rows",
    )


def _end_of_results_visible(page: Any) -> bool:
    body = _body_text(page)
    return "no more results" in body or "end of results" in body


def _collect_top_pins(
    *,
    page: Any,
    seed_keyword: str,
    max_records: int,
    artifacts_dir: Path,
) -> tuple[list[PinRecord], dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    unique_payload: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    duplicate_scrolls = 0
    previous_total = 0
    diagnostics = {
        "scrape_mode": "visible_rows",
        "raw_item_count": 0,
        "rejected_item_count": 0,
        "kept_item_count": 0,
        "final_record_count": 0,
        "engagement_available": False,
    }
    rejected_samples: list[dict[str, Any]] = []

    def _persist(records: list[PinRecord]) -> tuple[list[PinRecord], dict[str, Any]]:
        _write_json(artifacts_dir / "scraped_raw.json", snapshots)
        _write_json(artifacts_dir / "scraped_normalized.json", [record.to_dict() for record in records])
        if rejected_samples:
            _write_json(artifacts_dir / "scraped_rejected.json", rejected_samples)
        return records, diagnostics

    for _ in range(MAX_SCROLL_ATTEMPTS):
        payload = _extract_card_payloads(page)
        snapshots.extend(payload)

        for item in payload:
            key = str(item.get("pin_url", "")).strip() or (
                f"{item.get('title', '')}|{item.get('description', '')}"
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_payload.append(item)

        records, diagnostics, rejected_samples = _records_from_payload(
            seed_keyword=seed_keyword,
            payload=unique_payload,
            max_records=max_records,
        )
        if len(records) >= max_records:
            return _persist(records)

        if len(records) == previous_total:
            duplicate_scrolls += 1
        else:
            duplicate_scrolls = 0
        previous_total = len(records)

        if duplicate_scrolls >= MAX_DUPLICATE_SCROLLS or _end_of_results_visible(page):
            return _persist(records)

        page.mouse.wheel(0, random.randint(1300, 2200))
        _sleep_random(ACTION_DELAY_RANGE)

    records, diagnostics, rejected_samples = _records_from_payload(
        seed_keyword=seed_keyword,
        payload=unique_payload,
        max_records=max_records,
    )
    return _persist(records)


def _keyword_in_pins_search(page: Any, seed_keyword: str) -> bool:
    expected = seed_keyword.strip().casefold()
    if not expected:
        return False
    for selector in PINCLICKS_PINS_SEARCH_INPUT_SELECTORS:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 4)
            for index in range(count):
                field = locator.nth(index)
                if not field.is_visible(timeout=400):
                    continue
                value = str(field.input_value(timeout=800)).strip().casefold()
                if expected in value:
                    return True
        except Exception:
            continue
    return expected in _body_text(page)


def _attempt_keyword_targeting(page: Any, seed_keyword: str) -> str:
    saw_search_input = False
    saw_invalid_results_page = False
    for attempt in range(1, 4):
        selector = _first_existing_selector(page, PINCLICKS_PINS_SEARCH_INPUT_SELECTORS)
        if selector:
            saw_search_input = True
            try:
                input_locator = page.locator(selector).first
                input_locator.click(click_count=3, timeout=2500)
                input_locator.fill(seed_keyword, timeout=3500)
                _sleep_random((0.2, 0.6))
                page.keyboard.press("Enter")
                _sleep_random(NAVIGATION_DELAY_RANGE)
                _wait_for_results_loaded(page)
                _dismiss_pinclicks_popups(page)
                if _page_contains_not_found(page):
                    saw_invalid_results_page = True
                    break
                if _keyword_in_pins_search(page, seed_keyword):
                    return "ok"
                if _has_results_page_signals(page):
                    body = _body_text(page)
                    if seed_keyword.strip().casefold() in body:
                        return "ok"
            except Exception:
                pass

        try:
            filled = page.evaluate(
                """(keyword) => {
                  const visible = (node) => {
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(node);
                    return style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                  const hints = [
                    'search any keyword or topic to see top pins',
                    'keyword or topic'
                  ];
                  const inputs = Array.from(document.querySelectorAll('input'));
                  for (const node of inputs) {
                    if (!visible(node)) continue;
                    const label = normalize((node.getAttribute('placeholder') || '') + ' ' + (node.getAttribute('aria-label') || ''));
                    if (!label) continue;
                    if (!hints.some((hint) => label.includes(hint))) continue;
                    node.focus();
                    node.value = keyword;
                    node.dispatchEvent(new Event('input', { bubbles: true }));
                    node.dispatchEvent(new Event('change', { bubbles: true }));
                    node.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                    return true;
                  }
                  return false;
                }""",
                seed_keyword,
            )
            if filled:
                _sleep_random(NAVIGATION_DELAY_RANGE)
                if _page_contains_not_found(page):
                    saw_invalid_results_page = True
                    break
                if _keyword_in_pins_search(page, seed_keyword):
                    return "ok"
        except Exception:
            pass

        if attempt < 3:
            _sleep_random((0.4, 1.0))

    if saw_invalid_results_page:
        return PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE
    if saw_search_input:
        return PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED
    return PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND


def _navigate_direct_top_pins_status(page: Any, seed_keyword: str) -> str:
    try:
        url = build_top_pins_url(seed_keyword)
    except Exception:
        return PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED
    try:
        page.goto(url, wait_until="load")
        _sleep_random(NAVIGATION_DELAY_RANGE)
        _dismiss_pinclicks_popups(page)
        _wait_for_results_loaded(page)
    except Exception:
        return PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED
    issue = _results_page_issue(page)
    if issue:
        return issue
    expected = seed_keyword.strip().casefold()
    if not expected:
        return PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED
    body = _body_text(page)
    if _keyword_in_pins_search(page, seed_keyword) or expected in body:
        return "ok"
    return PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED


def _navigate_direct_top_pins(page: Any, seed_keyword: str) -> bool:
    return _navigate_direct_top_pins_status(page, seed_keyword) == "ok"


def _search_keyword_on_pins_page(page: Any, seed_keyword: str, artifacts_dir: Path | None = None) -> None:
    search_status = _attempt_keyword_targeting(page, seed_keyword)
    if search_status == "ok":
        return

    direct_status = _navigate_direct_top_pins_status(page, seed_keyword)
    if direct_status == "ok":
        return

    if artifacts_dir:
        label = (
            "invalid_results"
            if PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE in {search_status, direct_status}
            else "search_failed"
        )
        _dump_page_diagnostics(page, artifacts_dir, label)

    if PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE in {search_status, direct_status}:
        raise ScraperError(
            f"PinClicks results page for seed '{seed_keyword}' resolved to an invalid route or 404 page.",
            reason=PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE,
        )
    raise ScraperError(
        f"Could not locate a valid PinClicks results page for seed '{seed_keyword}'.",
        reason=PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
    )


def _download_export_file(page: Any, artifacts_dir: Path, seed_keyword: str) -> Path:
    _ensure_dir(artifacts_dir)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", seed_keyword.lower()).strip("_") or "keyword"
    default_file = artifacts_dir / f"top_pins_export_{slug}.csv"

    for selector in EXPORT_BUTTON_SELECTORS:
        try:
            button = page.locator(selector)
            if button.count() <= 0:
                continue
            with page.expect_download(timeout=EXPORT_DOWNLOAD_TIMEOUT_MS) as download_info:
                button.first.click(timeout=4000)
            download = download_info.value
            suggested = download.suggested_filename or default_file.name
            save_path = artifacts_dir / suggested
            download.save_as(str(save_path))
            return save_path
        except Exception:
            continue
    raise ScraperError(
        f"Could not trigger PinClicks export download for '{seed_keyword}'.",
        reason=PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
    )


def _dump_page_diagnostics(page: Any, artifacts_dir: Path, label: str) -> None:
    """Save page HTML and screenshot for post-mortem selector debugging."""
    _ensure_dir(artifacts_dir)
    prefix = label or "diag"
    try:
        html = page.content()
        (artifacts_dir / f"{prefix}_page.html").write_text(html, encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(artifacts_dir / f"{prefix}_screenshot.png"), full_page=True)
    except Exception:
        pass


def _camoufox_kwargs(*, headed: bool, storage_state_path: Path) -> dict[str, Any]:
    """Build keyword arguments for ``Camoufox(...)``."""
    kwargs: dict[str, Any] = {
        "headless": not headed,
        "humanize": True,
        "geoip": True,
    }
    return kwargs


def _run_scrape_once(
    *,
    seed_keyword: str,
    blog_suffix: str,
    artifacts_dir: Path,
    headed: bool,
    max_records: int,
) -> SeedScrapeResult:
    try:
        from camoufox.sync_api import Camoufox
    except ImportError as exc:
        raise ScraperError(
            "camoufox is required for PinClicks scraping. Install dependencies first."
        ) from exc

    import nest_asyncio
    nest_asyncio.apply()

    load_dotenv()
    app_base_url = os.getenv("PINCLICKS_APP_BASE_URL", PINCLICKS_DEFAULT_BASE_URL).strip()
    source_url = _build_pins_url(app_base_url)
    storage_state_path = _safe_storage_state_path()

    kwargs = _camoufox_kwargs(headed=headed, storage_state_path=storage_state_path)
    with Camoufox(**kwargs) as browser_or_context:
        context, owns_context = _ensure_browser_context(browser_or_context)
        page = context.new_page()
        try:
            if not _is_authenticated(page, app_base_url):
                _perform_login(
                    page=page,
                    context=context,
                    app_base_url=app_base_url,
                    headed=headed,
                )

            page.goto(source_url, wait_until="load", timeout=60_000)
            _sleep_random(NAVIGATION_DELAY_RANGE)
            _search_keyword_on_pins_page(page, seed_keyword, artifacts_dir=artifacts_dir)
            _ensure_valid_results_page(page, seed_keyword, artifacts_dir)

            if _contains_captcha(page):
                if headed:
                    print("Captcha detected on PinClicks pins page. Solve it in the browser window...", file=sys.stderr)
                    _wait_for_captcha_solved(page)
                else:
                    raise CaptchaCheckpointRequired(
                        "Captcha encountered on PinClicks pins page; retrying in headed mode."
                    )

            # Primary path: download and parse export.
            export_file = None
            parsed_export_records: list[PinRecord] = []
            try:
                export_file = _download_export_file(page, artifacts_dir=artifacts_dir, seed_keyword=seed_keyword)
                rows = parse_tabular_export(export_file)
                _write_json(artifacts_dir / "export_rows_raw.json", rows)
                parsed_export_records, export_diagnostics, export_rejected = _records_from_export_rows(
                    seed_keyword=seed_keyword,
                    rows=rows,
                    source_file=export_file,
                    source_url=source_url,
                    max_records=max_records,
                )
                _write_json(
                    artifacts_dir / "export_rows_normalized.json",
                    [record.to_dict() for record in parsed_export_records],
                )
                if export_rejected:
                    _write_json(artifacts_dir / "export_rows_rejected.json", export_rejected)
            except Exception:
                parsed_export_records = []
                export_diagnostics = {}

            if parsed_export_records:
                _persist_storage_state(context, storage_state_path)
                return SeedScrapeResult(
                    blog_suffix=blog_suffix,
                    seed_keyword=seed_keyword,
                    source_url=source_url,
                    records=parsed_export_records,
                    source_file=str(export_file) if export_file else "",
                    scraped_at=_now_utc_iso(),
                    scrape_mode="export",
                    diagnostics=export_diagnostics,
                )

            # Fallback path: scrape visible rows.
            records, scrape_diagnostics = _collect_top_pins(
                page=page,
                seed_keyword=seed_keyword,
                max_records=max_records,
                artifacts_dir=artifacts_dir,
            )
            if not records:
                _dump_page_diagnostics(page, artifacts_dir, "no_records")
                raise ScraperError(
                    f"No pin records were extracted for seed '{seed_keyword}'. "
                    "Export parse and on-page selectors both failed.",
                    reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
                )

            _persist_storage_state(context, storage_state_path)
            return SeedScrapeResult(
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                source_url=source_url,
                records=records,
                source_file=str(export_file) if export_file else "",
                scraped_at=_now_utc_iso(),
                scrape_mode="visible_rows",
                diagnostics=scrape_diagnostics,
            )
        finally:
            if owns_context and hasattr(context, "close"):
                context.close()


def _get_browser_mode() -> str:
    """Return the configured PinClicks browser mode."""
    load_dotenv()
    mode = os.getenv(PINCLICKS_BROWSER_MODE_ENV, "").strip().lower()
    if mode in (PINCLICKS_BROWSER_MODE_BRAVE, PINCLICKS_BROWSER_MODE_CAMOUFOX):
        return mode
    return PINCLICKS_BROWSER_MODE_DEFAULT


def _scrape_with_brave(
    *,
    seed_keyword: str,
    blog_suffix: str,
    artifacts_dir: Path,
    headed: bool,
    max_records: int,
) -> SeedScrapeResult:
    """Scrape PinClicks using real Brave browser with persistent profile."""
    from automating_wf.scrapers.brave_browser import BravePersistentBrowser

    load_dotenv()
    app_base_url = os.getenv("PINCLICKS_APP_BASE_URL", PINCLICKS_DEFAULT_BASE_URL).strip()
    source_url = _build_pins_url(app_base_url)

    session_status = ensure_pinclicks_brave_session(
        headed=headed,
        allow_manual_setup=False,
    )
    if not session_status.get("authenticated", False):
        raise ScraperError(
            str(session_status.get("message", "")).strip() or "PinClicks Stage 3 setup is required.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
        )

    with BravePersistentBrowser(headed=headed) as context:
        page = context.new_page()
        try:
            page.goto(source_url, wait_until="load", timeout=60_000)
            _sleep_random(NAVIGATION_DELAY_RANGE)
            _dismiss_pinclicks_popups(page)
            _search_keyword_on_pins_page(page, seed_keyword, artifacts_dir=artifacts_dir)
            _ensure_valid_results_page(page, seed_keyword, artifacts_dir)

            if _contains_captcha(page):
                if headed:
                    print("Captcha detected on PinClicks pins page. Solve it in the browser window...", file=sys.stderr)
                    _wait_for_captcha_solved(page)
                else:
                    raise CaptchaCheckpointRequired(
                        "Captcha encountered on PinClicks pins page; retrying in headed mode."
                    )

            # Primary path: download and parse export.
            export_file = None
            parsed_export_records: list[PinRecord] = []
            try:
                export_file = _download_export_file(
                    page, artifacts_dir=artifacts_dir, seed_keyword=seed_keyword
                )
                rows = parse_tabular_export(export_file)
                _write_json(artifacts_dir / "export_rows_raw.json", rows)
                parsed_export_records, export_diagnostics, export_rejected = _records_from_export_rows(
                    seed_keyword=seed_keyword,
                    rows=rows,
                    source_file=export_file,
                    source_url=source_url,
                    max_records=max_records,
                )
                _write_json(
                    artifacts_dir / "export_rows_normalized.json",
                    [record.to_dict() for record in parsed_export_records],
                )
                if export_rejected:
                    _write_json(artifacts_dir / "export_rows_rejected.json", export_rejected)
            except Exception:
                parsed_export_records = []
                export_diagnostics = {}

            if parsed_export_records:
                return SeedScrapeResult(
                    blog_suffix=blog_suffix,
                    seed_keyword=seed_keyword,
                    source_url=source_url,
                    records=parsed_export_records,
                    source_file=str(export_file) if export_file else "",
                    scraped_at=_now_utc_iso(),
                    scrape_mode="export",
                    diagnostics=export_diagnostics,
                )

            # Fallback path: scrape visible rows.
            records, scrape_diagnostics = _collect_top_pins(
                page=page,
                seed_keyword=seed_keyword,
                max_records=max_records,
                artifacts_dir=artifacts_dir,
            )
            if not records:
                _dump_page_diagnostics(page, artifacts_dir, "brave_no_records")
                raise ScraperError(
                    f"No pin records extracted for seed '{seed_keyword}' via Brave browser.",
                    reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
                )

            return SeedScrapeResult(
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                source_url=source_url,
                records=records,
                source_file=str(export_file) if export_file else "",
                scraped_at=_now_utc_iso(),
                scrape_mode="visible_rows",
                diagnostics=scrape_diagnostics,
            )
        finally:
            page.close()


def _scrape_with_cloudflare(
    *,
    seed_keyword: str,
    blog_suffix: str,
    artifacts_dir: Path,
    max_records: int,
    max_attempts: int,
) -> SeedScrapeResult:
    """Scrape PinClicks via Cloudflare Browser Rendering API (existing fallback)."""
    storage_state_path = _safe_storage_state_path()
    health = _check_session_health(storage_state_path)
    if not health["healthy"]:
        raise ScraperError(
            "PinClicks authentication is unavailable or expired; "
            "refresh PINCLICKS_STORAGE_STATE_PATH before Stage 3.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            start_url = build_top_pins_url(seed_keyword)
            cookie_header, xsrf_token = _cookie_header_for_host(
                storage_state_path,
                urlparse(start_url).netloc.strip() or "app.pinclicks.com",
            )
            request_payload = _build_cloudflare_crawl_payload(
                start_url=start_url,
                cookie_header=cookie_header,
                xsrf_token=xsrf_token,
            )
            _write_json(artifacts_dir / "cloudflare_crawl_request.json", request_payload)
            create_payload = _cloudflare_api_request(
                method="POST", path="/crawl", payload=request_payload,
            )
            _write_json(artifacts_dir / "cloudflare_crawl_create.json", create_payload)
            job_id = _cloudflare_job_id(create_payload)
            final_payload = _cloudflare_poll_job(job_id, artifacts_dir=artifacts_dir)
            _write_json(artifacts_dir / "cloudflare_crawl_response.json", final_payload)
            records = _records_from_crawl_payload(
                seed_keyword=seed_keyword,
                payload=final_payload,
                max_records=max_records,
            )
            _write_json(
                artifacts_dir / "cloudflare_records_normalized.json",
                [record.to_dict() for record in records],
            )
            if not records:
                response_text = json.dumps(final_payload, ensure_ascii=False)
                reason = _classify_scrape_error(RuntimeError(response_text))
                if reason == PINCLICKS_SKIP_REASON_UNKNOWN:
                    reason = PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED
                raise ScraperError(
                    f"No pin records extracted from Cloudflare crawl for seed '{seed_keyword}'.",
                    reason=reason,
                )
            result = SeedScrapeResult(
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                source_url=start_url,
                records=records,
                source_file=str(artifacts_dir / "cloudflare_crawl_response.json"),
                scraped_at=_now_utc_iso(),
            )
            _write_json(artifacts_dir / "seed_scrape_result.json", result.to_dict())
            return result
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                _sleep_random((1.0, 2.2))
            continue

    raise ScraperError(
        f"Failed to scrape seed '{seed_keyword}' after {max_attempts} Cloudflare attempts: {last_error}",
        reason=_classify_scrape_error(last_error if isinstance(last_error, Exception) else Exception()),
        attempts=max_attempts,
        used_headed_fallback=False,
    )


def scrape_seed(
    *,
    seed_keyword: str,
    blog_suffix: str,
    run_dir: Path,
    headed: bool = False,
    max_records: int = TOP_PIN_TARGET,
    max_attempts: int = SCRAPE_RETRY_ATTEMPTS,
) -> SeedScrapeResult:
    _ensure_dir(run_dir)
    seed_slug = re.sub(r"[^A-Za-z0-9]+", "_", seed_keyword.strip().lower()).strip("_") or "seed"
    artifacts_dir = run_dir / seed_slug
    _ensure_dir(artifacts_dir)

    from automating_wf.scrapers.brave_browser import is_available as brave_available

    # ── Brave persistent browser (primary) ──────────────────────────────
    if not brave_available():
        raise ScraperError(
            "Brave browser is required for Stage 3. Install Brave and retry PinClicks setup.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
        )

    last_brave_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = _scrape_with_brave(
                seed_keyword=seed_keyword,
                blog_suffix=blog_suffix,
                artifacts_dir=artifacts_dir,
                headed=headed,
                max_records=max_records,
            )
            _write_json(artifacts_dir / "seed_scrape_result.json", result.to_dict())
            return result
        except CaptchaCheckpointRequired:
            if not headed:
                headed = True
                last_brave_error = None
                continue
            raise
        except Exception as exc:
            last_brave_error = exc
            if isinstance(exc, ScraperError) and exc.reason == PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED:
                raise
            if not _should_retry_brave_error(exc):
                break
            if attempt < max_attempts:
                _sleep_random((1.0, 2.2))
            continue

    # ── Cloudflare Browser Rendering API (fallback) ─────────────────────
    try:
        result = _scrape_with_cloudflare(
            seed_keyword=seed_keyword,
            blog_suffix=blog_suffix,
            artifacts_dir=artifacts_dir,
            max_records=max_records,
            max_attempts=max_attempts,
        )
        _write_json(artifacts_dir / "seed_scrape_result.json", result.to_dict())
        return result
    except Exception as cloudflare_error:
        raise ScraperError(
            (
                f"Failed to scrape seed '{seed_keyword}' after {max_attempts} Brave attempts "
                f"and Cloudflare fallback: brave={last_brave_error}; cloudflare={cloudflare_error}"
            ),
            reason=_classify_scrape_error(
                cloudflare_error if isinstance(cloudflare_error, Exception) else Exception()
            ),
            attempts=max_attempts,
            used_headed_fallback=False,
        ) from cloudflare_error
