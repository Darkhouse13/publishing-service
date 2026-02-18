"""Subprocess wrapper for Playwright-based scrapers.

Runs in a dedicated process with Windows Proactor loop policy to avoid
Streamlit event-loop conflicts on Windows.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


def _to_jsonable(value: Any) -> Any:
    """Convert nested values into JSON-serializable equivalents."""
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__fspath__"):
        return str(os.fspath(value))
    return value


def _emit(payload: dict[str, Any]) -> None:
    """Write one JSON response payload to stdout."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.flush()


def _scrape_trends(payload: dict[str, Any]) -> dict[str, Any]:
    """Run Pinterest Trends scraping and return serializable data."""
    from pinterest_trends_scraper import scrape_trends_exports

    seed_keywords = payload.get("seed_keywords", [])
    run_dir = Path(str(payload.get("run_dir", "")).strip())
    headed = bool(payload.get("headed", False))
    max_attempts = int(payload.get("max_attempts", 3) or 3)
    region = str(payload.get("region", "")).strip()
    date_range = str(payload.get("date_range", "")).strip()

    if region:
        os.environ["PINTEREST_TRENDS_FILTER_REGION"] = region
    if date_range:
        os.environ["PINTEREST_TRENDS_FILTER_RANGE"] = date_range

    with contextlib.redirect_stdout(sys.stderr):
        result = scrape_trends_exports(
            seed_keywords=list(seed_keywords),
            run_dir=run_dir,
            headed=headed,
            max_attempts=max_attempts,
        )
    return _to_jsonable(result)


def _scrape_pinclicks(payload: dict[str, Any]) -> dict[str, Any]:
    """Run PinClicks scrape via scrape_seed and return serializable data."""
    from pinterest_scraper import scrape_seed

    seed_keyword = str(payload.get("seed_keyword", "")).strip()
    blog_suffix = str(payload.get("blog_suffix", "")).strip()
    run_dir = Path(str(payload.get("run_dir", "")).strip())
    headed = bool(payload.get("headed", False))
    max_records = int(payload.get("max_records", 25) or 25)
    max_attempts = int(payload.get("max_attempts", 3) or 3)

    with contextlib.redirect_stdout(sys.stderr):
        result = scrape_seed(
            seed_keyword=seed_keyword,
            blog_suffix=blog_suffix,
            run_dir=run_dir,
            headed=headed,
            max_records=max_records,
            max_attempts=max_attempts,
        )
    return _to_jsonable(result.to_dict())


def main() -> None:
    """Entry point for scraper subprocess actions."""
    try:
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Input JSON must be an object.")

        action = str(payload.get("action", "")).strip()
        if action == "scrape_trends":
            data = _scrape_trends(payload)
            _emit({"ok": True, "data": data})
            return
        if action == "scrape_pinclicks":
            data = _scrape_pinclicks(payload)
            _emit({"ok": True, "data": data})
            return

        _emit({"ok": False, "error": f"Unknown action: {action}", "error_type": "ValueError"})
    except Exception as exc:  # pragma: no cover - defensive output guard
        _emit(
            {
                "ok": False,
                "error": str(exc) or repr(exc),
                "error_type": type(exc).__name__,
            }
        )


if __name__ == "__main__":
    main()
