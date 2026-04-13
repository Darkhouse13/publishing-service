"""Tests for the ProviderFactory: credential resolution, provider instantiation,
registry management, and error handling.

Covers:
- VAL-CRED-005: LLM Provider Instantiation
- VAL-CRED-006: Image Provider Instantiation
- VAL-CRED-007: WP Provider Instantiation
- VAL-CRED-009: Decryption on Demand
- VAL-CROSS-001: Blog-to-Provider Credential Resolution
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt
from app.models.credential import Credential
from app.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
    WPMediaResult,
    WPPostResult,
    WordPressProvider,
)
from app.providers.factory import (
    ProviderFactory,
    get_image_provider,
    get_llm_provider,
    get_wordpress_provider,
)


# ---------------------------------------------------------------------------
# Minimal concrete provider stubs for testing
# ---------------------------------------------------------------------------


class StubLLMProvider(LLMProvider):
    """A minimal LLM provider that records its init args."""

    def __init__(self, *, api_key: str, **kwargs: object) -> None:
        self.api_key = api_key
        self.kwargs = kwargs

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return LLMResponse(text="stub", model="stub-model")

    async def close(self) -> None:
        pass


class StubImageProvider(ImageProvider):
    """A minimal Image provider that records its init args."""

    def __init__(self, *, api_key: str, **kwargs: object) -> None:
        self.api_key = api_key
        self.kwargs = kwargs

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> ImageResult:
        return ImageResult(url="https://example.com/stub.png")

    async def close(self) -> None:
        pass


class StubWPProvider(WordPressProvider):
    """A minimal WordPress provider that records its init args."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        **kwargs: object,
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.kwargs = kwargs

    async def create_post(
        self,
        title: str,
        content: str,
        *,
        status: str = "draft",
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: object,
    ) -> WPPostResult:
        return WPPostResult(id=1, url=f"{self.base_url}/posts/1")

    async def update_post(
        self,
        post_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: object,
    ) -> WPPostResult:
        return WPPostResult(id=post_id, url=f"{self.base_url}/posts/{post_id}")

    async def upload_media(
        self,
        file_data: bytes,
        filename: str,
        *,
        media_type: str = "image/jpeg",
        alt_text: str = "",
        title: str | None = None,
    ) -> WPMediaResult:
        return WPMediaResult(id=1, url="https://example.com/media/1")

    async def list_categories(
        self,
        *,
        per_page: int = 100,
        search: str | None = None,
    ) -> list[dict[str, object]]:
        return [{"id": 1, "name": "Uncategorized", "slug": "uncategorized"}]

    async def get_post(self, post_id: int) -> WPPostResult:
        return WPPostResult(id=post_id, url=f"{self.base_url}/posts/{post_id}")

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def register_stubs() -> Generator[None, None, None]:
    """Register stub providers and clean up after the test."""
    from app.providers import factory as factory_mod

    # Save original registries
    orig_llm = factory_mod._LLM_REGISTRY.copy()
    orig_image = factory_mod._IMAGE_REGISTRY.copy()
    orig_wp = factory_mod._WP_REGISTRY.copy()

    ProviderFactory.register_llm("deepseek", StubLLMProvider)
    ProviderFactory.register_llm("openai", StubLLMProvider)
    ProviderFactory.register_image("fal", StubImageProvider)
    ProviderFactory.register_wordpress("wp_rest", StubWPProvider)

    yield

    # Restore original registries
    factory_mod._LLM_REGISTRY.clear()
    factory_mod._LLM_REGISTRY.update(orig_llm)
    factory_mod._IMAGE_REGISTRY.clear()
    factory_mod._IMAGE_REGISTRY.update(orig_image)
    factory_mod._WP_REGISTRY.clear()
    factory_mod._WP_REGISTRY.update(orig_wp)


