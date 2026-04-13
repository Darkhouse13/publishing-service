"""Shared pytest fixtures for the backend test suite."""

import os

import pytest


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee an ``ENCRYPTION_KEY`` is set for every test.

    If the environment already provides one (e.g. via ``backend/.env``) we
    leave it untouched.  Otherwise we generate a fresh Fernet key so that
    crypto tests work in isolated CI environments.
    """
    if not os.getenv("ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        # Also patch the lazily-initialised module-level Fernet so it picks
        # up the new key on next access.
        import app.crypto as _crypto_mod

        _crypto_mod._fernet = None
