"""Comprehensive tests for ArticleGenerator service.

Covers: generation, JSON parsing, hard validations, soft fixes,
retry loop, temperature selection, error handling, and dataclass shape.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from app.providers.base import LLMProvider, LLMResponse
from app.services.article_generator import (
    ArticleGenerationError,
    ArticleGenerator,
    ArticlePayload,
    _extract_first_json_object,
    _parse_article_response,
    _remove_duplicate_h1,
    _split_overlong_paragraphs,
    _strip_code_fences,
    run_hard_validations,
    run_soft_fixes,
    INITIAL_TEMPERATURE,
    RETRY_TEMPERATURE,
    MAX_SEO_GENERATION_ATTEMPTS,
)


# ---------------------------------------------------------------------------
# Mock LLM Provider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """A mock LLM provider that returns pre-configured responses in order."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self._call_index = 0
        self.call_args: list[dict[str, Any]] = []

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.call_args.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._call_index >= len(self.responses):
            raise RuntimeError("MockLLMProvider ran out of responses")
        text = self.responses[self._call_index]
        self._call_index += 1
        return LLMResponse(
            text=text,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 100, "total_tokens": 110},
        )

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return self._call_index


# ---------------------------------------------------------------------------
# Helpers to build valid LLM responses
# ---------------------------------------------------------------------------


def _make_valid_article_json(
    *,
    word_count: int = 650,
    keyword: str = "outdoor patio furniture",
    keyword_count: int = 7,
    seo_title: str = "10 Best Outdoor Patio Furniture Sets for Your Backyard",
    meta_description: str | None = None,
    include_h2_with_keyword: bool = True,
    keyword_in_first_para: bool = True,
    extra_h1: bool = False,
) -> str:
    """Build a valid article JSON string for testing."""
    # Generate article body with controlled word count and keyword count
    body_parts: list[str] = []

    # First paragraph
    if keyword_in_first_para:
        first_para = (
            f"When it comes to {keyword}, homeowners have many exciting options to choose from. "
            "Transforming your outdoor space into a relaxing retreat requires careful planning "
            "and the right selection of pieces that combine style with durability. "
            "This comprehensive guide will help you navigate the many choices available today."
        )
    else:
        first_para = (
            "Homeowners have many exciting options to choose from when designing their spaces. "
            "Transforming your outdoor area into a relaxing retreat requires careful planning "
            "and the right selection of pieces that combine style with durability. "
            "This comprehensive guide will help you navigate the many choices available today."
        )
    body_parts.append(first_para)

    # H2 with keyword
    if include_h2_with_keyword:
        body_parts.append(f"## Why Choose {keyword.title()}")
    else:
        body_parts.append("## Why Choose Quality Materials")

    # Generate enough paragraphs to hit word count
    current_words = sum(len(p.split()) for p in body_parts)
    first_para_kw_count = body_parts[0].lower().count(keyword.lower()) if keyword_in_first_para else 0
    keywords_remaining = keyword_count - first_para_kw_count

    para_templates = [
        f"The best {keyword} pieces are made from weather-resistant materials that last for years. "
        "Premium teak, aluminum, and synthetic wicker are among the most popular choices. "
        "Each material offers unique benefits in terms of aesthetics and maintenance requirements.",

        "Shopping during off-season sales can save you hundreds of dollars on premium sets. "
        "Many retailers offer significant discounts during fall and winter months when demand is lower. "
        "Consider signing up for email alerts from your favorite retailers to catch these deals early.",

        f"Proper maintenance of your {keyword} extends its lifespan considerably. "
        "Regular cleaning with mild soap and water prevents buildup of dirt and debris. "
        "Investing in quality covers protects your pieces from harsh weather conditions year-round.",

        "Color coordination between your seating and surrounding landscape creates visual harmony. "
        "Neutral tones like gray, beige, and brown work well with most architectural styles. "
        "Consider adding colorful accent pillows to introduce seasonal pops of color throughout the year.",

        "Small spaces benefit from multi-functional pieces that serve dual purposes. "
        "Storage benches provide seating while keeping cushions and accessories organized. "
        "Folding chairs and stackable stools can be easily stored when not in use.",

        "Quality cushions transform any basic set into a comfortable lounging area. "
        "Look for UV-resistant fabrics that resist fading and water-resistant cores. "
        "Removable covers make cleaning simple and extend the life of your investment.",

        "Planning your layout before purchasing prevents costly returns and rearrangements. "
        "Measure your space carefully and leave room for walkways between pieces. "
        "Consider how many people you typically entertain to determine the right seating capacity.",

        "Accessorizing with planters, rugs, and lighting completes your outdoor room design. "
        "Outdoor rugs define seating areas and add warmth underfoot on hard surfaces. "
        "String lights and lanterns create ambiance for evening gatherings with friends and family.",
    ]

    idx = 0
    while current_words < word_count:
        template = para_templates[idx % len(para_templates)]
        para_words = len(template.split())

        if keywords_remaining > 0 and keyword.lower() not in template.lower():
            # This template has keyword already, just use it
            pass

        body_parts.append(template)
        current_words += para_words
        idx += 1

        # Add H2 headings periodically (only include keyword if include_h2_with_keyword)
        if idx % 3 == 0 and idx < len(para_templates):
            if include_h2_with_keyword:
                body_parts.append(f"## Tips for Selecting {keyword.title()}")
            else:
                body_parts.append("## Tips for Selecting Quality Pieces")

    article_markdown = "\n\n".join(body_parts)

    # Optionally add extra H1 headings at the top to test duplicate removal
    if extra_h1:
        article_markdown = f"# A Comprehensive Guide to Backyard Design\n\n# Another Heading For Testing\n\n{article_markdown}"

    if meta_description is None:
        meta_description = (
            f"Discover the best {keyword} options for your home. "
            "Our expert guide covers materials, styles, maintenance tips, and buying advice "
            "to help you create the perfect outdoor living space."
        )

    payload = {
        "title": seo_title,
        "article_markdown": article_markdown,
        "hero_image_prompt": f"A beautiful {keyword} display in a sunny backyard garden",
        "detail_image_prompt": f"Close-up of premium {keyword} material texture and craftsmanship",
        "seo_title": seo_title,
        "meta_description": meta_description,
        "focus_keyword": keyword,
    }
    return json.dumps(payload)