@pytest_asyncio.fixture()
async def seed_credentials(db_session: AsyncSession) -> dict[str, Credential]:
    """Seed the test database with sample encrypted credentials."""
    creds: dict[str, Credential] = {}

    samples = [
        ("deepseek", "api_key", "sk-deepseek-secret-123"),
        ("openai", "api_key", "sk-openai-secret-456"),
        ("fal", "api_key", "fal-key-secret-789"),
        ("wp_rest", "application_password", "wp-app-password-xyz"),
    ]

    for provider, key_name, value in samples:
        cred = Credential(
            provider=provider,
            key_name=key_name,
            value_encrypted=encrypt(value),
        )
        db_session.add(cred)
        creds[provider] = cred

    await db_session.flush()
    return creds


# ===========================================================================
# Tests: Registry Management
# ===========================================================================


class TestRegistry:
    """Tests for provider registration and listing."""

    def test_register_llm(self, register_stubs: None) -> None:
        """Registering an LLM provider makes it appear in the list."""
        assert "deepseek" in ProviderFactory.list_llm_providers()
        assert "openai" in ProviderFactory.list_llm_providers()

    def test_register_image(self, register_stubs: None) -> None:
        """Registering an Image provider makes it appear in the list."""
        assert "fal" in ProviderFactory.list_image_providers()

    def test_register_wordpress(self, register_stubs: None) -> None:
        """Registering a WordPress provider makes it appear in the list."""
        assert "wp_rest" in ProviderFactory.list_wordpress_providers()

    def test_list_llm_providers_sorted(self, register_stubs: None) -> None:
        """List of LLM providers is sorted alphabetically."""
        names = ProviderFactory.list_llm_providers()
        assert names == sorted(names)

    def test_list_image_providers_sorted(self, register_stubs: None) -> None:
        """List of Image providers is sorted alphabetically."""
        names = ProviderFactory.list_image_providers()
        assert names == sorted(names)

    def test_list_wordpress_providers_sorted(self, register_stubs: None) -> None:
        """List of WordPress providers is sorted alphabetically."""
        names = ProviderFactory.list_wordpress_providers()
        assert names == sorted(names)

    def test_register_replaces_existing(self, register_stubs: None) -> None:
        """Re-registering a provider name replaces the previous class."""

        class AnotherLLM(LLMProvider):
            async def generate(self, prompt: str, **kw: object) -> LLMResponse:
                return LLMResponse(text="", model="")

            async def close(self) -> None:
                pass

        ProviderFactory.register_llm("deepseek", AnotherLLM)
        assert "deepseek" in ProviderFactory.list_llm_providers()

    def test_empty_registry_without_registrations(self) -> None:
        """Without any registrations the lists are empty."""
        # Fresh import context → no stubs registered
        from app.providers import factory as factory_mod

        # Save and clear
        orig = factory_mod._LLM_REGISTRY.copy()
        factory_mod._LLM_REGISTRY.clear()
        assert ProviderFactory.list_llm_providers() == []
        factory_mod._LLM_REGISTRY.update(orig)


# ===========================================================================
# Tests: Credential Resolution (VAL-CRED-009)
# ===========================================================================


