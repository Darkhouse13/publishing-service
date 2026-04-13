"""Provider Abstraction Layer.

Re-exports all ABCs, result dataclasses, concrete providers, and the
provider factory for convenient access::

    from app.providers import LLMProvider, LLMResponse
    from app.providers import ImageProvider, ImageResult
    from app.providers import WordPressProvider, WPPostResult, WPMediaResult
    from app.providers import ProviderFactory
    from app.providers import get_llm_provider, get_image_provider, get_wordpress_provider
    from app.providers import DeepSeekProvider, OpenAIProvider, FalProvider, WPRestProvider
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

# Concrete provider implementations
from app.providers.image.fal import FalProvider
from app.providers.llm.deepseek import DeepSeekProvider
from app.providers.llm.openai import OpenAIProvider
from app.providers.wordpress.wp_rest import WPRestProvider

# Auto-register concrete providers with the factory
ProviderFactory.register_llm("deepseek", DeepSeekProvider)
ProviderFactory.register_llm("openai", OpenAIProvider)
ProviderFactory.register_image("fal", FalProvider)
ProviderFactory.register_wordpress("wp_rest", WPRestProvider)

__all__ = [
    "DeepSeekProvider",
    "FalProvider",
    "ImageProvider",
    "ImageResult",
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "ProviderFactory",
    "WPMediaResult",
    "WPPostResult",
    "WPRestProvider",
    "WordPressProvider",
    "get_image_provider",
    "get_llm_provider",
    "get_wordpress_provider",
]
