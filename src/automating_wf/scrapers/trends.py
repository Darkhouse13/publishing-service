from __future__ import annotations

import json
import os
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

from automating_wf.scrapers.file_parser import parse_tabular_export


PINTEREST_TRENDS_DEFAULT_BASE_URL = "https://trends.pinterest.com"
PINTEREST_TRENDS_DEFAULT_REGION = "GLOBAL"
PINTEREST_TRENDS_DEFAULT_RANGE = "12m"
TRENDS_RETRY_ATTEMPTS = 3
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
    "challenge",
    "2-step verification",
    "two-factor",
    "security challenge",
)

LOGIN_INPUT_SELECTORS = (
    "input[name='id']",
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
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "[role='button']:has-text('Log in')",
)

SEARCH_INPUT_SELECTORS = (
    "input[type='search']",
    "input[placeholder*='trend']",
    "input[placeholder*='search']",
    "input[aria-label*='Search']",
)

INCLUDE_KEYWORD_TRIGGER_SELECTORS = (
    "button[data-test-id='keyword-filter-button-toggle']",
    "[data-test-id='keyword-filter-button-toggle']",
    "button:has-text('Inclure le mot')",
    "[role='button']:has-text('Inclure le mot')",
    "button:has-text('Include keyword')",
    "[role='button']:has-text('Include keyword')",
)

INCLUDE_KEYWORD_TRIGGER_TEXT_HINTS = (
    "inclure le mot-cl",
    "include keyword",
)

INCLUDE_KEYWORD_INPUT_SELECTORS = (
    "input[data-test-id='keyword-filter-input']",
    "input[placeholder*='Type keyword']",
    "input[aria-label*='Type keyword']",
    "input[placeholder*='Saisir un mot-cl']",
    "input[aria-label*='Saisir un mot-cl']",
    "input[placeholder*='Enter keyword']",
    "input[aria-label*='Enter keyword']",
    "div[data-test-id='keyword-filter-input'] [contenteditable='true']",
    "[role='dialog'] [role='textbox'][contenteditable='true']",
    "[role='dialog'] input[type='text']",
)

INCLUDE_KEYWORD_INPUT_HINTS = (
    "type keyword",
    "saisir un mot-cl",
    "enter keyword",
)

EXPORT_BUTTON_SELECTORS = (
    "button[data-test-id='export-csv-button']",
    "[data-test-id='export-csv-button']",
    "button:has-text('Exporter')",
    "[role='button']:has-text('Exporter')",
    "a:has-text('Exporter')",
    "[aria-label*='Exporter']",
    "button:has-text('Export')",
    "a:has-text('Export')",
    "button:has-text('Download')",
    "[role='button']:has-text('Export')",
    "[aria-label*='Export']",
    "[data-testid*='export']",
    "[data-test-id*='export']",
)

EXPORT_BUTTON_TEXT_HINTS = (
    "exporter",
    "export",
)

GENERIC_INCLUDE_TOKENS = {
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
    "modern",
    "new",
    "of",
    "small",
    "the",
    "top",
    "your",
}

class TrendsScraperError(RuntimeError):
    """Raised when Pinterest Trends scraping cannot continue."""


class TrendsCaptchaCheckpointRequired(TrendsScraperError):
    """Raised when human checkpoint is required."""


def _sleep_random(delay_range: tuple[float, float]) -> None:
    time.sleep(random.uniform(*delay_range))


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_force_include_keyword_env() -> bool:
    raw = os.getenv("PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _keyword_for_include_filter(keyword: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", keyword)
    for token in tokens:
        lowered = token.casefold()
        if len(lowered) < 3:
            continue
        if lowered in GENERIC_INCLUDE_TOKENS:
            continue
        return token
    if tokens:
        return tokens[0]
    return keyword.strip()


def _normalize_text(value: str) -> str:
    base = unicodedata.normalize("NFKD", value or "")
    no_marks = "".join(ch for ch in base if not unicodedata.combining(ch))
    squashed = re.sub(r"\s+", " ", no_marks).strip().lower()
    return squashed.replace("’", "'")


