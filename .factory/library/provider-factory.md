# Provider Factory

## Overview
The `ProviderFactory` in `backend/app/providers/factory.py` resolves and instantiates providers from stored encrypted credentials using `CredentialService`.

## Key Design
- **Registry pattern**: Concrete provider classes register themselves via `ProviderFactory.register_llm()`, `register_image()`, `register_wordpress()`
- **Async credential resolution**: `_resolve_credential()` looks up credentials by `(provider, key_name)` pair from the database and decrypts via `CredentialService.decrypt_value()`
- **Default key names**: A mapping `_DEFAULT_CREDENTIAL_KEY_NAMES` provides fallback `key_name` per provider (e.g. "api_key" for LLM/image, "application_password" for WP)
- **Module-level convenience functions**: `get_llm_provider()`, `get_image_provider()`, `get_wordpress_provider()` wrap the factory for quick one-shot use

## Usage
```python
factory = ProviderFactory(session)
llm = await factory.get_llm_provider("deepseek")
response = await llm.generate("Hello world")

# Or use convenience function:
from app.providers import get_llm_provider
llm = await get_llm_provider(session, "openai")
```

## Concrete Providers
Concrete providers (DeepSeekProvider, OpenAIProvider, FalProvider, WPRestProvider) are implemented in a separate feature. They must accept `api_key=...` (LLM/Image) or `base_url=..., username=..., password=...` (WordPress) kwargs in their constructors.

## Validation Assertions Fulfilled
- VAL-CRED-005: LLM Provider Instantiation
- VAL-CRED-006: Image Provider Instantiation  
- VAL-CRED-007: WP Provider Instantiation
- VAL-CRED-009: Decryption on Demand
- VAL-CROSS-001: Blog-to-Provider Credential Resolution
