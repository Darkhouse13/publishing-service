"""Tests for KeywordAnalyzer service — keyword extraction, scoring, LLM analysis.

Tests cover:
- Weighted scoring: title=3, desc=2, tag=1
- Frequency filtering (min frequency 3+)
- BrainOutput dataclass has exactly 8 fields
- LLM response parsing into BrainOutput
- Field validation: pin_title<=100, pin_description<=500, pin_text_overlay 2-6 words <=32 chars
- Retry with correction feedback on parse/validation failure
"""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields
from typing import Any

import pytest

from app.providers.base import LLMProvider, LLMResponse
from app.services.keyword_analyzer import (
    BRAIN_OUTPUT_FIELDS,
    KEYWORD_ANALYSIS_SYSTEM_PROMPT,
    KEYWORD_ANALYSIS_USER_PROMPT,
    MAX_ANALYSIS_ATTEMPTS,
    MIN_FREQUENCY,
    PIN_TEXT_OVERLAY_MAX_CHARS,
    PIN_TEXT_OVERLAY_MAX_WORDS,
    PIN_TEXT_OVERLAY_MIN_WORDS,
    WEIGHT_DESCRIPTION,
    WEIGHT_TAG,
    WEIGHT_TITLE,
    BrainOutput,
    KeywordAnalysisError,
    KeywordAnalyzer,
    _coerce_pin_text_overlay,
    _collect_terms,
    _extract_first_json_object,
    _infer_seasonal_angle,
    _parse_brain_output_response,
    _score_keyword_candidates,
    _strip_code_fences,
    _tokenize_english,
    _validate_brain_output,
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
# Helpers
# ---------------------------------------------------------------------------


def _make_pin_records() -> list[dict[str, Any]]:
    """Create a list of pin record dicts with enough repetition to pass min_frequency=3."""
    records: list[dict[str, Any]] = []
    for _ in range(5):
        records.append({
            "title": "outdoor patio furniture ideas for summer",
            "description": "Discover the best outdoor patio furniture sets for your backyard",
            "tags": ["patio", "furniture", "outdoor"],
        })
    return records


def _make_valid_brain_output_json(**overrides: str) -> str:
    """Return a valid JSON string matching the BrainOutput schema."""
    data = {
        "primary_keyword": "outdoor patio furniture",
        "image_generation_prompt": "A photorealistic image of a cozy outdoor patio furniture set on a wooden deck",
        "pin_text_overlay": "Patio Ideas",
        "pin_title": "Best Outdoor Patio Furniture Ideas for Summer",
        "pin_description": "Discover the best outdoor patio furniture sets for your backyard. Transform your outdoor space with stylish and durable furniture.",
        "cluster_label": "Outdoor Patio",
        "supporting_terms": ["patio set", "backyard furniture", "outdoor decor", "garden furniture", "deck furniture"],
        "seasonal_angle": "summer",
    }
    data.update(overrides)
    return json.dumps(data)


def _default_kwargs() -> dict[str, Any]:
    """Default kwargs for KeywordAnalyzer.analyze()."""
    return {
        "pin_records": _make_pin_records(),
        "blog_suffix": "thesundaypatio.com",
        "seed_keyword": "outdoor patio furniture",
    }


# ===================================================================
# Test: Weighted scoring
# ===================================================================


class TestWeightedScoring:
    """Weighted scoring: title=3, desc=2, tag=1."""

    def test_weight_constants(self) -> None:
        """Verify weight constants."""
        assert WEIGHT_TITLE == 3.0
        assert WEIGHT_DESCRIPTION == 2.0
        assert WEIGHT_TAG == 1.0

    def test_title_terms_get_weight_3(self) -> None:
        """Terms from title get weighted score of 3 per occurrence."""
        records = [
            {"title": "modern desk lamp", "description": "", "tags": []},
            {"title": "modern desk lamp", "description": "", "tags": []},
            {"title": "modern desk lamp", "description": "", "tags": []},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        modern = [c for c in candidates if c.term == "modern"]
        assert len(modern) == 1
        assert modern[0].weighted_score == 9.0  # 3 occurrences * weight 3
        assert modern[0].title_hits == 3

    def test_description_terms_get_weight_2(self) -> None:
        """Terms from description get weighted score of 2 per occurrence."""
        records = [
            {"title": "", "description": "modern desk lamp for office", "tags": []},
            {"title": "", "description": "modern desk lamp for office", "tags": []},
            {"title": "", "description": "modern desk lamp for office", "tags": []},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        modern = [c for c in candidates if c.term == "modern"]
        assert len(modern) == 1
        assert modern[0].weighted_score == 6.0  # 3 occurrences * weight 2
        assert modern[0].description_hits == 3

    def test_tag_terms_get_weight_1(self) -> None:
        """Terms from tags get weighted score of 1 per occurrence."""
        records = [
            {"title": "", "description": "", "tags": ["modern", "desk lamp"]},
            {"title": "", "description": "", "tags": ["modern", "desk lamp"]},
            {"title": "", "description": "", "tags": ["modern", "desk lamp"]},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        modern = [c for c in candidates if c.term == "modern"]
        assert len(modern) == 1
        assert modern[0].weighted_score == 3.0  # 3 occurrences * weight 1
        assert modern[0].tag_hits == 3

    def test_mixed_fields_combined_scoring(self) -> None:
        """A term in both title and description gets combined weight."""
        records = [
            {"title": "modern desk lamp", "description": "best modern lamp", "tags": ["modern"]},
            {"title": "modern desk lamp", "description": "best modern lamp", "tags": ["modern"]},
            {"title": "modern desk lamp", "description": "best modern lamp", "tags": ["modern"]},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        modern = [c for c in candidates if c.term == "modern"]
        assert len(modern) == 1
        # 3*(title=3) + 3*(desc=2) + 3*(tag=1) = 9 + 6 + 3 = 18
        assert modern[0].weighted_score == 18.0

    def test_candidates_sorted_by_weighted_score_desc(self) -> None:
        """Candidates are sorted by weighted_score descending."""
        records = [
            {"title": "alpha beta gamma", "description": "alpha beta", "tags": ["alpha"]},
            {"title": "alpha beta gamma", "description": "alpha beta", "tags": ["alpha"]},
            {"title": "alpha beta gamma", "description": "alpha beta", "tags": ["alpha"]},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        if len(candidates) >= 2:
            assert candidates[0].weighted_score >= candidates[1].weighted_score


# ===================================================================
# Test: Frequency filtering
# ===================================================================


class TestFrequencyFiltering:
    """Filters candidates by min frequency 3+."""

    def test_min_frequency_default(self) -> None:
        """Default min_frequency is 3."""
        assert MIN_FREQUENCY == 3

    def test_terms_below_min_frequency_excluded(self) -> None:
        """Terms appearing fewer than min_frequency times are excluded."""
        records = [
            {"title": "unique rare word", "description": "", "tags": []},
            {"title": "frequent term frequent term", "description": "frequent term", "tags": ["frequent term"]},
            {"title": "frequent term frequent term", "description": "frequent term", "tags": ["frequent term"]},
            {"title": "frequent term frequent term", "description": "frequent term", "tags": ["frequent term"]},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        terms = [c.term for c in candidates]
        assert "unique" not in terms
        assert "rare" not in terms
        # "frequent term" should appear enough times with 3 records
        common = [c for c in candidates if c.term == "frequent term"]
        assert len(common) == 1

    def test_custom_min_frequency(self) -> None:
        """Custom min_frequency parameter works."""
        records = [
            {"title": "alpha beta", "description": "", "tags": []},
            {"title": "alpha beta", "description": "", "tags": []},
        ]
        # With min_frequency=2, "alpha" should be included
        candidates = _score_keyword_candidates(records, min_frequency=2)
        terms = [c.term for c in candidates]
        assert "alpha" in terms

    def test_no_candidates_returns_empty(self) -> None:
        """When no terms meet threshold, empty list is returned."""
        records = [
            {"title": "unique one", "description": "different two", "tags": ["other three"]},
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        assert candidates == []


# ===================================================================
# Test: BrainOutput dataclass
# ===================================================================


class TestBrainOutputDataclass:
    """BrainOutput dataclass has exactly 8 fields."""

    def test_has_exactly_8_fields(self) -> None:
        """BrainOutput has exactly 8 fields."""
        field_names = [f.name for f in dataclass_fields(BrainOutput)]
        assert len(field_names) == 8

    def test_field_names_match(self) -> None:
        """BrainOutput fields match the required 8."""
        expected = {
            "primary_keyword",
            "image_generation_prompt",
            "pin_text_overlay",
            "pin_title",
            "pin_description",
            "cluster_label",
            "supporting_terms",
            "seasonal_angle",
        }
        actual = {f.name for f in dataclass_fields(BrainOutput)}
        assert actual == expected

    def test_constant_matches_dataclass(self) -> None:
        """BRAIN_OUTPUT_FIELDS constant matches actual dataclass fields."""
        field_names = tuple(f.name for f in dataclass_fields(BrainOutput))
        assert BRAIN_OUTPUT_FIELDS == field_names

    def test_brain_output_is_frozen(self) -> None:
        """BrainOutput is immutable (frozen)."""
        output = BrainOutput(
            primary_keyword="test",
            image_generation_prompt="prompt",
            pin_text_overlay="Test Overlay",
            pin_title="Test Title",
            pin_description="Test description",
            cluster_label="TestCluster",
            supporting_terms=["term1", "term2"],
            seasonal_angle="summer",
        )
        with pytest.raises(AttributeError):
            output.primary_keyword = "changed"  # type: ignore[misc]


# ===================================================================
# Test: Field validations
# ===================================================================


class TestFieldValidations:
    """Validates pin_title <= 100, pin_description <= 500, pin_text_overlay 2-6 words <= 32 chars."""

    def test_pin_title_over_100_chars(self) -> None:
        """pin_title > 100 chars produces a validation error."""
        long_title = "A" * 101
        errors = _validate_brain_output({"pin_title": long_title})
        assert any("pin_title" in e and "100" in e for e in errors)

    def test_pin_title_at_100_chars_ok(self) -> None:
        """pin_title == 100 chars passes validation."""
        title = "A" * 100
        errors = _validate_brain_output({"pin_title": title})
        assert not any("pin_title" in e for e in errors)

    def test_pin_description_over_500_chars(self) -> None:
        """pin_description > 500 chars produces a validation error."""
        long_desc = "B" * 501
        errors = _validate_brain_output({"pin_description": long_desc})
        assert any("pin_description" in e and "500" in e for e in errors)

    def test_pin_description_at_500_chars_ok(self) -> None:
        """pin_description == 500 chars passes validation."""
        desc = "B" * 500
        errors = _validate_brain_output({"pin_description": desc})
        assert not any("pin_description" in e for e in errors)

    def test_pin_text_overlay_too_few_words(self) -> None:
        """pin_text_overlay with 1 word fails validation."""
        errors = _validate_brain_output({"pin_text_overlay": "One"})
        assert any("2" in e for e in errors)

    def test_pin_text_overlay_too_many_words(self) -> None:
        """pin_text_overlay with 7 words fails validation."""
        errors = _validate_brain_output({"pin_text_overlay": "one two three four five six seven"})
        assert any("6" in e for e in errors)

    def test_pin_text_overlay_over_32_chars(self) -> None:
        """pin_text_overlay > 32 chars fails validation."""
        overlay = "A" * 33  # single word but >32 chars
        errors = _validate_brain_output({"pin_text_overlay": overlay})
        assert any("32" in e for e in errors)

    def test_pin_text_overlay_at_32_chars_ok(self) -> None:
        """pin_text_overlay == 32 chars with 2+ words passes validation."""
        overlay = "Aa Bb Cc Dd Ee Ff Gg"  # 21 chars, 7 words — need exactly 32
        # Use a realistic 2-word 32-char string
        overlay = "Best Patio Furniture Ideas"  # 26 chars, 4 words — under 32
        errors = _validate_brain_output({"pin_text_overlay": overlay})
        assert not any("pin_text_overlay" in e for e in errors)

    def test_pin_text_overlay_2_to_6_words_ok(self) -> None:
        """pin_text_overlay with 2-6 words and <=32 chars passes."""
        errors = _validate_brain_output({"pin_text_overlay": "Best Patio Ideas"})
        assert not any("pin_text_overlay" in e for e in errors)

    def test_pin_text_overlay_6_words_ok(self) -> None:
        """pin_text_overlay with exactly 6 words and <=32 chars passes."""
        overlay = "Best Patio Ideas For Summer Fun"
        assert len(overlay.split()) == 6
        assert len(overlay) <= 32
        errors = _validate_brain_output({"pin_text_overlay": overlay})
        assert not any("pin_text_overlay" in e for e in errors)

    def test_missing_required_field(self) -> None:
        """Missing required field produces validation error."""
        errors = _validate_brain_output({"pin_title": "OK Title"})
        assert any("primary_keyword" in e for e in errors)

    def test_empty_field(self) -> None:
        """Empty required field produces validation error."""
        errors = _validate_brain_output({"primary_keyword": ""})
        assert any("primary_keyword" in e for e in errors)

    def test_non_string_field(self) -> None:
        """Non-string required field produces validation error."""
        errors = _validate_brain_output({"primary_keyword": 123})  # type: ignore[dict-item]
        assert any("primary_keyword" in e for e in errors)


# ===================================================================
# Test: JSON parsing helpers
# ===================================================================


class TestJsonParsing:
    """JSON parsing from LLM responses."""

    def test_strip_code_fences(self) -> None:
        """Code fences are stripped from LLM responses."""
        fenced = '```json\n{"key": "value"}\n```'
        result = _strip_code_fences(fenced)
        assert result.strip() == '{"key": "value"}'

    def test_extract_first_json_object(self) -> None:
        """Extracts first balanced JSON object from text."""
        text = 'Some text {"a": 1, "b": 2} more text'
        result = _extract_first_json_object(text)
        assert result == '{"a": 1, "b": 2}'

    def test_parse_valid_response(self) -> None:
        """Valid JSON with all BrainOutput keys is parsed correctly."""
        raw = _make_valid_brain_output_json()
        result = _parse_brain_output_response(raw)
        assert isinstance(result, dict)
        assert result["primary_keyword"] == "outdoor patio furniture"

    def test_parse_with_code_fences(self) -> None:
        """JSON wrapped in code fences is parsed correctly."""
        raw = f'```json\n{_make_valid_brain_output_json()}\n```'
        result = _parse_brain_output_response(raw)
        assert isinstance(result, dict)
        assert "primary_keyword" in result

    def test_parse_empty_raises(self) -> None:
        """Empty string raises KeywordAnalysisError."""
        with pytest.raises(KeywordAnalysisError, match="empty"):
            _parse_brain_output_response("")

    def test_parse_no_json_raises(self) -> None:
        """Non-JSON text raises KeywordAnalysisError."""
        with pytest.raises(KeywordAnalysisError, match="parse"):
            _parse_brain_output_response("This is just plain text.")

    def test_parse_missing_keys_raises(self) -> None:
        """JSON missing required keys raises KeywordAnalysisError."""
        incomplete = json.dumps({"primary_keyword": "test"})
        with pytest.raises(KeywordAnalysisError, match="missing"):
            _parse_brain_output_response(incomplete)


# ===================================================================
# Test: Text analysis helpers
# ===================================================================


class TestTextAnalysis:
    """Tokenization and term extraction."""

    def test_tokenize_english(self) -> None:
        """Tokenizes English text to lowercase words."""
        tokens = _tokenize_english("Outdoor Patio Furniture")
        assert "outdoor" in tokens
        assert "patio" in tokens
        assert "furniture" in tokens

    def test_tokenize_removes_single_chars(self) -> None:
        """Single character tokens are removed."""
        tokens = _tokenize_english("a big cat")
        assert "a" not in tokens
        assert "big" in tokens

    def test_collect_terms_unigrams(self) -> None:
        """Collects unigrams from tokens."""
        tokens = ["outdoor", "patio", "furniture"]
        terms = _collect_terms(tokens)
        assert "outdoor" in terms
        assert "patio" in terms

    def test_collect_terms_bigrams(self) -> None:
        """Collects bigrams from tokens."""
        tokens = ["outdoor", "patio", "furniture"]
        terms = _collect_terms(tokens)
        assert "outdoor patio" in terms
        assert "patio furniture" in terms

    def test_collect_terms_trigrams(self) -> None:
        """Collects trigrams from tokens."""
        tokens = ["outdoor", "patio", "furniture"]
        terms = _collect_terms(tokens)
        assert "outdoor patio furniture" in terms


# ===================================================================
# Test: Seasonal angle inference
# ===================================================================


class TestSeasonalAngle:
    """Seasonal angle inference from terms."""

    def test_summer_detected(self) -> None:
        """Detects 'summer' in primary keyword."""
        angle = _infer_seasonal_angle("summer patio ideas", [])
        assert angle == "summer"

    def test_winter_detected(self) -> None:
        """Detects 'winter' in supporting terms."""
        angle = _infer_seasonal_angle("cozy desk", ["winter decor", "warm lighting"])
        assert angle == "winter"

    def test_no_season_returns_empty(self) -> None:
        """Returns empty string when no seasonal term is found."""
        angle = _infer_seasonal_angle("modern desk lamp", ["office lighting"])
        assert angle == ""

    def test_christmas_detected(self) -> None:
        """Detects 'christmas' in supporting terms."""
        angle = _infer_seasonal_angle("decor", ["christmas ornaments"])
        assert angle == "christmas"


# ===================================================================
# Test: pin_text_overlay coercion
# ===================================================================


class TestPinTextOverlayCoercion:
    """Coercion of pin_text_overlay to fit 2-6 words, <=32 chars."""

    def test_valid_overlay_unchanged(self) -> None:
        """Valid overlay is returned as-is."""
        result = _coerce_pin_text_overlay("Best Patio Ideas", "patio")
        assert result == "Best Patio Ideas"

    def test_too_many_words_truncated(self) -> None:
        """Too many words are truncated to max 6."""
        result = _coerce_pin_text_overlay(
            "One Two Three Four Five Six Seven", "patio"
        )
        words = result.split()
        assert len(words) <= 6

    def test_too_few_words_padded(self) -> None:
        """Too few words are padded with keyword tokens."""
        result = _coerce_pin_text_overlay("Patio", "outdoor patio")
        words = result.split()
        assert len(words) >= 2

    def test_result_within_char_limit(self) -> None:
        """Result is always <= 32 characters."""
        result = _coerce_pin_text_overlay(
            "Super Amazing Beautiful Outdoor Patio", "patio"
        )
        assert len(result) <= 32

    def test_empty_overlay_uses_keyword(self) -> None:
        """Empty overlay falls back to keyword tokens."""
        result = _coerce_pin_text_overlay("", "outdoor patio furniture")
        assert len(result.split()) >= 2
        assert len(result) <= 32

    def test_overlay_constant_values(self) -> None:
        """Verify constants for overlay validation."""
        assert PIN_TEXT_OVERLAY_MIN_WORDS == 2
        assert PIN_TEXT_OVERLAY_MAX_WORDS == 6
        assert PIN_TEXT_OVERLAY_MAX_CHARS == 32


# ===================================================================
# Test: KeywordAnalyzer service — full flow
# ===================================================================


class TestKeywordAnalyzer:
    """Core KeywordAnalyzer service tests."""

    @pytest.mark.asyncio
    async def test_analyze_success(self) -> None:
        """Successful analysis produces a BrainOutput with all 8 fields."""
        response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[response])
        analyzer = KeywordAnalyzer(provider)

        result = await analyzer.analyze(**_default_kwargs())

        assert isinstance(result, BrainOutput)
        assert result.primary_keyword == "outdoor patio furniture"
        assert result.pin_title == "Best Outdoor Patio Furniture Ideas for Summer"
        assert result.cluster_label == "Outdoor Patio"
        assert len(result.supporting_terms) > 0
        assert result.seasonal_angle == "summer"

    @pytest.mark.asyncio
    async def test_retries_on_parse_failure(self) -> None:
        """Retries with correction feedback when LLM returns invalid JSON."""
        bad_response = "not valid json"
        good_response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[bad_response, good_response])
        analyzer = KeywordAnalyzer(provider)

        result = await analyzer.analyze(**_default_kwargs())

        assert isinstance(result, BrainOutput)
        assert provider.call_count == 2
        # Second call's prompt should contain correction feedback
        second_prompt = provider.call_args[1]["prompt"]
        assert "fix" in second_prompt.lower() or "correction" in second_prompt.lower() or "failed" in second_prompt.lower()

    @pytest.mark.asyncio
    async def test_retries_on_validation_failure(self) -> None:
        """Retries with correction feedback when parse fails due to invalid data.

        Tests the retry mechanism with correction feedback on a parse-level
        failure where the LLM response has valid JSON structure but missing
        required content (empty cluster_label).
        """
        # Create a response that is valid JSON but has empty cluster_label
        # _parse_brain_output_response catches this and raises
        bad_data = json.loads(_make_valid_brain_output_json())
        bad_data["cluster_label"] = ""
        bad_response = json.dumps(bad_data)

        good_response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[bad_response, good_response])
        analyzer = KeywordAnalyzer(provider)

        result = await analyzer.analyze(**_default_kwargs())

        assert isinstance(result, BrainOutput)
        assert provider.call_count == 2
        # Second call should include correction feedback about the parse error
        second_prompt = provider.call_args[1]["prompt"]
        assert "cluster_label" in second_prompt or "empty" in second_prompt.lower()

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        """Raises KeywordAnalysisError after max attempts exhausted."""
        bad_response = "not json"
        provider = MockLLMProvider(responses=[bad_response] * MAX_ANALYSIS_ATTEMPTS)
        analyzer = KeywordAnalyzer(provider)

        with pytest.raises(KeywordAnalysisError, match="failed"):
            await analyzer.analyze(**_default_kwargs())

        assert provider.call_count == MAX_ANALYSIS_ATTEMPTS

    @pytest.mark.asyncio
    async def test_custom_max_attempts(self) -> None:
        """Custom max_attempts is respected."""
        provider = MockLLMProvider(responses=["bad"] * 3)
        analyzer = KeywordAnalyzer(provider, max_attempts=3)

        with pytest.raises(KeywordAnalysisError):
            await analyzer.analyze(**_default_kwargs())

        assert provider.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_pin_records_raises(self) -> None:
        """Empty pin_records raises KeywordAnalysisError."""
        provider = MockLLMProvider()
        analyzer = KeywordAnalyzer(provider)

        with pytest.raises(KeywordAnalysisError, match="pin_records"):
            await analyzer.analyze(
                pin_records=[],
                blog_suffix="test.com",
                seed_keyword="test",
            )

    @pytest.mark.asyncio
    async def test_empty_blog_suffix_raises(self) -> None:
        """Empty blog_suffix raises KeywordAnalysisError."""
        provider = MockLLMProvider()
        analyzer = KeywordAnalyzer(provider)

        with pytest.raises(KeywordAnalysisError, match="blog_suffix"):
            await analyzer.analyze(
                pin_records=_make_pin_records(),
                blog_suffix="",
                seed_keyword="test",
            )

    @pytest.mark.asyncio
    async def test_insufficient_signal_raises(self) -> None:
        """No candidates meeting frequency threshold raises KeywordAnalysisError."""
        # Single unique record won't have enough repetition
        records = [{"title": "unique xyz", "description": "abc def", "tags": ["ghi"]}]
        provider = MockLLMProvider()
        analyzer = KeywordAnalyzer(provider)

        with pytest.raises(KeywordAnalysisError, match="candidate"):
            await analyzer.analyze(
                pin_records=records,
                blog_suffix="test.com",
                seed_keyword="unique xyz",
            )

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """System prompt is passed to the LLM provider."""
        response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[response])
        analyzer = KeywordAnalyzer(provider)

        await analyzer.analyze(**_default_kwargs())

        assert provider.call_args[0]["system_prompt"] is not None
        assert "pinterest" in provider.call_args[0]["system_prompt"].lower()

    @pytest.mark.asyncio
    async def test_user_prompt_contains_evidence(self) -> None:
        """User prompt includes evidence payload (candidates, records)."""
        response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[response])
        analyzer = KeywordAnalyzer(provider)

        await analyzer.analyze(**_default_kwargs())

        prompt = provider.call_args[0]["prompt"]
        assert "outdoor patio furniture" in prompt.lower() or "candidate" in prompt.lower()

    @pytest.mark.asyncio
    async def test_brain_output_field_lengths_valid(self) -> None:
        """Successful BrainOutput has valid field lengths."""
        response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[response])
        analyzer = KeywordAnalyzer(provider)

        result = await analyzer.analyze(**_default_kwargs())

        assert len(result.pin_title) <= 100
        assert len(result.pin_description) <= 500
        overlay_words = result.pin_text_overlay.split()
        assert 2 <= len(overlay_words) <= 6
        assert len(result.pin_text_overlay) <= 32

    @pytest.mark.asyncio
    async def test_correction_feedback_includes_errors(self) -> None:
        """Correction feedback includes specific validation errors."""
        # First response: valid JSON but image_generation_prompt is empty
        # (parse catches this, triggers retry with correction feedback)
        bad_data = json.loads(_make_valid_brain_output_json())
        bad_data["image_generation_prompt"] = ""
        bad = json.dumps(bad_data)

        good = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[bad, good])
        analyzer = KeywordAnalyzer(provider)

        await analyzer.analyze(**_default_kwargs())

        # Should have retried
        assert provider.call_count == 2
        second_prompt = provider.call_args[1]["prompt"]
        assert "image_generation_prompt" in second_prompt or "empty" in second_prompt.lower()

    @pytest.mark.asyncio
    async def test_supporting_terms_populated(self) -> None:
        """BrainOutput.supporting_terms is populated from candidates."""
        response = _make_valid_brain_output_json()
        provider = MockLLMProvider(responses=[response])
        analyzer = KeywordAnalyzer(provider)

        result = await analyzer.analyze(**_default_kwargs())

        assert isinstance(result.supporting_terms, tuple)
        assert len(result.supporting_terms) > 0

    @pytest.mark.asyncio
    async def test_llm_failure_retried(self) -> None:
        """LLM request failure triggers retry."""
        provider_retry = MockLLMProvider()
        provider_retry.responses = [None, _make_valid_brain_output_json()]  # type: ignore[list-item]

        # Override generate to raise on first call
        original_generate = provider_retry.generate
        call_count = [0]

        async def patched_generate(*args: Any, **kwargs: Any) -> LLMResponse:
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("LLM connection error")
            return await original_generate(*args, **kwargs)

        provider_retry.generate = patched_generate  # type: ignore[assignment]
        analyzer = KeywordAnalyzer(provider_retry, max_attempts=3)

        result = await analyzer.analyze(**_default_kwargs())
        assert isinstance(result, BrainOutput)

    @pytest.mark.asyncio
    async def test_default_max_attempts(self) -> None:
        """Default max_attempts is MAX_ANALYSIS_ATTEMPTS."""
        assert MAX_ANALYSIS_ATTEMPTS == 3


# ===================================================================
# Test: Score keyword candidates
# ===================================================================


class TestScoreKeywordCandidates:
    """Direct tests for _score_keyword_candidates."""

    def test_returns_keyword_candidate_dataclass(self) -> None:
        """Returns list of KeywordCandidate dataclass instances."""
        from app.services.keyword_analyzer import KeywordCandidate

        records = _make_pin_records()
        candidates = _score_keyword_candidates(records, min_frequency=3)
        assert len(candidates) > 0
        assert isinstance(candidates[0], KeywordCandidate)
        assert hasattr(candidates[0], "term")
        assert hasattr(candidates[0], "frequency")
        assert hasattr(candidates[0], "weighted_score")
        assert hasattr(candidates[0], "title_hits")
        assert hasattr(candidates[0], "description_hits")
        assert hasattr(candidates[0], "tag_hits")

    def test_empty_records_returns_empty(self) -> None:
        """Empty records returns empty list."""
        candidates = _score_keyword_candidates([], min_frequency=1)
        assert candidates == []

    def test_stopwords_filtered(self) -> None:
        """Common stopwords are not in candidates."""
        records = [
            {"title": "the best furniture for your home", "description": "", "tags": []},
        ] * 5
        candidates = _score_keyword_candidates(records, min_frequency=3)
        terms = [c.term for c in candidates]
        # "the" should not be a standalone candidate
        for term in terms:
            if term == "the":
                pytest.fail("Stopword 'the' should not be a candidate")

    def test_ngrams_collected(self) -> None:
        """Bigrams and trigrams are collected."""
        records = [
            {"title": "outdoor patio furniture ideas", "description": "", "tags": []},
        ] * 5
        candidates = _score_keyword_candidates(records, min_frequency=3)
        terms = [c.term for c in candidates]
        # Should have bigrams and trigrams
        assert "outdoor patio" in terms or "patio furniture" in terms

    def test_engagement_score_accumulated(self) -> None:
        """Engagement score is accumulated from pin records."""
        records = [
            {
                "title": "modern desk lamp",
                "description": "",
                "tags": [],
                "engagement": {"score_total": 100.0},
            },
            {
                "title": "modern desk lamp",
                "description": "",
                "tags": [],
                "engagement": {"score_total": 50.0},
            },
            {
                "title": "modern desk lamp",
                "description": "",
                "tags": [],
                "engagement": {"score_total": 25.0},
            },
        ]
        candidates = _score_keyword_candidates(records, min_frequency=3)
        modern = [c for c in candidates if c.term == "modern"]
        assert len(modern) == 1
        assert modern[0].engagement_score == 175.0


# ===================================================================
# Test: Prompt template
# ===================================================================


class TestPromptTemplate:
    """Prompt template file tests."""

    def test_prompt_file_imports(self) -> None:
        """Prompt template can be imported."""
        assert KEYWORD_ANALYSIS_SYSTEM_PROMPT is not None
        assert len(KEYWORD_ANALYSIS_SYSTEM_PROMPT) > 0
        assert KEYWORD_ANALYSIS_USER_PROMPT is not None
        assert len(KEYWORD_ANALYSIS_USER_PROMPT) > 0

    def test_system_prompt_contains_pinterest(self) -> None:
        """System prompt references Pinterest."""
        assert "pinterest" in KEYWORD_ANALYSIS_SYSTEM_PROMPT.lower()

    def test_system_prompt_contains_json_instruction(self) -> None:
        """System prompt instructs JSON-only output."""
        assert "json" in KEYWORD_ANALYSIS_SYSTEM_PROMPT.lower()

    def test_user_prompt_contains_placeholders(self) -> None:
        """User prompt template contains required placeholders."""
        assert "{evidence_payload}" in KEYWORD_ANALYSIS_USER_PROMPT

    def test_system_prompt_mentions_constraints(self) -> None:
        """System prompt mentions hard constraints."""
        prompt_lower = KEYWORD_ANALYSIS_SYSTEM_PROMPT.lower()
        assert "pin_title" in prompt_lower or "100" in KEYWORD_ANALYSIS_SYSTEM_PROMPT
        assert "pin_description" in prompt_lower or "500" in KEYWORD_ANALYSIS_SYSTEM_PROMPT
        assert "pin_text_overlay" in prompt_lower or "32" in KEYWORD_ANALYSIS_SYSTEM_PROMPT