def _first_existing_selector(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return selector
        except Exception:
            continue
    return ""


def _body_text(page: Any) -> str:
    try:
        body = page.locator("body")
        if body.count() == 0:
            return ""
        return str(body.inner_text(timeout=5000)).strip().lower()
    except Exception:
        return ""


def _contains_challenge(page: Any) -> bool:
    body = _body_text(page)
    if not body:
        return False
    return any(marker in body for marker in CAPTCHA_MARKERS)


def _dismiss_popups(page: Any, *, allow_escape: bool = True) -> int:
    dismissed = 0
    close_selectors = (
        "button[aria-label='Close']",
        "button[aria-label='close']",
        "button[aria-label*='close' i]",
        "button:has-text('Not now')",
        "button:has-text('Maybe later')",
        "button:has-text('Reject all')",
        "button:has-text('Decline')",
        "[data-testid*='close']",
        "[data-test-id*='close']",
        "[role='button'][aria-label*='close' i]",
    )

    # Try multiple rounds because one dialog can open another.
    for _ in range(3):
        if allow_escape:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

        round_dismissed = 0
        for selector in close_selectors:
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 4)
                for index in range(count):
                    handle = locator.nth(index)
                    try:
                        if handle.is_visible(timeout=500):
                            handle.click(timeout=800, force=True)
                            _sleep_random((0.15, 0.4))
                            round_dismissed += 1
                    except Exception:
                        continue
            except Exception:
                continue

        # JS fallback for icon-only X buttons.
        try:
            clicked = page.evaluate(
                """() => {
                  let count = 0;
                  const candidates = Array.from(document.querySelectorAll('button,[role="button"]'));
                  for (const node of candidates) {
                    const label = ((node.getAttribute('aria-label') || '') + ' ' + (node.textContent || '')).trim().toLowerCase();
                    if (!label) continue;
                    if (label === 'x' || label.includes('close') || label.includes('dismiss')) {
                      const rect = node.getBoundingClientRect();
                      if (rect.width > 0 && rect.height > 0) {
                        node.click();
                        count += 1;
                      }
                    }
                    if (count >= 5) break;
                  }
                  return count;
                }"""
            )
            if isinstance(clicked, int):
                round_dismissed += clicked
        except Exception:
            pass

        dismissed += round_dismissed
        if round_dismissed == 0:
            break
    return dismissed


def _save_keyword_debug_artifacts(page: Any, keyword_dir: Path, prefix: str) -> None:
    _ensure_dir(keyword_dir)
    try:
        page.screenshot(path=str(keyword_dir / f"{prefix}.png"), full_page=True)
    except Exception:
        pass
    try:
        html = page.content()
        (keyword_dir / f"{prefix}.html").write_text(str(html), encoding="utf-8")
    except Exception:
        pass
    try:
        visible_buttons = page.evaluate(
            """() => {
              return Array.from(document.querySelectorAll('button,[role="button"]'))
                .map(node => (node.textContent || '').trim())
                .filter(Boolean)
                .slice(0, 200);
            }"""
        )
        _write_json(keyword_dir / f"{prefix}_buttons.json", visible_buttons)
    except Exception:
        pass