def _default_kwargs() -> dict[str, str]:
    return {
        "topic": "outdoor patio furniture guide",
        "vibe": "informative and friendly",
        "profile_prompt": "A home and garden blog focused on outdoor living spaces",
        "focus_keyword": "outdoor patio furniture",
    }


# ===================================================================
# Test: ArticlePayload dataclass
# ===================================================================


class TestArticlePayload:
    """VAL-AGEN-019: ArticlePayload dataclass defines correct fields."""

    def test_has_exactly_seven_fields(self) -> None:
        fields = dataclasses.fields(ArticlePayload)
        assert len(fields) == 7

    def test_field_names(self) -> None:
        fields = dataclasses.fields(ArticlePayload)
        names = {f.name for f in fields}
        expected = {
            "title",
            "article_markdown",
            "hero_image_prompt",
            "detail_image_prompt",
            "seo_title",
            "meta_description",
            "focus_keyword",
        }
        assert names == expected

    def test_construction(self) -> None:
        payload = ArticlePayload(
            title="Test",
            article_markdown="content",
            hero_image_prompt="hero",
            detail_image_prompt="detail",
            seo_title="seo",
            meta_description="meta",
            focus_keyword="kw",
        )
        assert payload.title == "Test"
        assert payload.article_markdown == "content"

    def test_frozen(self) -> None:
        payload = ArticlePayload(
            title="T",
            article_markdown="M",
            hero_image_prompt="H",
            detail_image_prompt="D",
            seo_title="S",
            meta_description="MD",
            focus_keyword="FK",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            payload.title = "changed"  # type: ignore[misc]


# ===================================================================
# Test: JSON Parsing
# ===================================================================


class TestJSONParsing:
    """VAL-AGEN-004, VAL-AGEN-005: JSON parsing from various LLM outputs."""

    def test_strip_code_fences(self) -> None:
        text = '```json\n{"title": "T", "article_markdown": "M", "hero_image_prompt": "H", "detail_image_prompt": "D", "seo_title": "S", "meta_description": "MD", "focus_keyword": "FK"}\n```'
        result = _strip_code_fences(text)
        assert result.startswith("{")
        assert result.endswith("}")

    def test_strip_code_fences_no_fences(self) -> None:
        text = '{"key": "value"}'
        assert _strip_code_fences(text) == text.strip()

    def test_extract_first_json_from_mixed(self) -> None:
        text = 'Here is the result: {"title": "T"} and some more text'
        result = _extract_first_json_object(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["title"] == "T"

    def test_parse_article_from_code_fences(self) -> None:
        raw = _make_valid_article_json()
        wrapped = f"```json\n{raw}\n```"
        result = _parse_article_response(wrapped)
        assert "title" in result
        assert "article_markdown" in result

    def test_parse_article_from_mixed_output(self) -> None:
        raw = _make_valid_article_json()
        mixed = f"Here is your article:\n{raw}\nHope that helps!"
        result = _parse_article_response(mixed)
        assert "title" in result

    def test_parse_article_empty_raises(self) -> None:
        with pytest.raises(ArticleGenerationError, match="empty"):
            _parse_article_response("")

    def test_parse_article_no_json_raises(self) -> None:
        with pytest.raises(ArticleGenerationError, match="Could not parse"):
            _parse_article_response("This is just plain text with no JSON at all.")

    def test_parse_article_missing_keys_raises(self) -> None:
        with pytest.raises(ArticleGenerationError, match="missing required"):
            _parse_article_response('{"title": "T"}')


# ===================================================================
# Test: Hard validations
# ===================================================================


class TestHardValidations:
    """VAL-AGEN-006 through VAL-AGEN-010."""

    def _make_valid_payload(self, **overrides: str) -> dict[str, str]:
        base: dict[str, str] = {
            "title": "10 Best Tips",
            "article_markdown": " ".join(["outdoor patio furniture word"] * 650),
            "hero_image_prompt": "hero",
            "detail_image_prompt": "detail",
            "seo_title": "10 Best Outdoor Patio Furniture",
            "meta_description": "m" * 140,
            "focus_keyword": "outdoor patio furniture",
        }
        base.update(overrides)
        return base

    def test_word_count_below_600_triggers_retry(self) -> None:
        """VAL-AGEN-006"""
        short_article = " ".join(["word"] * 100)
        payload = self._make_valid_payload(article_markdown=short_article)
        errors = run_hard_validations(payload, "outdoor patio furniture")
        assert any("word count" in e.lower() for e in errors)

    def test_keyword_count_below_5_triggers_retry(self) -> None:
        """VAL-AGEN-007"""
        # Article with keyword appearing only 2 times
        body = "outdoor patio furniture " + " and more words" * 200
        payload = self._make_valid_payload(article_markdown=body)
        errors = run_hard_validations(payload, "outdoor patio furniture")
        assert any("keyword count" in e.lower() for e in errors)

    def test_keyword_count_above_9_triggers_retry(self) -> None:
        """VAL-AGEN-007"""
        kw = "outdoor patio furniture"
        body = (f"{kw} " * 15) + "more words " * 200
        payload = self._make_valid_payload(article_markdown=body)
        errors = run_hard_validations(payload, kw)
        assert any("keyword count" in e.lower() for e in errors)

    def test_keyword_not_in_first_paragraph_triggers_retry(self) -> None:
        """VAL-AGEN-008"""
        body = (
            "This is an introduction without the keyword present at all here. "
            "It has enough words to be a proper first paragraph for testing. "
            "More sentences to make it longer and more detailed for sure."
            "\n\n## outdoor patio furniture Tips\n\n"
            "outdoor patio furniture " * 7
        )
        payload = self._make_valid_payload(article_markdown=body)
        errors = run_hard_validations(payload, "outdoor patio furniture")
        assert any("first paragraph" in e.lower() for e in errors)

    def test_no_h2_with_keyword_triggers_retry(self) -> None:
        """VAL-AGEN-009"""
        body = (
            "outdoor patio furniture is great for your home and garden space. "
            "Many people enjoy decorating their yards with quality pieces."
            "\n\n## General Tips\n\n"
            "outdoor patio furniture " * 7
        )
        payload = self._make_valid_payload(article_markdown=body)
        errors = run_hard_validations(payload, "outdoor patio furniture")
        assert any("h2" in e.lower() for e in errors)

    def test_seo_title_no_number_triggers_retry(self) -> None:
        """VAL-AGEN-010"""
        payload = self._make_valid_payload(seo_title="Best Outdoor Patio Furniture Guide")
        errors = run_hard_validations(payload, "outdoor patio furniture")
        assert any("number" in e.lower() for e in errors)

    def test_all_validations_pass(self) -> None:
        raw = _make_valid_article_json()
        parsed = _parse_article_response(raw)
        errors = run_hard_validations(parsed, "outdoor patio furniture")
        assert errors == []


# ===================================================================
# Test: Soft fixes
# ===================================================================


class TestSoftFixes:
    """VAL-AGEN-011 through VAL-AGEN-015."""

    def _make_base_parsed(self, **overrides: str) -> dict[str, str]:
        base: dict[str, str] = {
            "title": "Test Article",
            "article_markdown": "Some content with keyword outdoor patio furniture in it.",
            "hero_image_prompt": "hero",
            "detail_image_prompt": "detail",
            "seo_title": "Outdoor Patio Furniture Guide",
            "meta_description": "A" * 140,
            "focus_keyword": "outdoor patio furniture",
        }
        base.update(overrides)
        return base

    def test_truncates_seo_title_to_60(self) -> None:
        """VAL-AGEN-011"""
        long_title = "A" * 80
        parsed = self._make_base_parsed(seo_title=long_title)
        fixed = run_soft_fixes(parsed, "outdoor patio furniture")
        assert len(fixed["seo_title"]) <= 60

    def test_keyword_inserted_in_seo_title_if_missing(self) -> None:
        """VAL-AGEN-012"""
        parsed = self._make_base_parsed(seo_title="A completely unrelated title that has no keyword")
        fixed = run_soft_fixes(parsed, "outdoor patio furniture")
        assert "outdoor patio furniture" in fixed["seo_title"].lower()

    def test_meta_description_adjusted_to_range(self) -> None:
        """VAL-AGEN-013"""
        # Too short
        parsed = self._make_base_parsed(meta_description="Short desc")
        fixed = run_soft_fixes(parsed, "outdoor patio furniture")
        assert 120 <= len(fixed["meta_description"]) <= 155

    def test_meta_description_truncated_when_too_long(self) -> None:
        """VAL-AGEN-013"""
        long_desc = "A" * 200
        parsed = self._make_base_parsed(meta_description=long_desc)
        fixed = run_soft_fixes(parsed, "outdoor patio furniture")
        assert len(fixed["meta_description"]) <= 155

    def test_splits_overlong_paragraphs(self) -> None:
        """VAL-AGEN-014"""
        long_para = ". ".join([f"Sentence number {i} about outdoor patio furniture" for i in range(10)]) + "."
        result = _split_overlong_paragraphs(long_para)
        # Should have been split
        paragraphs = [p.strip() for p in result.split("\n\n") if p.strip()]
        assert len(paragraphs) > 1

    def test_removes_duplicate_h1(self) -> None:
        """VAL-AGEN-015"""
        markdown = (
            "# First Heading\n\n"
            "Some content here.\n\n"
            "# Second Heading\n\n"
            "More content here."
        )
        result = _remove_duplicate_h1(markdown, "First Heading")
        h1_count = sum(1 for line in result.splitlines() if line.strip().startswith("# ") and not line.strip().startswith("## "))
        assert h1_count <= 1

    def test_no_duplicate_h1_single_h1_unchanged(self) -> None:
        """VAL-AGEN-015 - single H1 should be kept."""
        markdown = "# Only Heading\n\nSome content."
        result = _remove_duplicate_h1(markdown, "Only Heading")
        h1_count = sum(1 for line in result.splitlines() if line.strip().startswith("# ") and not line.strip().startswith("## "))
        assert h1_count == 1


# ===================================================================
# Test: ArticleGenerator service
# ===================================================================


class TestArticleGenerator:
    """VAL-AGEN-001, VAL-AGEN-002, VAL-AGEN-003: Core generation flow."""

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        """VAL-AGEN-001: Generates valid ArticlePayload from well-formed LLM response."""
        raw = _make_valid_article_json()
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())

        assert isinstance(result, ArticlePayload)
        assert result.title
        assert result.article_markdown
        assert result.hero_image_prompt
        assert result.detail_image_prompt
        assert result.seo_title
        assert result.meta_description
        assert result.focus_keyword == "outdoor patio furniture"

    @pytest.mark.asyncio
    async def test_generate_retries_on_failure(self) -> None:
        """VAL-AGEN-002: Retries on invalid LLM response, succeeds on second."""
        bad_response = "not json at all"
        good_response = _make_valid_article_json()

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())

        assert isinstance(result, ArticlePayload)
        assert provider.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        """VAL-AGEN-003: Raises ArticleGenerationError after max attempts."""
        bad_response = "not json"
        provider = MockLLMProvider(responses=[bad_response] * MAX_SEO_GENERATION_ATTEMPTS)
        generator = ArticleGenerator(provider)

        with pytest.raises(ArticleGenerationError) as exc_info:
            await generator.generate(**_default_kwargs())

        assert "failed after" in str(exc_info.value).lower()
        assert provider.call_count == MAX_SEO_GENERATION_ATTEMPTS

    @pytest.mark.asyncio
    async def test_parses_code_fence_response(self) -> None:
        """VAL-AGEN-004: Parses JSON from code-fence-wrapped responses."""
        raw = _make_valid_article_json()
        wrapped = f"```json\n{raw}\n```"

        provider = MockLLMProvider(responses=[wrapped])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)

    @pytest.mark.asyncio
    async def test_extracts_json_from_mixed_output(self) -> None:
        """VAL-AGEN-005: Extracts first JSON object from mixed output."""
        raw = _make_valid_article_json()
        mixed = f"Here is the article:\n{raw}\nEnd of output."

        provider = MockLLMProvider(responses=[mixed])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)

    @pytest.mark.asyncio
    async def test_word_count_triggers_retry(self) -> None:
        """VAL-AGEN-006: Hard validation — word count < 600 triggers retry."""
        # Create a response with insufficient word count
        short_payload = {
            "title": "Short Article",
            "article_markdown": "This is too short. " * 10,
            "hero_image_prompt": "hero",
            "detail_image_prompt": "detail",
            "seo_title": "10 Best Tips for Garden",
            "meta_description": "A" * 140,
            "focus_keyword": "outdoor patio furniture",
        }
        bad_response = json.dumps(short_payload)
        good_response = _make_valid_article_json()

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)
        assert provider.call_count == 2
        # Verify error feedback was included in second prompt
        assert "word count" in provider.call_args[1]["prompt"].lower()

    @pytest.mark.asyncio
    async def test_keyword_count_triggers_retry(self) -> None:
        """VAL-AGEN-007: Hard validation — keyword count outside [5,9] triggers retry."""
        # Article with too few keywords (just 2)
        kw = "outdoor patio furniture"
        body = f"{kw} is great. " + "Regular content here. " * 200
        bad_payload = {
            "title": "Test",
            "article_markdown": body,
            "hero_image_prompt": "hero",
            "detail_image_prompt": "detail",
            "seo_title": "10 Best Outdoor Patio Furniture",
            "meta_description": "A" * 140,
            "focus_keyword": kw,
        }
        bad_response = json.dumps(bad_payload)
        good_response = _make_valid_article_json()

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)
        assert "keyword count" in provider.call_args[1]["prompt"].lower()

    @pytest.mark.asyncio
    async def test_keyword_in_first_paragraph_triggers_retry(self) -> None:
        """VAL-AGEN-008: Hard validation — keyword in first paragraph."""
        bad_response = _make_valid_article_json(keyword_in_first_para=False)
        good_response = _make_valid_article_json(keyword_in_first_para=True)

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)
        assert "first paragraph" in provider.call_args[1]["prompt"].lower()

    @pytest.mark.asyncio
    async def test_h2_with_keyword_triggers_retry(self) -> None:
        """VAL-AGEN-009: Hard validation — H2 with keyword."""
        bad_response = _make_valid_article_json(include_h2_with_keyword=False)
        good_response = _make_valid_article_json(include_h2_with_keyword=True)

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)
        assert "h2" in provider.call_args[1]["prompt"].lower()

    @pytest.mark.asyncio
    async def test_seo_title_number_triggers_retry(self) -> None:
        """VAL-AGEN-010: Hard validation — seo_title has number."""
        bad_response = _make_valid_article_json(seo_title="Best Outdoor Patio Furniture Guide")
        good_response = _make_valid_article_json(seo_title="10 Best Outdoor Patio Furniture Guide")

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert isinstance(result, ArticlePayload)
        assert "number" in provider.call_args[1]["prompt"].lower()

    @pytest.mark.asyncio
    async def test_soft_fix_truncates_seo_title(self) -> None:
        """VAL-AGEN-011: Soft fix — truncates seo_title to 60 chars."""
        long_seo = "A" * 80
        raw = _make_valid_article_json(seo_title=f"10 {long_seo}")
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert len(result.seo_title) <= 60

    @pytest.mark.asyncio
    async def test_soft_fix_keyword_in_seo_title(self) -> None:
        """VAL-AGEN-012: Soft fix — keyword inserted in seo_title if missing."""
        raw = _make_valid_article_json(seo_title="10 Completely Unrelated Title Here")
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert "outdoor patio furniture" in result.seo_title.lower()

    @pytest.mark.asyncio
    async def test_soft_fix_meta_description_range(self) -> None:
        """VAL-AGEN-013: Soft fix — meta_description 120-155 chars."""
        raw = _make_valid_article_json(meta_description="Short")
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        assert 120 <= len(result.meta_description) <= 155

    @pytest.mark.asyncio
    async def test_soft_fix_removes_duplicate_h1(self) -> None:
        """VAL-AGEN-015: Soft fix — removes duplicate H1."""
        raw = _make_valid_article_json(extra_h1=True)
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())
        h1_lines = [
            line
            for line in result.article_markdown.splitlines()
            if line.strip().startswith("# ") and not line.strip().startswith("## ")
        ]
        assert len(h1_lines) <= 1

    @pytest.mark.asyncio
    async def test_initial_temperature_06(self) -> None:
        """VAL-AGEN-016: Uses temperature 0.6 on initial call."""
        raw = _make_valid_article_json()
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        await generator.generate(**_default_kwargs())

        assert provider.call_args[0]["temperature"] == INITIAL_TEMPERATURE
        assert INITIAL_TEMPERATURE == 0.6

    @pytest.mark.asyncio
    async def test_retry_temperature_02(self) -> None:
        """VAL-AGEN-017: Uses temperature 0.2 on retries."""
        bad_response = "not json"
        good_response = _make_valid_article_json()

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        await generator.generate(**_default_kwargs())

        assert provider.call_args[0]["temperature"] == INITIAL_TEMPERATURE
        assert provider.call_args[1]["temperature"] == RETRY_TEMPERATURE
        assert RETRY_TEMPERATURE == 0.2

    @pytest.mark.asyncio
    async def test_article_payload_has_all_fields(self) -> None:
        """VAL-AGEN-018: ArticlePayload has all fields populated."""
        raw = _make_valid_article_json()
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        result = await generator.generate(**_default_kwargs())

        assert result.title is not None and result.title != ""
        assert result.article_markdown is not None and result.article_markdown != ""
        assert result.hero_image_prompt is not None and result.hero_image_prompt != ""
        assert result.detail_image_prompt is not None and result.detail_image_prompt != ""
        assert result.seo_title is not None and result.seo_title != ""
        assert result.meta_description is not None and result.meta_description != ""
        assert result.focus_keyword is not None and result.focus_keyword != ""

    @pytest.mark.asyncio
    async def test_error_feedback_includes_specific_errors(self) -> None:
        """Verify error feedback includes specific validation errors."""
        bad_response = _make_valid_article_json(seo_title="No Number Title")
        good_response = _make_valid_article_json()

        provider = MockLLMProvider(responses=[bad_response, good_response])
        generator = ArticleGenerator(provider)

        await generator.generate(**_default_kwargs())

        # The second call's prompt should include the error feedback
        second_prompt = provider.call_args[1]["prompt"]
        assert "validations" in second_prompt.lower() or "number" in second_prompt.lower()

    @pytest.mark.asyncio
    async def test_empty_topic_raises(self) -> None:
        """Empty topic raises immediately."""
        provider = MockLLMProvider()
        generator = ArticleGenerator(provider)

        with pytest.raises(ArticleGenerationError, match="Topic"):
            await generator.generate(
                topic="",
                vibe="test",
                profile_prompt="test",
                focus_keyword="test",
            )

    @pytest.mark.asyncio
    async def test_empty_profile_prompt_raises(self) -> None:
        """Empty profile_prompt raises immediately."""
        provider = MockLLMProvider()
        generator = ArticleGenerator(provider)

        with pytest.raises(ArticleGenerationError, match="profile_prompt"):
            await generator.generate(
                topic="test",
                vibe="test",
                profile_prompt="",
                focus_keyword="test",
            )

    @pytest.mark.asyncio
    async def test_empty_focus_keyword_raises(self) -> None:
        """Empty focus_keyword raises immediately."""
        provider = MockLLMProvider()
        generator = ArticleGenerator(provider)

        with pytest.raises(ArticleGenerationError, match="focus_keyword"):
            await generator.generate(
                topic="test",
                vibe="test",
                profile_prompt="test",
                focus_keyword="",
            )

    @pytest.mark.asyncio
    async def test_custom_max_attempts(self) -> None:
        """Custom max_attempts is respected."""
        provider = MockLLMProvider(responses=["bad"] * 3)
        generator = ArticleGenerator(provider, max_attempts=3)

        with pytest.raises(ArticleGenerationError):
            await generator.generate(**_default_kwargs())

        assert provider.call_count == 3

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """System prompt is passed to the LLM provider."""
        raw = _make_valid_article_json()
        provider = MockLLMProvider(responses=[raw])
        generator = ArticleGenerator(provider)

        await generator.generate(**_default_kwargs())

        assert provider.call_args[0]["system_prompt"] is not None
        assert "seo" in provider.call_args[0]["system_prompt"].lower()


# ===================================================================
# Test: Prompt template
# ===================================================================


class TestPromptTemplate:
    """VAL-PROM-001: Article generation prompt file."""

    def test_prompt_file_imports(self) -> None:
        from app.prompts.article_generation import (
            ARTICLE_GENERATION_SYSTEM_PROMPT,
            ARTICLE_GENERATION_USER_PROMPT,
        )
        assert ARTICLE_GENERATION_SYSTEM_PROMPT
        assert ARTICLE_GENERATION_USER_PROMPT

    def test_user_prompt_contains_placeholders(self) -> None:
        from app.prompts.article_generation import ARTICLE_GENERATION_USER_PROMPT
        assert "{topic}" in ARTICLE_GENERATION_USER_PROMPT
        assert "{profile_prompt}" in ARTICLE_GENERATION_USER_PROMPT
        assert "{focus_keyword}" in ARTICLE_GENERATION_USER_PROMPT

    def test_prompt_contains_seo_rules(self) -> None:
        from app.prompts.article_generation import ARTICLE_GENERATION_USER_PROMPT
        assert "CONTENT RULES" in ARTICLE_GENERATION_USER_PROMPT
        assert "SEO META RULES" in ARTICLE_GENERATION_USER_PROMPT
