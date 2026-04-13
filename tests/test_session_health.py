"""Tests for _check_session_health and circuit breaker logic."""
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

from automating_wf.scrapers.pinclicks import (
    PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED,
    PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED,
    PINCLICKS_SKIP_REASON_CAPTCHA_CHECKPOINT_REQUIRED,
    PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED,
    ScraperError,
    _check_session_health,
)


def _write_state(path: Path, cookies: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookies": cookies}), encoding="utf-8")


class TestCheckSessionHealth(unittest.TestCase):
    """Tests for _check_session_health with fixture JSON."""

    def test_missing_file_returns_unhealthy(self) -> None:
        with TemporaryDirectory() as tmp:
            result = _check_session_health(Path(tmp) / "nonexistent.json")
        self.assertFalse(result["healthy"])
        self.assertTrue(result["needs_reauth"])
        self.assertFalse(result["cf_valid"])

    def test_all_cookies_valid(self) -> None:
        future = time.time() + 86400
        cookies = [
            {"name": "pinclicks_session", "expires": future},
            {"name": "XSRF-TOKEN", "expires": future},
            {"name": "cf_clearance", "expires": future},
        ]
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            _write_state(state_path, cookies)
            result = _check_session_health(state_path)
        self.assertTrue(result["healthy"])
        self.assertFalse(result["needs_reauth"])
        self.assertTrue(result["cf_valid"])
        self.assertEqual(result["expired_critical"], [])

    def test_expired_critical_cookies(self) -> None:
        past = time.time() - 86400
        future = time.time() + 86400
        cookies = [
            {"name": "pinclicks_session", "expires": past},
            {"name": "XSRF-TOKEN", "expires": past},
            {"name": "cf_clearance", "expires": future},
        ]
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            _write_state(state_path, cookies)
            result = _check_session_health(state_path)
        self.assertFalse(result["healthy"])
        self.assertTrue(result["needs_reauth"])
        self.assertTrue(result["cf_valid"])
        self.assertIn("pinclicks_session", result["expired_critical"])
        self.assertIn("XSRF-TOKEN", result["expired_critical"])

    def test_expired_cf_clearance(self) -> None:
        future = time.time() + 86400
        past = time.time() - 86400
        cookies = [
            {"name": "pinclicks_session", "expires": future},
            {"name": "XSRF-TOKEN", "expires": future},
            {"name": "cf_clearance", "expires": past},
        ]
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            _write_state(state_path, cookies)
            result = _check_session_health(state_path)
        self.assertTrue(result["healthy"])
        self.assertFalse(result["cf_valid"])

    def test_session_cookies_with_no_expiry(self) -> None:
        """Cookies with expires=-1 or 0 are treated as session cookies (not expired)."""
        cookies = [
            {"name": "pinclicks_session", "expires": -1},
            {"name": "XSRF-TOKEN", "expires": 0},
            {"name": "cf_clearance", "expires": time.time() + 86400},
        ]
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            _write_state(state_path, cookies)
            result = _check_session_health(state_path)
        self.assertTrue(result["healthy"])
        self.assertFalse(result["needs_reauth"])

    def test_corrupt_json_returns_unhealthy(self) -> None:
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text("not json", encoding="utf-8")
            result = _check_session_health(state_path)
        self.assertFalse(result["healthy"])


class TestCircuitBreaker(unittest.TestCase):
    """Tests for circuit breaker logic in _collect_pinclicks_data_sync."""

    _PIPELINE = "automating_wf.engine.pipeline"
    _COMMON_PATCHES = {
        "setup": f"{_PIPELINE}._bootstrap_pinclicks_session_bridge",
        "bridge": f"{_PIPELINE}._scrape_seed_bridge",
        "rank": f"{_PIPELINE}.rank_pinclicks_keywords",
        "load_entries": f"{_PIPELINE}._load_manifest_entries",
        "latest": f"{_PIPELINE}._latest_status_by_seed",
        "append": f"{_PIPELINE}._append_manifest",
        "cached": f"{_PIPELINE}._load_cached_top_keywords",
        "run_dir": f"{_PIPELINE}._resolve_phase_run_dir",
        "sleep": f"{_PIPELINE}.time.sleep",
    }

    def _make_opts(self) -> MagicMock:
        opts = MagicMock()
        opts.blog_suffix = "TEST"
        opts.headed = False
        opts.pinclicks_max_records = 25
        opts.winners_count = 5
        return opts

    def _run_with_mocks(self, keywords, bridge_side_effect):
        from automating_wf.engine.pipeline import _collect_pinclicks_data_sync

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            patchers = {}
            mocks = {}
            for name, target in self._COMMON_PATCHES.items():
                p = patch(target)
                patchers[name] = p
                mocks[name] = p.start()

            mocks["setup"].return_value = {"authenticated": True, "setup_required": False}
            mocks["rank"].return_value = []
            mocks["load_entries"].return_value = []
            mocks["latest"].return_value = {}
            mocks["cached"].return_value = []
            mocks["run_dir"].return_value = run_dir
            mocks["bridge"].side_effect = bridge_side_effect

            try:
                result = _collect_pinclicks_data_sync(
                    opts=self._make_opts(),
                    selected_keywords=keywords,
                    run_id="test_run",
                )
                return result, mocks
            finally:
                for p in patchers.values():
                    p.stop()

    def test_circuit_breaker_trips_on_3_consecutive_failures(self) -> None:
        keywords = ["kw1", "kw2", "kw3", "kw4", "kw5"]
        result, mocks = self._run_with_mocks(
            keywords,
            ScraperError("No records", reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED),
        )

        # Bridge should be called exactly 3 times (trips after 3rd)
        self.assertEqual(mocks["bridge"].call_count, 3)
        cb_skipped = [s for s in result.skipped if s["reason"] == "circuit_breaker_tripped"]
        self.assertEqual(len(cb_skipped), 2)
        cb_keywords = {s["keyword"] for s in cb_skipped}
        self.assertEqual(cb_keywords, {"kw4", "kw5"})

    def test_circuit_breaker_trips_on_2_auth_failures(self) -> None:
        keywords = ["kw1", "kw2", "kw3", "kw4"]
        result, mocks = self._run_with_mocks(
            keywords,
            ScraperError("Auth failed", reason=PINCLICKS_SKIP_REASON_AUTHENTICATION_FAILED),
        )

        self.assertEqual(mocks["bridge"].call_count, 2)
        cb_skipped = [s for s in result.skipped if s["reason"] == "circuit_breaker_tripped"]
        self.assertEqual(len(cb_skipped), 2)

    def test_success_resets_circuit_breaker(self) -> None:
        from automating_wf.models.pinterest import SeedScrapeResult

        success_result = SeedScrapeResult(
            blog_suffix="TEST",
            seed_keyword="ok_kw",
            source_url="https://example.com",
            records=[],
            source_file="",
            scraped_at="2026-03-08T00:00:00Z",
        )
        # fail, fail, succeed, fail, fail — should NOT trip because success resets
        side_effects = [
            ScraperError("err", reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED),
            ScraperError("err", reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED),
            success_result,
            ScraperError("err", reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED),
            ScraperError("err", reason=PINCLICKS_SKIP_REASON_NO_RECORDS_EXTRACTED),
        ]
        keywords = ["kw1", "kw2", "kw3", "kw4", "kw5"]
        result, mocks = self._run_with_mocks(keywords, side_effects)

        self.assertEqual(mocks["bridge"].call_count, 5)
        cb_skipped = [s for s in result.skipped if s["reason"] == "circuit_breaker_tripped"]
        self.assertEqual(len(cb_skipped), 0)


class TestStage3Preflight(unittest.TestCase):
    """Tests Stage 3 Brave-session preflight behavior."""

    _PIPELINE = "automating_wf.engine.pipeline"
    _COMMON_PATCHES = TestCircuitBreaker._COMMON_PATCHES

    def _make_opts(self) -> MagicMock:
        opts = MagicMock()
        opts.blog_suffix = "TEST"
        opts.headed = False
        opts.pinclicks_max_records = 25
        opts.winners_count = 5
        return opts

    def test_authenticated_brave_session_allows_scraping_to_continue(self) -> None:
        from automating_wf.engine.pipeline import _collect_pinclicks_data_sync
        from automating_wf.models.pinterest import SeedScrapeResult

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            patchers = {}
            mocks = {}
            for name, target in self._COMMON_PATCHES.items():
                p = patch(target)
                patchers[name] = p
                mocks[name] = p.start()

            mocks["setup"].return_value = {"authenticated": True, "setup_required": False}
            mocks["rank"].return_value = []
            mocks["load_entries"].return_value = []
            mocks["latest"].return_value = {}
            mocks["cached"].return_value = []
            mocks["run_dir"].return_value = run_dir
            mocks["bridge"].return_value = SeedScrapeResult(
                blog_suffix="TEST",
                seed_keyword="kw1",
                source_url="https://example.com",
                records=[],
                source_file="",
                scraped_at="2026-03-08T00:00:00Z",
            )

            try:
                result = _collect_pinclicks_data_sync(
                    opts=self._make_opts(),
                    selected_keywords=["kw1"],
                    run_id="test_run",
                )
            finally:
                for p in patchers.values():
                    p.stop()

        preflight_skips = [s for s in result.skipped if s["keyword"] == "__preflight__"]
        self.assertEqual(len(preflight_skips), 0, "Authenticated Brave session should bypass preflight")
        self.assertTrue(mocks["bridge"].called, "Scraping should proceed")

    def test_setup_required_session_blocks_scraping(self) -> None:
        from automating_wf.engine.pipeline import _collect_pinclicks_data_sync

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            patchers = {}
            mocks = {}
            for name, target in self._COMMON_PATCHES.items():
                p = patch(target)
                patchers[name] = p
                mocks[name] = p.start()

            mocks["setup"].return_value = {
                "authenticated": False,
                "setup_required": True,
                "message": "PinClicks Stage 3 setup is required.",
            }
            mocks["rank"].return_value = []
            mocks["load_entries"].return_value = []
            mocks["latest"].return_value = {}
            mocks["cached"].return_value = []
            mocks["run_dir"].return_value = run_dir

            try:
                result = _collect_pinclicks_data_sync(
                    opts=self._make_opts(),
                    selected_keywords=["kw1"],
                    run_id="test_run",
                )
            finally:
                for p in patchers.values():
                    p.stop()

        preflight_skips = [s for s in result.skipped if s["keyword"] == "__preflight__"]
        self.assertEqual(len(preflight_skips), 1, "Setup-required session should block Stage 3")
        self.assertEqual(preflight_skips[0]["reason"], PINCLICKS_SKIP_REASON_AUTHENTICATION_SETUP_REQUIRED)
        self.assertFalse(mocks["bridge"].called, "Scraping should NOT proceed")


class TestCheckBraveSessionHealth(unittest.TestCase):
    """Tests for _check_brave_session_health reading Chromium Cookies DB."""

    # Chromium timestamps: microseconds since 1601-01-01 00:00:00 UTC.
    _WEBKIT_EPOCH_OFFSET = 11_644_473_600

    def _unix_to_webkit(self, unix_ts: float) -> int:
        return int((unix_ts + self._WEBKIT_EPOCH_OFFSET) * 1_000_000)

    def _create_cookies_db(self, db_path: Path, cookies: list[tuple[str, str, float, int]]) -> None:
        """Create a minimal Chromium Cookies DB with the given rows.

        Each cookie is (name, host_key, expires_unix, has_expires).
        """
        import sqlite3

        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE cookies ("
            "creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL, "
            "top_frame_site_key TEXT NOT NULL, name TEXT NOT NULL, "
            "value TEXT NOT NULL, encrypted_value BLOB NOT NULL, "
            "path TEXT NOT NULL, expires_utc INTEGER NOT NULL, "
            "is_secure INTEGER NOT NULL, is_httponly INTEGER NOT NULL, "
            "last_access_utc INTEGER NOT NULL, has_expires INTEGER NOT NULL, "
            "is_persistent INTEGER NOT NULL, priority INTEGER NOT NULL, "
            "samesite INTEGER NOT NULL, source_scheme INTEGER NOT NULL, "
            "source_port INTEGER NOT NULL, last_update_utc INTEGER NOT NULL, "
            "source_type INTEGER NOT NULL, has_cross_site_ancestor INTEGER NOT NULL)"
        )
        for name, host, expires_unix, has_exp in cookies:
            webkit_ts = self._unix_to_webkit(expires_unix) if has_exp else 0
            conn.execute(
                "INSERT INTO cookies VALUES (0,?,?,?,?,?,?,?,0,0,0,?,0,0,0,0,0,0,0,0)",
                (host, "", name, "", b"", "/", webkit_ts, has_exp),
            )
        conn.commit()
        conn.close()

    @patch("automating_wf.scrapers.brave_browser.pinflow_profile_dir", return_value=None)
    def test_missing_profile_returns_unhealthy(self, _mock: Any) -> None:
        from automating_wf.scrapers.pinclicks import _check_brave_session_health

        result = _check_brave_session_health()
        self.assertFalse(result["healthy"])
        self.assertTrue(result["needs_reauth"])
        self.assertEqual(result["expired_critical"], [])

    def test_missing_cookies_db_returns_unhealthy(self) -> None:
        from automating_wf.scrapers.pinclicks import _check_brave_session_health

        with TemporaryDirectory() as tmp:
            with patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value=tmp,
            ):
                result = _check_brave_session_health()
        self.assertFalse(result["healthy"])
        self.assertTrue(result["needs_reauth"])

    def test_all_cookies_valid(self) -> None:
        from automating_wf.scrapers.pinclicks import _check_brave_session_health

        future = time.time() + 86400
        cookies = [
            ("pinclicks_session", "app.pinclicks.com", future, 1),
            ("XSRF-TOKEN", "app.pinclicks.com", future, 1),
            ("cf_clearance", ".pinclicks.com", future, 1),
        ]
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "Default" / "Network" / "Cookies"
            self._create_cookies_db(db_path, cookies)
            with patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value=tmp,
            ):
                result = _check_brave_session_health()
        self.assertTrue(result["healthy"])
        self.assertFalse(result["needs_reauth"])
        self.assertTrue(result["cf_valid"])
        self.assertEqual(result["expired_critical"], [])
        self.assertEqual(result["expired_at"], {})

    def test_expired_critical_cookies(self) -> None:
        from automating_wf.scrapers.pinclicks import _check_brave_session_health

        past = time.time() - 86400
        future = time.time() + 86400
        cookies = [
            ("pinclicks_session", "app.pinclicks.com", past, 1),
            ("XSRF-TOKEN", "app.pinclicks.com", past, 1),
            ("cf_clearance", ".pinclicks.com", future, 1),
        ]
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "Default" / "Network" / "Cookies"
            self._create_cookies_db(db_path, cookies)
            with patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value=tmp,
            ):
                result = _check_brave_session_health()
        self.assertFalse(result["healthy"])
        self.assertTrue(result["needs_reauth"])
        self.assertTrue(result["cf_valid"])
        self.assertIn("pinclicks_session", result["expired_critical"])
        self.assertIn("XSRF-TOKEN", result["expired_critical"])

    def test_expired_at_contains_human_dates(self) -> None:
        from automating_wf.scrapers.pinclicks import _check_brave_session_health

        # Use a known timestamp: 2026-02-24 00:00:00 UTC
        known_ts = 1771977600.0
        cookies = [
            ("pinclicks_session", "app.pinclicks.com", known_ts, 1),
            ("XSRF-TOKEN", "app.pinclicks.com", known_ts, 1),
        ]
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "Default" / "Network" / "Cookies"
            self._create_cookies_db(db_path, cookies)
            with patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value=tmp,
            ):
                result = _check_brave_session_health()
        self.assertIn("pinclicks_session", result["expired_at"])
        self.assertIn("Feb", result["expired_at"]["pinclicks_session"])


