"""Brave persistent browser context for PinClicks scraping.

Stage 3 relies on a real Brave installation with a dedicated persistent
``PinFlow`` profile. The browser always runs non-headless so PinClicks and
Cloudflare see a genuine browser window; non-interactive runs are moved
off-screen instead of using headless mode.
"""

from __future__ import annotations

import os
from typing import Any


_BRAVE_EXECUTABLE_CANDIDATES = (
    # Windows
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    # Linux
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    # macOS
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

_BRAVE_PROFILE_CANDIDATES = (
    # Windows
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
    # Linux
    os.path.expanduser("~/.config/BraveSoftware/Brave-Browser"),
    # macOS
    os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser"),
)

_PINFLOW_PROFILE_NAME = "PinFlow"
_OFFSCREEN_WINDOW_POSITION = "-2000,-2000"


def find_brave_path() -> str | None:
    """Return the Brave executable path, or None if not found."""
    for candidate in _BRAVE_EXECUTABLE_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_brave_profile_dir() -> str | None:
    """Return the Brave user data directory, or None if not found."""
    for candidate in _BRAVE_PROFILE_CANDIDATES:
        if os.path.isdir(candidate):
            return candidate
    return None


def is_available() -> bool:
    """Return True if Brave browser is installed and has a profile directory."""
    return find_brave_path() is not None and find_brave_profile_dir() is not None


def pinflow_profile_dir() -> str | None:
    """Return the dedicated PinFlow Brave user data directory, if available."""
    profile_root = find_brave_profile_dir()
    if not profile_root:
        return None
    return os.path.join(profile_root, _PINFLOW_PROFILE_NAME)


class BravePersistentBrowser:
    """Context manager that launches real Brave with a persistent profile.

    Usage::

        with BravePersistentBrowser(headed=True) as context:
            page = context.new_page()
            page.goto("https://app.pinclicks.com")
            ...
    """

    def __init__(self, *, headed: bool = False) -> None:
        self.headed = headed
        self._playwright: Any | None = None
        self._context: Any | None = None

    def __enter__(self) -> Any:
        brave_path = find_brave_path()
        profile_dir = find_brave_profile_dir()
        if not brave_path or not profile_dir:
            raise RuntimeError(
                "Brave browser is not installed or profile directory not found. "
                f"Executable: {brave_path}, Profile: {profile_dir}"
            )

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        pinflow_profile = os.path.join(profile_dir, _PINFLOW_PROFILE_NAME)
        os.makedirs(pinflow_profile, exist_ok=True)

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
        if not self.headed:
            launch_args.extend(
                [
                    f"--window-position={_OFFSCREEN_WINDOW_POSITION}",
                    "--window-size=1366,768",
                ]
            )

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=pinflow_profile,
            executable_path=brave_path,
            headless=False,
            viewport={"width": 1366, "height": 768},
            args=launch_args,
        )
        self._context.set_default_navigation_timeout(60_000)
        return self._context

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
