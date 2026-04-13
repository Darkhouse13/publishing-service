"""Comprehensive tests for ArticleValidator service.

Covers: SEO issue detection, repair loop, patch application (replace_h2,
replace_paragraph), re-validation after patches, no-LLM-call when clean,
and max_repair_attempts exhaustion.

Validates assertions VAL-AVAL-001 through VAL-AVAL-007 and VAL-PROM-003.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.providers.base import LLMProvider, LLMResponse
from app.services.article_validator import (
    MAX_REPAIR_ATTEMPTS,
    ValidatorResult,
    ArticleValidator,
    _apply_patch,
    _apply_patches,
    _extract_h2_segments,
    _extract_paragraph_segments,
    _parse_patch_response,
)
from app.prompts.article_repair import (
    ARTICLE_REPAIR_SYSTEM_PROMPT,
    ARTICLE_REPAIR_USER_TEMPLATE,
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
# Helpers to build markdown content with known characteristics
# ---------------------------------------------------------------------------


def _count_keyword(text: str, keyword: str) -> int:
    """Count occurrences of keyword in text (case-insensitive, word-boundary)."""
    import re as _re
    escaped = _re.escape(keyword.strip())
    pattern = _re.compile(
        rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", _re.IGNORECASE
    )
    return len(pattern.findall(text))


def _make_clean_markdown(
    *,
    keyword: str = "outdoor patio furniture",
    keyword_count: int = 7,
    num_h2_with_keyword: int = 1,
    num_h2_total: int = 3,
) -> str:
    """Build article markdown that passes all SEO validations."""
    # First paragraph with keyword
    parts: list[str] = [
        f"When it comes to {keyword}, homeowners have many exciting options to "
        "choose from. Transforming your outdoor space into a relaxing retreat "
        "requires careful planning and the right selection of pieces that combine "
        "style with durability. This comprehensive guide will help you navigate "
        "the many choices available today."
    ]

    # First H2 with keyword
    if num_h2_with_keyword >= 1:
        parts.append(f"## Why Choose {keyword.title()}")
    else:
        parts.append("## Why Choose Quality Materials")

    # Add paragraphs with keywords spread out
    kw_inserted = _count_keyword(parts[0], keyword)
    templates_with_kw = [
        f"The best {keyword} pieces are made from weather-resistant materials that last for years. "
        "Premium teak, aluminum, and synthetic wicker are among the most popular choices. "
        "Each material offers unique benefits in terms of aesthetics and maintenance requirements.",
        f"Proper maintenance of your {keyword} extends its lifespan considerably. "
        "Regular cleaning with mild soap and water prevents buildup of dirt and debris. "
        "Investing in quality covers protects your pieces from harsh weather conditions year-round.",
        f"Shopping during off-season sales can save you hundreds on {keyword}. "
        "Many retailers offer significant discounts during fall and winter months. "
        "Consider signing up for email alerts to catch these deals early.",
        f"Quality cushions transform any {keyword} set into a comfortable lounging area. "
        "Look for UV-resistant fabrics that resist fading and water-resistant cores. "
        "Removable covers make cleaning simple and extend the life of your investment.",
    ]

    templates_no_kw = [
        "Color coordination between your seating and surrounding landscape creates visual harmony. "
        "Neutral tones like gray, beige, and brown work well with most architectural styles. "
        "Consider adding colorful accent pillows to introduce seasonal pops of color.",
        "Small spaces benefit from multi-functional pieces that serve dual purposes. "
        "Storage benches provide seating while keeping cushions and accessories organized. "
        "Folding chairs and stackable stools can be easily stored when not in use.",
        "Planning your layout before purchasing prevents costly returns and rearrangements. "
        "Measure your space carefully and leave room for walkways between pieces. "
        "Consider how many people you typically entertain to determine the right seating capacity.",
        "Accessorizing with planters, rugs, and lighting completes your outdoor room design. "
        "Outdoor rugs define seating areas and add warmth underfoot on hard surfaces. "
        "String lights and lanterns create ambiance for evening gatherings with friends.",
    ]

    kw_idx = 0
    no_kw_idx = 0
    h2_added = 1  # already added one above

    while kw_inserted < keyword_count:
        template = templates_with_kw[kw_idx % len(templates_with_kw)]
        parts.append(template)
        kw_inserted += _count_keyword(template, keyword)
        kw_idx += 1
        if kw_idx > 20:
            break

        # Add H2 headings periodically
        if h2_added < num_h2_total and kw_idx % 2 == 0:
            if h2_added < num_h2_with_keyword:
                parts.append(f"## Tips for Selecting {keyword.title()}")
            else:
                parts.append("## Tips for Selecting Quality Pieces")
            h2_added += 1

    # Add more content to reach sufficient word count (with safety limit)
    safety = 0
    while sum(len(p.split()) for p in parts) < 600 and safety < 20:
        template = templates_no_kw[no_kw_idx % len(templates_no_kw)]
        parts.append(template)
        no_kw_idx += 1
        safety += 1

    return "\n\n".join(parts)


def _make_problematic_markdown(
    *,
    keyword: str = "outdoor patio furniture",
    missing_h2_keyword: bool = False,
    low_keyword_count: bool = False,
) -> str:
    """Build article markdown that fails SEO validations.

    Set flags to introduce specific problems.
    """
    parts: list[str] = [
        f"When it comes to {keyword}, homeowners have many exciting options to "
        "choose from. Transforming your outdoor space into a relaxing retreat "
        "requires careful planning and the right selection of pieces that combine "
        "style with durability. This comprehensive guide will help you navigate "
        "the many choices available today."
    ]

    if missing_h2_keyword:
        parts.append("## Why Choose Quality Materials")
    else:
        parts.append(f"## Why Choose {keyword.title()}")

    # Build enough paragraphs with controlled keyword count
    kw_count = _count_keyword(parts[0], keyword)
    target_kw = 2 if low_keyword_count else 7

    kw_templates = [
        f"The best {keyword} pieces are made from weather-resistant materials. "
        "Premium teak and aluminum are among the most popular choices available. "
        "Each material offers unique benefits for aesthetics and maintenance.",
    ]
    no_kw_templates = [
        "Color coordination between your seating and surrounding landscape creates visual harmony. "
        "Neutral tones like gray, beige, and brown work well with most architectural styles. "
        "Consider adding colorful accent pillows to introduce seasonal pops of color.",
        "Small spaces benefit from multi-functional pieces that serve dual purposes. "
        "Storage benches provide seating while keeping cushions and accessories organized. "
        "Folding chairs and stackable stools can be easily stored when not in use.",
        "Planning your layout before purchasing prevents costly returns and rearrangements. "
        "Measure your space carefully and leave room for walkways between pieces. "
        "Consider how many people you typically entertain to determine the right seating capacity.",
        "Accessorizing with planters, rugs, and lighting completes your outdoor room design. "
        "Outdoor rugs define seating areas and add warmth underfoot on hard surfaces. "
        "String lights and lanterns create ambiance for evening gatherings with friends.",
        "Quality construction ensures durability through all seasons and weather conditions. "
        "Look for rust-resistant frames and water-repellent fabric finishes. "
        "Proper care extends the life of your investment significantly over the years.",
        "Entertaining guests becomes effortless with the right seating arrangement. "
        "Consider modular sectionals that can be reconfigured for different occasions. "
        "Add a dining set for outdoor meals during warm summer evenings.",
    ]

    idx = 0
    safety = 0
    while kw_count < target_kw and safety < 20:
        template = kw_templates[idx % len(kw_templates)]
        parts.append(template)
        kw_count += _count_keyword(template, keyword)
        idx += 1
        safety += 1

    # Add more content to reach sufficient word count (with safety limit)
    idx = 0
    safety = 0
    while sum(len(p.split()) for p in parts) < 600 and safety < 20:
        parts.append(no_kw_templates[idx % len(no_kw_templates)])
        idx += 1
        safety += 1

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Patch response builders
# ---------------------------------------------------------------------------


def _make_replace_h2_patch(target_index: int, new_text: str) -> dict[str, Any]:
    return {
        "op": "replace_h2",
        "target_index": target_index,
        "text": new_text,
    }


def _make_replace_paragraph_patch(target_index: int, new_text: str) -> dict[str, Any]:
    return {
        "op": "replace_paragraph",
        "target_index": target_index,
        "text": new_text,
    }


def _make_patch_response(patches: list[dict[str, Any]]) -> str:
    return json.dumps({"patches": patches})


# ===================================================================
# Test: Prompt file (VAL-PROM-003)
# ===================================================================


class TestPromptFile:
    """VAL-PROM-003: Validation/repair prompt file exists."""

    def test_prompt_file_imports(self) -> None:
        from app.prompts.article_repair import (
            ARTICLE_REPAIR_SYSTEM_PROMPT,
            ARTICLE_REPAIR_USER_TEMPLATE,
        )
        assert ARTICLE_REPAIR_SYSTEM_PROMPT
        assert ARTICLE_REPAIR_USER_TEMPLATE

    def test_prompt_contains_patch_instructions(self) -> None:
        assert "replace_h2" in ARTICLE_REPAIR_SYSTEM_PROMPT
        assert "replace_paragraph" in ARTICLE_REPAIR_SYSTEM_PROMPT

    def test_prompt_contains_json_schema(self) -> None:
        assert "patches" in ARTICLE_REPAIR_SYSTEM_PROMPT

    def test_user_template_contains_placeholders(self) -> None:
        assert "{focus_keyword}" in ARTICLE_REPAIR_USER_TEMPLATE
        assert "{blog_profile}" in ARTICLE_REPAIR_USER_TEMPLATE


# ===================================================================
# Test: H2 and paragraph segment extraction
# ===================================================================


class TestSegmentExtraction:
    """Tests for internal segment extraction helpers."""

    def test_extract_h2_segments(self) -> None:
        md = "## First Heading\n\nSome text\n\n## Second Heading\n\nMore text"
        segments = _extract_h2_segments(md)
        assert len(segments) == 2
        assert segments[0].text == "First Heading"
        assert segments[1].text == "Second Heading"

    def test_extract_h2_ignores_h1_and_h3(self) -> None:
        md = "# H1\n\n## H2\n\n### H3\n\n## Another H2"
        segments = _extract_h2_segments(md)
        assert len(segments) == 2
        assert segments[0].text == "H2"
        assert segments[1].text == "Another H2"

    def test_extract_paragraph_segments(self) -> None:
        md = "First paragraph here.\n\n## Heading\n\nSecond paragraph here."
        segments = _extract_paragraph_segments(md)
        assert len(segments) == 2
        assert "First paragraph" in segments[0].text
        assert "Second paragraph" in segments[1].text

    def test_extract_paragraph_skips_headings(self) -> None:
        md = "## Heading\n\nParagraph text\n\n### Another heading"
        segments = _extract_paragraph_segments(md)
        assert len(segments) == 1
        assert "Paragraph text" in segments[0].text


# ===================================================================
# Test: Patch parsing (VAL-AVAL-003, VAL-AVAL-004)
# ===================================================================


class TestPatchParsing:
    """Tests for _parse_patch_response."""

    def test_parse_valid_patches(self) -> None:
        raw = _make_patch_response([
            _make_replace_h2_patch(0, "## New Heading"),
            _make_replace_paragraph_patch(1, "New paragraph text."),
        ])
        patches = _parse_patch_response(raw)
        assert len(patches) == 2
        assert patches[0]["op"] == "replace_h2"
        assert patches[0]["target_index"] == 0
        assert patches[1]["op"] == "replace_paragraph"

    def test_parse_empty_response_raises(self) -> None:
        with pytest.raises(Exception, match="empty"):
            _parse_patch_response("")

    def test_parse_no_patches_raises(self) -> None:
        with pytest.raises(Exception, match="patches"):
            _parse_patch_response('{"patches": []}')

    def test_parse_invalid_op_raises(self) -> None:
        raw = _make_patch_response([
            {"op": "delete_section", "target_index": 0, "text": "stuff"},
        ])
        with pytest.raises(Exception, match="Unsupported"):
            _parse_patch_response(raw)

    def test_parse_missing_target_index_raises(self) -> None:
        raw = json.dumps({
            "patches": [{"op": "replace_h2", "text": "## Heading"}]
        })
        with pytest.raises(Exception, match="target_index"):
            _parse_patch_response(raw)

    def test_parse_negative_target_index_raises(self) -> None:
        raw = _make_patch_response([
            _make_replace_h2_patch(-1, "## Heading"),
        ])
        with pytest.raises(Exception, match=">= 0"):
            _parse_patch_response(raw)


# ===================================================================
# Test: Patch application (VAL-AVAL-003, VAL-AVAL-004)
# ===================================================================


class TestPatchApplication:
    """Tests for _apply_patch and _apply_patches."""

    def test_apply_replace_h2(self) -> None:
        """VAL-AVAL-003: replace_h2 patch modifies the targeted H2."""
        md = "## Old Heading\n\nSome paragraph text here.\n\n## Another Heading"
        patch = _make_replace_h2_patch(0, "## New Heading with outdoor patio furniture")
        result = _apply_patch(md, patch)
        assert "## New Heading with outdoor patio furniture" in result
        assert "## Old Heading" not in result
        # Second heading should be unchanged
        assert "## Another Heading" in result

    def test_apply_replace_h2_second_heading(self) -> None:
        """VAL-AVAL-003: replace_h2 targets by index."""
        md = "## First\n\n## Second\n\n## Third"
        patch = _make_replace_h2_patch(1, "## Replaced Second")
        result = _apply_patch(md, patch)
        assert "## First" in result
        assert "## Replaced Second" in result
        assert "## Third" in result

    def test_apply_replace_h2_auto_prefix(self) -> None:
        """replace_h2 adds ## prefix if missing."""
        md = "## Old Heading\n\nText"
        patch = {"op": "replace_h2", "target_index": 0, "text": "New Heading"}
        result = _apply_patch(md, patch)
        assert "## New Heading" in result

    def test_apply_replace_paragraph(self) -> None:
        """VAL-AVAL-004: replace_paragraph patch modifies the targeted paragraph."""
        md = "First paragraph here.\n\n## Heading\n\nSecond paragraph here."
        patch = _make_replace_paragraph_patch(0, "Replaced first paragraph with outdoor patio furniture.")
        result = _apply_patch(md, patch)
        assert "Replaced first paragraph with outdoor patio furniture." in result
        assert "First paragraph here." not in result

    def test_apply_replace_paragraph_second(self) -> None:
        """VAL-AVAL-004: replace_paragraph targets by paragraph index."""
        md = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        patch = _make_replace_paragraph_patch(1, "Replaced second paragraph.")
        result = _apply_patch(md, patch)
        assert "First paragraph." in result
        assert "Replaced second paragraph." in result
        assert "Third paragraph." in result
        assert "Second paragraph." not in result

    def test_apply_multiple_patches(self) -> None:
        """Multiple patches applied in sequence."""
        md = "## Old H2\n\nOld paragraph text.\n\n## Another H2\n\nAnother paragraph."
        patches = [
            _make_replace_h2_patch(0, "## New H2 with keyword"),
            _make_replace_paragraph_patch(0, "New paragraph with keyword."),
        ]
        result = _apply_patches(md, patches)
        assert "## New H2 with keyword" in result
        assert "New paragraph with keyword." in result

    def test_apply_h2_out_of_range_raises(self) -> None:
        md = "## Only One Heading\n\nText"
        patch = _make_replace_h2_patch(5, "## Out of Range")
        with pytest.raises(Exception, match="out of range"):
            _apply_patch(md, patch)

    def test_apply_paragraph_out_of_range_raises(self) -> None:
        md = "Only one paragraph here."
        patch = _make_replace_paragraph_patch(5, "Out of range")
        with pytest.raises(Exception, match="out of range"):
            _apply_patch(md, patch)


