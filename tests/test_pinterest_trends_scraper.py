import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from pinterest_trends_scraper import (
    EXPORT_BUTTON_SELECTORS,
    INCLUDE_KEYWORD_INPUT_SELECTORS,
    INCLUDE_KEYWORD_TRIGGER_SELECTORS,
    TrendsScraperError,
    _apply_include_keyword_filter,
    _keyword_for_include_filter,
    _read_force_include_keyword_env,
    _search_keyword,
)


class _DummyKeyboard:
    def press(self, _key: str) -> None:
        return None


class _DummyPage:
    def __init__(self) -> None:
        self.keyboard = _DummyKeyboard()
        self.goto_calls: list[str] = []

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        self.goto_calls.append(url)
        _ = wait_until


class PinterestTrendsScraperTests(unittest.TestCase):
    def test_keyword_for_include_filter_uses_single_word(self) -> None:
        self.assertEqual(_keyword_for_include_filter("patio furniture"), "patio")
        self.assertEqual(_keyword_for_include_filter("  small-patio ideas  "), "patio")

    def test_read_force_include_keyword_env_defaults_true(self) -> None:
        with patch.dict(environ, {}, clear=True):
            self.assertTrue(_read_force_include_keyword_env())

    def test_selector_constants_cover_french_and_english(self) -> None:
        self.assertTrue(any("Inclure le mot" in value for value in INCLUDE_KEYWORD_TRIGGER_SELECTORS))
        self.assertTrue(any("Include keyword" in value for value in INCLUDE_KEYWORD_TRIGGER_SELECTORS))
        self.assertTrue(any("Saisir un mot-cl" in value for value in INCLUDE_KEYWORD_INPUT_SELECTORS))
        self.assertTrue(any("Enter keyword" in value for value in INCLUDE_KEYWORD_INPUT_SELECTORS))
        self.assertTrue(any("Exporter" in value for value in EXPORT_BUTTON_SELECTORS))
        self.assertTrue(any("Export" in value for value in EXPORT_BUTTON_SELECTORS))

    def test_search_keyword_force_mode_never_uses_fallback(self) -> None:
        page = _DummyPage()
        call_order: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(
            environ, {"PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD": "1"}, clear=False
        ), patch("pinterest_trends_scraper._sleep_random"), patch(
            "pinterest_trends_scraper._dismiss_popups"
        ), patch(
            "pinterest_trends_scraper._apply_include_keyword_filter",
            side_effect=lambda *_args, **_kwargs: call_order.append("include") or False,
        ), patch(
            "pinterest_trends_scraper._fallback_global_search",
            side_effect=lambda *_args, **_kwargs: call_order.append("fallback") or True,
        ), patch(
            "pinterest_trends_scraper._save_keyword_debug_artifacts"
        ):
            with self.assertRaises(TrendsScraperError):
                _search_keyword(
                    page=page,
                    keyword="patio furniture",
                    base_url="https://trends.pinterest.com",
                    keyword_dir=Path(tmp_dir),
                )

        self.assertGreaterEqual(call_order.count("include"), 3)
        self.assertNotIn("fallback", call_order)

    def test_search_keyword_skips_fallback_when_include_succeeds(self) -> None:
        page = _DummyPage()
        with patch.dict(
            environ, {"PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD": "1"}, clear=False
        ), patch("pinterest_trends_scraper._sleep_random"), patch(
            "pinterest_trends_scraper._dismiss_popups"
        ), patch(
            "pinterest_trends_scraper._apply_include_keyword_filter", return_value=True
        ), patch(
            "pinterest_trends_scraper._fallback_global_search"
        ) as fallback_mock:
            _search_keyword(
                page=page,
                keyword="patio furniture",
                base_url="https://trends.pinterest.com",
            )
        fallback_mock.assert_not_called()

    def test_search_keyword_uses_single_include_attempt_when_force_disabled(self) -> None:
        page = _DummyPage()
        with patch.dict(
            environ, {"PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD": "0"}, clear=False
        ), patch("pinterest_trends_scraper._sleep_random"), patch(
            "pinterest_trends_scraper._dismiss_popups"
        ), patch(
            "pinterest_trends_scraper._apply_include_keyword_filter", return_value=False
        ) as include_mock, patch(
            "pinterest_trends_scraper._fallback_global_search", return_value=True
        ):
            _search_keyword(
                page=page,
                keyword="patio furniture",
                base_url="https://trends.pinterest.com",
            )
        self.assertEqual(include_mock.call_count, 1)

    def test_search_keyword_raises_when_include_and_fallback_fail(self) -> None:
        page = _DummyPage()
        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(
            environ, {"PINTEREST_TRENDS_FORCE_INCLUDE_KEYWORD": "1"}, clear=False
        ), patch("pinterest_trends_scraper._sleep_random"), patch(
            "pinterest_trends_scraper._dismiss_popups"
        ), patch(
            "pinterest_trends_scraper._apply_include_keyword_filter", return_value=False
        ), patch(
            "pinterest_trends_scraper._fallback_global_search", return_value=False
        ), patch(
            "pinterest_trends_scraper._save_keyword_debug_artifacts"
        ) as debug_mock:
            with self.assertRaises(TrendsScraperError):
                _search_keyword(
                    page=page,
                    keyword="patio furniture",
                    base_url="https://trends.pinterest.com",
                    keyword_dir=Path(tmp_dir),
                )
        debug_mock.assert_called_once()

    def test_apply_include_keyword_filter_uses_no_escape_after_panel_open(self) -> None:
        page = _DummyPage()
        with patch("pinterest_trends_scraper._open_include_keyword_panel", return_value=True), patch(
            "pinterest_trends_scraper._fill_include_keyword_input", return_value=True
        ), patch(
            "pinterest_trends_scraper._verify_keyword_filter_applied", return_value=True
        ), patch(
            "pinterest_trends_scraper._dismiss_popups"
        ) as dismiss_mock:
            result = _apply_include_keyword_filter(page, "patio furniture")

        self.assertTrue(result)
        self.assertTrue(any(call.kwargs.get("allow_escape") is False for call in dismiss_mock.call_args_list))


if __name__ == "__main__":
    unittest.main()
