"""ArticleValidator service — LLM-powered article repair with patch application.

Validates article SEO rules (keyword count, H2 headings, first-paragraph keyword),
enters a repair loop if issues are found, calls the LLM for JSON patches
(replace_h2, replace_paragraph), applies them, and re-validates.

Ported from ``src/automating_wf/content/validator.py`` but rewritten cleanly
against the new async provider architecture.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.providers.base import LLMProvider
from app.prompts.article_repair import (
    ARTICLE_REPAIR_SYSTEM_PROMPT,
    ARTICLE_REPAIR_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REPAIR_ATTEMPTS: int = 2
KEYWORD_COUNT_MIN: int = 5
KEYWORD_COUNT_MAX: int = 9
MAX_CONTEXT_PARAGRAPHS: int = 16
MAX_CONTEXT_CHARS: int = 420
ALLOWED_PATCH_OPS: set[str] = {"replace_h2", "replace_paragraph"}
H2_PATTERN = re.compile(r"^\s{0,3}##(?!#)\s*(.*?)\s*#*\s*$")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatorResult:
    """Result of article validation, optionally with repair applied.

    Attributes:
        issues: List of validation error descriptions. Empty if all rules pass.
        repaired: True if patches were applied.
        attempts_used: Number of LLM repair attempts made (0 if no repair needed).
        article_markdown: The (possibly repaired) article markdown content.
    """

    issues: list[str]
    repaired: bool
    attempts_used: int
    article_markdown: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ArticleValidatorError(RuntimeError):
    """Raised when patch parsing or application fails."""


# ---------------------------------------------------------------------------
# Internal segment dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _H2Segment:
    index: int
    line_index: int
    text: str


@dataclass(slots=True)
class _ParagraphSegment:
    index: int
    start_line: int
    end_line: int
    text: str


# ---------------------------------------------------------------------------
# Segment extraction helpers
# ---------------------------------------------------------------------------


def _keyword_pattern(focus_keyword: str) -> re.Pattern[str]:
    """Build a word-boundary regex for the focus keyword."""
    escaped = re.escape(focus_keyword.strip())
    return re.compile(
        rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE
    )


def _is_non_paragraph_line(line: str) -> bool:
    """Check if a line is not a plain-text paragraph (heading, list, etc.)."""
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


def _extract_h2_segments(article_markdown: str) -> list[_H2Segment]:
    """Extract ATX-style H2 headings from markdown with their line indices."""
    segments: list[_H2Segment] = []
    in_fenced_code = False

    for line_index, line in enumerate(article_markdown.splitlines()):
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue

        match = H2_PATTERN.match(line)
        if match:
            heading = match.group(1).strip()
            if heading:
                segments.append(
                    _H2Segment(
                        index=len(segments),
                        line_index=line_index,
                        text=heading,
                    )
                )
    return segments


def _extract_paragraph_segments(article_markdown: str) -> list[_ParagraphSegment]:
    """Extract plain-text paragraph segments from markdown."""
    lines = article_markdown.splitlines()
    segments: list[_ParagraphSegment] = []
    buffer: list[str] = []
    start_line: int | None = None
    in_fenced_code = False

    def flush(end_line: int) -> None:
        nonlocal buffer, start_line
        if start_line is None or not buffer:
            buffer = []
            start_line = None
            return
        merged = " ".join(item.strip() for item in buffer if item.strip()).strip()
        if merged:
            segments.append(
                _ParagraphSegment(
                    index=len(segments),
                    start_line=start_line,
                    end_line=end_line,
                    text=merged,
                )
            )
        buffer = []
        start_line = None

    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            flush(line_index)
            in_fenced_code = not in_fenced_code
            continue

        if in_fenced_code:
            flush(line_index)
            continue

        if not stripped:
            flush(line_index)
            continue

        if _is_non_paragraph_line(line):
            flush(line_index)
            continue

        if start_line is None:
            start_line = line_index
        buffer.append(line)

    flush(len(lines))
    return segments


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_seo(article_markdown: str, focus_keyword: str) -> list[str]:
    """Run SEO validation rules against the article markdown.

    Returns a list of issue descriptions. Empty list means all rules pass.
    """
    keyword = str(focus_keyword or "").strip()
    if not keyword:
        return ["focus_keyword is required for validation."]

    keyword_re = _keyword_pattern(keyword)
    keyword_count = len(keyword_re.findall(article_markdown))

    h2_segments = _extract_h2_segments(article_markdown)
    h2_keyword_match_count = sum(
        1 for seg in h2_segments if keyword_re.search(seg.text)
    )

    issues: list[str] = []

    if keyword_count < KEYWORD_COUNT_MIN:
        issues.append(
            f"Keyword count {keyword_count} is below minimum {KEYWORD_COUNT_MIN}."
        )
    if keyword_count > KEYWORD_COUNT_MAX:
        issues.append(
            f"Keyword count {keyword_count} exceeds maximum {KEYWORD_COUNT_MAX}."
        )
    if h2_keyword_match_count <= 0:
        issues.append(
            "At least one H2 heading must contain the exact focus keyword."
        )

    return issues


# ---------------------------------------------------------------------------
# User prompt construction
# ---------------------------------------------------------------------------


def _truncate(value: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Truncate text to limit with ellipsis."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _targeted_instructions(issues: list[str], focus_keyword: str) -> list[str]:
    """Build targeted fix instructions based on detected issues."""
    instructions: list[str] = []
    issue_text = " ".join(issues).lower()

    if "h2" in issue_text:
        instructions.append(
            f"Rewrite one existing H2 heading so it includes the exact phrase '{focus_keyword}'."
        )
    if "below minimum" in issue_text:
        instructions.append(
            "Increase exact keyword occurrences by editing existing paragraphs only."
        )
    if "exceeds maximum" in issue_text:
        instructions.append(
            "Reduce exact keyword occurrences by editing existing paragraphs only."
        )

    if not instructions:
        instructions.append("Make minimal edits so all validation rules pass.")

    return instructions


def _build_user_prompt(
    *,
    article_markdown: str,
    focus_keyword: str,
    issues: list[str],
    blog_profile: str,
) -> str:
    """Build the repair user prompt with context about issues and article structure."""
    keyword_re = _keyword_pattern(focus_keyword)
    h2_segments = _extract_h2_segments(article_markdown)
    paragraph_segments = _extract_paragraph_segments(article_markdown)
    keyword_count = len(keyword_re.findall(article_markdown))
    h2_keyword_match_count = sum(
        1 for seg in h2_segments if keyword_re.search(seg.text)
    )

    h2_listing = "\n".join(
        f"- index={seg.index} text={_truncate(seg.text)}"
        for seg in h2_segments
    ) or "- none"

    paragraph_listing = "\n".join(
        f"- index={seg.index} keyword_hits={len(keyword_re.findall(seg.text))} "
        f"text={_truncate(seg.text)}"
        for seg in paragraph_segments[:MAX_CONTEXT_PARAGRAPHS]
    ) or "- none"

    errors_block = "\n".join(f"- {issue}" for issue in issues)
    instructions = _targeted_instructions(issues, focus_keyword)
    instructions_block = "\n".join(f"- {instr}" for instr in instructions)

    return ARTICLE_REPAIR_USER_TEMPLATE.format(
        blog_profile=blog_profile.strip(),
        focus_keyword=focus_keyword,
        errors_block=errors_block,
        instructions_block=instructions_block,
        keyword_count=keyword_count,
        keyword_count_min=KEYWORD_COUNT_MIN,
        keyword_count_max=KEYWORD_COUNT_MAX,
        h2_keyword_match_count=h2_keyword_match_count,
        h2_listing=h2_listing,
        paragraph_listing=paragraph_listing,
        article_markdown=article_markdown,
    )


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Patch parsing
# ---------------------------------------------------------------------------


def _parse_patch_response(raw_response: str) -> list[dict[str, Any]]:
    """Parse the LLM repair response into a list of patch dicts."""
    content = str(raw_response or "").strip()
    if not content:
        raise ArticleValidatorError("Repair model returned empty response.")

    candidates = [content]
    extracted = _extract_first_json_object(content)
    if extracted and extracted != content:
        candidates.append(extracted)

    payload: dict[str, Any] | None = None
    last_error = "no JSON object found"

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            continue
        if not isinstance(parsed, dict):
            last_error = "response JSON root is not an object"
            continue
        payload = parsed
        break

    if payload is None:
        raise ArticleValidatorError(
            f"Could not parse repair JSON: {last_error}"
        )

    patches = payload.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ArticleValidatorError(
            "Repair JSON must include a non-empty 'patches' array."
        )

    normalized: list[dict[str, Any]] = []
    for patch in patches:
        if not isinstance(patch, dict):
            raise ArticleValidatorError("Each patch item must be a JSON object.")

        op = str(patch.get("op", "")).strip()
        if op not in ALLOWED_PATCH_OPS:
            raise ArticleValidatorError(f"Unsupported patch op '{op}'.")

        target_index_raw = patch.get("target_index")
        try:
            target_index = int(target_index_raw)
        except (TypeError, ValueError) as exc:
            raise ArticleValidatorError(
                "Patch target_index must be an integer."
            ) from exc

        if target_index < 0:
            raise ArticleValidatorError("Patch target_index must be >= 0.")

        text = str(patch.get("text", "")).strip()
        if not text:
            raise ArticleValidatorError("Patch text must be non-empty.")

        normalized.append(
            {
                "op": op,
                "target_index": target_index,
                "text": text,
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------


def _rejoin_lines(lines: list[str], had_trailing_newline: bool) -> str:
    """Rejoin split lines, preserving trailing newline."""
    text = "\n".join(lines)
    if had_trailing_newline:
        return text + "\n"
    return text


def _normalize_h2_text(value: str) -> str:
    """Normalize H2 heading text, ensuring ## prefix."""
    text = str(value or "").strip()
    if not text:
        raise ArticleValidatorError("replace_h2 patch text cannot be empty.")
    if text.startswith("##"):
        return text
    cleaned = text.lstrip("#").strip()
    if not cleaned:
        raise ArticleValidatorError("replace_h2 patch text cannot be empty.")
    return f"## {cleaned}"


