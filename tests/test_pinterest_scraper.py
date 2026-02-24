import unittest
from os import environ
from unittest.mock import patch

from automating_wf.scrapers.pinclicks import (
    PINCLICKS_SKIP_REASON_EXPORT_DOWNLOAD_FAILED,
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
    ScraperError,
    _build_pins_url,
    _classify_scrape_error,
    _extract_engagement,
    _get_pinclicks_credentials,
    _search_keyword_on_pins_page,
    build_top_pins_url,
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

    def test_search_keyword_uses_direct_top_pins_fallback(self) -> None:
        with patch(
            "automating_wf.scrapers.pinclicks._attempt_keyword_targeting",
            return_value=PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        ), patch(
            "automating_wf.scrapers.pinclicks._navigate_direct_top_pins",
            return_value=True,
        ):
            _search_keyword_on_pins_page(page=object(), seed_keyword="desk setup")

    def test_search_keyword_raises_when_all_fallbacks_fail(self) -> None:
        with patch(
            "automating_wf.scrapers.pinclicks._attempt_keyword_targeting",
            return_value=PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
        ), patch(
            "automating_wf.scrapers.pinclicks._navigate_direct_top_pins",
            return_value=False,
        ):
            with self.assertRaises(ScraperError):
                _search_keyword_on_pins_page(page=object(), seed_keyword="desk setup")


if __name__ == "__main__":
    unittest.main()