def _safe_storage_state_path() -> Path:
    load_dotenv()
    configured = os.getenv("PINTEREST_STORAGE_STATE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".codex" / "secrets" / "pinterest_state.json").resolve()


def _get_credentials() -> tuple[str, str]:
    load_dotenv()
    username = os.getenv("PINTEREST_USERNAME", "").strip()
    password = os.getenv("PINTEREST_PASSWORD", "").strip()
    return username, password


def _is_authenticated(page: Any, base_url: str) -> bool:
    page.goto(base_url, wait_until="domcontentloaded")
    _sleep_random(NAVIGATION_DELAY_RANGE)
    password_selector = _first_existing_selector(page, PASSWORD_INPUT_SELECTORS)
    if password_selector:
        return False
    body = _body_text(page)
    if "log in" in body and ("pinterest" in body or "continue with" in body):
        return False
    return True


def _persist_storage_state(context: Any, storage_state_path: Path) -> None:
    _ensure_dir(storage_state_path.parent)
    context.storage_state(path=str(storage_state_path))


def _perform_login(
    *,
    page: Any,
    context: Any,
    base_url: str,
    storage_state_path: Path,
    headed: bool,
) -> None:
    username, password = _get_credentials()
    if not username or not password:
        raise TrendsScraperError(
            "Pinterest authentication required but PINTEREST_USERNAME/PINTEREST_PASSWORD are missing."
        )

    login_url_candidates = (
        "https://www.pinterest.com/login/",
        "https://www.pinterest.com",
        base_url.rstrip("/") + "/login",
    )
    for login_url in login_url_candidates:
        page.goto(login_url, wait_until="domcontentloaded")
        _sleep_random(NAVIGATION_DELAY_RANGE)
        username_selector = _first_existing_selector(page, LOGIN_INPUT_SELECTORS)
        password_selector = _first_existing_selector(page, PASSWORD_INPUT_SELECTORS)
        login_button_selector = _first_existing_selector(page, LOGIN_BUTTON_SELECTORS)
        if username_selector and password_selector and login_button_selector:
            page.fill(username_selector, username)
            _sleep_random(ACTION_DELAY_RANGE)
            page.fill(password_selector, password)
            _sleep_random(ACTION_DELAY_RANGE)
            page.click(login_button_selector)
            _sleep_random(NAVIGATION_DELAY_RANGE)
            break
    else:
        raise TrendsScraperError("Could not locate Pinterest login form fields.")

    if _contains_challenge(page):
        if headed:
            print(
                "Pinterest challenge detected. Solve in browser, then press Enter to continue."
            )
            try:
                input()
            except EOFError:
                pass
        else:
            raise TrendsCaptchaCheckpointRequired(
                "Pinterest challenge encountered in headless mode; retry in headed mode."
            )

    if not _is_authenticated(page, base_url):
        raise TrendsScraperError("Pinterest login failed; session appears unauthenticated.")

    _persist_storage_state(context, storage_state_path)


def _build_search_url(base_url: str, keyword: str) -> str:
    template = os.getenv("PINTEREST_TRENDS_QUERY_URL_TEMPLATE", "").strip()
    if template:
        return template.format(keyword=quote_plus(keyword), raw_keyword=keyword)
    return f"{base_url.rstrip('/')}/search/?q={quote_plus(keyword)}"


def _set_filter_if_present(page: Any, label: str, option: str) -> None:
    try:
        _dismiss_popups(page)
        trigger_candidates = (
            f"button:has-text('{label}')",
            f"[role='button']:has-text('{label}')",
            f"[aria-label*='{label}']",
        )
        for selector in trigger_candidates:
            locator = page.locator(selector)
            if locator.count() <= 0:
                continue
            locator.first.click(timeout=3000)
            _sleep_random(ACTION_DELAY_RANGE)
            option_locator = page.locator(
                f"button:has-text('{option}'), [role='option']:has-text('{option}'), li:has-text('{option}')"
            )
            if option_locator.count() > 0:
                option_locator.first.click(timeout=3000)
                _sleep_random(ACTION_DELAY_RANGE)
            break
    except Exception:
        return


def _include_keyword_panel_open(page: Any) -> bool:
    expanded_selectors = (
        "button[data-test-id='keyword-filter-button-toggle'][aria-expanded='true']",
        "button[aria-controls*='Include keyword'][aria-expanded='true']",
        "button[aria-controls*='Inclure'][aria-expanded='true']",
        "[role='button'][aria-controls*='Include keyword'][aria-expanded='true']",
        "[role='button'][aria-controls*='Inclure'][aria-expanded='true']",
    )
    for selector in expanded_selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                return True
        except Exception:
            continue

    for selector in INCLUDE_KEYWORD_INPUT_SELECTORS:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                return True
        except Exception:
            continue

    try:
        return bool(
            page.evaluate(
                """(inputHints) => {
                  const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                  const visible = (node) => {
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(node);
                    return style.visibility !== 'hidden' && style.display !== 'none';
                  };

                  const expanded = Array.from(
                    document.querySelectorAll(
                      "button[data-test-id='keyword-filter-button-toggle'],button[aria-controls], [role='button'][aria-controls]"
                    )
                  ).some((node) => {
                    if (!visible(node)) return false;
                    const controls = normalize(node.getAttribute('aria-controls') || '');
                    const expandedValue = (node.getAttribute('aria-expanded') || '').toLowerCase();
                    if (!expandedValue) return false;
                    if (expandedValue !== 'true') return false;
                    return controls.includes('include keyword') || controls.includes('inclure');
                  });
                  if (expanded) return true;

                  const matchesHint = (text) => inputHints.some((hint) => text.includes(hint));
                  const nodes = Array.from(document.querySelectorAll('input,[role=\"textbox\"],[contenteditable=\"true\"]'));
                  for (const node of nodes) {
                    if (!visible(node)) continue;
                    const text = normalize(
                      (node.getAttribute('placeholder') || '') +
                      ' ' + (node.getAttribute('aria-label') || '') +
                      ' ' + (node.textContent || '')
                    );
                    if (!text) continue;
                    if (matchesHint(text)) return true;
                  }
                  return false;
                }""",
                list(INCLUDE_KEYWORD_INPUT_HINTS),
            )
        )
    except Exception:
        return False


def _open_include_keyword_panel(page: Any) -> bool:
    _dismiss_popups(page)
    for selector in INCLUDE_KEYWORD_TRIGGER_SELECTORS:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 4)
            for index in range(count):
                trigger = locator.nth(index)
                if trigger.is_visible(timeout=800):
                    trigger.click(timeout=3000)
                    _sleep_random((0.25, 0.6))
                    if _include_keyword_panel_open(page):
                        return True
        except Exception:
            continue

    try:
        clicked = page.evaluate(
            """(textHints) => {
              const normalize = (value) => (value || '')
                .normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '')
                .replace(/\\s+/g, ' ')
                .trim()
                .toLowerCase();
              const visible = (node) => {
                const rect = node.getBoundingClientRect();
                if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(node);
                return style.visibility !== 'hidden' && style.display !== 'none';
              };
              const matchesHint = (text) => textHints.some((hint) => text.includes(hint));
              const nodes = Array.from(document.querySelectorAll('button,[role=\"button\"]'));
              for (const node of nodes) {
                if (!visible(node)) continue;
                const label = normalize((node.getAttribute('aria-label') || '') + ' ' + (node.textContent || ''));
                if (!label) continue;
                if (matchesHint(label)) {
                  node.click();
                  return true;
                }
              }
              return false;
            }""",
            list(INCLUDE_KEYWORD_TRIGGER_TEXT_HINTS),
        )
        if clicked:
            _sleep_random((0.25, 0.6))
            return _include_keyword_panel_open(page)
        return False
    except Exception:
        return False


