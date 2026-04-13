"""ArticleGenerator service — LLM article generation with retry loop.

Implements the core article generation logic with hard validations and soft
fixes.  Ported from ``src/automating_wf/content/generators.py`` but rewritten
cleanly against the new async provider architecture.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.providers.base import LLMProvider
from app.prompts.article_generation import (
    ARTICLE_GENERATION_SYSTEM_PROMPT,
    ARTICLE_GENERATION_USER_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_ARTICLE_KEYS = (
    "title",
    "article_markdown",
    "hero_image_prompt",
    "detail_image_prompt",
    "seo_title",
    "meta_description",
    "focus_keyword",
)

MIN_ARTICLE_WORD_COUNT = 600
KEYWORD_COUNT_MIN = 5
KEYWORD_COUNT_MAX = 9
MAX_SEO_GENERATION_ATTEMPTS = 5
INITIAL_TEMPERATURE = 0.6
RETRY_TEMPERATURE = 0.2
MAX_PARAGRAPH_SENTENCES = 4


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArticlePayload:
    """Structured result of a successful article generation.

    Contains exactly 7 fields as specified in the validation contract.
    """

    title: str
    article_markdown: str
    hero_image_prompt: str
    detail_image_prompt: str
    seo_title: str
    meta_description: str
    focus_keyword: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ArticleGenerationError(RuntimeError):
    """Raised when article generation exhausts retries due to hard validation failures."""

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
    for index, char in enumerate(text):
        if char != "{":
            continue
        candidate = _extract_balanced_json(text, index)
        if candidate:
            return candidate
    return None


def _collect_json_candidates(raw_content: str) -> list[str]:
    """Build a list of candidate JSON strings to try parsing."""
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
    return candidates


def _parse_article_response(raw_content: str) -> dict[str, str]:
    """Parse the LLM output into the expected article payload shape."""
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise ArticleGenerationError("LLM returned empty content.")

    candidates = _collect_json_candidates(raw_content)
    parse_errors: list[str] = []

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
            continue

        if not isinstance(parsed, dict):
            raise ArticleGenerationError("LLM response is not a JSON object.")

        # Validate required keys
        missing_keys = [key for key in REQUIRED_ARTICLE_KEYS if key not in parsed]
        if missing_keys:
            raise ArticleGenerationError(
                "LLM JSON is missing required keys: " + ", ".join(missing_keys)
            )

        validated: dict[str, str] = {}
        for key in REQUIRED_ARTICLE_KEYS:
            value = parsed.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ArticleGenerationError(
                    f"LLM JSON field '{key}' is empty or invalid."
                )
            validated[key] = value.strip()
        return validated

    error_hint = parse_errors[-1] if parse_errors else "no JSON object found"
    raise ArticleGenerationError(
        f"Could not parse LLM JSON response: {error_hint}"
    )


# ---------------------------------------------------------------------------
# Text analysis helpers
# ---------------------------------------------------------------------------


def _count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text))


def _keyword_pattern(focus_keyword: str) -> re.Pattern[str]:
    escaped = re.escape(focus_keyword.strip())
    return re.compile(
        rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE
    )


def _is_non_paragraph_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#") or stripped.startswith(">") or stripped.startswith("|"):
        return True
    if re.match(r"^([-*+]\s+|\d+[.)]\s+)", stripped):
        return True
    if re.match(r"^\s{4,}\S", line):
        return True
    return False


def _extract_paragraph_blocks(article_markdown: str) -> list[str]:
    """Extract plain-text paragraph blocks from markdown."""
    paragraphs: list[str] = []
    buffer: list[str] = []
    in_fenced_code = False

    for line in article_markdown.splitlines():
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            if buffer:
                paragraph = " ".join(item.strip() for item in buffer if item.strip()).strip()
                if paragraph:
                    paragraphs.append(paragraph)
                buffer = []
            in_fenced_code = not in_fenced_code
            continue

        if in_fenced_code:
            continue

        if not stripped:
            if buffer:
                paragraph = " ".join(item.strip() for item in buffer if item.strip()).strip()
                if paragraph:
                    paragraphs.append(paragraph)
                buffer = []
            continue

        if _is_non_paragraph_line(line):
            if buffer:
                paragraph = " ".join(item.strip() for item in buffer if item.strip()).strip()
                if paragraph:
                    paragraphs.append(paragraph)
                buffer = []
            continue

        buffer.append(line)

    if buffer:
        paragraph = " ".join(item.strip() for item in buffer if item.strip()).strip()
        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs


def _count_sentences(paragraph: str) -> int:
    normalized = " ".join(paragraph.split()).strip()
    if not normalized:
        return 0
    sentence_endings = len(re.findall(r"[.!?]+(?=\s|$)", normalized))
    if normalized[-1] not in ".!?":
        sentence_endings += 1
    return sentence_endings


def _extract_h2_headings(article_markdown: str) -> list[str]:
    headings: list[str] = []
    lines = article_markdown.splitlines()
    in_fenced_code = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue

        atx_match = re.match(r"^\s{0,3}##(?!#)\s*(.*?)\s*#*\s*$", line)
        if atx_match:
            heading = atx_match.group(1).strip()
            if heading:
                headings.append(heading)
            continue

        if index + 1 >= len(lines):
            continue
        next_line = lines[index + 1].strip()
        if not stripped:
            continue
        if re.match(r"^\s{0,3}-+\s*$", next_line) and not _is_non_paragraph_line(line):
            headings.append(stripped)

    return headings


# ---------------------------------------------------------------------------
# Hard validations
# ---------------------------------------------------------------------------


def run_hard_validations(parsed: dict[str, str], focus_keyword: str) -> list[str]:
    """Run strict validations that must pass before article acceptance."""
    errors: list[str] = []

    for key in REQUIRED_ARTICLE_KEYS:
        value = parsed.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty required field: {key}")

    resolved_keyword = str(focus_keyword or "").strip()
    if not resolved_keyword:
        errors.append("focus_keyword is required for validation.")
        return errors

    article_markdown = str(parsed.get("article_markdown", "")).strip()
    seo_title = str(parsed.get("seo_title", "")).strip()
    keyword_regex = _keyword_pattern(resolved_keyword)

    word_count = _count_words(article_markdown)
    if word_count < MIN_ARTICLE_WORD_COUNT:
        errors.append(
            f"Article word count must be >= {MIN_ARTICLE_WORD_COUNT}; got {word_count}."
        )

    keyword_count = len(keyword_regex.findall(article_markdown))
    if not (KEYWORD_COUNT_MIN <= keyword_count <= KEYWORD_COUNT_MAX):
        errors.append(
            f"Keyword count {keyword_count} is outside allowed range "
            f"{KEYWORD_COUNT_MIN}–{KEYWORD_COUNT_MAX}"
        )

    paragraphs = _extract_paragraph_blocks(article_markdown)
    if not paragraphs:
        errors.append("Article must include at least one plain-text paragraph.")
    else:
        first_paragraph = paragraphs[0]
        if not keyword_regex.search(first_paragraph):
            errors.append("Focus keyword must appear in the first paragraph.")

    h2_headings = _extract_h2_headings(article_markdown)
    if not any(keyword_regex.search(heading) for heading in h2_headings):
        errors.append("At least one H2 heading must contain the exact focus keyword.")

    if seo_title and not re.search(r"\d", seo_title):
        errors.append("seo_title must include at least one number.")

    return errors


# ---------------------------------------------------------------------------
# Soft fixes
# ---------------------------------------------------------------------------


def _truncate_at_word_boundary(text: str, limit: int) -> str:
    cleaned = str(text or "").strip()
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit].rstrip()
    if " " in truncated:
        candidate = truncated.rsplit(" ", 1)[0].rstrip()
        if candidate:
            return candidate
    return truncated


def _truncate_with_ellipsis(text: str, limit: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return "…"[:limit]
    body = _truncate_at_word_boundary(cleaned, limit - 1).rstrip(" .")
    if not body:
        body = cleaned[: limit - 1].rstrip()
    return f"{body}…"


def _normalize_heading_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _remove_duplicate_h1(article_markdown: str, title: str) -> str:
    """Remove duplicate H1 heading if it matches the article title."""
    lines = article_markdown.splitlines()
    if not lines:
        return article_markdown

    # Count H1 headings
    h1_count = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#\s+", stripped):
            h1_count += 1

    if h1_count <= 1:
        return article_markdown

    # Remove all but the first H1
    first_h1_seen = False
    rebuilt: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#\s+", stripped):
            if not first_h1_seen:
                first_h1_seen = True
                rebuilt.append(line)
            # Skip subsequent H1 headings
        else:
            rebuilt.append(line)

    return "\n".join(rebuilt)


def _sentence_boundary_after_n(text: str, sentence_count: int) -> int | None:
    if sentence_count <= 0:
        return None
    matches = list(re.finditer(r"[.!?]+(?=\s|$)", text))
    if len(matches) >= sentence_count:
        return matches[sentence_count - 1].end()
    if text and text[-1] not in ".!?" and (len(matches) + 1) >= sentence_count:
        return len(text)
    return None


def _split_paragraph_at_sentence_limit(
    paragraph: str, max_sentences: int
) -> list[str]:
    normalized = " ".join(str(paragraph or "").split()).strip()
    if not normalized:
        return []

    parts: list[str] = []
    remaining = normalized
    while _count_sentences(remaining) > max_sentences:
        boundary = _sentence_boundary_after_n(remaining, max_sentences)
        if boundary is None or boundary <= 0 or boundary >= len(remaining):
            break
        left = remaining[:boundary].strip()
        right = remaining[boundary:].strip()
        if not left or not right:
            break
        parts.append(left)
        remaining = right
    parts.append(remaining)
    return parts


def _is_plain_paragraph_block(block_text: str) -> bool:
    lines = block_text.splitlines()
    first_line = ""
    for line in lines:
        if line.strip():
            first_line = line
            break
    if not first_line:
        return False
    return not _is_non_paragraph_line(first_line)


def _split_overlong_paragraphs(article_markdown: str) -> str:
    """Split paragraphs exceeding the sentence limit into shorter ones."""
    if not isinstance(article_markdown, str) or not article_markdown.strip():
        return article_markdown

    lines = article_markdown.splitlines()
    rebuilt: list[str] = []
    paragraph_buffer: list[str] = []
    in_fenced_code = False

    def flush_buffer() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        block_text = "\n".join(paragraph_buffer)
        paragraph_buffer = []
        if not _is_plain_paragraph_block(block_text):
            rebuilt.extend(block_text.splitlines())
            return

        merged = " ".join(
            line.strip() for line in block_text.splitlines() if line.strip()
        ).strip()
        split_parts = _split_paragraph_at_sentence_limit(
            merged, MAX_PARAGRAPH_SENTENCES
        )
        if not split_parts:
            return
        for idx, part in enumerate(split_parts):
            rebuilt.append(part)
            if idx < len(split_parts) - 1:
                rebuilt.append("")

    for line in lines:
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            flush_buffer()
            in_fenced_code = not in_fenced_code
            rebuilt.append(line)
            continue

        if in_fenced_code:
            rebuilt.append(line)
            continue

        if not stripped:
            flush_buffer()
            rebuilt.append("")
            continue

        if _is_non_paragraph_line(line):
            flush_buffer()
            rebuilt.append(line)
            continue

        paragraph_buffer.append(line)

    flush_buffer()
    updated = "\n".join(rebuilt).rstrip()
    if article_markdown.endswith("\n"):
        return f"{updated}\n"
    return updated


def run_soft_fixes(parsed: dict[str, str], focus_keyword: str) -> dict[str, str]:
    """Apply non-blocking SEO/content fixes after hard validation passes."""
    fixed = dict(parsed)
    for key in REQUIRED_ARTICLE_KEYS:
        value = fixed.get(key, "")
        fixed[key] = str(value).strip() if value is not None else ""

    resolved_keyword = str(focus_keyword or "").strip()
    fixed["focus_keyword"] = resolved_keyword

    # --- seo_title ---
    seo_title = fixed["seo_title"]
    if len(seo_title) > 60:
        seo_title = _truncate_at_word_boundary(seo_title, 60)
    if resolved_keyword.casefold() not in seo_title.casefold():
        prefixed_title = f"{resolved_keyword} - {seo_title}".strip(" -")
        seo_title = _truncate_at_word_boundary(prefixed_title, 60)
    fixed["seo_title"] = seo_title

    # --- meta_description ---
    meta_description = fixed["meta_description"]
    if len(meta_description) < 120:
        while len(meta_description) < 120:
            meta_description = (
                f"{meta_description.rstrip()} Learn more about {resolved_keyword} here."
            ).strip()
    if len(meta_description) > 155:
        meta_description = _truncate_with_ellipsis(meta_description, 155)
    if resolved_keyword.casefold() not in meta_description.casefold():
        meta_description = (
            f"{meta_description.rstrip()} Discover more about {resolved_keyword}."
        ).strip()
        if len(meta_description) > 155:
            meta_description = _truncate_with_ellipsis(meta_description, 155)
    fixed["meta_description"] = meta_description

    # --- article_markdown ---
    article_markdown = fixed["article_markdown"]
    article_markdown = _remove_duplicate_h1(article_markdown, fixed["title"])
    article_markdown = _split_overlong_paragraphs(article_markdown)
    fixed["article_markdown"] = article_markdown

    return fixed


# ---------------------------------------------------------------------------
# ArticleGenerator service
# ---------------------------------------------------------------------------


class ArticleGenerator:
    """LLM article generation with retry loop, hard validation, and soft fixes.

    Parameters:
        provider: An :class:`LLMProvider` instance used for text generation.
        max_attempts: Maximum number of generation attempts before raising
            :class:`ArticleGenerationError`.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_attempts: int = MAX_SEO_GENERATION_ATTEMPTS,
    ) -> None:
        self._provider = provider
        self._max_attempts = max_attempts

    async def generate(
        self,
        *,
        topic: str,
        vibe: str,
        profile_prompt: str,
        focus_keyword: str,
    ) -> ArticlePayload:
        """Generate an SEO-optimised article.

        Args:
            topic: The article topic / title seed.
            vibe: Tone / style descriptor for the article.
            profile_prompt: Blog domain context for the LLM.
            focus_keyword: The exact SEO focus keyword to use.

        Returns:
            An :class:`ArticlePayload` with all fields populated.

        Raises:
            ArticleGenerationError: After exhausting all retry attempts.
        """
        if not topic or not topic.strip():
            raise ArticleGenerationError("Topic is required.")
        if not profile_prompt or not profile_prompt.strip():
            raise ArticleGenerationError("profile_prompt is required.")

        resolved_keyword = str(focus_keyword or "").strip()
        if not resolved_keyword:
            raise ArticleGenerationError("focus_keyword is required.")

        base_user_prompt = ARTICLE_GENERATION_USER_PROMPT.format(
            topic=topic.strip(),
            vibe=vibe.strip(),
            profile_prompt=profile_prompt.strip(),
            focus_keyword=resolved_keyword,
        )

        last_errors: list[str] = []

        for attempt in range(1, self._max_attempts + 1):
            feedback_block = ""
            if last_errors:
                feedback_block = (
                    "\n\nYour previous attempt failed these validations. "
                    "You MUST fix them:\n"
                    + "\n".join(f"- {error}" for error in last_errors)
                    + "\n\nDo not repeat these mistakes."
                )
            full_prompt = base_user_prompt + feedback_block

            temperature = INITIAL_TEMPERATURE if attempt == 1 else RETRY_TEMPERATURE

            logger.debug(
                "Article generation attempt %d/%d (temp=%.1f)",
                attempt,
                self._max_attempts,
                temperature,
            )

            # --- Call LLM ---
            try:
                response = await self._provider.generate(
                    full_prompt,
                    system_prompt=ARTICLE_GENERATION_SYSTEM_PROMPT,
                    temperature=temperature,
                )
                raw_content = response.text
            except Exception as exc:
                logger.warning("LLM request failed on attempt %d: %s", attempt, exc)
                last_errors = [f"LLM request failed: {exc}"]
                continue

            # --- Parse response ---
            try:
                parsed = _parse_article_response(raw_content)
            except ArticleGenerationError as exc:
                logger.warning("Parse failed on attempt %d: %s", attempt, exc)
                last_errors = [str(exc)]
                continue

            # Track best effort payload for potential diagnostics
            _best_effort_payload = dict(parsed)  # noqa: F841

            # --- Hard validation ---
            validation_errors = run_hard_validations(
                parsed=parsed, focus_keyword=resolved_keyword
            )
            if validation_errors:
                logger.warning(
                    "Validation failed on attempt %d: %s",
                    attempt,
                    "; ".join(validation_errors),
                )
                last_errors = validation_errors
                continue

            # --- Soft fixes ---
            fixed = run_soft_fixes(parsed=parsed, focus_keyword=resolved_keyword)
            logger.info(
                "Article generated successfully after %d attempt(s)", attempt
            )
            return ArticlePayload(
                title=fixed["title"],
                article_markdown=fixed["article_markdown"],
                hero_image_prompt=fixed["hero_image_prompt"],
                detail_image_prompt=fixed["detail_image_prompt"],
                seo_title=fixed["seo_title"],
                meta_description=fixed["meta_description"],
                focus_keyword=fixed["focus_keyword"],
            )

        error_summary = "; ".join(last_errors) if last_errors else "Unknown failure."
        raise ArticleGenerationError(
            f"Article generation failed after {self._max_attempts} attempts. "
            f"Last errors: {error_summary}",
            errors=last_errors,
        )
