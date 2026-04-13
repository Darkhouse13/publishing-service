"""Provider factory — resolves and instantiates providers from stored credentials.

The factory uses :class:`CredentialService` to look up encrypted credentials
by ``(provider, key_name)`` pair, decrypts them on demand, and constructs the
appropriate concrete provider instance.

Usage::

    factory = ProviderFactory(session)
    llm = await factory.get_llm_provider("deepseek")
    response = await llm.generate("Hello world")

The factory discovers concrete provider implementations via a registry.
Concrete providers register themselves at import time, or they can be
registered manually with :meth:`ProviderFactory.register_llm` etc.

Currently supported providers:
- **LLM**: ``deepseek``, ``openai``
- **Image**: ``fal``
- **WordPress**: ``wp_rest``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.providers.base import (
    ImageProvider,
    LLMProvider,
    WordPressProvider,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Registries: provider_name -> concrete implementation class
# ---------------------------------------------------------------------------

_LLM_REGISTRY: dict[str, type[LLMProvider]] = {}
_IMAGE_REGISTRY: dict[str, type[ImageProvider]] = {}
_WP_REGISTRY: dict[str, type[WordPressProvider]] = {}

# Default key_name mappings for credential resolution.
# Each provider type has a well-known ``key_name`` used to look up the
# primary credential in the ``credentials`` table.
_DEFAULT_CREDENTIAL_KEY_NAMES: dict[str, str] = {
    # LLM providers
    "deepseek": "api_key",
    "openai": "api_key",
    # Image providers
    "fal": "api_key",
    # WordPress providers – uses the blog record instead
    "wp_rest": "application_password",
}


class ProviderFactory:
    """Instantiate providers from stored, encrypted credentials.

    Parameters:
        session: An :class:`~sqlalchemy.ext.asyncio.AsyncSession` used to
            query the ``credentials`` table.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def register_llm(name: str, cls: type[LLMProvider]) -> None:
        """Register a concrete LLM provider class under *name*."""
        _LLM_REGISTRY[name] = cls

    @staticmethod
    def register_image(name: str, cls: type[ImageProvider]) -> None:
        """Register a concrete Image provider class under *name*."""
        _IMAGE_REGISTRY[name] = cls

    @staticmethod
    def register_wordpress(name: str, cls: type[WordPressProvider]) -> None:
        """Register a concrete WordPress provider class under *name*."""
        _WP_REGISTRY[name] = cls

    @staticmethod
    def list_llm_providers() -> list[str]:
        """Return the names of all registered LLM providers."""
        return sorted(_LLM_REGISTRY.keys())

    @staticmethod
    def list_image_providers() -> list[str]:
        """Return the names of all registered Image providers."""
        return sorted(_IMAGE_REGISTRY.keys())

    @staticmethod
    def list_wordpress_providers() -> list[str]:
        """Return the names of all registered WordPress providers."""
        return sorted(_WP_REGISTRY.keys())

    # ------------------------------------------------------------------
    # Internal credential resolution
    # ------------------------------------------------------------------

    async def _resolve_credential(self, provider_name: str, key_name: str | None = None) -> str:
        """Look up and decrypt a credential value.

        Args:
            provider_name: The provider identifier (e.g. ``"openai"``).
            key_name: Specific credential key to look up.  If ``None``,
                the factory falls back to the default key name for the
                provider.

        Returns:
            The decrypted plaintext credential value.

        Raises:
            ValueError: If the credential is not found in the database.
        """
        from app.services.credential import CredentialService

        resolved_key = key_name or _DEFAULT_CREDENTIAL_KEY_NAMES.get(provider_name, "api_key")

        service = CredentialService(self._session)
        from sqlalchemy import select
        from app.models.credential import Credential

        result = await self._session.execute(
            select(Credential).where(
                Credential.provider == provider_name,
                Credential.key_name == resolved_key,
            )
        )
        credential = result.scalar_one_or_none()
        if credential is None:
            raise ValueError(
                f"No credential found for provider='{provider_name}', "
                f"key_name='{resolved_key}'."
            )
        return service.decrypt_value(credential)

    # ------------------------------------------------------------------
    # Public factory methods
    # ------------------------------------------------------------------

    async def get_llm_provider(self, provider_name: str, **kwargs: object) -> LLMProvider:
        """Instantiate and return an LLM provider by name.

        The provider's API key is automatically resolved from the
        ``credentials`` table.

        Args:
            provider_name: Registered provider name (e.g. ``"deepseek"``,
                ``"openai"``).
            **kwargs: Additional keyword arguments forwarded to the
                concrete provider constructor (e.g. ``base_url``, ``model``).

        Returns:
            A fully-initialised :class:`LLMProvider` instance.

        Raises:
            ValueError: If *provider_name* is not registered or the
                credential cannot be found.
        """
        cls = _LLM_REGISTRY.get(provider_name)
        if cls is None:
            raise ValueError(
                f"Unknown LLM provider '{provider_name}'. "
                f"Registered: {self.list_llm_providers()}"
            )
        api_key = await self._resolve_credential(provider_name)
        return cls(api_key=api_key, **kwargs)  # type: ignore[call-arg]

    async def get_image_provider(self, provider_name: str, **kwargs: object) -> ImageProvider:
        """Instantiate and return an Image provider by name.

        Args:
            provider_name: Registered provider name (e.g. ``"fal"``).
            **kwargs: Additional keyword arguments forwarded to the
                concrete provider constructor.

        Returns:
            A fully-initialised :class:`ImageProvider` instance.

        Raises:
            ValueError: If *provider_name* is not registered or the
                credential cannot be found.
        """
        cls = _IMAGE_REGISTRY.get(provider_name)
        if cls is None:
            raise ValueError(
                f"Unknown Image provider '{provider_name}'. "
                f"Registered: {self.list_image_providers()}"
            )
        api_key = await self._resolve_credential(provider_name)
        return cls(api_key=api_key, **kwargs)  # type: ignore[call-arg]

    async def get_wordpress_provider(
        self,
        provider_name: str,
        *,
        base_url: str,
        username: str,
        key_name: str = "application_password",
        **kwargs: object,
    ) -> WordPressProvider:
        """Instantiate and return a WordPress provider by name.

        WordPress credentials are resolved from the ``credentials`` table
        by default, but callers must supply ``base_url`` and ``username``
        explicitly since they are not stored in the credentials table.

        Args:
            provider_name: Registered provider name (e.g. ``"wp_rest"``).
            base_url: The WordPress site's base URL.
            username: WordPress username.
            key_name: The credential key name to look up.
            **kwargs: Additional keyword arguments forwarded to the
                concrete provider constructor.

        Returns:
            A fully-initialised :class:`WordPressProvider` instance.

        Raises:
            ValueError: If *provider_name* is not registered or the
                credential cannot be found.
        """
        cls = _WP_REGISTRY.get(provider_name)
        if cls is None:
            raise ValueError(
                f"Unknown WordPress provider '{provider_name}'. "
                f"Registered: {self.list_wordpress_providers()}"
            )
        password = await self._resolve_credential(provider_name, key_name=key_name)
        return cls(
            base_url=base_url,
            username=username,
            password=password,
            **kwargs,
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


async def get_llm_provider(
    session: AsyncSession,
    provider_name: str,
    **kwargs: object,
) -> LLMProvider:
    """Convenience wrapper: create a factory and resolve an LLM provider."""
    factory = ProviderFactory(session)
    return await factory.get_llm_provider(provider_name, **kwargs)


async def get_image_provider(
    session: AsyncSession,
    provider_name: str,
    **kwargs: object,
) -> ImageProvider:
    """Convenience wrapper: create a factory and resolve an Image provider."""
    factory = ProviderFactory(session)
    return await factory.get_image_provider(provider_name, **kwargs)


async def get_wordpress_provider(
    session: AsyncSession,
    provider_name: str,
    *,
    base_url: str,
    username: str,
    key_name: str = "application_password",
    **kwargs: object,
) -> WordPressProvider:
    """Convenience wrapper: create a factory and resolve a WordPress provider."""
    factory = ProviderFactory(session)
    return await factory.get_wordpress_provider(
        provider_name,
        base_url=base_url,
        username=username,
        key_name=key_name,
        **kwargs,
    )
