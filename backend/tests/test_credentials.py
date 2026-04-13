"""Tests for Credential CRUD endpoints.

Fulfils validation assertions:
- VAL-CRED-001: Create credential with encryption
- VAL-CRED-002: Upsert credential behavior
- VAL-CRED-003: List credentials (masked)
- VAL-CRED-004: Delete credential
- VAL-CRED-008: Encryption at rest verification
"""

import uuid
from typing import Any

from httpx import AsyncClient

from app.crypto import decrypt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CREDENTIAL_PAYLOAD: dict[str, str] = {
    "provider": "openai",
    "key_name": "api_key",
    "value": "sk-proj-test-123",
}


async def _create_credential(
    client: AsyncClient,
    provider: str = "openai",
    key_name: str = "api_key",
    value: str = "sk-proj-test-123",
) -> dict[str, Any]:
    """Helper to create a credential and return the JSON response."""
    resp = await client.post(
        "/api/v1/credentials",
        json={"provider": provider, "key_name": key_name, "value": value},
    )
    assert resp.status_code in (200, 201)
    return dict(resp.json())


# ===========================================================================
# VAL-CRED-001: Create Credential with Encryption
# ===========================================================================


class TestCreateCredential:
    """Tests for POST /api/v1/credentials."""

    async def test_create_credential_returns_201(self, client: AsyncClient) -> None:
        """POST /api/v1/credentials returns 201 for new credential."""
        resp = await client.post("/api/v1/credentials", json=_CREDENTIAL_PAYLOAD)
        assert resp.status_code == 201

    async def test_create_credential_response_has_id(self, client: AsyncClient) -> None:
        """Response contains a valid UUID id."""
        data = await _create_credential(client)
        assert "id" in data
        # Validate it's a proper UUID
        uuid.UUID(data["id"])

    async def test_create_credential_response_has_provider(self, client: AsyncClient) -> None:
        """Response contains the provider field."""
        data = await _create_credential(client)
        assert data["provider"] == "openai"

    async def test_create_credential_response_has_key_name(self, client: AsyncClient) -> None:
        """Response contains the key_name field."""
        data = await _create_credential(client)
        assert data["key_name"] == "api_key"

    async def test_create_credential_response_has_created_at(self, client: AsyncClient) -> None:
        """Response contains the created_at timestamp."""
        data = await _create_credential(client)
        assert "created_at" in data
        assert data["created_at"] is not None

    async def test_create_credential_response_has_updated_at(self, client: AsyncClient) -> None:
        """Response contains the updated_at timestamp."""
        data = await _create_credential(client)
        assert "updated_at" in data
        assert data["updated_at"] is not None

    async def test_create_credential_no_value_in_response(self, client: AsyncClient) -> None:
        """VAL-CRED-001: The value field must NOT be present in the response."""
        resp = await client.post("/api/v1/credentials", json=_CREDENTIAL_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert "value" not in data

    async def test_create_credential_value_encrypted_in_db(
        self, client: AsyncClient, db_session: Any
    ) -> None:
        """VAL-CRED-008: Credential value is stored encrypted in the database."""
        from sqlalchemy import text

        await _create_credential(client, provider="enc_test", key_name="secret", value="plaintext-value")

        result = await db_session.execute(
            text("SELECT value_encrypted FROM credentials WHERE provider = 'enc_test'")
        )
        row = result.fetchone()
        assert row is not None
        encrypted_value = row[0]
        # Encrypted value should NOT be the plaintext
        assert encrypted_value != "plaintext-value"
        # Encrypted value should be decryptable back to plaintext
        decrypted = decrypt(encrypted_value)
        assert decrypted == "plaintext-value"

    async def test_create_credential_missing_provider_returns_422(self, client: AsyncClient) -> None:
        """Missing required provider field returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"key_name": "api_key", "value": "test"},
        )
        assert resp.status_code == 422

    async def test_create_credential_missing_key_name_returns_422(self, client: AsyncClient) -> None:
        """Missing required key_name field returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "value": "test"},
        )
        assert resp.status_code == 422

    async def test_create_credential_missing_value_returns_422(self, client: AsyncClient) -> None:
        """Missing required value field returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "api_key"},
        )
        assert resp.status_code == 422

    async def test_create_credential_empty_provider_returns_422(self, client: AsyncClient) -> None:
        """Empty provider string returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "", "key_name": "api_key", "value": "test"},
        )
        assert resp.status_code == 422

    async def test_create_credential_empty_key_name_returns_422(self, client: AsyncClient) -> None:
        """Empty key_name string returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "", "value": "test"},
        )
        assert resp.status_code == 422

    async def test_create_credential_empty_value_returns_422(self, client: AsyncClient) -> None:
        """Empty value string returns 422."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "api_key", "value": ""},
        )
        assert resp.status_code == 422


