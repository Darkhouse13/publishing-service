"""Provider Abstraction Layer.

Re-exports all ABCs, result dataclasses, and the provider factory
for convenient access::

    from app.providers import LLMProvider, LLMResponse
    from app.providers import ImageProvider, ImageResult
    from app.providers import WordPressProvider, WPPostResult, WPMediaResult
    from app.providers import ProviderFactory
    from app.providers import get_llm_provider, get_image_provider, get_wordpress_provider
"""

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

__all__ = [
    "ImageProvider",
    "ImageResult",
    "LLMProvider",
    "LLMResponse",
    "ProviderFactory",
    "WPMediaResult",
    "WPPostResult",
    "WordPressProvider",
    "get_image_provider",
    "get_llm_provider",
    "get_wordpress_provider",
]