def _normalize_paragraph_text(value: str) -> str:
    """Normalize paragraph text by collapsing whitespace."""
    collapsed = " ".join(str(value or "").split()).strip()
    if not collapsed:
        raise ArticleValidatorError("replace_paragraph patch text cannot be empty.")
    return collapsed


def _apply_patch(article_markdown: str, patch: dict[str, Any]) -> str:
    """Apply a single patch to the article markdown.

    Args:
        article_markdown: The current article markdown.
        patch: A dict with keys 'op', 'target_index', 'text'.

    Returns:
        Updated article markdown with the patch applied.
    """
    op = str(patch.get("op", "")).strip()
    target_index = int(patch.get("target_index", -1))
    raw_text = str(patch.get("text", "")).strip()
    lines = article_markdown.splitlines()
    had_trailing_newline = article_markdown.endswith("\n")

    if op == "replace_h2":
        segments = _extract_h2_segments(article_markdown)
        if target_index >= len(segments):
            raise ArticleValidatorError(
                f"replace_h2 target_index={target_index} is out of range "
                f"(total={len(segments)})."
            )
        segment = segments[target_index]
        lines[segment.line_index] = _normalize_h2_text(raw_text)
        return _rejoin_lines(lines, had_trailing_newline)

    if op == "replace_paragraph":
        segments = _extract_paragraph_segments(article_markdown)
        if target_index >= len(segments):
            raise ArticleValidatorError(
                f"replace_paragraph target_index={target_index} is out of range "
                f"(total={len(segments)})."
            )
        segment = segments[target_index]
        replacement = _normalize_paragraph_text(raw_text)
        updated_lines = (
            lines[: segment.start_line] + [replacement] + lines[segment.end_line :]
        )
        return _rejoin_lines(updated_lines, had_trailing_newline)

    raise ArticleValidatorError(f"Unsupported patch op '{op}'.")


