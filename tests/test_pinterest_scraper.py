import unittest
from os import environ
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automating_wf.models.pinterest import SeedScrapeResult
from automating_wf.scrapers.pinclicks import (
    PINCLICKS_SCRAPE_SOURCE_BRAVE,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
    PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED,
    PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
    PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
    PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE,
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
    ScraperError,
    _scrape_with_brave,
    _build_cloudflare_crawl_payload,
    _cookie_header_for_host,
    _build_pins_url,
    _camoufox_kwargs,
    _classify_scrape_error,
    _extract_engagement,
    _get_pinclicks_credentials,
    _navigate_direct_top_pins_status,
    _records_from_crawl_payload,
    _records_from_export_rows,
    _records_from_payload,
    _search_keyword_on_pins_page,
    ensure_pinclicks_brave_session,
    build_top_pins_url,
    scrape_seed,
)


class PinterestScraperTests(unittest.TestCase):
    def test_build_pins_url(self) -> None:
        self.assertEqual(
            _build_pins_url("https://app.pinclicks.com"),
            "https://app.pinclicks.com/pins",
        )
        self.assertEqual(
            _build_pins_url("https://app.pinclicks.com/"),
            "https://app.pinclicks.com/pins",
        )

    def test_build_top_pins_url_uses_keyword_placeholder(self) -> None:
        with patch.dict(
            environ,
            {"PINCLICKS_TOP_PINS_URL_TEMPLATE": "https://app.pinclicks.com/top-pins?query={keyword}"},
            clear=False,
        ):
            url = build_top_pins_url("dark mode desk")
        self.assertEqual(url, "https://app.pinclicks.com/top-pins?query=dark+mode+desk")

    def test_build_top_pins_url_requires_placeholder(self) -> None:
        with patch.dict(
            environ,
            {"PINCLICKS_TOP_PINS_URL_TEMPLATE": "https://app.pinclicks.com/top-pins"},
            clear=False,
        ):
            with self.assertRaises(ScraperError):
                build_top_pins_url("dark mode desk")

    def test_extract_engagement_parses_compact_metrics(self) -> None:
        metrics = _extract_engagement("1.2k saves 345 clicks 2m impressions")
        self.assertEqual(metrics["saves"], 1200.0)
        self.assertEqual(metrics["clicks"], 345.0)
        self.assertEqual(metrics["impressions"], 2_000_000.0)
        self.assertGreater(metrics["score_total"], 0.0)

    def test_records_from_payload_normalizes_mojibake_and_metrics(self) -> None:
        records, diagnostics, rejected = _records_from_payload(
            seed_keyword="iced coffee",
            payload=[
                {
                    "pin_url": "https://www.pinterest.com/pin/123456/",
                    "title": "Nescaf\u00c3\u00a9 Gold Iced Coffee \u00e2\u20ac\u201c Easy Recipe",
                    "description": "www.example.com",
                    "tags": ["#coffee", "Pin By", "www.example.com"],
                    "metric_text": "1.2k saves 345 clicks",
                    "metric_fragments": ["2m views", "12 comments"],
                }
            ],
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Nescaf\u00e9 Gold Iced Coffee - Easy Recipe")
        self.assertEqual(records[0].description, "")
        self.assertEqual(records[0].tags, ["coffee"])
        self.assertGreater(records[0].engagement["score_total"], 0.0)
        self.assertTrue(diagnostics["engagement_available"])
        self.assertEqual(rejected, [])

    def test_records_from_payload_rejects_ui_noise_rows(self) -> None:
        records, diagnostics, rejected = _records_from_payload(
            seed_keyword="coffee",
            payload=[
                {
                    "pin_url": "",
                    "title": "",
                    "description": "Select/deselect item for export",
                    "tags": [],
                    "metric_text": "Select/deselect item",
                },
                {
                    "pin_url": "https://www.pinterest.com/pin/987654/",
                    "title": "Pin by Alex on Coffee",
                    "description": "Helpful recipe",
                    "tags": [],
                    "metric_text": "100 saves",
                },
                {
                    "pin_url": "https://www.pinterest.com/pin/555555/",
                    "title": "Cold brew coffee recipe",
                    "description": "Easy summer drink",
                    "tags": ["coffee"],
                    "metric_text": "900 saves",
                },
            ],
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Cold brew coffee recipe")
        self.assertEqual(diagnostics["rejected_item_count"], 2)
        self.assertEqual(len(rejected), 2)

    def test_records_from_export_rows_apply_same_filtering(self) -> None:
        records, diagnostics, rejected = _records_from_export_rows(
            seed_keyword="iced coffee",
            rows=[
                {
                    "Pin Title": "Pin by Alex on Coffee",
                    "Description": "Helpful recipe",
                    "Pin URL": "https://www.pinterest.com/pin/111111/",
                    "Saves": "100",
                },
                {
                    "Pin Title": "Nescaf\u00c3\u00a9 Gold Iced Coffee",
                    "Description": "Easy recipe",
                    "Pin URL": "https://www.pinterest.com/pin/222222/",
                    "Tags": "coffee, www.example.com, pin by",
                    "Views": "1.1k",
                },
            ],
            source_file=Path("export.csv"),
            source_url="https://app.pinclicks.com/pins",
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Nescaf\u00e9 Gold Iced Coffee")
        self.assertEqual(records[0].tags, ["coffee"])
        self.assertEqual(diagnostics["scrape_mode"], "export")
        self.assertEqual(diagnostics["rejected_item_count"], 1)
        self.assertEqual(rejected[0]["reason"], "ui_noise")

    def test_cookie_header_for_host_filters_expired_and_wrong_domain(self) -> None:
        import tempfile
        import time

        payload = {
            "cookies": [
                {"name": "pinclicks_session", "value": "abc", "domain": ".app.pinclicks.com", "expires": 0},
                {"name": "XSRF-TOKEN", "value": "token123", "domain": "app.pinclicks.com", "expires": 0},
                {"name": "other", "value": "skip", "domain": ".example.com", "expires": 0},
                {"name": "expired", "value": "gone", "domain": ".app.pinclicks.com", "expires": time.time() - 10},
            ]
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = Path(handle.name)
        try:
            cookie_header, xsrf = _cookie_header_for_host(path, "app.pinclicks.com")
        finally:
            path.unlink(missing_ok=True)

        self.assertIn("pinclicks_session=abc", cookie_header)
        self.assertIn("XSRF-TOKEN=token123", cookie_header)
        self.assertNotIn("other=skip", cookie_header)
        self.assertEqual(xsrf, "token123")

    def test_build_cloudflare_crawl_payload_includes_headers_and_limits(self) -> None:
        with patch.dict(environ, {"PINCLICKS_CRAWL_MAX_PAGES": "4"}, clear=False):
            payload = _build_cloudflare_crawl_payload(
                start_url="https://app.pinclicks.com/top-pins?query=desk+setup",
                cookie_header="pinclicks_session=abc; XSRF-TOKEN=xyz",
                xsrf_token="xyz",
            )

        self.assertEqual(payload["url"], "https://app.pinclicks.com/top-pins?query=desk+setup")
        self.assertEqual(payload["maxPages"], 4)
        self.assertEqual(payload["crawlerOptions"]["limit"], 4)
        self.assertEqual(
            payload["sessionOptions"]["extraHTTPHeaders"]["Cookie"],
            "pinclicks_session=abc; XSRF-TOKEN=xyz",
        )
        self.assertEqual(payload["sessionOptions"]["extraHTTPHeaders"]["X-XSRF-TOKEN"], "xyz")

    def test_records_from_crawl_payload_parses_html_pin_links(self) -> None:
        payload = {
            "result": {
                "status": "completed",
                "records": [
                    {
                        "html": """
                        <div>
                          <a href="https://www.pinterest.com/pin/12345/">Summer Crochet Top</a>
                          <span>1.2k saves 345 clicks</span>
                        </div>
                        <div>
                          <a href="https://www.pinterest.com/pin/67890/">Crochet Beach Bag</a>
                          <span>900 saves 12 comments</span>
                        </div>
                        """
                    }
                ]
            }
        }

        records = _records_from_crawl_payload(
            seed_keyword="summer crochet",
            payload=payload,
            max_records=5,
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].pin_id, "12345")
        self.assertEqual(records[0].title, "Summer Crochet Top")
        self.assertGreater(records[0].engagement["score_total"], 0.0)

    def test_get_pinclicks_credentials_prefers_pinclicks_keys(self) -> None:
        with patch.dict(
            environ,
            {
                "PINCLICKS_USERNAME": "pc_user",
                "PINCLICKS_PASSWORD": "pc_pass",
                "PINTEREST_USERNAME": "legacy_user",
                "PINTEREST_PASSWORD": "legacy_pass",
            },
            clear=False,
        ):
            username, password = _get_pinclicks_credentials()
        self.assertEqual(username, "pc_user")
        self.assertEqual(password, "pc_pass")

    def test_classify_scrape_error_uses_structured_reason(self) -> None:
        error = ScraperError(
            "Could not trigger PinClicks export download for 'desk setup'.",
            reason=PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
        )
        self.assertEqual(
            _classify_scrape_error(error),
            PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
        )

    def test_classify_scrape_error_falls_back_to_text_match(self) -> None:
        self.assertEqual(
            _classify_scrape_error(RuntimeError("Could not enter keyword in search box")),
            PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        )

    def test_classify_scrape_error_detects_cloudflare_bot_block(self) -> None:
        self.assertEqual(
            _classify_scrape_error(RuntimeError("Cloudflare crawl hit access denied bot challenge")),
            PINCLICKS_SKIP_REASON_CLOUDFLARE_BOT_BLOCKED,
        )

    def test_classify_scrape_error_detects_stage3_setup_required(self) -> None:
        self.assertEqual(
            _classify_scrape_error(RuntimeError("PinClicks setup is required before Stage 3")),
            PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
        )

    def test_classify_scrape_error_detects_invalid_results_page(self) -> None:
        self.assertEqual(
            _classify_scrape_error(RuntimeError("PinClicks results page returned 404 Not Found.")),
            PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE,
        )

    def test_search_keyword_prefers_pins_search_input_before_direct_fallback(self) -> None:
        with patch(
            "automating_wf.scrapers.pinclicks._attempt_keyword_targeting",
            return_value="ok",
        ), patch(
            "automating_wf.scrapers.pinclicks._navigate_direct_top_pins_status",
        ) as mock_direct:
            _search_keyword_on_pins_page(page=object(), seed_keyword="desk setup")
        mock_direct.assert_not_called()

    def test_search_keyword_uses_direct_top_pins_fallback(self) -> None:
        with patch(
            "automating_wf.scrapers.pinclicks._attempt_keyword_targeting",
            return_value=PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        ), patch(
            "automating_wf.scrapers.pinclicks._navigate_direct_top_pins_status",
            return_value="ok",
        ):
            _search_keyword_on_pins_page(page=object(), seed_keyword="desk setup")

    def test_search_keyword_raises_when_all_fallbacks_fail(self) -> None:
        with patch(
            "automating_wf.scrapers.pinclicks._attempt_keyword_targeting",
            return_value=PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        ), patch(
            "automating_wf.scrapers.pinclicks._navigate_direct_top_pins_status",
            return_value=PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
        ):
            with self.assertRaises(ScraperError) as ctx:
                _search_keyword_on_pins_page(page=object(), seed_keyword="desk setup")
        self.assertEqual(
            ctx.exception.reason,
            PINCLICKS_SKIP_REASON_DIRECT_TOP_PINS_NAVIGATION_FAILED,
        )

    def test_navigate_direct_top_pins_status_rejects_not_found_page(self) -> None:
        class FakeLocator:
            def __init__(self, *, count: int = 0, text: str = "", value: str = "") -> None:
                self._count = count
                self._text = text
                self._value = value

            def count(self) -> int:
                return self._count

            def is_visible(self, timeout: int | None = None) -> bool:
                return self._count > 0

            def input_value(self, timeout: int | None = None) -> str:
                return self._value

            def inner_text(self, timeout: int | None = None) -> str:
                return self._text

            @property
            def first(self) -> "FakeLocator":
                return self

            def nth(self, index: int) -> "FakeLocator":
                return self

        class FakePage:
            url = "https://app.pinclicks.com/top-pins?query=desk+setup"

            def goto(self, url: str, wait_until: str = "load", timeout: int | None = None) -> None:
                self.url = url

            def locator(self, selector: str) -> FakeLocator:
                if selector == "body":
                    return FakeLocator(count=1, text="404 Not Found")
                return FakeLocator()

            def title(self) -> str:
                return "Not Found"

        with patch(
            "automating_wf.scrapers.pinclicks.build_top_pins_url",
            return_value="https://app.pinclicks.com/top-pins?query=desk+setup",
        ), patch("automating_wf.scrapers.pinclicks._sleep_random"), patch(
            "automating_wf.scrapers.pinclicks._dismiss_pinclicks_popups"
        ), patch("automating_wf.scrapers.pinclicks._wait_for_results_loaded"):
            status = _navigate_direct_top_pins_status(FakePage(), "desk setup")

        self.assertEqual(status, PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE)

    def test_camoufox_kwargs_headless_no_storage(self) -> None:
        fake_path = Path("/tmp/_nonexistent_storage_state.json")
        kwargs = _camoufox_kwargs(headed=False, storage_state_path=fake_path)
        self.assertTrue(kwargs["headless"])
        self.assertTrue(kwargs["humanize"])
        self.assertTrue(kwargs["geoip"])
        self.assertNotIn("accept_downloads", kwargs)
        self.assertNotIn("storage_state", kwargs)

    def test_camoufox_kwargs_headed_with_storage(self, tmp_path: Path | None = None) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            storage_path = Path(f.name)
        try:
            kwargs = _camoufox_kwargs(headed=True, storage_state_path=storage_path)
            self.assertFalse(kwargs["headless"])
            self.assertNotIn("storage_state", kwargs)
        finally:
            storage_path.unlink(missing_ok=True)

    def test_ensure_brave_session_returns_setup_required_when_not_authenticated(self) -> None:
        class FakePage:
            def close(self) -> None:
                return None

        fake_page = FakePage()

        class FakeBrowser:
            def __enter__(self):
                class Context:
                    def new_page(self_inner):
                        return fake_page
                return Context()

            def __exit__(self, exc_type, exc, tb):
                return None

        with (
            patch("automating_wf.scrapers.brave_browser.is_available", return_value=True),
            patch("automating_wf.scrapers.brave_browser.pinflow_profile_dir", return_value=r"C:\Brave\User Data\PinFlow"),
            patch("automating_wf.scrapers.brave_browser.BravePersistentBrowser", return_value=FakeBrowser()),
            patch("automating_wf.scrapers.pinclicks._is_authenticated", return_value=False),
            patch("automating_wf.scrapers.pinclicks._has_pinclicks_credentials", return_value=False),
        ):
            result = ensure_pinclicks_brave_session(
                headed=False,
                allow_manual_setup=False,
            )

        self.assertFalse(result["authenticated"])
        self.assertTrue(result["setup_required"])
        self.assertEqual(result["browser_mode"], PINCLICKS_SCRAPE_SOURCE_BRAVE)

    def test_ensure_brave_session_raises_when_brave_missing(self) -> None:
        with patch("automating_wf.scrapers.brave_browser.is_available", return_value=False):
            with self.assertRaises(ScraperError) as ctx:
                ensure_pinclicks_brave_session(headed=False, allow_manual_setup=False)

        self.assertEqual(ctx.exception.reason, PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED)

    def test_scrape_with_brave_raises_invalid_results_page_before_record_extraction(self) -> None:
        class FakeLocator:
            def __init__(self, *, count: int = 0, text: str = "") -> None:
                self._count = count
                self._text = text

            def count(self) -> int:
                return self._count

            def inner_text(self, timeout: int | None = None) -> str:
                return self._text

        class FakePage:
            url = "https://app.pinclicks.com/top-pins?query=desk+setup"

            def goto(self, url: str, wait_until: str = "load", timeout: int | None = None) -> None:
                self.url = url

            def locator(self, selector: str) -> FakeLocator:
                if selector == "body":
                    return FakeLocator(count=1, text="404 Not Found")
                return FakeLocator()

            def title(self) -> str:
                return "Not Found"

            def close(self) -> None:
                return None

        page = FakePage()

        class FakeContext:
            def new_page(self) -> FakePage:
                return page

        class FakeBrowser:
            def __enter__(self) -> FakeContext:
                return FakeContext()

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        with TemporaryDirectory() as tmp_dir, patch(
            "automating_wf.scrapers.pinclicks.ensure_pinclicks_brave_session",
            return_value={"authenticated": True, "setup_required": False},
        ), patch(
            "automating_wf.scrapers.brave_browser.BravePersistentBrowser",
            return_value=FakeBrowser(),
        ), patch("automating_wf.scrapers.pinclicks._sleep_random"), patch(
            "automating_wf.scrapers.pinclicks._dismiss_pinclicks_popups"
        ), patch("automating_wf.scrapers.pinclicks._search_keyword_on_pins_page"), patch(
            "automating_wf.scrapers.pinclicks._contains_captcha",
            return_value=False,
        ):
            with self.assertRaises(ScraperError) as ctx:
                _scrape_with_brave(
                    seed_keyword="desk setup",
                    blog_suffix="THE_SUNDAY_PATIO",
                    artifacts_dir=Path(tmp_dir),
                    headed=False,
                    max_records=25,
                )

        self.assertEqual(ctx.exception.reason, PINCLICKS_SKIP_REASON_INVALID_RESULTS_PAGE)

    def test_scrape_seed_falls_back_to_cloudflare_after_non_retryable_brave_error(self) -> None:
        expected = _records_from_payload(
            seed_keyword="desk setup",
            payload=[
                {
                    "pin_url": "https://www.pinterest.com/pin/123456/",
                    "title": "Desk setup guide",
                    "description": "Productive desk setup ideas",
                    "tags": ["desk"],
                    "metric_text": "1.2k saves 345 clicks",
                }
            ],
            max_records=5,
        )[0][0]
        with TemporaryDirectory() as tmp_dir:
            fallback_result = SeedScrapeResult(
                blog_suffix="THE_SUNDAY_PATIO",
                seed_keyword="desk setup",
                source_url="https://app.pinclicks.com/top-pins?query=desk+setup",
                records=[expected],
                source_file=str(Path(tmp_dir) / "cloudflare.json"),
                scraped_at="2026-04-10T10:00:00Z",
            )
            with patch(
                "automating_wf.scrapers.brave_browser.is_available",
                return_value=True,
            ), patch(
                "automating_wf.scrapers.pinclicks._scrape_with_brave",
                side_effect=RuntimeError(
                    "It looks like you are using Playwright Sync API inside the asyncio loop."
                ),
            ) as mock_brave, patch(
                "automating_wf.scrapers.pinclicks._scrape_with_cloudflare",
                return_value=fallback_result,
            ) as mock_cloudflare:
                result = scrape_seed(
                    seed_keyword="desk setup",
                    blog_suffix="THE_SUNDAY_PATIO",
                    run_dir=Path(tmp_dir),
                    headed=False,
                    max_records=5,
                    max_attempts=3,
                )

        self.assertEqual(result.source_file, fallback_result.source_file)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(mock_brave.call_count, 1)
        mock_cloudflare.assert_called_once()


if __name__ == "__main__":
    unittest.main()