def _fill_include_keyword_input(page: Any, keyword: str) -> bool:
    _dismiss_popups(page, allow_escape=False)
    for selector in INCLUDE_KEYWORD_INPUT_SELECTORS:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 4)
            for index in range(count):
                field = locator.nth(index)
                if not field.is_visible(timeout=800):
                    continue
                field.click(timeout=2000)
                editable = field.evaluate(
                    """(node) => {
                      if (!node) return false;
                      const tag = (node.tagName || '').toLowerCase();
                      if (tag === 'input' || tag === 'textarea') return true;
                      return !!node.getAttribute('contenteditable');
                    }"""
                )
                if editable:
                    tag_name = field.evaluate("(node) => (node?.tagName || '').toLowerCase()")
                    if tag_name in {"input", "textarea"}:
                        field.fill(keyword, timeout=3000)
                    else:
                        page.keyboard.press("Control+A")
                        _sleep_random((0.08, 0.2))
                        page.keyboard.type(keyword, delay=40)
                else:
                    field.fill(keyword, timeout=3000)
                _sleep_random((0.15, 0.45))
                page.keyboard.press("Enter")
                _sleep_random(ACTION_DELAY_RANGE)
                return True
        except Exception:
            continue

    try:
        filled = page.evaluate(
            """({ keyword, inputHints }) => {
              const normalize = (value) => (value || '')
                .normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '')
                .replace(/\\s+/g, ' ')
                .trim()
                .toLowerCase();
              const visible = (node) => {
                const rect = node.getBoundingClientRect();
                if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(node);
                return style.visibility !== 'hidden' && style.display !== 'none';
              };
              const matchesHint = (text) => inputHints.some((hint) => text.includes(hint));
              const nodes = Array.from(document.querySelectorAll('input,textarea,[role=\"textbox\"],[contenteditable=\"true\"]'));
              for (const node of nodes) {
                if (!visible(node)) continue;
                const label = normalize((node.getAttribute('placeholder') || '') + ' ' + (node.getAttribute('aria-label') || ''));
                if (!label) continue;
                if (matchesHint(label)) {
                  node.focus();
                  if ('value' in node) {
                    node.value = keyword;
                  } else {
                    node.textContent = keyword;
                  }
                  node.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                  node.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                  node.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                  node.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                  return true;
                }
              }
              return false;
            }""",
            {"keyword": keyword, "inputHints": list(INCLUDE_KEYWORD_INPUT_HINTS)},
        )
        if filled:
            _sleep_random(ACTION_DELAY_RANGE)
            return True
    except Exception:
        return False
    return False


