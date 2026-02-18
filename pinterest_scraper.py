from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

from pinterest_file_parser import coerce_numeric, parse_tabular_export
from pinterest_models import PinRecord, PinClicksExportRecord, SeedScrapeResult


PINCLICKS_DEFAULT_BASE_URL = "https://app.pinclicks.com"
TOP_PIN_TARGET = 25
MAX_SCROLL_ATTEMPTS = 36
MAX_DUPLICATE_SCROLLS = 5
SCRAPE_RETRY_ATTEMPTS = 3
NAVIGATION_DELAY_RANGE = (2.0, 5.0)
ACTION_DELAY_RANGE = (0.8, 1.8)

DEFAULT_VIEWPORTS = (
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900},
    {"width": 1920, "height": 1080},
)

DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

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
)

PASSWORD_INPUT_SELECTORS = (
    "input[name='password']",
    "input[type='password']",
    "input[autocomplete='current-password']",
)

LOGIN_BUTTON_SELECTORS = (
    "button[type='submit']",
    "button:has-text('Log in')",
    "button:has-text('Sign in')",
    "[role='button']:has-text('Log in')",
    "[role='button']:has-text('Sign in')",
)

EXPORT_BUTTON_SELECTORS = (
    "button:has-text('Export')",
    "button:has-text('Download')",
    "[role='button']:has-text('Export')",
    "[aria-label*='Export']",
    "[data-testid*='export']",
)

PINCLICKS_PINS_SEARCH_INPUT_SELECTORS = (
    "input[placeholder*='search any keyword or topic to see top pins' i]",
    "input[aria-label*='search any keyword or topic to see top pins' i]",
    "input[placeholder*='keyword or topic' i]",
    "input[aria-label*='keyword or topic' i]",
)

PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND = "search_input_not_found"
PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED = "search_input_rejected"
PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED = "direct_top_pins_navigation_failed"
PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED = "export_download_failed"
PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED = "no_records_extracted"
PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED = "captcha_checkpoint_required"
PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED = "authentication_failed"
PINCLICKS_SKIP_REASON_UNKNOWN = "unknown_scrape_failure"

