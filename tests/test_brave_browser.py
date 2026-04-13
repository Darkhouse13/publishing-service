"""Tests for the Brave persistent browser module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from automating_wf.scrapers.brave_browser import (
    BravePersistentBrowser,
    find_brave_path,
    find_brave_profile_dir,
    is_available,
    pinflow_profile_dir,
)


class TestFindBravePath:
    """Tests for find_brave_path()."""

    def test_returns_none_when_no_candidate_exists(self) -> None:
        with patch("os.path.isfile", return_value=False):
            assert find_brave_path() is None

    def test_returns_first_existing_candidate(self) -> None:
        sentinel = os.path.expandvars(
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
        )

        def mock_isfile(path: str) -> bool:
            return path == sentinel

        with patch("os.path.isfile", side_effect=mock_isfile):
            result = find_brave_path()
            assert result == sentinel

    def test_returns_linux_path_when_available(self) -> None:
        def mock_isfile(path: str) -> bool:
            return path == "/usr/bin/brave-browser"

        with patch("os.path.isfile", side_effect=mock_isfile):
            result = find_brave_path()
            assert result == "/usr/bin/brave-browser"


class TestFindBraveProfileDir:
    """Tests for find_brave_profile_dir()."""

    def test_returns_none_when_no_candidate_exists(self) -> None:
        with patch("os.path.isdir", return_value=False):
            assert find_brave_profile_dir() is None

    def test_returns_first_existing_candidate(self) -> None:
        sentinel = os.path.expandvars(
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"
        )

        def mock_isdir(path: str) -> bool:
            return path == sentinel

        with patch("os.path.isdir", side_effect=mock_isdir):
            result = find_brave_profile_dir()
            assert result == sentinel


class TestIsAvailable:
    """Tests for is_available()."""

    def test_available_when_both_exist(self) -> None:
        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value="/usr/bin/brave",
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value="/home/user/.config/BraveSoftware/Brave-Browser",
            ),
        ):
            assert is_available() is True

    def test_not_available_when_path_missing(self) -> None:
        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value=None,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value="/some/dir",
            ),
        ):
            assert is_available() is False


class TestPinFlowProfileDir:
    """Tests for pinflow_profile_dir()."""

    def test_returns_pinflow_subdirectory(self) -> None:
        with patch(
            "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
            return_value=r"C:\Users\tester\AppData\Local\BraveSoftware\Brave-Browser\User Data",
        ):
            assert pinflow_profile_dir().endswith(r"User Data\PinFlow")

    def test_not_available_when_profile_missing(self) -> None:
        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value="/usr/bin/brave",
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value=None,
            ),
        ):
            assert is_available() is False


class TestBravePersistentBrowser:
    """Tests for BravePersistentBrowser context manager."""

    def test_raises_when_brave_not_installed(self) -> None:
        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value=None,
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value=None,
            ),
        ):
            with pytest.raises(RuntimeError, match="Brave browser is not installed"):
                with BravePersistentBrowser(headed=False) as _ctx:
                    pass

    def test_non_interactive_mode_forces_non_headless_and_moves_window_offscreen(self) -> None:
        launch_mock = MagicMock(return_value=MagicMock())
        chromium_mock = MagicMock(launch_persistent_context=launch_mock)
        playwright_instance = MagicMock(chromium=chromium_mock)
        sync_playwright_mock = MagicMock()
        sync_playwright_mock.start.return_value = playwright_instance

        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value=r"C:\Brave\brave.exe",
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value=r"C:\Users\tester\AppData\Local\BraveSoftware\Brave-Browser\User Data",
            ),
            patch("automating_wf.scrapers.brave_browser.os.makedirs"),
            patch("playwright.sync_api.sync_playwright", return_value=sync_playwright_mock),
        ):
            with BravePersistentBrowser(headed=False):
                pass

        kwargs = launch_mock.call_args.kwargs
        assert kwargs["headless"] is False
        assert "--window-position=-2000,-2000" in kwargs["args"]
        assert "--window-size=1366,768" in kwargs["args"]

    def test_interactive_mode_does_not_apply_offscreen_window_position(self) -> None:
        launch_mock = MagicMock(return_value=MagicMock())
        chromium_mock = MagicMock(launch_persistent_context=launch_mock)
        playwright_instance = MagicMock(chromium=chromium_mock)
        sync_playwright_mock = MagicMock()
        sync_playwright_mock.start.return_value = playwright_instance

        with (
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_path",
                return_value=r"C:\Brave\brave.exe",
            ),
            patch(
                "automating_wf.scrapers.brave_browser.find_brave_profile_dir",
                return_value=r"C:\Users\tester\AppData\Local\BraveSoftware\Brave-Browser\User Data",
            ),
            patch("automating_wf.scrapers.brave_browser.os.makedirs"),
            patch("playwright.sync_api.sync_playwright", return_value=sync_playwright_mock),
        ):
            with BravePersistentBrowser(headed=True):
                pass

        kwargs = launch_mock.call_args.kwargs
        assert kwargs["headless"] is False
        assert "--window-position=-2000,-2000" not in kwargs["args"]
