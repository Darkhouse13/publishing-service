"""Tests for app.crypto – Fernet encrypt/decrypt round-trip and error handling."""

import pytest

from app.crypto import decrypt, encrypt


class TestEncryptDecryptRoundTrip:
    """Verify that encrypt/decrypt produces the original plaintext."""

    def test_basic_round_trip(self) -> None:
        plain = "my-secret-api-key"
        token = encrypt(plain)
        assert isinstance(token, str)
        assert token != plain
        assert decrypt(token) == plain

    def test_empty_string(self) -> None:
        token = encrypt("")
        assert decrypt(token) == ""

    def test_long_value(self) -> None:
        plain = "x" * 10_000
        assert decrypt(encrypt(plain)) == plain

    def test_unicode_characters(self) -> None:
        plain = "kłucze-api-日本語-🔒"
        assert decrypt(encrypt(plain)) == plain

    def test_special_characters(self) -> None:
        plain = "p@$$w0rd!#%^&*()"
        assert decrypt(encrypt(plain)) == plain

    def test_different_plaintexts_produce_different_tokens(self) -> None:
        tok1 = encrypt("alpha")
        tok2 = encrypt("beta")
        assert tok1 != tok2


class TestDecryptErrors:
    """Verify error handling on bad input."""

    def test_decrypt_invalid_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt("not-a-valid-fernet-token")

    def test_decrypt_garbage_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            decrypt("gAAAAABogus==")
