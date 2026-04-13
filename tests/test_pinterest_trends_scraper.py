import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from automating_wf.scrapers.trends import (
    EXPORT_BUTTON_SELECTORS,
    INCLUDE_KEYWORD_INPUT_SELECTORS,
    INCLUDE_KEYWORD_TRIGGER_SELECTORS,
    TrendsNoResultsError,
    TrendsScraperError,
    _detect_no_results_reason,
    _apply_include_keyword_filter,
    _keyword_for_include_filter,
    _match_filter_option,
    _read_force_include_keyword_env,
    _search_keyword,
    scrape_trends_exports,
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


class _BodyLocator:
    def __init__(self, body: str) -> None:
        self._body = body

    def count(self) -> int:
        return 1

    def inner_text(self, timeout: int = 5000) -> str:
        _ = timeout
        return self._body


class _NoResultsPage(_DummyPage):
    def __init__(self) -> None:
        super().__init__()
        self.body = (
            "Oops! Filters are too narrow. Try expanding your search. "
            "Switch trend type to Top yearly trends."
        )

    def locator(self, _selector: str):
        return _BodyLocator(self.body)

    def evaluate(self, _script: str, _arg=None):
        return True


class _FakeBrowser:
    def close(self) -> None:
        return None


class _FakeContext:
    def __init__(self, page: object) -> None:
        self._page = page

    def new_page(self) -> object:
        return self._page

    def close(self) -> None:
        return None


class _FakePlaywrightContextManager:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False


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
        ), patch("automating_wf.scrapers.trends._sleep_random"), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._apply_include_keyword_filter",
            side_effect=lambda *_args, **_kwargs: call_order.append("include") or False,
        ), patch(
            "automating_wf.scrapers.trends._fallback_global_search",
            side_effect=lambda *_args, **_kwargs: call_order.append("fallback") or True,
        ), patch(
            "automating_wf.scrapers.trends._save_keyword_debug_artifacts"
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
        ), patch("automating_wf.scrapers.trends._sleep_random"), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._apply_include_keyword_filter", return_value=True
        ), patch(
            "automating_wf.scrapers.trends._fallback_global_search"
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
        ), patch("automating_wf.scrapers.trends._sleep_random"), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._apply_include_keyword_filter", return_value=False
        ) as include_mock, patch(
            "automating_wf.scrapers.trends._fallback_global_search", return_value=True
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
        ), patch("automating_wf.scrapers.trends._sleep_random"), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._apply_include_keyword_filter", return_value=False
        ), patch(
            "automating_wf.scrapers.trends._fallback_global_search", return_value=False
        ), patch(
            "automating_wf.scrapers.trends._save_keyword_debug_artifacts"
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
        with patch("automating_wf.scrapers.trends._open_include_keyword_panel", return_value=True), patch(
            "automating_wf.scrapers.trends._fill_include_keyword_input", return_value=True
        ), patch(
            "automating_wf.scrapers.trends._verify_keyword_filter_applied", return_value=True
        ), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ) as dismiss_mock:
            result = _apply_include_keyword_filter(page, "patio furniture")

        self.assertTrue(result)
        self.assertTrue(any(call.kwargs.get("allow_escape") is False for call in dismiss_mock.call_args_list))

    def test_match_filter_option_handles_global_aliases(self) -> None:
        match = _match_filter_option(
            "GLOBAL",
            [
                {"value": "US", "text": "United States"},
                {"value": "WORLDWIDE", "text": "Worldwide"},
            ],
        )

        self.assertEqual(match, {"value": "WORLDWIDE", "text": "Worldwide"})

    def test_detect_no_results_reason_flags_empty_trends_page(self) -> None:
        reason = _detect_no_results_reason(_NoResultsPage())
        self.assertEqual(reason, "filters_too_narrow")

    def test_download_export_raises_no_results_error_before_click_retries(self) -> None:
        page = _NoResultsPage()
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._save_keyword_debug_artifacts"
        ) as debug_mock:
            with self.assertRaises(TrendsNoResultsError):
                from automating_wf.scrapers.trends import _download_export

                _download_export(page, Path(tmp_dir), "knitting")

        debug_mock.assert_called_once()

    def test_scrape_trends_exports_skips_seed_with_no_results(self) -> None:
        page = _DummyPage()
        page.url = "https://trends.pinterest.com/search/?q=demo"
        export_file = Path(tempfile.gettempdir()) / "demo_trends_export.csv"
        export_file.write_text("Keyword,Interest\ncrochet,42\n", encoding="utf-8")

        def _download_side_effect(_page: object, _seed_dir: Path, keyword: str) -> Path:
            if keyword == "knitting":
                raise TrendsNoResultsError(keyword, "filters_too_narrow")
            return export_file

        def _filter_state(_page: object, label: str, option: str) -> dict[str, object]:
            if label == "Region":
                return {
                    "found": True,
                    "matched": option == "GLOBAL",
                    "requested": option,
                    "value": "GLOBAL",
                    "text": "Worldwide",
                    "available_options": [{"value": "GLOBAL", "text": "Worldwide"}],
                }
            return {
                "found": True,
                "matched": True,
                "requested": option,
                "value": option,
                "text": option,
                "available_options": [{"value": option, "text": option}],
            }

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "playwright.sync_api.sync_playwright",
            return_value=_FakePlaywrightContextManager(),
        ), patch(
            "automating_wf.scrapers.trends._build_context",
            return_value=(_FakeBrowser(), _FakeContext(page)),
        ), patch(
            "automating_wf.scrapers.trends._is_authenticated", return_value=True
        ), patch(
            "automating_wf.scrapers.trends._search_keyword", return_value=True
        ), patch(
            "automating_wf.scrapers.trends._dismiss_popups"
        ), patch(
            "automating_wf.scrapers.trends._set_filter_if_present",
            side_effect=_filter_state,
        ), patch(
            "automating_wf.scrapers.trends._contains_challenge", return_value=False
        ), patch(
            "automating_wf.scrapers.trends._download_export",
            side_effect=_download_side_effect,
        ), patch(
            "automating_wf.scrapers.trends._parse_and_persist_rows",
            return_value=[{"Keyword": "crochet", "Interest": 42}],
        ), patch(
            "automating_wf.scrapers.trends._sleep_random"
        ), patch(
            "automating_wf.scrapers.trends._now_utc_iso",
            return_value="2026-04-10T18:00:00Z",
        ):
            results = scrape_trends_exports(
                seed_keywords=["knitting", "crochet patterns"],
                run_dir=Path(tmp_dir),
            )

            self.assertEqual(results["knitting"], [])
            self.assertEqual(results["crochet patterns"], [str(export_file)])
            skip_meta = (
                Path(tmp_dir) / "knitting" / "trends_skip_metadata.json"
            ).read_text(encoding="utf-8")
            self.assertIn("filters_too_narrow", skip_meta)
            success_meta = (
                Path(tmp_dir) / "crochet_patterns" / "trends_export_metadata.json"
            ).read_text(encoding="utf-8")
            self.assertIn('"applied_region": "Worldwide"', success_meta)


if __name__ == "__main__":
    unittest.main()