PINCLICKS_SKIP_REASONS = {
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND,
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
    PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
    PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
    PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
    PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
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
    if "export" in text and ("download" in text or "trigger" in text):
        return PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED
    if "captcha" in text or "challenge" in text or "verify you are human" in text:
        return PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED
    if "login" in text or "unauthenticated" in text or "authentication" in text:
        return PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED
    if "no pin records" in text or "no records" in text:
        return PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED
    return PINCLICKS_SKIP_REASON_UNKNOWN


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
        "impressions": r"(\d[\d.,]*[km]?)\s*impressions?",
        "comments": r"(\d[\d.,]*[km]?)\s*comments?",
        "outbound": r"(\d[\d.,]*[km]?)\s*outbound",
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


def _contains_captcha(page: Any) -> bool:
    body_text = _body_text(page)
    if not body_text:
        return False
    return any(marker in body_text for marker in CAPTCHA_MARKERS)


def _first_existing_selector(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return selector
        except Exception:
            continue
    return ""


def _is_authenticated(page: Any, app_base_url: str) -> bool:
    page.goto(app_base_url, wait_until="domcontentloaded")
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


def _persist_storage_state(context: Any, storage_state_path: Path) -> None:
    _ensure_dir(storage_state_path.parent)
    context.storage_state(path=str(storage_state_path))


def _perform_login(
    *,
    page: Any,
    context: Any,
    app_base_url: str,
    storage_state_path: Path,
    headed: bool,
) -> None:
    username, password = _get_pinclicks_credentials()
    if not username or not password:
        raise ScraperError(
            "PinClicks authentication required but PINCLICKS_USERNAME/PINCLICKS_PASSWORD are missing.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    page.goto(f"{app_base_url.rstrip('/')}/login", wait_until="domcontentloaded")
    _sleep_random(NAVIGATION_DELAY_RANGE)

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
    _sleep_random(NAVIGATION_DELAY_RANGE)

    if _contains_captcha(page):
        if headed:
            print(
                "PinClicks challenge detected. Solve it in browser and press Enter after completion."
            )
            try:
                input()
            except EOFError:
                pass
        else:
            raise CaptchaCheckpointRequired(
                "PinClicks challenge encountered during headless login; retry in headed mode."
            )

    if not _is_authenticated(page, app_base_url):
        raise ScraperError(
            "PinClicks login failed; session is still unauthenticated.",
            reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
        )

    _persist_storage_state(context, storage_state_path)


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
      output.push({
        pin_url: pinUrl,
        title: titleNode ? (titleNode.textContent || "").trim() : "",
        description: descriptionNode ? (descriptionNode.textContent || "").trim() : "",
        tags,
        metric_text: text.slice(0, 2500)
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
) -> list[PinRecord]:
    parsed_records: list[PinClicksExportRecord] = []
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

        parsed_records.append(
            PinClicksExportRecord(
                keyword=seed_keyword,
                title=title,
                description=description,
                tags=tags[:12],
                pin_url=pin_url,
                pin_id=_extract_pin_id(pin_url),
                engagement=_engagement_from_export_row(row),
                source_url=source_url,
                source_file=str(source_file),
            )
        )

    normalized: list[PinRecord] = []
    seen: set[str] = set()
    scraped_at = _now_utc_iso()
    for parsed in parsed_records:
        dedupe_key = parsed.pin_id or parsed.pin_url or f"{parsed.title}|{parsed.description}"
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            PinRecord(
                seed_keyword=seed_keyword,
                rank=len(normalized) + 1,
                pin_url=parsed.pin_url,
                pin_id=parsed.pin_id,
                title=parsed.title,
                description=parsed.description,
                tags=parsed.tags,
                engagement=parsed.engagement,
                scraped_at=scraped_at,
            )
        )
        if len(normalized) >= max_records:
            break
    return normalized


def _records_from_payload(
    seed_keyword: str,
    payload: list[dict[str, Any]],
    max_records: int,
) -> list[PinRecord]:
    records: list[PinRecord] = []
    seen_keys: set[str] = set()
    now = _now_utc_iso()
    for item in payload:
        pin_url = str(item.get("pin_url", "")).strip()
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
        metric_text = str(item.get("metric_text", "")).strip()
        pin_id = _extract_pin_id(pin_url)
        dedupe_key = pin_id or pin_url or f"{title}|{description}"
        if not dedupe_key or dedupe_key in seen_keys:
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
                tags=tags[:12],
                engagement=_extract_engagement(metric_text),
                scraped_at=now,
            )
        )
        if len(records) >= max_records:
            break
    return records


def _end_of_results_visible(page: Any) -> bool:
    body = _body_text(page)
    return "no more results" in body or "end of results" in body


def _collect_top_pins(
    *,
    page: Any,
    seed_keyword: str,
    max_records: int,
    artifacts_dir: Path,
) -> list[PinRecord]:
    snapshots: list[dict[str, Any]] = []
    unique_payload: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    duplicate_scrolls = 0
    previous_total = 0

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

        records = _records_from_payload(seed_keyword=seed_keyword, payload=unique_payload, max_records=max_records)
        if len(records) >= max_records:
            _write_json(artifacts_dir / "scraped_raw.json", snapshots)
            _write_json(artifacts_dir / "scraped_normalized.json", [record.to_dict() for record in records])
            return records

        if len(records) == previous_total:
            duplicate_scrolls += 1
        else:
            duplicate_scrolls = 0
        previous_total = len(records)

        if duplicate_scrolls >= MAX_DUPLICATE_SCROLLS or _end_of_results_visible(page):
            _write_json(artifacts_dir / "scraped_raw.json", snapshots)
            _write_json(artifacts_dir / "scraped_normalized.json", [record.to_dict() for record in records])
            return records

        page.mouse.wheel(0, random.randint(1300, 2200))
        _sleep_random(ACTION_DELAY_RANGE)

    records = _records_from_payload(seed_keyword=seed_keyword, payload=unique_payload, max_records=max_records)
    _write_json(artifacts_dir / "scraped_raw.json", snapshots)
    _write_json(artifacts_dir / "scraped_normalized.json", [record.to_dict() for record in records])
    return records


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
    for attempt in range(1, 4):
        selector = _first_existing_selector(page, PINCLICKS_PINS_SEARCH_INPUT_SELECTORS)
        if selector:
            saw_search_input = True
            try:
                input_locator = page.locator(selector).first
                input_locator.click(timeout=2500)
                input_locator.fill(seed_keyword, timeout=3500)
                _sleep_random((0.2, 0.6))
                page.keyboard.press("Enter")
                _sleep_random(NAVIGATION_DELAY_RANGE)
                if _keyword_in_pins_search(page, seed_keyword):
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
                if _keyword_in_pins_search(page, seed_keyword):
                    return "ok"
        except Exception:
            pass

        if attempt < 3:
            _sleep_random((0.4, 1.0))

    if saw_search_input:
        return PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED
    return PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND


def _navigate_direct_top_pins(page: Any, seed_keyword: str) -> bool:
    try:
        url = build_top_pins_url(seed_keyword)
    except Exception:
        return False
    try:
        page.goto(url, wait_until="domcontentloaded")
        _sleep_random(NAVIGATION_DELAY_RANGE)
    except Exception:
        return False
    expected = seed_keyword.strip().casefold()
    if not expected:
        return False
    body = _body_text(page)
    return expected in body or quote_plus(seed_keyword).casefold() in str(page.url).casefold()


def _search_keyword_on_pins_page(page: Any, seed_keyword: str) -> None:
    search_status = _attempt_keyword_targeting(page, seed_keyword)
    if search_status == "ok":
        return
    if _navigate_direct_top_pins(page, seed_keyword):
        return

    reason = (
        PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED
        if search_status in {
            PINCLICKS_SKIP_REASON_SEARCH_INPUT_NOT_FOUND,
            PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        }
        else PINCLICKS_SKIP_REASON_UNKNOWN
    )
    raise ScraperError(
        f"Could not enter keyword '{seed_keyword}' in PinClicks /pins search box.",
        reason=reason,
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
            with page.expect_download(timeout=12000) as download_info:
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


def _build_context(playwright: Any, *, headed: bool, storage_state_path: Path) -> tuple[Any, Any]:
    browser = playwright.chromium.launch(
        headless=not headed,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context_kwargs: dict[str, Any] = {
        "viewport": dict(random.choice(DEFAULT_VIEWPORTS)),
        "user_agent": random.choice(DEFAULT_USER_AGENTS),
        "accept_downloads": True,
    }
    if storage_state_path.exists():
        context_kwargs["storage_state"] = str(storage_state_path)
    context = browser.new_context(**context_kwargs)
    return browser, context


def _run_scrape_once(
    *,
    seed_keyword: str,
    blog_suffix: str,
    artifacts_dir: Path,
    headed: bool,
    max_records: int,
) -> SeedScrapeResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ScraperError(
            "playwright is required for PinClicks scraping. Install dependencies first."
        ) from exc

    load_dotenv()
    app_base_url = os.getenv("PINCLICKS_APP_BASE_URL", PINCLICKS_DEFAULT_BASE_URL).strip()
    source_url = _build_pins_url(app_base_url)
    storage_state_path = _safe_storage_state_path()

    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            browser, context = _build_context(
                playwright=playwright,
                headed=headed,
                storage_state_path=storage_state_path,
            )
            page = context.new_page()

            if not _is_authenticated(page, app_base_url):
                _perform_login(
                    page=page,
                    context=context,
                    app_base_url=app_base_url,
                    storage_state_path=storage_state_path,
                    headed=headed,
                )

            page.goto(source_url, wait_until="domcontentloaded")
            _sleep_random(NAVIGATION_DELAY_RANGE)
            _search_keyword_on_pins_page(page, seed_keyword)

            if _contains_captcha(page):
                if headed:
                    print(
                        "Captcha checkpoint detected on PinClicks pins page. Solve it in the browser and press Enter."
                    )
                    try:
                        input()
                    except EOFError:
                        pass
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
                parsed_export_records = _records_from_export_rows(
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
            except Exception:
                parsed_export_records = []

            if parsed_export_records:
                return SeedScrapeResult(
                    blog_suffix=blog_suffix,
                    seed_keyword=seed_keyword,
                    source_url=source_url,
                    records=parsed_export_records,
                    source_file=str(export_file) if export_file else "",
                    scraped_at=_now_utc_iso(),
                )

            # Fallback path: scrape visible rows.
            records = _collect_top_pins(
                page=page,
                seed_keyword=seed_keyword,
                max_records=max_records,
                artifacts_dir=artifacts_dir,
            )
            if not records:
                raise ScraperError(
                    f"No pin records were extracted for seed '{seed_keyword}'. "
                    "Export parse and on-page selectors both failed.",
                    reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
                )

            return SeedScrapeResult(
                blog_suffix=blog_suffix,
                seed_keyword=seed_keyword,
                source_url=source_url,
                records=records,
                source_file=str(export_file) if export_file else "",
                scraped_at=_now_utc_iso(),
            )
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()


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

    last_error: Exception | None = None
    used_headed_fallback = False
    for attempt in range(1, max_attempts + 1):
        try:
            result = _run_scrape_once(
                seed_keyword=seed_keyword,
                blog_suffix=blog_suffix,
                artifacts_dir=artifacts_dir,
                headed=headed,
                max_records=max_records,
            )
            _write_json(artifacts_dir / "seed_scrape_result.json", result.to_dict())
            return result
        except CaptchaCheckpointRequired:
            if headed:
                raise
            try:
                used_headed_fallback = True
                result = _run_scrape_once(
                    seed_keyword=seed_keyword,
                    blog_suffix=blog_suffix,
                    artifacts_dir=artifacts_dir,
                    headed=True,
                    max_records=max_records,
                )
                _write_json(artifacts_dir / "seed_scrape_result.json", result.to_dict())
                return result
            except Exception as exc:  # pragma: no cover - defensive fallback
                last_error = exc
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                _sleep_random((1.0, 2.2))
            continue

    raise ScraperError(
        f"Failed to scrape seed '{seed_keyword}' after {max_attempts} attempts: {last_error}",
        reason=_classify_scrape_error(last_error if isinstance(last_error, Exception) else Exception()),
        attempts=max_attempts,
        used_headed_fallback=used_headed_fallback,
    )