def _verify_keyword_filter_applied(page: Any, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    if not normalized_keyword:
        return False

    for selector in INCLUDE_KEYWORD_INPUT_SELECTORS:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 4)
            for index in range(count):
                field = locator.nth(index)
                if not field.is_visible(timeout=500):
                    continue
                value = _normalize_text(str(field.input_value(timeout=700)))
                if normalized_keyword in value:
                    return True
        except Exception:
            continue

    try:
        return bool(
            page.evaluate(
                """(keyword) => {
                  const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                  const target = normalize(keyword);
                  if (!target) return false;
                  const visible = (node) => {
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(node);
                    return style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const nodes = Array.from(document.querySelectorAll('button,[role=\"button\"],li,span,input'));
                  for (const node of nodes) {
                    if (!visible(node)) continue;
                    const text = normalize((node.value || '') + ' ' + (node.getAttribute('aria-label') || '') + ' ' + (node.textContent || ''));
                    if (text.includes(target)) return true;
                  }
                  return false;
                }""",
                keyword,
            )
        )
    except Exception:
        return False


def _fallback_global_search(page: Any, keyword: str) -> bool:
    input_selector = _first_existing_selector(page, SEARCH_INPUT_SELECTORS)
    if not input_selector:
        return False
    try:
        page.fill(input_selector, keyword)
        _sleep_random((0.15, 0.45))
        page.keyboard.press("Enter")
        _sleep_random(NAVIGATION_DELAY_RANGE)
        _dismiss_popups(page)
        return True
    except Exception:
        return False


def _apply_include_keyword_filter(page: Any, keyword: str) -> bool:
    include_keyword = _keyword_for_include_filter(keyword)
    _dismiss_popups(page)
    if not _open_include_keyword_panel(page):
        return False
    _dismiss_popups(page, allow_escape=False)
    if not _fill_include_keyword_input(page, include_keyword):
        return False
    _dismiss_popups(page, allow_escape=False)
    return _verify_keyword_filter_applied(page, include_keyword)


def _search_keyword(page: Any, keyword: str, base_url: str, keyword_dir: Path | None = None) -> bool:
    """Navigate to trends search for *keyword* and apply the include-keyword filter.

    Returns ``True`` if the precise include-keyword filter was applied
    successfully, ``False`` if execution fell back to a broad global search.
    """
    page.goto(_build_search_url(base_url, keyword), wait_until="domcontentloaded")
    _sleep_random(NAVIGATION_DELAY_RANGE)

    force_include_path = _read_force_include_keyword_env()
    include_keyword = _keyword_for_include_filter(keyword)
    include_attempts = 3 if force_include_path else 1

    for attempt in range(1, include_attempts + 1):
        if _apply_include_keyword_filter(page, keyword):
            return True
        _dismiss_popups(page)
        if attempt < include_attempts:
            _sleep_random((0.4, 0.9))

    if keyword_dir is not None:
        _save_keyword_debug_artifacts(page, keyword_dir, "include_keyword_input_failed")

    if force_include_path:
        raise TrendsScraperError(
            f"Could not apply Trends include-keyword filter for '{include_keyword}' (seed: '{keyword}')."
        )

    if _fallback_global_search(page, keyword):
        return False

    raise TrendsScraperError(
        f"Could not apply Trends keyword search for keyword '{keyword}'."
    )


