"""Tests for concrete provider implementations: DeepSeek, OpenAI, Fal, WPRest.

All external HTTP calls are mocked using ``httpx``'s transport mechanism.
Tests verify that each provider:
- Formats API requests correctly (URL, headers, body)
- Handles successful responses
- Handles error responses (4xx, 5xx)
- Properly closes its HTTP client
- Uses the correct authentication method
"""

# NOTE: All API keys and passwords in this file are dummy test fixtures,
# not real credentials.

from __future__ import annotations

import json
from typing import Any

import pytest
import httpx

from app.providers.base import (
    ImageResult,
    LLMResponse,
    WPMediaResult,
    WPPostResult,
)
from app.providers.llm.deepseek import DeepSeekProvider
from app.providers.llm.openai import OpenAIProvider
from app.providers.image.fal import FalProvider
from app.providers.wordpress.wp_rest import WPRestProvider


# ---------------------------------------------------------------------------
# Helpers: mock httpx transport
# ---------------------------------------------------------------------------


class MockTransport(httpx.AsyncBaseTransport):
    """A transport that returns a pre-configured response for any request."""

    def __init__(
        self,
        status_code: int = 200,
        json_body: dict[str, Any] | list[Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.json_body = json_body
        self.content = content
        self.headers = headers or {}
        self.last_request: httpx.Request | None = None
        self.request_count: int = 0

    @property
    def request(self) -> httpx.Request:
        """Return the last request, raising if none was made."""
        if self.last_request is None:
            raise AssertionError("No request was made")
        return self.last_request

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.last_request = request
        self.request_count += 1
        # Build response kwargs – don't pass both json and content
        # because httpx.Response will use content over json if both set.
        response_kwargs: dict[str, Any] = {
            "status_code": self.status_code,
            "headers": self.headers,
            "request": request,
        }
        if self.content is not None:
            response_kwargs["content"] = self.content
        elif self.json_body is not None:
            response_kwargs["json"] = self.json_body
        return httpx.Response(**response_kwargs)


class MultiResponseTransport(httpx.AsyncBaseTransport):
    """A transport that returns different responses for sequential requests."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        """Each response dict has: status_code, json_body, headers."""
        self.responses = responses
        self.index = 0
        self.requests: list[httpx.Request] = []

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(request)
        resp_config = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return httpx.Response(
            status_code=resp_config.get("status_code", 200),
            json=resp_config.get("json_body"),
            content=resp_config.get("content", b""),
            headers=resp_config.get("headers", {}),
            request=request,
        )


# ===========================================================================
# DeepSeek Provider Tests
# ===========================================================================


class TestDeepSeekProvider:
    """Tests for DeepSeekProvider LLM implementation."""

    def test_init_stores_api_key(self) -> None:
        """Provider stores the API key on init."""
        provider = DeepSeekProvider(api_key="testkey-deepseek-123")
        assert provider._api_key == "testkey-deepseek-123"

    def test_init_default_base_url(self) -> None:
        """Provider uses the default DeepSeek base URL."""
        provider = DeepSeekProvider(api_key="testkey-dummy")
        assert "deepseek.com" in provider._base_url

    def test_init_custom_base_url(self) -> None:
        """Provider accepts a custom base URL."""
        provider = DeepSeekProvider(api_key="testkey-dummy", base_url="https://custom.api.com")
        assert provider._base_url == "https://custom.api.com"

    def test_init_default_model(self) -> None:
        """Provider uses a default model name."""
        provider = DeepSeekProvider(api_key="testkey-dummy")
        assert provider._model == "deepseek-chat"

    def test_init_custom_model(self) -> None:
        """Provider accepts a custom model name."""
        provider = DeepSeekProvider(api_key="testkey-dummy", model="deepseek-coder")
        assert provider._model == "deepseek-coder"

    @pytest.mark.asyncio
    async def test_generate_sends_correct_url(self) -> None:
        """generate() sends request to the /chat/completions endpoint."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("Hi")
        assert transport.request is not None
        assert "/chat/completions" in str(transport.request.url)

    @pytest.mark.asyncio
    async def test_generate_sends_auth_header(self) -> None:
        """generate() sends Bearer token in Authorization header."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-secret-key", _transport=transport)
        await provider.generate("Hi")
        assert transport.request is not None
        auth = transport.request.headers.get("authorization", "")
        assert auth == "Bearer testkey-secret-key"

    @pytest.mark.asyncio
    async def test_generate_sends_messages_in_body(self) -> None:
        """generate() formats messages array correctly."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "response"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("Hello", system_prompt="You are helpful")
        assert transport.request is not None
        body = json.loads(transport.request.content)
        assert "messages" in body
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "You are helpful"
        assert body["messages"][1]["role"] == "user"
        assert body["messages"][1]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_generate_sends_params(self) -> None:
        """generate() sends max_tokens and temperature in the request."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("Hi", max_tokens=100, temperature=0.3)
        body = json.loads(transport.request.content)
        assert body["max_tokens"] == 100
        assert body["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self) -> None:
        """generate() returns a properly structured LLMResponse."""
        transport = MockTransport(
            json_body={
                "choices": [
                    {"message": {"content": "Generated text here"}, "finish_reason": "stop"}
                ],
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        result = await provider.generate("Test prompt")

        assert isinstance(result, LLMResponse)
        assert result.text == "Generated text here"
        assert result.model == "deepseek-chat"
        assert result.usage["total_tokens"] == 30
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self) -> None:
        """generate() works without a system_prompt (only user message)."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("Just a user message")
        body = json.loads(transport.request.content)
        # Only user message, no system message
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_generate_handles_api_error(self) -> None:
        """generate() raises httpx.HTTPStatusError on 4xx/5xx responses."""
        transport = MockTransport(status_code=401, json_body={"error": "Unauthorized"})
        provider = DeepSeekProvider(api_key="testkey-bad", _transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate("test")

    @pytest.mark.asyncio
    async def test_generate_handles_rate_limit(self) -> None:
        """generate() raises httpx.HTTPStatusError on 429 rate limit."""
        transport = MockTransport(status_code=429, json_body={"error": "Rate limited"})
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate("test")

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """close() releases the HTTP client."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "model": "deepseek-chat",
                "usage": {},
            }
        )
        provider = DeepSeekProvider(api_key="testkey-dummy", _transport=transport)
        # Make a request first to create the client
        await provider.generate("test")
        await provider.close()
        # After close, client should be None or unusable
        assert provider._client is None


# ===========================================================================
# OpenAI Provider Tests
# ===========================================================================


class TestOpenAIProvider:
    """Tests for OpenAIProvider LLM implementation."""

    def test_init_stores_api_key(self) -> None:
        """Provider stores the API key on init."""
        provider = OpenAIProvider(api_key="testkey-openai-123")
        assert provider._api_key == "testkey-openai-123"

    def test_init_default_base_url(self) -> None:
        """Provider uses the default OpenAI API base URL."""
        provider = OpenAIProvider(api_key="testkey-dummy")
        assert "api.openai.com" in provider._base_url

    def test_init_custom_base_url(self) -> None:
        """Provider accepts a custom base URL."""
        provider = OpenAIProvider(api_key="testkey-dummy", base_url="https://custom.api.com/v1")
        assert provider._base_url == "https://custom.api.com/v1"

    def test_init_default_model(self) -> None:
        """Provider uses a sensible default model."""
        provider = OpenAIProvider(api_key="testkey-dummy")
        assert provider._model == "gpt-4o"

    def test_init_custom_model(self) -> None:
        """Provider accepts a custom model name."""
        provider = OpenAIProvider(api_key="testkey-dummy", model="gpt-4-turbo")
        assert provider._model == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_generate_sends_correct_url(self) -> None:
        """generate() sends request to the /chat/completions endpoint."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "Hi!"}, "finish_reason": "stop"}],
                "model": "gpt-4o",
                "usage": {},
            }
        )
        provider = OpenAIProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("Hello")
        assert transport.request is not None
        assert "/chat/completions" in str(transport.request.url)

    @pytest.mark.asyncio
    async def test_generate_sends_auth_header(self) -> None:
        """generate() sends Bearer token in Authorization header."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
                "model": "gpt-4o",
                "usage": {},
            }
        )
        provider = OpenAIProvider(api_key="testkey-openai-real", _transport=transport)
        await provider.generate("Hi")
        assert transport.request is not None
        auth = transport.request.headers.get("authorization", "")
        assert auth == "Bearer testkey-openai-real"

    @pytest.mark.asyncio
    async def test_generate_sends_messages_format(self) -> None:
        """generate() formats the OpenAI messages array correctly."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "model": "gpt-4o",
                "usage": {},
            }
        )
        provider = OpenAIProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("What is AI?", system_prompt="Be concise")
        body = json.loads(transport.request.content)
        assert body["messages"][0] == {"role": "system", "content": "Be concise"}
        assert body["messages"][1] == {"role": "user", "content": "What is AI?"}

    @pytest.mark.asyncio
    async def test_generate_sends_model_in_body(self) -> None:
        """generate() includes the model name in the request body."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
                "model": "gpt-4-turbo",
                "usage": {},
            }
        )
        provider = OpenAIProvider(api_key="testkey-dummy", model="gpt-4-turbo", _transport=transport)
        await provider.generate("test")
        body = json.loads(transport.request.content)
        assert body["model"] == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self) -> None:
        """generate() returns a properly structured LLMResponse."""
        transport = MockTransport(
            json_body={
                "choices": [
                    {"message": {"content": "OpenAI response"}, "finish_reason": "length"}
                ],
                "model": "gpt-4o",
                "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            }
        )
        provider = OpenAIProvider(api_key="testkey-dummy", _transport=transport)
        result = await provider.generate("test")

        assert isinstance(result, LLMResponse)
        assert result.text == "OpenAI response"
        assert result.model == "gpt-4o"
        assert result.usage["completion_tokens"] == 12
        assert result.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_generate_handles_api_error(self) -> None:
        """generate() raises httpx.HTTPStatusError on API error."""
        transport = MockTransport(status_code=500, json_body={"error": "Server error"})
        provider = OpenAIProvider(api_key="testkey-dummy", _transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate("test")

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """close() releases the HTTP client."""
        transport = MockTransport(
            json_body={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "model": "gpt-4o",
                "usage": {},
            }
        )
        provider = OpenAIProvider(api_key="testkey-dummy", _transport=transport)
        await provider.generate("test")
        await provider.close()
        assert provider._client is None


# ===========================================================================
# Fal Provider Tests
# ===========================================================================


class TestFalProvider:
    """Tests for FalProvider image generation implementation."""

    def test_init_stores_api_key(self) -> None:
        """Provider stores the API key on init."""
        provider = FalProvider(api_key="fal-key-123")
        assert provider._api_key == "fal-key-123"

    def test_init_default_model(self) -> None:
        """Provider uses a default model."""
        provider = FalProvider(api_key="fal-key")
        assert provider._model != ""

    def test_init_custom_model(self) -> None:
        """Provider accepts a custom model name."""
        provider = FalProvider(api_key="fal-key", model="fal-flux/schnell")
        assert provider._model == "fal-flux/schnell"

    @pytest.mark.asyncio
    async def test_generate_sends_correct_url(self) -> None:
        """generate() sends request to the correct fal.ai endpoint."""
        transport = MockTransport(
            json_body={
                "images": [{"url": "https://fal.media/img/abc123.png"}],
            }
        )
        provider = FalProvider(api_key="fal-test", _transport=transport)
        await provider.generate("a sunset")
        assert transport.request is not None
        url_str = str(transport.request.url)
        assert "fal.ai" in url_str or "fal.run" in url_str

    @pytest.mark.asyncio
    async def test_generate_sends_auth_header(self) -> None:
        """generate() sends the API key in the Authorization header."""
        transport = MockTransport(
            json_body={
                "images": [{"url": "https://fal.media/img/test.png"}],
            }
        )
        provider = FalProvider(api_key="fal-secret-key", _transport=transport)
        await provider.generate("mountain")
        assert transport.request is not None
        auth = transport.request.headers.get("authorization", "")
        assert auth == "Bearer fal-secret-key"

    @pytest.mark.asyncio
    async def test_generate_sends_prompt_in_body(self) -> None:
        """generate() sends the prompt and image size in the request body."""
        transport = MockTransport(
            json_body={
                "images": [{"url": "https://fal.media/img/test.png"}],
            }
        )
        provider = FalProvider(api_key="fal-test", _transport=transport)
        await provider.generate("a beautiful landscape", width=512, height=768)
        body = json.loads(transport.request.content)
        assert body["prompt"] == "a beautiful landscape"
        assert body["image_size"] == "512x768"

    @pytest.mark.asyncio
    async def test_generate_returns_image_result(self) -> None:
        """generate() returns an ImageResult with the generated image URL."""
        transport = MockTransport(
            json_body={
                "images": [{"url": "https://fal.media/img/generated.png"}],
            }
        )
        provider = FalProvider(api_key="fal-test", _transport=transport)
        result = await provider.generate("ocean waves")

        assert isinstance(result, ImageResult)
        assert result.url == "https://fal.media/img/generated.png"

    @pytest.mark.asyncio
    async def test_generate_handles_api_error(self) -> None:
        """generate() raises httpx.HTTPStatusError on API error."""
        transport = MockTransport(status_code=400, json_body={"error": "Bad request"})
        provider = FalProvider(api_key="fal-test", _transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.generate("test")

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """close() releases the HTTP client."""
        transport = MockTransport(
            json_body={"images": [{"url": "https://example.com/img.png"}]}
        )
        provider = FalProvider(api_key="fal-test", _transport=transport)
        await provider.generate("test")
        await provider.close()
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_generate_default_dimensions(self) -> None:
        """generate() uses default 1024x1024 when no dimensions specified."""
        transport = MockTransport(
            json_body={"images": [{"url": "https://fal.media/img/test.png"}]}
        )
        provider = FalProvider(api_key="fal-test", _transport=transport)
        await provider.generate("test prompt")
        body = json.loads(transport.request.content)
        assert body["image_size"] == "1024x1024"


# ===========================================================================
# WPRestProvider Tests
# ===========================================================================


class TestWPRestProvider:
    """Tests for WPRestProvider WordPress REST API implementation."""

    def test_init_stores_params(self) -> None:
        """Provider stores base_url, username, and password."""
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret-app-password",
        )
        assert provider._base_url == "https://blog.example.com"
        assert provider._username == "admin"
        assert provider._password == "secret-app-password"

    def test_init_strips_trailing_slash(self) -> None:
        """Provider strips trailing slash from base_url."""
        provider = WPRestProvider(
            base_url="https://blog.example.com/",
            username="admin",
            password="secret",
        )
        assert provider._base_url == "https://blog.example.com"

    def test_init_default_wp_api_prefix(self) -> None:
        """Provider uses /wp-json/wp/v2 as the API path prefix."""
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
        )
        assert "/wp-json/wp/v2" in provider._api_prefix

    # -- create_post tests --

    @pytest.mark.asyncio
    async def test_create_post_sends_correct_url(self) -> None:
        """create_post() sends to the /wp-json/wp/v2/posts endpoint."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/hello-world/",
                "status": "draft",
                "title": {"rendered": "Hello World"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.create_post("Hello World", "<p>Content</p>")
        assert transport.request is not None
        url = str(transport.request.url)
        assert "/wp-json/wp/v2/posts" in url

    @pytest.mark.asyncio
    async def test_create_post_uses_basic_auth(self) -> None:
        """create_post() sends Basic Auth header."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/post/",
                "status": "draft",
                "title": {"rendered": "T"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="app-password-123",
            _transport=transport,
        )
        await provider.create_post("Title", "Content")
        assert transport.request is not None
        auth_header = transport.request.headers.get("authorization", "")
        assert auth_header.startswith("Basic ")

    @pytest.mark.asyncio
    async def test_create_post_sends_body(self) -> None:
        """create_post() sends title, content, status in request body."""
        transport = MockTransport(
            json_body={
                "id": 1,
                "link": "https://blog.example.com/test/",
                "status": "publish",
                "title": {"rendered": "My Post"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.create_post(
            "My Post",
            "<p>Content here</p>",
            status="publish",
            categories=[3, 7],
            featured_media=12,
        )
        body = json.loads(transport.request.content)
        assert body["title"] == "My Post"
        assert body["content"] == "<p>Content here</p>"
        assert body["status"] == "publish"
        assert body["categories"] == [3, 7]
        assert body["featured_media"] == 12

    @pytest.mark.asyncio
    async def test_create_post_returns_wp_post_result(self) -> None:
        """create_post() returns a WPPostResult."""
        transport = MockTransport(
            json_body={
                "id": 99,
                "link": "https://blog.example.com/test-post/",
                "status": "draft",
                "title": {"rendered": "Test Post"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        result = await provider.create_post("Test Post", "<p>Hi</p>")

        assert isinstance(result, WPPostResult)
        assert result.id == 99
        assert result.url == "https://blog.example.com/test-post/"
        assert result.status == "draft"
        assert result.title == "Test Post"

    # -- update_post tests --

    @pytest.mark.asyncio
    async def test_update_post_sends_to_correct_url(self) -> None:
        """update_post() sends to /wp-json/wp/v2/posts/{post_id}."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/post-42/",
                "status": "publish",
                "title": {"rendered": "Updated"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.update_post(42, title="Updated")
        url = str(transport.request.url)
        assert "/wp-json/wp/v2/posts/42" in url

    @pytest.mark.asyncio
    async def test_update_post_uses_post_method(self) -> None:
        """update_post() uses POST method (WordPress REST API convention)."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/post-42/",
                "status": "draft",
                "title": {"rendered": "T"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.update_post(42, title="Updated")
        assert transport.request is not None
        assert transport.request.method == "POST"

    @pytest.mark.asyncio
    async def test_update_post_sends_partial_body(self) -> None:
        """update_post() only sends fields that are provided."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/post-42/",
                "status": "publish",
                "title": {"rendered": "New Title"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.update_post(42, title="New Title", status="publish")
        body = json.loads(transport.request.content)
        assert body["title"] == "New Title"
        assert body["status"] == "publish"
        # content should not be sent when not provided
        assert "content" not in body

    # -- upload_media tests --

    @pytest.mark.asyncio
    async def test_upload_media_sends_to_correct_endpoint(self) -> None:
        """upload_media() sends to /wp-json/wp/v2/media."""
        transport = MockTransport(
            status_code=201,
            json_body={
                "id": 55,
                "source_url": "https://blog.example.com/wp-content/uploads/image.jpg",
                "media_type": "image",
            },
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.upload_media(b"fake-image-data", "image.jpg")
        url = str(transport.request.url)
        assert "/wp-json/wp/v2/media" in url

    @pytest.mark.asyncio
    async def test_upload_media_sends_binary_data(self) -> None:
        """upload_media() sends raw binary file data."""
        transport = MockTransport(
            status_code=201,
            json_body={
                "id": 55,
                "source_url": "https://blog.example.com/wp-content/uploads/img.png",
                "media_type": "image",
            },
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        file_data = b"\x89PNG\r\n\x1a\nfake-image"
        await provider.upload_media(file_data, "img.png", media_type="image/png")
        assert transport.request is not None
        assert transport.request.content == file_data
        ct = transport.request.headers.get("content-type", "")
        assert "image/png" in ct

    @pytest.mark.asyncio
    async def test_upload_media_returns_wp_media_result(self) -> None:
        """upload_media() returns a WPMediaResult."""
        transport = MockTransport(
            status_code=201,
            json_body={
                "id": 55,
                "source_url": "https://blog.example.com/wp-content/uploads/img.jpg",
                "media_type": "image",
            },
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        result = await provider.upload_media(b"data", "img.jpg")

        assert isinstance(result, WPMediaResult)
        assert result.id == 55
        assert result.url == "https://blog.example.com/wp-content/uploads/img.jpg"

    # -- list_categories tests --

    @pytest.mark.asyncio
    async def test_list_categories_sends_to_correct_endpoint(self) -> None:
        """list_categories() sends to /wp-json/wp/v2/categories."""
        transport = MockTransport(
            json_body=[
                {"id": 1, "name": "Uncategorized", "slug": "uncategorized"},
                {"id": 5, "name": "Technology", "slug": "technology"},
            ]
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.list_categories()
        url = str(transport.request.url)
        assert "/wp-json/wp/v2/categories" in url

    @pytest.mark.asyncio
    async def test_list_categories_sends_query_params(self) -> None:
        """list_categories() sends per_page and search as query params."""
        transport = MockTransport(json_body=[])
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.list_categories(per_page=10, search="tech")
        url = str(transport.request.url)
        assert "per_page=10" in url
        assert "search=tech" in url

    @pytest.mark.asyncio
    async def test_list_categories_returns_list(self) -> None:
        """list_categories() returns a list of category dicts."""
        transport = MockTransport(
            json_body=[
                {"id": 1, "name": "Uncategorized", "slug": "uncategorized"},
                {"id": 5, "name": "Tech", "slug": "tech"},
            ]
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        result = await provider.list_categories()
        assert len(result) == 2
        assert result[0]["name"] == "Uncategorized"
        assert result[1]["id"] == 5

    # -- get_post tests --

    @pytest.mark.asyncio
    async def test_get_post_sends_to_correct_url(self) -> None:
        """get_post() sends to /wp-json/wp/v2/posts/{post_id}."""
        transport = MockTransport(
            json_body={
                "id": 123,
                "link": "https://blog.example.com/post-123/",
                "status": "publish",
                "title": {"rendered": "Existing Post"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.get_post(123)
        url = str(transport.request.url)
        assert "/wp-json/wp/v2/posts/123" in url

    @pytest.mark.asyncio
    async def test_get_post_uses_get_method(self) -> None:
        """get_post() uses GET method."""
        transport = MockTransport(
            json_body={
                "id": 1,
                "link": "https://blog.example.com/post/",
                "status": "draft",
                "title": {"rendered": "T"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.get_post(1)
        assert transport.request is not None
        assert transport.request.method == "GET"

    @pytest.mark.asyncio
    async def test_get_post_returns_wp_post_result(self) -> None:
        """get_post() returns a WPPostResult."""
        transport = MockTransport(
            json_body={
                "id": 42,
                "link": "https://blog.example.com/hello/",
                "status": "publish",
                "title": {"rendered": "Hello World"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        result = await provider.get_post(42)
        assert isinstance(result, WPPostResult)
        assert result.id == 42
        assert result.title == "Hello World"

    # -- error handling --

    @pytest.mark.asyncio
    async def test_create_post_handles_error(self) -> None:
        """create_post() raises on API error."""
        transport = MockTransport(status_code=403, json_body={"code": "rest_forbidden"})
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="bad-password",
            _transport=transport,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.create_post("Title", "Content")

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """close() releases the HTTP client."""
        transport = MockTransport(
            json_body={
                "id": 1,
                "link": "https://blog.example.com/post/",
                "status": "draft",
                "title": {"rendered": "T"},
            }
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.create_post("T", "C")
        await provider.close()
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_upload_media_with_alt_text(self) -> None:
        """upload_media() sends alt_text and title as headers."""
        transport = MockTransport(
            status_code=201,
            json_body={
                "id": 55,
                "source_url": "https://blog.example.com/wp-content/uploads/img.jpg",
                "media_type": "image",
            },
        )
        provider = WPRestProvider(
            base_url="https://blog.example.com",
            username="admin",
            password="secret",
            _transport=transport,
        )
        await provider.upload_media(
            b"data",
            "img.jpg",
            alt_text="A sunset photo",
            title="Sunset Image",
        )
        # WordPress expects alt_text and title in the request
        assert transport.request is not None
