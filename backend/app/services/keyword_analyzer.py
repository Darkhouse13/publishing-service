"""KeywordAnalyzer service — keyword extraction, scoring, and LLM analysis.

Extracts keyword candidates from pin records with weighted scoring
(title=3, desc=2, tag=1), filters by min frequency 3+, sends evidence
payload to LLM, parses into BrainOutput dataclass.  Retries with
correction feedback on parse/validation failure.

Ported from ``src/automating_wf/analysis/pinterest.py`` but rewritten
cleanly against the new async provider architecture.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.providers.base import LLMProvider
from app.prompts.keyword_analysis import (
    KEYWORD_ANALYSIS_SYSTEM_PROMPT,
    KEYWORD_ANALYSIS_USER_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEIGHT_TITLE: float = 3.0
WEIGHT_DESCRIPTION: float = 2.0
WEIGHT_TAG: float = 1.0

MIN_FREQUENCY: int = 3
MAX_SUPPORTING_TERMS: int = 5
MAX_ANALYSIS_ATTEMPTS: int = 3

PIN_TEXT_OVERLAY_MIN_WORDS: int = 2
PIN_TEXT_OVERLAY_MAX_WORDS: int = 6
PIN_TEXT_OVERLAY_MAX_CHARS: int = 32

INITIAL_TEMPERATURE: float = 0.2
RETRY_TEMPERATURE: float = 0.2

BRAIN_OUTPUT_FIELDS = (
    "primary_keyword",
    "image_generation_prompt",
    "pin_text_overlay",
    "pin_title",
    "pin_description",
    "cluster_label",
    "supporting_terms",
    "seasonal_angle",
)

STOPWORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "this", "that",
    "it", "as", "from", "your", "you", "our", "their", "how", "why",
    "what", "when",
}

SEASONAL_TERMS: set[str] = {
    "spring", "summer", "autumn", "fall", "winter", "holiday",
    "christmas", "new year", "back to school",
}

JUNK_TERM_PATTERNS: tuple[str, ...] = (
    "pin by", "select deselect", "select", "deselect", "www", "com", "nescaf",
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordCandidate:
    """A scored keyword candidate extracted from pin records."""

    term: str
    frequency: int
    weighted_score: float
    engagement_score: float = 0.0
    title_hits: int = 0
    description_hits: int = 0
    tag_hits: int = 0


@dataclass(frozen=True)
class BrainOutput:
    """Structured result of keyword analysis — exactly 8 fields.

    Fields:
        primary_keyword: The main keyword identified from pin data.
        image_generation_prompt: Prompt for generating a Pinterest image.
        pin_text_overlay: Short text overlay for the pin (2-6 words, <=32 chars).
        pin_title: Pin title (max 100 chars).
        pin_description: Pin description (max 500 chars).
        cluster_label: Short topic cluster name.
        supporting_terms: List of 1-5 supporting keyword terms.
        seasonal_angle: Seasonal relevance string (empty if none).
    """

    primary_keyword: str
    image_generation_prompt: str
    pin_text_overlay: str
    pin_title: str
    pin_description: str
    cluster_label: str
    supporting_terms: tuple[str, ...] = ()
    seasonal_angle: str = ""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class KeywordAnalysisError(RuntimeError):
    """Raised when keyword analysis or LLM generation fails."""

    def __init__(
        self,
        message: str,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = list(errors or [])


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove surrounding markdown code fences from *text*."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped

    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_balanced_json(text: str, start_index: int) -> str | None:
    """Extract a balanced ``{…}`` from *text* starting at *start_index*."""
    depth = 0
    in_string = False
    escape = False

    for index in range(start_index, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            depth += 1
            continue

        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
            if depth < 0:
                return None
    return None


def _extract_first_json_object(text: str) -> str | None:
    """Find and return the first balanced JSON object in *text*."""
    for index, char_val in enumerate(text):
        if char_val != "{":
            continue
        candidate = _extract_balanced_json(text, index)
        if candidate:
            return candidate
    return None


def _parse_brain_output_response(raw_content: str) -> dict[str, Any]:
    """Parse the LLM output into the expected BrainOutput shape.

    Validates that all required keys are present and non-empty strings.
    """
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise KeywordAnalysisError("LLM returned empty content.")

    base = raw_content.strip()
    stripped = _strip_code_fences(base)
    extracted_base = _extract_first_json_object(base)
    extracted_stripped = _extract_first_json_object(stripped)

    candidates: list[str] = []
    seen: set[str] = set()

    for candidate in [base, stripped, extracted_base, extracted_stripped]:
        if candidate is None:
            continue
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)

    parse_errors: list[str] = []

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
            continue

        if not isinstance(parsed, dict):
            raise KeywordAnalysisError("LLM response is not a JSON object.")

        # Validate required keys (string fields only; supporting_terms handled separately)
        string_keys = tuple(k for k in BRAIN_OUTPUT_FIELDS if k != "supporting_terms")
        missing_keys = [key for key in string_keys if key not in parsed]
        if missing_keys:
            raise KeywordAnalysisError(
                "LLM JSON is missing required keys: " + ", ".join(missing_keys)
            )
        if "supporting_terms" not in parsed:
            raise KeywordAnalysisError(
                "LLM JSON is missing required key: supporting_terms"
            )

        # Validate string fields are non-empty
        validated: dict[str, Any] = {}
        for key in string_keys:
            value = parsed.get(key)
            if not isinstance(value, str) or not value.strip():
                raise KeywordAnalysisError(
                    f"LLM JSON field '{key}' is empty or invalid."
                )
            validated[key] = value.strip()

        # Validate supporting_terms is a list of strings
        terms_val = parsed["supporting_terms"]
        if not isinstance(terms_val, list):
            raise KeywordAnalysisError(
                "LLM JSON field 'supporting_terms' must be a list."
            )
        validated["supporting_terms"] = [str(t).strip() for t in terms_val if t]

        return validated

    error_hint = parse_errors[-1] if parse_errors else "no JSON object found"
    raise KeywordAnalysisError(
        f"Could not parse LLM JSON response: {error_hint}"
    )


# ---------------------------------------------------------------------------
# Text analysis helpers
# ---------------------------------------------------------------------------


def _tokenize_english(text: str) -> list[str]:
    """Tokenize English text to lowercase words (>1 char)."""
    lowered = text.casefold()
    tokens = re.findall(r"[a-z][a-z0-9']*", lowered)
    return [token for token in tokens if len(token) > 1]


def _term_is_valid(term: str) -> bool:
    """Check if a term is a valid keyword candidate."""
    tokens = term.split()
    if not tokens:
        return False
    lowered = term.casefold()
    if any(pattern in lowered for pattern in JUNK_TERM_PATTERNS):
        return False
    if all(token in STOPWORDS for token in tokens):
        return False
    if len(term) < 3:
        return False
    if len(tokens) == 1 and tokens[0] in STOPWORDS:
        return False
    if re.fullmatch(r"(?:www|com|net|org)", lowered):
        return False
    return True


def _collect_terms(tokens: list[str]) -> list[str]:
    """Collect unigrams, bigrams, and trigrams from tokens."""
    terms: list[str] = []
    for ngram_size in (1, 2, 3):
        if len(tokens) < ngram_size:
            continue
        for index in range(len(tokens) - ngram_size + 1):
            candidate = " ".join(tokens[index : index + ngram_size]).strip()
            if not _term_is_valid(candidate):
                continue
            terms.append(candidate)
    return terms


def _record_engagement_score(record: dict[str, Any]) -> float:
    """Extract engagement score from a pin record."""
    engagement = record.get("engagement") or {}
    score_total = engagement.get("score_total")
    if isinstance(score_total, (int, float)):
        return float(score_total)
    numeric_values = [
        float(value)
        for value in engagement.values()
        if isinstance(value, (int, float))
    ]
    return sum(numeric_values)


def _score_keyword_candidates(
    records: list[dict[str, Any]],
    *,
    min_frequency: int = MIN_FREQUENCY,
) -> list[KeywordCandidate]:
    """Score and rank keyword candidates from pin records.

    Uses weighted scoring: title=3, description=2, tag=1.
    Filters by minimum frequency threshold.
    """
    candidate_freq: dict[str, int] = defaultdict(int)
    candidate_weighted: dict[str, float] = defaultdict(float)
    candidate_engagement: dict[str, float] = defaultdict(float)
    title_hits: dict[str, int] = defaultdict(int)
    description_hits: dict[str, int] = defaultdict(int)
    tag_hits: dict[str, int] = defaultdict(int)

    for record in records:
        engagement_score = _record_engagement_score(record)

        field_terms = (
            (
                _collect_terms(_tokenize_english(record.get("title", "") or "")),
                WEIGHT_TITLE,
                title_hits,
            ),
            (
                _collect_terms(
                    _tokenize_english(record.get("description", "") or "")
                ),
                WEIGHT_DESCRIPTION,
                description_hits,
            ),
            (
                _collect_terms(
                    _tokenize_english(
                        " ".join(record.get("tags", []) or [])
                    )
                ),
                WEIGHT_TAG,
                tag_hits,
            ),
        )

        for terms, weight, hit_bucket in field_terms:
            for term in terms:
                candidate_freq[term] += 1
                candidate_weighted[term] += weight
                candidate_engagement[term] += engagement_score
                hit_bucket[term] += 1

    candidates: list[KeywordCandidate] = []
    for term, frequency in candidate_freq.items():
        if frequency < min_frequency:
            continue
        candidates.append(
            KeywordCandidate(
                term=term,
                frequency=frequency,
                weighted_score=round(candidate_weighted[term], 4),
                engagement_score=round(candidate_engagement[term], 4),
                title_hits=title_hits.get(term, 0),
                description_hits=description_hits.get(term, 0),
                tag_hits=tag_hits.get(term, 0),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.weighted_score,
            -item.engagement_score,
            -item.frequency,
            -len(item.term.split()),
            item.term,
        )
    )
    return candidates


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_brain_output(parsed: dict[str, Any]) -> list[str]:
    """Validate parsed BrainOutput fields against hard constraints.

    Returns a list of error strings.  Empty list means all validations pass.
    """
    errors: list[str] = []

    # Check all required string fields
    string_keys = tuple(k for k in BRAIN_OUTPUT_FIELDS if k != "supporting_terms")
    for key in string_keys:
        value = parsed.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty required field: {key}")

    # pin_title <= 100 chars
    pin_title = str(parsed.get("pin_title", ""))
    if len(pin_title) > 100:
        errors.append(f"pin_title exceeds 100 characters (got {len(pin_title)})")

    # pin_description <= 500 chars
    pin_description = str(parsed.get("pin_description", ""))
    if len(pin_description) > 500:
        errors.append(
            f"pin_description exceeds 500 characters (got {len(pin_description)})"
        )

    # pin_text_overlay 2-6 words, <= 32 chars
    pin_text_overlay = str(parsed.get("pin_text_overlay", ""))
    overlay_errors = _validate_pin_text_overlay(pin_text_overlay)
    errors.extend(overlay_errors)

    return errors


def _validate_pin_text_overlay(value: str) -> list[str]:
    """Validate pin_text_overlay: 2-6 words, <=32 characters."""
    errors: list[str] = []
    normalized = " ".join(str(value).split())
    words = normalized.split()

    if len(words) < PIN_TEXT_OVERLAY_MIN_WORDS:
        errors.append(
            f"pin_text_overlay must have at least {PIN_TEXT_OVERLAY_MIN_WORDS} words "
            f"(got {len(words)})"
        )
    if len(words) > PIN_TEXT_OVERLAY_MAX_WORDS:
        errors.append(
            f"pin_text_overlay exceeds {PIN_TEXT_OVERLAY_MAX_WORDS} words "
            f"(got {len(words)})"
        )
    if len(normalized) > PIN_TEXT_OVERLAY_MAX_CHARS:
        errors.append(
            f"pin_text_overlay exceeds {PIN_TEXT_OVERLAY_MAX_CHARS} characters "
            f"(got {len(normalized)})"
        )
    return errors


# ---------------------------------------------------------------------------
# Soft coercion helpers
# ---------------------------------------------------------------------------


def _truncate_with_ellipsis(value: str, limit: int) -> str:
    """Truncate string to *limit*, appending ellipsis if needed."""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    truncated = value[: limit - 3].rstrip()
    return f"{truncated}..."


def _coerce_pin_text_overlay(value: str, primary_keyword: str) -> str:
    """Coerce pin_text_overlay to fit within 2-6 words and <=32 chars.

    Pads short overlays from the primary keyword tokens and truncates
    long ones to fit constraints.
    """
    tokens = [t for t in re.findall(r"[A-Za-z0-9&']+", value) if t]
    fallback_tokens = [t for t in re.findall(r"[A-Za-z0-9&']+", primary_keyword) if t]
    if not fallback_tokens:
        fallback_tokens = ["Easy", "Ideas"]
    if not tokens:
        tokens = fallback_tokens.copy()

    # Truncate to max words
    tokens = tokens[:PIN_TEXT_OVERLAY_MAX_WORDS]

    # Pad to min words from keyword tokens
    fallback_index = 0
    while len(tokens) < PIN_TEXT_OVERLAY_MIN_WORDS:
        if fallback_index < len(fallback_tokens):
            tokens.append(fallback_tokens[fallback_index])
            fallback_index += 1
            continue
        tokens.append("Ideas")

    # Try to find a valid combination that fits within char limit
    max_count = min(PIN_TEXT_OVERLAY_MAX_WORDS, len(tokens))
    for count in range(max_count, PIN_TEXT_OVERLAY_MIN_WORDS - 1, -1):
        candidate = " ".join(tokens[:count]).strip()
        if len(candidate) <= PIN_TEXT_OVERLAY_MAX_CHARS:
            return candidate

    # Fallback: force two-word fit
    first = tokens[0][: max(1, PIN_TEXT_OVERLAY_MAX_CHARS - 2)]
    second_budget = max(1, PIN_TEXT_OVERLAY_MAX_CHARS - len(first) - 1)
    second = tokens[1][:second_budget] if len(tokens) > 1 else ""
    candidate = f"{first} {second}".strip()
    if len(candidate) > PIN_TEXT_OVERLAY_MAX_CHARS:
        candidate = candidate[:PIN_TEXT_OVERLAY_MAX_CHARS].rstrip()
    if " " not in candidate:
        split_at = max(1, min(len(candidate) - 1, len(candidate) // 2))
        candidate = f"{candidate[:split_at]} {candidate[split_at:]}".strip()
    return candidate


def _coerce_brain_output(parsed: dict[str, Any]) -> dict[str, Any]:
    """Apply soft coercion to fit BrainOutput within field constraints."""
    fixed = dict(parsed)

    # Truncate pin_title to 100 chars
    pin_title = str(fixed.get("pin_title", "")).strip()
    fixed["pin_title"] = _truncate_with_ellipsis(pin_title, 100)

    # Truncate pin_description to 500 chars
    pin_description = str(fixed.get("pin_description", "")).strip()
    fixed["pin_description"] = _truncate_with_ellipsis(pin_description, 500)

    # Coerce pin_text_overlay to 2-6 words, <=32 chars
    pin_text_overlay = str(fixed.get("pin_text_overlay", "")).strip()
    primary_keyword = str(fixed.get("primary_keyword", "")).strip()
    fixed["pin_text_overlay"] = _coerce_pin_text_overlay(
        pin_text_overlay, primary_keyword
    )

    return fixed


# ---------------------------------------------------------------------------
# Seasonal angle inference
# ---------------------------------------------------------------------------


def _infer_seasonal_angle(
    primary_keyword: str, supporting_terms: list[str]
) -> str:
    """Infer seasonal angle from keyword and supporting terms."""
    haystack = " ".join([primary_keyword, *supporting_terms]).casefold()
    for seasonal_term in sorted(SEASONAL_TERMS):
        if seasonal_term in haystack:
            return seasonal_term
    return ""


# ---------------------------------------------------------------------------
# KeywordAnalyzer service
# ---------------------------------------------------------------------------


class KeywordAnalyzer:
    """LLM keyword analysis with retry loop and validation.

    Extracts keyword candidates from pin records with weighted scoring,
    filters by min frequency, sends evidence to LLM, parses into
    BrainOutput dataclass.

    Parameters:
        provider: An :class:`LLMProvider` instance used for text generation.
        max_attempts: Maximum number of analysis attempts before raising
            :class:`KeywordAnalysisError`.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_attempts: int = MAX_ANALYSIS_ATTEMPTS,
    ) -> None:
        self._provider = provider
        self._max_attempts = max_attempts

    async def analyze(
        self,
        *,
        pin_records: list[dict[str, Any]],
        blog_suffix: str,
        seed_keyword: str,
        min_frequency: int = MIN_FREQUENCY,
    ) -> BrainOutput:
        """Analyze pin records and produce a BrainOutput.

        Args:
            pin_records: List of pin record dicts with title, description,
                tags, and optional engagement fields.
            blog_suffix: The blog domain suffix for context.
            seed_keyword: The original seed keyword used for scraping.
            min_frequency: Minimum frequency threshold for candidates.

        Returns:
            A :class:`BrainOutput` with all 8 fields populated.

        Raises:
            KeywordAnalysisError: On input validation failure or after
                exhausting all retry attempts.
        """
        # --- Input validation ---
        if not pin_records:
            raise KeywordAnalysisError("pin_records must not be empty.")

        if not blog_suffix or not blog_suffix.strip():
            raise KeywordAnalysisError("blog_suffix is required.")

        resolved_seed = str(seed_keyword or "").strip()

        # --- Score candidates ---
        candidates = _score_keyword_candidates(
            pin_records, min_frequency=min_frequency
        )

        if not candidates:
            raise KeywordAnalysisError(
                f"No keyword candidates reached frequency >= {min_frequency} "
                f"for seed '{resolved_seed}'."
            )

        # --- Build evidence ---
        primary_candidate = candidates[0]
        supporting_terms = [
            item.term
            for item in candidates[1 : 1 + MAX_SUPPORTING_TERMS]
        ]
        cluster_label = primary_candidate.term
        seasonal_angle = _infer_seasonal_angle(
            primary_candidate.term, supporting_terms
        )

        evidence_payload = json.dumps(
            {
                "blog_suffix": blog_suffix.strip(),
                "seed_keyword": resolved_seed,
                "primary_candidate": {
                    "term": primary_candidate.term,
                    "frequency": primary_candidate.frequency,
                    "weighted_score": primary_candidate.weighted_score,
                    "title_hits": primary_candidate.title_hits,
                    "description_hits": primary_candidate.description_hits,
                    "tag_hits": primary_candidate.tag_hits,
                },
                "supporting_terms": supporting_terms,
                "seasonal_angle": seasonal_angle,
                "records": pin_records,
            },
            ensure_ascii=False,
        )

        last_errors: list[str] = []

        for attempt in range(1, self._max_attempts + 1):
            correction_block = ""
            if last_errors:
                correction_block = (
                    "\n\nYour previous attempt failed these validations. "
                    "You MUST fix them:\n"
                    + "\n".join(f"- {error}" for error in last_errors)
                    + "\n\nDo not repeat these mistakes. Return JSON only."
                )

            full_prompt = KEYWORD_ANALYSIS_USER_PROMPT.format(
                evidence_payload=evidence_payload,
                correction_block=correction_block,
            )

            logger.debug(
                "Keyword analysis attempt %d/%d", attempt, self._max_attempts
            )

            # --- Call LLM ---
            try:
                response = await self._provider.generate(
                    full_prompt,
                    system_prompt=KEYWORD_ANALYSIS_SYSTEM_PROMPT,
                    temperature=INITIAL_TEMPERATURE,
                )
                raw_content = response.text
            except Exception as exc:
                logger.warning(
                    "LLM request failed on attempt %d: %s", attempt, exc
                )
                last_errors = [f"LLM request failed: {exc}"]
                continue

            # --- Parse response ---
            try:
                parsed = _parse_brain_output_response(raw_content)
            except KeywordAnalysisError as exc:
                logger.warning(
                    "Parse failed on attempt %d: %s", attempt, exc
                )
                last_errors = [str(exc)]
                continue

            # --- Validate ---
            validation_errors = _validate_brain_output(parsed)
            if validation_errors:
                logger.warning(
                    "Validation failed on attempt %d: %s",
                    attempt,
                    "; ".join(validation_errors),
                )
                last_errors = validation_errors
                # Apply coercion as a best-effort fix
                coerced = _coerce_brain_output(parsed)
                coerced_errors = _validate_brain_output(coerced)
                if not coerced_errors:
                    # Coercion fixed all issues
                    logger.info(
                        "Keyword analysis succeeded after coercion on attempt %d",
                        attempt,
                    )
                    return self._build_brain_output(
                        coerced, cluster_label, supporting_terms, seasonal_angle
                    )
                continue

            # --- Build output ---
            logger.info(
                "Keyword analysis succeeded on attempt %d", attempt
            )
            return self._build_brain_output(
                parsed, cluster_label, supporting_terms, seasonal_angle
            )

        error_summary = (
            "; ".join(last_errors) if last_errors else "Unknown failure."
        )
        raise KeywordAnalysisError(
            f"Keyword analysis failed after {self._max_attempts} attempts. "
            f"Last errors: {error_summary}",
            errors=last_errors,
        )

    @staticmethod
    def _build_brain_output(
        parsed: dict[str, Any],
        cluster_label: str,
        supporting_terms: list[str],
        seasonal_angle: str,
    ) -> BrainOutput:
        """Build a BrainOutput from parsed LLM response and computed fields."""
        # Use LLM's supporting_terms if available, otherwise fallback
        llm_terms = parsed.get("supporting_terms")
        if isinstance(llm_terms, list) and llm_terms:
            final_terms = tuple(str(t).strip() for t in llm_terms if t)
        else:
            final_terms = tuple(supporting_terms)

        # Use LLM's seasonal_angle if provided, otherwise fallback
        llm_seasonal = str(parsed.get("seasonal_angle", "")).strip()
        final_seasonal = llm_seasonal if llm_seasonal else seasonal_angle

        # Use LLM's cluster_label if provided, otherwise fallback
        llm_cluster = str(parsed.get("cluster_label", "")).strip()
        final_cluster = llm_cluster if llm_cluster else cluster_label

        return BrainOutput(
            primary_keyword=str(parsed["primary_keyword"]).strip(),
            image_generation_prompt=str(parsed["image_generation_prompt"]).strip(),
            pin_text_overlay=str(parsed["pin_text_overlay"]).strip(),
            pin_title=str(parsed["pin_title"]).strip(),
            pin_description=str(parsed["pin_description"]).strip(),
            cluster_label=final_cluster,
            supporting_terms=final_terms,
            seasonal_angle=final_seasonal,
        )