def _apply_patches(article_markdown: str, patches: list[dict[str, Any]]) -> str:
    """Apply a sequence of patches to the article markdown."""
    updated = article_markdown
    for patch in patches:
        updated = _apply_patch(updated, patch)
    return updated


# ---------------------------------------------------------------------------
# ArticleValidator service
# ---------------------------------------------------------------------------


class ArticleValidator:
    """LLM-powered article repair with JSON patch application.

    Validates article SEO rules (keyword count, H2 headings, first-paragraph
    keyword).  If issues are found, enters a repair loop that calls the LLM
    for JSON patches, applies them, and re-validates.

    Returns immediately (no LLM call) when no issues are found.
    Returns after ``max_repair_attempts`` with remaining issues listed.

    Parameters:
        provider: An :class:`LLMProvider` instance used for repair calls.
        max_repair_attempts: Maximum number of repair attempts (default 2).
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    ) -> None:
        self._provider = provider
        self._max_repair_attempts = max_repair_attempts

    async def run(
        self,
        *,
        article_markdown: str,
        focus_keyword: str,
        blog_profile: str,
    ) -> ValidatorResult:
        """Validate and optionally repair an article.

        Args:
            article_markdown: The article content in markdown format.
            focus_keyword: The SEO focus keyword to validate against.
            blog_profile: Blog domain context for the repair prompt.

        Returns:
            A :class:`ValidatorResult` with issues, repair status, and
            (possibly repaired) article markdown.
        """
        current_markdown = str(article_markdown or "").strip()

        # Initial validation
        issues = _validate_seo(current_markdown, focus_keyword)

        if not issues:
            logger.info("Article passed validation with no issues.")
            return ValidatorResult(
                issues=[],
                repaired=False,
                attempts_used=0,
                article_markdown=current_markdown,
            )

        logger.warning(
            "Article validation found %d issue(s): %s",
            len(issues),
            "; ".join(issues),
        )

        # Repair loop
        current_issues = issues
        patches_applied = False

        for attempt in range(1, self._max_repair_attempts + 1):
            logger.info(
                "Repair attempt %d/%d", attempt, self._max_repair_attempts
            )

            user_prompt = _build_user_prompt(
                article_markdown=current_markdown,
                focus_keyword=focus_keyword,
                issues=current_issues,
                blog_profile=blog_profile,
            )

            try:
                response = await self._provider.generate(
                    user_prompt,
                    system_prompt=ARTICLE_REPAIR_SYSTEM_PROMPT,
                    temperature=0.1,
                )
                raw_response = response.text
            except Exception as exc:
                logger.error("LLM repair call failed on attempt %d: %s", attempt, exc)
                continue

            try:
                patches = _parse_patch_response(raw_response)
                current_markdown = _apply_patches(current_markdown, patches)
                patches_applied = True
            except ArticleValidatorError as exc:
                logger.warning(
                    "Patch parse/apply failed on attempt %d: %s", attempt, exc
                )
                continue

            # Re-validate after applying patches
            current_issues = _validate_seo(current_markdown, focus_keyword)
            logger.debug(
                "After attempt %d, %d issue(s) remain", attempt, len(current_issues)
            )

            if not current_issues:
                logger.info(
                    "Article repair succeeded after %d attempt(s)", attempt
                )
                return ValidatorResult(
                    issues=[],
                    repaired=True,
                    attempts_used=attempt,
                    article_markdown=current_markdown,
                )

        # Exhausted repair attempts
        logger.warning(
            "Article repair exhausted %d attempt(s). Remaining issues: %s",
            self._max_repair_attempts,
            "; ".join(current_issues),
        )
        return ValidatorResult(
            issues=current_issues,
            repaired=patches_applied,
            attempts_used=self._max_repair_attempts,
            article_markdown=current_markdown,
        )