def _download_export(page: Any, keyword_dir: Path, keyword: str) -> Path:
    _ensure_dir(keyword_dir)
    filename_base = re.sub(r"[^A-Za-z0-9]+", "_", keyword.lower()).strip("_") or "keyword"
    export_path = keyword_dir / f"trends_export_{filename_base}.csv"
    include_keyword = _keyword_for_include_filter(keyword)

    for export_attempt in range(1, 4):
        _dismiss_popups(page)
        if not _verify_keyword_filter_applied(page, include_keyword):
            _apply_include_keyword_filter(page, include_keyword)
            _dismiss_popups(page)

        for selector in EXPORT_BUTTON_SELECTORS:
            try:
                button = page.locator(selector)
                if button.count() <= 0:
                    continue
                if not button.first.is_visible(timeout=1200):
                    continue
                with page.expect_download(timeout=12000) as download_info:
                    button.first.click(timeout=4000)
                download = download_info.value
                suggested = download.suggested_filename or export_path.name
                save_path = keyword_dir / suggested
                download.save_as(str(save_path))
                return save_path
            except Exception:
                _dismiss_popups(page)
                continue

        try:
            with page.expect_download(timeout=12000) as download_info:
                clicked = page.evaluate(
                    """(textHints) => {
                      const normalize = (value) => (value || '')
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();
                      const visible = (node) => {
                        const rect = node.getBoundingClientRect();
                        if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                        const style = window.getComputedStyle(node);
                        return style.visibility !== 'hidden' && style.display !== 'none';
                      };
                      const matchesHint = (text) => textHints.some((hint) => text.includes(hint));
                      const nodes = Array.from(document.querySelectorAll('button,[role=\"button\"],a'));
                      for (const node of nodes) {
                        if (!visible(node)) continue;
                        const text = normalize((node.getAttribute('aria-label') || '') + ' ' + (node.textContent || ''));
                        if (!text) continue;
                        if (matchesHint(text)) {
                          node.click();
                          return true;
                        }
                      }
                      return false;
                    }""",
                    list(EXPORT_BUTTON_TEXT_HINTS),
                )
                if not clicked:
                    raise TrendsScraperError("Export control not found.")
            download = download_info.value
            suggested = download.suggested_filename or export_path.name
            save_path = keyword_dir / suggested
            download.save_as(str(save_path))
            return save_path
        except Exception:
            _dismiss_popups(page)

        _apply_include_keyword_filter(page, include_keyword)
        _dismiss_popups(page)
        if export_attempt < 3:
            _sleep_random((0.5, 1.1))

    _save_keyword_debug_artifacts(page, keyword_dir, "export_click_failed")
    raise TrendsScraperError(
        f"Could not trigger Trends export download for keyword '{keyword}'."
    )


def _parse_and_persist_rows(export_file: Path, keyword_dir: Path) -> list[dict[str, Any]]:
    rows = parse_tabular_export(export_file)
    _write_json(keyword_dir / "trends_rows_raw.json", rows)
    return rows


def _build_context(
    playwright: Any,
    *,
    headed: bool,
    storage_state_path: Path,
    downloads_path: Path,
) -> tuple[Any, Any]:
    args = ["--disable-blink-features=AutomationControlled"]
    if headed:
        args += ["--window-position=-32000,-32000", "--window-size=1,1"]
    browser = playwright.chromium.launch(
        headless=not headed,
        args=args,
    )
    context_kwargs: dict[str, Any] = {
        "viewport": dict(random.choice(DEFAULT_VIEWPORTS)),
        "user_agent": random.choice(DEFAULT_USER_AGENTS),
        "accept_downloads": True,
    }
    if storage_state_path.exists():
        context_kwargs["storage_state"] = str(storage_state_path)
    _ensure_dir(downloads_path)
    context = browser.new_context(**context_kwargs)
    return browser, context