class TestCredentialResolution:
    """Tests for decrypting credentials on demand (VAL-CRED-009)."""

    @pytest.mark.asyncio
    async def test_resolve_credential_decrypts_correctly(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """The factory decrypts the stored credential to the original value."""
        factory = ProviderFactory(db_session)
        plaintext = await factory._resolve_credential("deepseek", "api_key")
        assert plaintext == "sk-deepseek-secret-123"

    @pytest.mark.asyncio
    async def test_resolve_credential_uses_default_key_name(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """When key_name is not specified, the factory uses the default."""
        factory = ProviderFactory(db_session)
        # deepseek's default key_name is "api_key"
        plaintext = await factory._resolve_credential("deepseek")
        assert plaintext == "sk-deepseek-secret-123"

    @pytest.mark.asyncio
    async def test_resolve_credential_raises_for_missing(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Missing credential raises a descriptive ValueError."""
        factory = ProviderFactory(db_session)
        with pytest.raises(ValueError, match="No credential found"):
            await factory._resolve_credential("nonexistent_provider")

    @pytest.mark.asyncio
    async def test_resolve_credential_custom_key_name(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """A credential with a custom key_name can be resolved."""
        # Seed a credential with a custom key_name
        cred = Credential(
            provider="custom_provider",
            key_name="custom_key",
            value_encrypted=encrypt("my-custom-value"),
        )
        db_session.add(cred)
        await db_session.flush()

        factory = ProviderFactory(db_session)
        plaintext = await factory._resolve_credential("custom_provider", "custom_key")
        assert plaintext == "my-custom-value"


# ===========================================================================
# Tests: LLM Provider Instantiation (VAL-CRED-005)
# ===========================================================================


class TestLLMProviderInstantiation:
    """Tests for creating LLM providers from stored credentials (VAL-CRED-005)."""

    @pytest.mark.asyncio
    async def test_get_llm_provider_deepseek(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Factory creates a DeepSeek LLM provider with decrypted API key."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("deepseek")

        assert isinstance(provider, StubLLMProvider)
        assert provider.api_key == "sk-deepseek-secret-123"

    @pytest.mark.asyncio
    async def test_get_llm_provider_openai(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Factory creates an OpenAI LLM provider with decrypted API key."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("openai")

        assert isinstance(provider, StubLLMProvider)
        assert provider.api_key == "sk-openai-secret-456"

    @pytest.mark.asyncio
    async def test_get_llm_provider_unknown_raises(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Requesting an unregistered LLM provider raises ValueError."""
        factory = ProviderFactory(db_session)
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            await factory.get_llm_provider("nonexistent")

    @pytest.mark.asyncio
    async def test_get_llm_provider_missing_credential_raises(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """If the credential doesn't exist, ValueError is raised."""
        # Register a provider but don't seed a credential
        ProviderFactory.register_llm("mistral", StubLLMProvider)
        factory = ProviderFactory(db_session)
        with pytest.raises(ValueError, match="No credential found"):
            await factory.get_llm_provider("mistral")

    @pytest.mark.asyncio
    async def test_get_llm_provider_returns_correct_type(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """The returned provider is an instance of LLMProvider ABC."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("deepseek")
        assert isinstance(provider, LLMProvider)

    @pytest.mark.asyncio
    async def test_get_llm_provider_with_extra_kwargs(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Extra kwargs are forwarded to the concrete provider constructor."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("deepseek", base_url="https://custom.api.com")
        assert isinstance(provider, StubLLMProvider)
        assert provider.kwargs.get("base_url") == "https://custom.api.com"


# ===========================================================================
# Tests: Image Provider Instantiation (VAL-CRED-006)
# ===========================================================================


class TestImageProviderInstantiation:
    """Tests for creating Image providers from stored credentials (VAL-CRED-006)."""

    @pytest.mark.asyncio
    async def test_get_image_provider_fal(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Factory creates a Fal Image provider with decrypted API key."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_image_provider("fal")

        assert isinstance(provider, StubImageProvider)
        assert provider.api_key == "fal-key-secret-789"

    @pytest.mark.asyncio
    async def test_get_image_provider_unknown_raises(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Requesting an unregistered Image provider raises ValueError."""
        factory = ProviderFactory(db_session)
        with pytest.raises(ValueError, match="Unknown Image provider"):
            await factory.get_image_provider("dalle")

    @pytest.mark.asyncio
    async def test_get_image_provider_returns_correct_type(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """The returned provider is an instance of ImageProvider ABC."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_image_provider("fal")
        assert isinstance(provider, ImageProvider)


# ===========================================================================
# Tests: WordPress Provider Instantiation (VAL-CRED-007)
# ===========================================================================


class TestWPProviderInstantiation:
    """Tests for creating WordPress providers from stored credentials (VAL-CRED-007)."""

    @pytest.mark.asyncio
    async def test_get_wp_provider(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Factory creates a WP REST provider with decrypted password."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url="https://blog.example.com",
            username="admin",
        )

        assert isinstance(provider, StubWPProvider)
        assert provider.base_url == "https://blog.example.com"
        assert provider.username == "admin"
        assert provider.password == "wp-app-password-xyz"

    @pytest.mark.asyncio
    async def test_get_wp_provider_custom_key_name(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """WP provider can resolve a credential with a custom key_name."""
        cred = Credential(
            provider="wp_rest",
            key_name="staging_password",
            value_encrypted=encrypt("staging-pass-123"),
        )
        db_session.add(cred)
        await db_session.flush()

        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url="https://staging.example.com",
            username="editor",
            key_name="staging_password",
        )
        assert isinstance(provider, StubWPProvider)
        assert provider.password == "staging-pass-123"

    @pytest.mark.asyncio
    async def test_get_wp_provider_unknown_raises(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Requesting an unregistered WP provider raises ValueError."""
        factory = ProviderFactory(db_session)
        with pytest.raises(ValueError, match="Unknown WordPress provider"):
            await factory.get_wordpress_provider(
                "nonexistent",
                base_url="https://example.com",
                username="admin",
            )

    @pytest.mark.asyncio
    async def test_get_wp_provider_returns_correct_type(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """The returned provider is an instance of WordPressProvider ABC."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url="https://blog.example.com",
            username="admin",
        )
        assert isinstance(provider, WordPressProvider)

    @pytest.mark.asyncio
    async def test_get_wp_provider_password_not_in_logs(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Decrypted password should not appear in __repr__ or string output."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url="https://blog.example.com",
            username="admin",
        )
        # Verify password is accessible but not in string representation
        assert isinstance(provider, StubWPProvider)
        assert provider.password == "wp-app-password-xyz"
        assert "wp-app-password-xyz" not in repr(provider)
        assert "wp-app-password-xyz" not in str(provider)


# ===========================================================================
# Tests: Module-level convenience functions
# ===========================================================================


class TestConvenienceFunctions:
    """Tests for get_llm_provider, get_image_provider, get_wordpress_provider."""

    @pytest.mark.asyncio
    async def test_get_llm_provider_function(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Module-level get_llm_provider creates a provider correctly."""
        provider = await get_llm_provider(db_session, "deepseek")
        assert isinstance(provider, StubLLMProvider)
        assert provider.api_key == "sk-deepseek-secret-123"

    @pytest.mark.asyncio
    async def test_get_image_provider_function(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Module-level get_image_provider creates a provider correctly."""
        provider = await get_image_provider(db_session, "fal")
        assert isinstance(provider, StubImageProvider)
        assert provider.api_key == "fal-key-secret-789"

    @pytest.mark.asyncio
    async def test_get_wordpress_provider_function(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Module-level get_wordpress_provider creates a provider correctly."""
        provider = await get_wordpress_provider(
            db_session,
            "wp_rest",
            base_url="https://blog.example.com",
            username="admin",
        )
        assert isinstance(provider, StubWPProvider)
        assert provider.password == "wp-app-password-xyz"


# ===========================================================================
# Tests: Decryption on Demand (VAL-CRED-009)
# ===========================================================================


class TestDecryptionOnDemand:
    """Tests verifying credentials are decrypted only when needed (VAL-CRED-009)."""

    @pytest.mark.asyncio
    async def test_stored_credential_is_encrypted(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Verify the stored value in the DB is NOT plaintext."""
        cred = seed_credentials["deepseek"]
        assert cred.value_encrypted != "sk-deepseek-secret-123"
        # Encrypted values are base64-encoded Fernet tokens
        assert len(cred.value_encrypted) > len("sk-deepseek-secret-123")

    @pytest.mark.asyncio
    async def test_factory_decrypts_for_provider(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """The factory successfully decrypts when creating a provider."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("deepseek")
        # Provider received the decrypted key, not the encrypted blob
        assert isinstance(provider, StubLLMProvider)
        assert provider.api_key == "sk-deepseek-secret-123"
        assert provider.api_key != seed_credentials["deepseek"].value_encrypted

    @pytest.mark.asyncio
    async def test_multiple_decrypts_same_result(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Multiple factory calls produce the same decrypted credential."""
        factory = ProviderFactory(db_session)
        p1 = await factory.get_llm_provider("openai")
        p2 = await factory.get_llm_provider("openai")
        assert isinstance(p1, StubLLMProvider)
        assert isinstance(p2, StubLLMProvider)
        assert p1.api_key == p2.api_key == "sk-openai-secret-456"


# ===========================================================================
# Tests: Blog-to-Provider Credential Resolution (VAL-CROSS-001)
# ===========================================================================


class TestBlogToProviderResolution:
    """Tests for resolving WordPress credentials from blog configuration.

    This simulates the flow where a blog record stores connection details
    and the factory resolves the corresponding credential.
    """

    @pytest.mark.asyncio
    async def test_blog_wp_credentials_resolved(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Simulate blog → WP credential resolution flow."""
        from app.models.blog import Blog

        # Create a blog with encrypted WP password
        blog = Blog(
            name="Test Blog",
            slug="test-blog",
            url="https://testblog.example.com",
            wp_username="admin",
            wp_app_password_encrypted=encrypt("my-wp-app-password"),
        )
        db_session.add(blog)
        await db_session.flush()

        # Also create a credential for the WP REST provider
        cred = Credential(
            provider="wp_rest",
            key_name="application_password",
            value_encrypted=encrypt("my-wp-app-password"),
        )
        db_session.add(cred)
        await db_session.flush()

        # Resolve the provider using the blog's info
        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url=blog.url,
            username=blog.wp_username,
        )

        assert isinstance(provider, StubWPProvider)
        assert provider.base_url == "https://testblog.example.com"
        assert provider.username == "admin"
        assert provider.password == "my-wp-app-password"


# ===========================================================================
# Tests: Edge Cases
# ===========================================================================


class TestEdgeCases:
    """Edge case and error handling tests."""

    @pytest.mark.asyncio
    async def test_provider_can_be_used_after_creation(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """A provider created by the factory can be used normally."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_llm_provider("deepseek")
        response = await provider.generate("Hello world")
        assert response.text == "stub"

    @pytest.mark.asyncio
    async def test_image_provider_can_generate(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """An Image provider created by the factory can generate."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_image_provider("fal")
        result = await provider.generate("A beautiful sunset")
        assert result.url == "https://example.com/stub.png"

    @pytest.mark.asyncio
    async def test_wp_provider_can_create_post(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """A WP provider created by the factory can create posts."""
        factory = ProviderFactory(db_session)
        provider = await factory.get_wordpress_provider(
            "wp_rest",
            base_url="https://blog.example.com",
            username="admin",
        )
        result = await provider.create_post("Test Title", "<p>Content</p>", status="draft")
        assert result.id == 1
        assert "blog.example.com" in result.url

    @pytest.mark.asyncio
    async def test_factory_with_empty_db_raises(
        self,
        db_session: AsyncSession,
        register_stubs: None,
    ) -> None:
        """Factory raises for all provider types when DB is empty."""
        factory = ProviderFactory(db_session)

        with pytest.raises(ValueError, match="No credential found"):
            await factory.get_llm_provider("deepseek")

        with pytest.raises(ValueError, match="No credential found"):
            await factory.get_image_provider("fal")

        with pytest.raises(ValueError, match="No credential found"):
            await factory.get_wordpress_provider(
                "wp_rest",
                base_url="https://example.com",
                username="admin",
            )

    @pytest.mark.asyncio
    async def test_new_factory_instance_same_session(
        self,
        db_session: AsyncSession,
        seed_credentials: dict[str, Credential],
        register_stubs: None,
    ) -> None:
        """Multiple factory instances on the same session work independently."""
        factory1 = ProviderFactory(db_session)
        factory2 = ProviderFactory(db_session)

        p1 = await factory1.get_llm_provider("deepseek")
        p2 = await factory2.get_llm_provider("openai")

        assert isinstance(p1, StubLLMProvider)
        assert isinstance(p2, StubLLMProvider)
        assert p1.api_key == "sk-deepseek-secret-123"
        assert p2.api_key == "sk-openai-secret-456"