# ===========================================================================
# VAL-CRED-002: Upsert Credential Behavior
# ===========================================================================


class TestUpsertCredential:
    """Tests for upsert (create-or-update) behavior on POST /api/v1/credentials."""

    async def test_upsert_creates_new_when_not_exists(self, client: AsyncClient) -> None:
        """First POST for a (provider, key_name) pair creates a new record (201)."""
        resp = await client.post("/api/v1/credentials", json=_CREDENTIAL_PAYLOAD)
        assert resp.status_code == 201

    async def test_upsert_updates_existing_when_exists(self, client: AsyncClient) -> None:
        """VAL-CRED-002: Second POST for same (provider, key_name) returns 200."""
        await _create_credential(client)
        resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "api_key", "value": "new-sk-proj-456"},
        )
        assert resp.status_code == 200

    async def test_upsert_preserves_same_id(self, client: AsyncClient) -> None:
        """Upserting a credential preserves the original record ID."""
        data1 = await _create_credential(client)
        original_id = data1["id"]

        data2_resp = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "api_key", "value": "new-sk-proj-456"},
        )
        assert data2_resp.status_code == 200
        data2 = data2_resp.json()
        assert data2["id"] == original_id

    async def test_upsert_no_duplicate_records(self, client: AsyncClient) -> None:
        """VAL-CRED-002: After upsert, listing shows only one entry for the pair."""
        await _create_credential(client)
        await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "key_name": "api_key", "value": "new-sk-proj-456"},
        )

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        openai_keys = [c for c in data if c["provider"] == "openai" and c["key_name"] == "api_key"]
        assert len(openai_keys) == 1

    async def test_upsert_updates_encrypted_value(
        self, client: AsyncClient, db_session: Any
    ) -> None:
        """Upserting updates the encrypted value in the database."""
        from sqlalchemy import text

        await _create_credential(client, provider="upsert_test", key_name="key1", value="old-value")

        await client.post(
            "/api/v1/credentials",
            json={"provider": "upsert_test", "key_name": "key1", "value": "new-value"},
        )

        result = await db_session.execute(
            text("SELECT value_encrypted FROM credentials WHERE provider = 'upsert_test'")
        )
        row = result.fetchone()
        assert row is not None
        decrypted = decrypt(row[0])
        assert decrypted == "new-value"

    async def test_different_providers_create_separate_records(self, client: AsyncClient) -> None:
        """Different providers create separate credential records."""
        await _create_credential(client, provider="openai", key_name="api_key", value="val1")
        await _create_credential(client, provider="deepseek", key_name="api_key", value="val2")

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        assert len(data) == 2

    async def test_different_key_names_create_separate_records(self, client: AsyncClient) -> None:
        """Different key_names for the same provider create separate records."""
        await _create_credential(client, provider="openai", key_name="api_key", value="val1")
        await _create_credential(client, provider="openai", key_name="org_id", value="val2")

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        assert len(data) == 2


# ===========================================================================
# VAL-CRED-003: List Credentials (Masked)
# ===========================================================================