def scrape_trends_exports(
    *,
    seed_keywords: list[str],
    run_dir: Path,
    headed: bool = False,
    max_attempts: int = TRENDS_RETRY_ATTEMPTS,
) -> dict[str, list[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise TrendsScraperError(
            "playwright is required for Pinterest Trends scraping. Install dependencies first."
        ) from exc

    if not seed_keywords:
        return {}
    _ensure_dir(run_dir)
    load_dotenv()
    base_url = os.getenv("PINTEREST_TRENDS_BASE_URL", PINTEREST_TRENDS_DEFAULT_BASE_URL).strip()
    region = os.getenv("PINTEREST_TRENDS_FILTER_REGION", PINTEREST_TRENDS_DEFAULT_REGION).strip() or PINTEREST_TRENDS_DEFAULT_REGION
    time_range = os.getenv("PINTEREST_TRENDS_FILTER_RANGE", PINTEREST_TRENDS_DEFAULT_RANGE).strip() or PINTEREST_TRENDS_DEFAULT_RANGE
    storage_state_path = _safe_storage_state_path()

    export_files_by_seed: dict[str, list[str]] = {}
    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            browser, context = _build_context(
                playwright=playwright,
                headed=headed,
                storage_state_path=storage_state_path,
                downloads_path=run_dir,
            )
            page = context.new_page()

            if not _is_authenticated(page, base_url):
                _perform_login(
                    page=page,
                    context=context,
                    base_url=base_url,
                    storage_state_path=storage_state_path,
                    headed=headed,
                )

            for seed_keyword in seed_keywords:
                seed_dir = run_dir / (
                    re.sub(r"[^A-Za-z0-9]+", "_", seed_keyword.lower()).strip("_") or "seed"
                )
                _ensure_dir(seed_dir)
                last_error: Exception | None = None

                for attempt in range(1, max_attempts + 1):
                    try:
                        include_keyword_applied = _search_keyword(page, seed_keyword, base_url, seed_dir)
                        _dismiss_popups(page)
                        _set_filter_if_present(page, "Region", region)
                        _set_filter_if_present(page, "Time", time_range)
                        _set_filter_if_present(page, "Date", time_range)
                        _dismiss_popups(page)
                        if _contains_challenge(page):
                            if headed:
                                print(
                                    f"Pinterest challenge detected for '{seed_keyword}'. "
                                    "Solve in browser and press Enter."
                                )
                                try:
                                    input()
                                except EOFError:
                                    pass
                            else:
                                raise TrendsCaptchaCheckpointRequired(
                                    "Pinterest challenge encountered on Trends page; retrying in headed mode."
                                )
                        export_file = _download_export(page, seed_dir, seed_keyword)
                        rows = _parse_and_persist_rows(export_file, seed_dir)
                        export_files_by_seed.setdefault(seed_keyword, []).append(str(export_file))
                        _write_json(
                            seed_dir / "trends_export_metadata.json",
                            {
                                "seed_keyword": seed_keyword,
                                "region": region,
                                "time_range": time_range,
                                "source_url": page.url,
                                "export_file": str(export_file),
                                "row_count": len(rows),
                                "scraped_at": _now_utc_iso(),
                                "include_keyword_applied": include_keyword_applied,
                            },
                        )
                        last_error = None
                        break
                    except TrendsCaptchaCheckpointRequired:
                        if headed:
                            raise
                        # One-step escalation to headed within same attempt.
                        browser.close()
                        browser, context = _build_context(
                            playwright=playwright,
                            headed=True,
                            storage_state_path=storage_state_path,
                            downloads_path=run_dir,
                        )
                        page = context.new_page()
                        last_error = TrendsCaptchaCheckpointRequired(
                            "Escalated to headed mode for challenge checkpoint."
                        )
                    except Exception as exc:
                        last_error = exc
                        if attempt < max_attempts:
                            _sleep_random((1.0, 2.3))
                        continue

                if last_error is not None:
                    raise TrendsScraperError(
                        f"Failed Pinterest Trends export for seed '{seed_keyword}': {last_error}"
                    )

            return export_files_by_seed
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()