# ===================================================================
# Test: ArticleValidator — VAL-AVAL-001 through VAL-AVAL-007
# ===================================================================


class TestArticleValidator:
    """Core ArticleValidator service tests."""

    @pytest.mark.asyncio
    async def test_detects_seo_issues(self) -> None:
        """VAL-AVAL-001: ValidatorResult has non-empty issues for SEO violations."""
        # Create markdown with no H2 containing keyword and low keyword count
        md = _make_problematic_markdown(
            missing_h2_keyword=True,
            low_keyword_count=True,
        )
        provider = MockLLMProvider()
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword="outdoor patio furniture",
            blog_profile="A home and garden blog",
        )

        assert isinstance(result, ValidatorResult)
        assert len(result.issues) > 0
        # Should detect H2 keyword issue and/or keyword count issue
        issue_text = " ".join(result.issues).lower()
        assert "h2" in issue_text or "keyword" in issue_text

    @pytest.mark.asyncio
    async def test_enters_repair_loop_on_issues(self) -> None:
        """VAL-AVAL-002: When issues found, LLM is called for repair patches."""
        md = _make_problematic_markdown(missing_h2_keyword=True)
        # Provide a repair response that fixes the H2
        repair_response = _make_patch_response([
            _make_replace_h2_patch(0, "## Why Choose Outdoor Patio Furniture"),
        ])
        provider = MockLLMProvider(responses=[repair_response])
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword="outdoor patio furniture",
            blog_profile="A home and garden blog",
        )

        assert provider.call_count >= 1
        assert result.repaired is True

    @pytest.mark.asyncio
    async def test_applies_replace_h2_patch(self) -> None:
        """VAL-AVAL-003: replace_h2 patch modifies the correct H2 heading."""
        # Article with no keyword in H2
        md = (
            "outdoor patio furniture is great for your home and garden space. "
            "Many people enjoy decorating their yards with quality pieces."
            "\n\n## General Tips\n\n"
            + "outdoor patio furniture " * 7
            + "\n\n## Another Section\n\nMore content here about design and style."
        )
        # Provide patches to fix H2
        repair = _make_patch_response([
            _make_replace_h2_patch(0, "## outdoor patio furniture Tips"),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword="outdoor patio furniture",
            blog_profile="A home and garden blog",
        )

        # The repaired content should have the new H2
        assert "outdoor patio furniture Tips" in result.article_markdown

    @pytest.mark.asyncio
    async def test_applies_replace_paragraph_patch(self) -> None:
        """VAL-AVAL-004: replace_paragraph patch modifies the correct paragraph."""
        # Article with low keyword count — only in first paragraph
        kw = "outdoor patio furniture"
        md = (
            f"{kw} is great for your home and garden space. "
            "Many people enjoy decorating their yards with quality pieces."
            "\n\n## Why Choose Quality\n\n"
            "This is a paragraph without any keywords. "
            "It talks about general design principles. "
            "We need more variety in our selections."
            "\n\n## Tips Section\n\n"
            "Another paragraph about maintenance and care. "
            "Regular cleaning keeps everything looking fresh."
        )
        # Replace the second paragraph with one containing the keyword
        repair = _make_patch_response([
            _make_replace_paragraph_patch(
                1,
                f"Choosing the right {kw} requires careful consideration of materials and style. "
                "Premium options include teak, aluminum, and synthetic wicker varieties. "
                "Each material offers unique benefits for your outdoor living space.",
            ),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        # The repaired content should have the new paragraph text
        assert "Choosing the right outdoor patio furniture" in result.article_markdown

    @pytest.mark.asyncio
    async def test_revalidates_after_patches(self) -> None:
        """VAL-AVAL-005: Re-validates after patches; loop continues if issues persist."""
        # Create markdown with both H2 issue AND keyword count issue
        kw = "outdoor patio furniture"
        md = (
            f"{kw} is great. "
            "\n\n## General Tips\n\n"
            "No keyword here. Just general text about design. "
            "More sentences about outdoor living and garden spaces."
        )
        # First repair fixes H2 but keyword count still too low
        first_repair = _make_patch_response([
            _make_replace_h2_patch(0, f"## {kw} Tips"),
        ])
        # Second repair adds keyword to a paragraph
        second_repair = _make_patch_response([
            _make_replace_paragraph_patch(
                1,
                f"Proper maintenance of your {kw} extends its lifespan considerably. "
                f"Regular cleaning of {kw} prevents buildup. "
                "Investing in quality covers protects from harsh weather. "
                f"Seasonal care for {kw} ensures lasting beauty. "
                "These tips will help you maintain your investment. "
                f"Quality {kw} deserves proper attention.",
            ),
        ])
        provider = MockLLMProvider(responses=[first_repair, second_repair])
        validator = ArticleValidator(provider, max_repair_attempts=2)

        await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        # Should have called LLM at least twice (re-validation triggered second call)
        assert provider.call_count >= 2

    @pytest.mark.asyncio
    async def test_returns_immediately_when_no_issues(self) -> None:
        """VAL-AVAL-006: No issues → immediate return, no LLM call."""
        md = _make_clean_markdown(keyword="outdoor patio furniture")
        provider = MockLLMProvider()
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword="outdoor patio furniture",
            blog_profile="A home and garden blog",
        )

        assert result.issues == []
        assert result.repaired is False
        assert result.attempts_used == 0
        # LLM should NOT have been called
        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_returns_after_max_repair_attempts(self) -> None:
        """VAL-AVAL-007: Returns after max_repair_attempts with remaining issues."""
        # Create markdown with issues that can't be fixed by the patches
        kw = "outdoor patio furniture"
        md = (
            f"{kw} is great. "
            "\n\n## General Tips\n\n"
            "No keyword here at all. Just text. More text. More sentences. "
            "This is all about general outdoor living design tips."
        )
        # Provide ineffective patches (doesn't fix the real issues)
        ineffective_patch = _make_patch_response([
            _make_replace_h2_patch(0, "## Still No Keyword In Heading"),
        ])
        provider = MockLLMProvider(responses=[ineffective_patch, ineffective_patch])
        validator = ArticleValidator(provider, max_repair_attempts=2)

        await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        # Should have called LLM exactly max_repair_attempts times
        assert provider.call_count == 2

    @pytest.mark.asyncio
    async def test_repair_succeeds_on_first_attempt(self) -> None:
        """Repair succeeds on first attempt — returns with repaired=True."""
        kw = "outdoor patio furniture"
        md = (
            f"{kw} is great for your home and garden space. "
            "Many people enjoy decorating their yards with quality pieces."
            "\n\n## General Tips\n\n"
            + f"{kw} " * 7
            + "more words about design. "
            "Proper planning is essential for any outdoor project. "
            "Consider your space and budget before making decisions."
        )
        repair = _make_patch_response([
            _make_replace_h2_patch(0, f"## {kw} Tips"),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        assert result.repaired is True
        assert result.attempts_used == 1
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_result_contains_updated_markdown(self) -> None:
        """Result's article_markdown reflects applied patches."""
        kw = "outdoor patio furniture"
        md = (
            f"{kw} is great. "
            "\n\n## General Tips\n\n"
            + f"{kw} " * 7
            + "more words."
        )
        new_heading = f"## Best {kw} Choices"
        repair = _make_patch_response([
            _make_replace_h2_patch(0, new_heading),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        assert new_heading in result.article_markdown

    @pytest.mark.asyncio
    async def test_custom_max_repair_attempts(self) -> None:
        """Custom max_repair_attempts is respected."""
        kw = "outdoor patio furniture"
        md = f"{kw} is great.\n\n## General Tips\n\n" + f"{kw} " * 7 + "more words."
        ineffective = _make_patch_response([
            _make_replace_h2_patch(0, "## Still Bad Heading"),
        ])
        provider = MockLLMProvider(responses=[ineffective, ineffective, ineffective])
        validator = ArticleValidator(provider, max_repair_attempts=3)

        result = await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        assert provider.call_count == 3
        assert result.attempts_used == 3

    @pytest.mark.asyncio
    async def test_default_max_repair_attempts(self) -> None:
        """Default max_repair_attempts is 2."""
        assert MAX_REPAIR_ATTEMPTS == 2

    @pytest.mark.asyncio
    async def test_empty_focus_keyword_still_detects_issues(self) -> None:
        """Empty focus_keyword results in validation issues."""
        md = _make_clean_markdown()
        provider = MockLLMProvider()
        validator = ArticleValidator(provider)

        result = await validator.run(
            article_markdown=md,
            focus_keyword="",
            blog_profile="A home and garden blog",
        )

        # Should have issues because keyword is empty
        assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_uses_system_prompt(self) -> None:
        """Verify the system prompt is sent to the LLM."""
        kw = "outdoor patio furniture"
        md = f"{kw} is great.\n\n## General Tips\n\n" + f"{kw} " * 7 + "more words."
        repair = _make_patch_response([
            _make_replace_h2_patch(0, f"## {kw} Tips"),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        assert provider.call_args[0]["system_prompt"] is not None
        assert "replace_h2" in provider.call_args[0]["system_prompt"]

    @pytest.mark.asyncio
    async def test_user_prompt_contains_article_content(self) -> None:
        """Verify the user prompt includes article markdown and errors."""
        kw = "outdoor patio furniture"
        md = f"{kw} is great.\n\n## General Tips\n\n" + f"{kw} " * 7 + "more words."
        repair = _make_patch_response([
            _make_replace_h2_patch(0, f"## {kw} Tips"),
        ])
        provider = MockLLMProvider(responses=[repair])
        validator = ArticleValidator(provider)

        await validator.run(
            article_markdown=md,
            focus_keyword=kw,
            blog_profile="A home and garden blog",
        )

        user_prompt = provider.call_args[0]["prompt"]
        assert kw in user_prompt
        assert "General Tips" in user_prompt


# ===================================================================
# Test: ValidatorResult dataclass
# ===================================================================


class TestValidatorResult:
    """Tests for ValidatorResult dataclass."""

    def test_result_fields(self) -> None:
        result = ValidatorResult(
            issues=["Issue 1"],
            repaired=False,
            attempts_used=0,
            article_markdown="# Hello",
        )
        assert result.issues == ["Issue 1"]
        assert result.repaired is False
        assert result.attempts_used == 0
        assert result.article_markdown == "# Hello"

    def test_result_repaired_true(self) -> None:
        result = ValidatorResult(
            issues=[],
            repaired=True,
            attempts_used=1,
            article_markdown="Fixed content",
        )
        assert result.repaired is True
        assert result.issues == []