class TestExpiredCookiesSkipBrowserLaunch(unittest.TestCase):
    """Test that expired cookies cause early return without launching Brave."""

    def test_expired_cookies_skip_browser_launch(self) -> None:
        from automating_wf.scrapers.pinclicks import ensure_pinclicks_brave_session

        expired_health = {
            "healthy": False,
            "cf_valid": True,
            "needs_reauth": True,
            "expired_critical": ["pinclicks_session", "XSRF-TOKEN"],
            "expired_at": {"pinclicks_session": "Feb 24, 2026", "XSRF-TOKEN": "Feb 24, 2026"},
        }
        json_health = {
            "healthy": False,
            "cf_valid": False,
            "needs_reauth": True,
            "expired_critical": [],
        }

        with (
            patch(
                "automating_wf.scrapers.pinclicks._check_brave_session_health",
                return_value=expired_health,
            ),
            patch(
                "automating_wf.scrapers.pinclicks._check_session_health",
                return_value=json_health,
            ),
            patch(
                "automating_wf.scrapers.pinclicks._has_pinclicks_credentials",
                return_value=False,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.BravePersistentBrowser",
            ) as mock_browser,
            patch(
                "automating_wf.scrapers.brave_browser.is_available",
                return_value=True,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value="/tmp/fake_profile",
            ),
        ):
            result = ensure_pinclicks_brave_session(
                headed=False,
                allow_manual_setup=False,
            )

        self.assertFalse(result["authenticated"])
        self.assertTrue(result["session_expired"])
        self.assertIn("pinclicks_session", result["expired_cookies"])
        self.assertIn("XSRF-TOKEN", result["expired_cookies"])
        self.assertIn("expired", result["message"].lower())
        mock_browser.assert_not_called()


    def test_healthy_cookies_skip_browser_launch(self) -> None:
        from automating_wf.scrapers.pinclicks import ensure_pinclicks_brave_session

        healthy = {
            "healthy": True,
            "cf_valid": True,
            "needs_reauth": False,
            "expired_critical": [],
            "expired_at": {},
        }
        json_health = {
            "healthy": True,
            "cf_valid": True,
            "needs_reauth": False,
            "expired_critical": [],
        }

        with (
            patch(
                "automating_wf.scrapers.pinclicks._check_brave_session_health",
                return_value=healthy,
            ),
            patch(
                "automating_wf.scrapers.pinclicks._check_session_health",
                return_value=json_health,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.BravePersistentBrowser",
            ) as mock_browser,
            patch(
                "automating_wf.scrapers.brave_browser.is_available",
                return_value=True,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.pinflow_profile_dir",
                return_value="/tmp/fake_profile",
            ),
        ):
            result = ensure_pinclicks_brave_session(
                headed=False,
                allow_manual_setup=False,
            )

        self.assertTrue(result["authenticated"])
        self.assertFalse(result.get("session_expired", False))
        self.assertIn("valid", result["message"].lower())
        mock_browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