class TestListCredentials:
    """Tests for GET /api/v1/credentials."""

    async def test_list_credentials_returns_200(self, client: AsyncClient) -> None:
        """GET /api/v1/credentials returns 200."""
        resp = await client.get("/api/v1/credentials")
        assert resp.status_code == 200

    async def test_list_credentials_empty(self, client: AsyncClient) -> None:
        """Empty list when no credentials exist."""
        resp = await client.get("/api/v1/credentials")
        assert resp.json() == []

    async def test_list_credentials_returns_created(self, client: AsyncClient) -> None:
        """List includes created credentials."""
        await _create_credential(client, provider="openai", key_name="key1", value="val1")
        await _create_credential(client, provider="deepseek", key_name="key2", value="val2")

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        assert len(data) == 2

    async def test_list_credentials_no_value_field(self, client: AsyncClient) -> None:
        """VAL-CRED-003: No object contains the value field or plaintext secret."""
        await _create_credential(client, provider="openai", key_name="api_key", value="secret-val")

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        for item in data:
            assert "value" not in item

    async def test_list_credentials_has_required_fields(self, client: AsyncClient) -> None:
        """Each list item has id, provider, key_name, created_at, updated_at."""
        await _create_credential(client)

        resp = await client.get("/api/v1/credentials")
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert "id" in item
        assert "provider" in item
        assert "key_name" in item
        assert "created_at" in item
        assert "updated_at" in item

    async def test_list_credentials_no_plaintext_secrets(self, client: AsyncClient) -> None:
        """VAL-CRED-003: Plaintext secrets must not appear anywhere in the response."""
        plaintext = "test-plaintext-value-that-must-not-leak"
        await _create_credential(client, provider="secret_test", key_name="key", value=plaintext)

        resp = await client.get("/api/v1/credentials")
        text = resp.text
        assert plaintext not in text


# ===========================================================================
# VAL-CRED-004: Delete Credential
# ===========================================================================


class TestDeleteCredential:
    """Tests for DELETE /api/v1/credentials/{id}."""

    async def test_delete_credential_returns_204(self, client: AsyncClient) -> None:
        """DELETE returns 204 No Content for existing credential."""
        data = await _create_credential(client)
        resp = await client.delete(f"/api/v1/credentials/{data['id']}")
        assert resp.status_code == 204

    async def test_delete_credential_removes_from_list(self, client: AsyncClient) -> None:
        """VAL-CRED-004: Deleted credential no longer appears in list."""
        data = await _create_credential(client, provider="delete_test", key_name="key1")
        await client.delete(f"/api/v1/credentials/{data['id']}")

        resp = await client.get("/api/v1/credentials")
        items = resp.json()
        assert all(c["provider"] != "delete_test" for c in items)

    async def test_delete_nonexistent_credential_returns_404(self, client: AsyncClient) -> None:
        """Deleting a non-existent credential returns 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/credentials/{fake_id}")
        assert resp.status_code == 404

    async def test_delete_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Deleting with invalid UUID returns 422."""
        resp = await client.delete("/api/v1/credentials/not-a-uuid")
        assert resp.status_code == 422

    async def test_delete_twice_returns_404(self, client: AsyncClient) -> None:
        """Deleting the same credential twice returns 404 on second attempt."""
        data = await _create_credential(client)
        await client.delete(f"/api/v1/credentials/{data['id']}")
        resp = await client.delete(f"/api/v1/credentials/{data['id']}")
        assert resp.status_code == 404


# ===========================================================================
# VAL-CRED-008: Encryption at Rest (additional coverage)
# ===========================================================================


class TestEncryptionAtRest:
    """Tests verifying that credentials are encrypted at rest (VAL-CRED-008)."""

    async def test_stored_value_is_fernet_token(
        self, client: AsyncClient, db_session: Any
    ) -> None:
        """The stored value is a valid Fernet token (base64-encoded)."""
        from sqlalchemy import text

        await _create_credential(client, provider="fernet_test", key_name="key1", value="my-secret")

        result = await db_session.execute(
            text("SELECT value_encrypted FROM credentials WHERE provider = 'fernet_test'")
        )
        row = result.fetchone()
        assert row is not None
        encrypted = row[0]
        # Fernet tokens are base64-encoded and start with 'gAAAAA' by default
        assert encrypted.startswith("gAAAAA") or len(encrypted) > 20

    async def test_different_values_produce_different_tokens(
        self, client: AsyncClient, db_session: Any
    ) -> None:
        """Encrypting different values produces different encrypted tokens."""
        from sqlalchemy import text

        await _create_credential(client, provider="diff1", key_name="k", value="value-a")
        await _create_credential(client, provider="diff2", key_name="k", value="value-b")

        result = await db_session.execute(
            text("SELECT provider, value_encrypted FROM credentials WHERE provider IN ('diff1', 'diff2')")
        )
        rows = {row[0]: row[1] for row in result.fetchall()}
        assert rows["diff1"] != rows["diff2"]
