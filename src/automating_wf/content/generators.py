from __future__ import annotations

import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


REQUIRED_ARTICLE_KEYS = (
    "title",
    "article_markdown",
    "hero_image_prompt",
    "detail_image_prompt",
    "seo_title",
    "meta_description",
    "focus_keyword",
)
VIBE_KEY = "vibes"
MIN_ARTICLE_WORD_COUNT = 600
MAX_PARAGRAPH_SENTENCES = 4
KEYWORD_COUNT_MIN = 5  # Fixed minimum exact keyword occurrences in article body.
KEYWORD_COUNT_MAX = 9  # Fixed maximum exact keyword occurrences in article body.
MAX_SEO_GENERATION_ATTEMPTS = 5
DEFAULT_DEEPSEEK_INITIAL_TEMPERATURE = 0.6
DEFAULT_DEEPSEEK_RETRY_TEMPERATURE = 0.2
SEO_TARGET_MIN_WORDS = 600
SEO_TARGET_MAX_WORDS = 900


class GenerationError(RuntimeError):
    """Raised when article or image generation fails."""


class ArticleValidationError(GenerationError):
    """Raised when article generation exhausts retries due to hard validation failures."""

    def __init__(
        self,
        message: str,
        errors: list[str] | None = None,
        payload: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = list(errors or [])
        self.payload = dict(payload) if isinstance(payload, dict) else None


def _strip_code_fences(text: str) -> str:
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
    for index, char in enumerate(text):
        if char != "{":
            continue
        candidate = _extract_balanced_json(text, index)
        if candidate:
            return candidate
    return None


def _validate_article_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise GenerationError("DeepSeek response is not a JSON object.")

    missing_keys = [key for key in REQUIRED_ARTICLE_KEYS if key not in payload]
    if missing_keys:
        raise GenerationError(
            "DeepSeek JSON is missing required keys: " + ", ".join(missing_keys)
        )

    validated: dict[str, str] = {}
    for key in REQUIRED_ARTICLE_KEYS:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GenerationError(f"DeepSeek JSON field '{key}' is empty or invalid.")
        validated[key] = value.strip()
    # Backward-compatibility alias used by existing Streamlit/uploader code paths.
    validated["content_markdown"] = validated["article_markdown"]
    return validated


def derive_focus_keyword(topic: str) -> str:
    """Derive a deterministic 2-5 word focus keyword phrase from a topic string."""
    raw = str(topic or "").strip()
    if not raw:
        raise GenerationError("Topic is required to derive focus keyword.")

    lowered = raw.casefold()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    if not tokens:
        raise GenerationError("Could not derive focus keyword from topic.")

    instruction_markers = {
        "write",
        "article",
        "about",
        "benefits",
        "using",
        "explain",
        "create",
        "generate",
        "show",
        "help",
        "guide",
        "blog",
        "post",
        "please",
    }
    sentence_like = bool(re.search(r"[.!?]", raw)) or len(tokens) > 7 or any(
        marker in tokens for marker in instruction_markers
    )
    if not sentence_like:
        phrase = " ".join(tokens[:5]).strip()
        if len(phrase.split()) >= 2:
            return phrase

    filtered = [token for token in tokens if token not in instruction_markers]
    if len(filtered) < 2:
        filtered = tokens
    phrase_tokens = filtered[:5]
    if len(phrase_tokens) < 2 and len(tokens) >= 2:
        phrase_tokens = tokens[:2]
    phrase = " ".join(phrase_tokens).strip()
    if not phrase:
        raise GenerationError("Could not derive focus keyword from topic.")
    return phrase


def _keyword_pattern(focus_keyword: str) -> re.Pattern[str]:
    escaped_keyword = re.escape(focus_keyword.strip())
    return re.compile(rf"(?<![A-Za-z0-9]){escaped_keyword}(?![A-Za-z0-9])", re.IGNORECASE)


def _count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text))


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


def run_hard_validations(parsed: dict, focus_keyword: str) -> list[str]:
    """Run strict validations that must pass before an article can be accepted."""
    errors: list[str] = []
    if not isinstance(parsed, dict):
        return ["Parsed payload must be a JSON object."]

    for key in REQUIRED_ARTICLE_KEYS:
        value = parsed.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty required field: {key}")

    resolved_focus_keyword = str(focus_keyword or "").strip()
    if not resolved_focus_keyword:
        errors.append("focus_keyword is required for validation.")
        return errors

    article_markdown = str(parsed.get("article_markdown", "")).strip()
    seo_title = str(parsed.get("seo_title", "")).strip()
    keyword_regex = _keyword_pattern(resolved_focus_keyword)

    word_count = _count_words(article_markdown)
    if word_count < MIN_ARTICLE_WORD_COUNT:
        errors.append(
            f"Article word count must be >= {MIN_ARTICLE_WORD_COUNT}; got {word_count}."
        )

    keyword_count = len(keyword_regex.findall(article_markdown))
    if not (KEYWORD_COUNT_MIN <= keyword_count <= KEYWORD_COUNT_MAX):
        errors.append(
            f"Keyword count {keyword_count} is outside allowed range {KEYWORD_COUNT_MIN}–{KEYWORD_COUNT_MAX}"
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


def _remove_duplicate_leading_h1(article_markdown: str, title: str) -> str:
    lines = article_markdown.splitlines()
    if not lines:
        return article_markdown

    first_line = lines[0].strip()
    match = re.match(r"^#\s+(.*)$", first_line)
    if not match:
        return article_markdown

    heading_text = _normalize_heading_text(match.group(1))
    normalized_title = _normalize_heading_text(title)
    if not heading_text or not normalized_title or heading_text != normalized_title:
        return article_markdown

    remaining = lines[1:]
    while remaining and not remaining[0].strip():
        remaining = remaining[1:]
    return "\n".join(remaining)


def _sentence_boundary_after_n(text: str, sentence_count: int) -> int | None:
    if sentence_count <= 0:
        return None
    matches = list(re.finditer(r"[.!?]+(?=\s|$)", text))
    if len(matches) >= sentence_count:
        return matches[sentence_count - 1].end()
    if text and text[-1] not in ".!?" and (len(matches) + 1) >= sentence_count:
        return len(text)
    return None


def _split_paragraph_at_sentence_limit(paragraph: str, max_sentences: int) -> list[str]:
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


def _split_overlong_plain_paragraphs(article_markdown: str) -> str:
    if not isinstance(article_markdown, str) or not article_markdown.strip():
        return article_markdown

    lines = article_markdown.splitlines()
    rebuilt: list[str] = []
    paragraph_buffer: list[str] = []
    in_fenced_code = False

    def flush_paragraph_buffer() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        block_text = "\n".join(paragraph_buffer)
        paragraph_buffer = []
        if not _is_plain_paragraph_block(block_text):
            rebuilt.extend(block_text.splitlines())
            return

        merged = " ".join(line.strip() for line in block_text.splitlines() if line.strip()).strip()
        split_parts = _split_paragraph_at_sentence_limit(merged, MAX_PARAGRAPH_SENTENCES)
        if not split_parts:
            return
        for index, part in enumerate(split_parts):
            rebuilt.append(part)
            if index < len(split_parts) - 1:
                rebuilt.append("")

    for line in lines:
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            flush_paragraph_buffer()
            in_fenced_code = not in_fenced_code
            rebuilt.append(line)
            continue

        if in_fenced_code:
            rebuilt.append(line)
            continue

        if not stripped:
            flush_paragraph_buffer()
            rebuilt.append("")
            continue

        if _is_non_paragraph_line(line):
            flush_paragraph_buffer()
            rebuilt.append(line)
            continue

        paragraph_buffer.append(line)

    flush_paragraph_buffer()
    updated = "\n".join(rebuilt).rstrip()
    if article_markdown.endswith("\n"):
        return f"{updated}\n"
    return updated


def run_soft_fixes(parsed: dict, focus_keyword: str) -> dict:
    """Apply non-blocking SEO/content fixes after hard validation passes."""
    fixed = dict(parsed)
    for key in REQUIRED_ARTICLE_KEYS:
        value = fixed.get(key, "")
        fixed[key] = str(value).strip() if value is not None else ""

    resolved_focus_keyword = str(focus_keyword or "").strip()
    fixed["focus_keyword"] = resolved_focus_keyword

    seo_title = fixed["seo_title"]
    if len(seo_title) > 60:
        seo_title = _truncate_at_word_boundary(seo_title, 60)
    if resolved_focus_keyword.casefold() not in seo_title.casefold():
        prefixed_title = f"{resolved_focus_keyword} - {seo_title}".strip(" -")
        seo_title = _truncate_at_word_boundary(prefixed_title, 60)
    fixed["seo_title"] = seo_title

    meta_description = fixed["meta_description"]
    if len(meta_description) < 120:
        while len(meta_description) < 120:
            meta_description = (
                f"{meta_description.rstrip()} Learn more about {resolved_focus_keyword} here."
            ).strip()
    if len(meta_description) > 155:
        meta_description = _truncate_with_ellipsis(meta_description, 155)
    if resolved_focus_keyword.casefold() not in meta_description.casefold():
        meta_description = (
            f"{meta_description.rstrip()} Discover more about {resolved_focus_keyword}."
        ).strip()
        if len(meta_description) > 155:
            meta_description = _truncate_with_ellipsis(meta_description, 155)
    fixed["meta_description"] = meta_description

    article_markdown = fixed["article_markdown"]
    article_markdown = _remove_duplicate_leading_h1(article_markdown, fixed["title"])
    article_markdown = _split_overlong_plain_paragraphs(article_markdown)
    fixed["article_markdown"] = article_markdown
    fixed["content_markdown"] = article_markdown
    return fixed


def validate_article_seo(payload: dict[str, str]) -> list[str]:
    focus_keyword = str(payload.get("focus_keyword", "")).strip()
    return run_hard_validations(parsed=payload, focus_keyword=focus_keyword)


def _collect_json_candidates(raw_content: str) -> list[str]:
    candidates: list[str] = []
    base = raw_content.strip()
    stripped = _strip_code_fences(base)
    extracted_base = _extract_first_json_object(base)
    extracted_stripped = _extract_first_json_object(stripped)

    candidates.append(base)
    candidates.append(stripped)
    if extracted_base:
        candidates.append(extracted_base)
    if extracted_stripped:
        candidates.append(extracted_stripped)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def parse_article_response(raw_content: str) -> dict[str, str]:
    """Parse and validate DeepSeek output into the expected article payload shape."""
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise GenerationError("DeepSeek returned empty content.")

    candidates = _collect_json_candidates(raw_content)
    parse_errors: list[str] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return _validate_article_payload(parsed)
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
        except GenerationError:
            raise

    error_hint = parse_errors[-1] if parse_errors else "no JSON object found"
    raise GenerationError(f"Could not parse DeepSeek JSON response: {error_hint}")


def parse_vibe_response(raw_content: str, max_count: int) -> list[str]:
    """Parse and validate a DeepSeek vibe-bank JSON payload."""
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise GenerationError("DeepSeek returned empty vibe content.")
    if max_count <= 0:
        raise GenerationError("max_count must be greater than zero.")

    candidates = _collect_json_candidates(raw_content)
    parse_errors: list[str] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            parse_errors.append(str(exc))
            continue

        if not isinstance(payload, dict):
            raise GenerationError("Vibe response must be a JSON object.")
        if VIBE_KEY not in payload:
            raise GenerationError("Vibe response JSON must include the 'vibes' key.")

        raw_vibes = payload.get(VIBE_KEY)
        if not isinstance(raw_vibes, list):
            raise GenerationError("'vibes' must be a JSON array.")

        cleaned: list[str] = []
        seen_norm: set[str] = set()
        for item in raw_vibes:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if len(value) < 3 or len(value) > 120:
                continue
            normalized = value.casefold()
            if normalized in seen_norm:
                continue
            seen_norm.add(normalized)
            cleaned.append(value)
            if len(cleaned) >= max_count:
                break

        if not cleaned:
            raise GenerationError("No valid vibe options found in DeepSeek response.")
        return cleaned

    error_hint = parse_errors[-1] if parse_errors else "no JSON object found"
    raise GenerationError(f"Could not parse DeepSeek vibe response: {error_hint}")


def _build_deepseek_client() -> tuple[Any, str]:
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not deepseek_api_key:
        raise GenerationError("Missing DEEPSEEK_API_KEY in environment.")

    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise GenerationError(
            "openai package is required for DeepSeek integration. Install dependencies."
        ) from exc

    return OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com"), deepseek_model


def _read_env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    return value


def generate_article(
    topic: str,
    vibe: str,
    blog_profile: str,
    focus_keyword: str | None = None,
) -> dict[str, str]:
    """Generate an SEO article payload with strict retries and soft post-processing fixes."""
    load_dotenv()

    if not topic or not topic.strip():
        raise GenerationError("Topic is required.")
    if not blog_profile or not blog_profile.strip():
        raise GenerationError("blog_profile is required.")

    explicit_focus_keyword = str(focus_keyword or "").strip()
    resolved_focus_keyword = explicit_focus_keyword or derive_focus_keyword(topic)

    system_prompt = (
        "You are an expert SEO blog writer. "
        "Return valid JSON only with no extra text or markdown fences."
    )
    base_user_prompt = (
        f"Topic: {topic.strip()}\n"
        f"Vibe/Style: {vibe.strip()}\n\n"
        f"Blog Domain Context: {blog_profile.strip()}\n\n"
        "You are an SEO content writer. Generate a blog article as a JSON object\n"
        "with these exact keys: title, article_markdown, hero_image_prompt,\n"
        "detail_image_prompt, seo_title, meta_description, focus_keyword.\n\n"
        "CONTENT RULES:\n"
        f"1. Write {SEO_TARGET_MIN_WORDS}–{SEO_TARGET_MAX_WORDS} words (excluding headings and markdown syntax).\n"
        f'2. Use the EXACT focus keyword "{resolved_focus_keyword}" between 5 and 9 times\n'
        "   in the body text. This count is non-negotiable — fewer or more will\n"
        "   be rejected.\n"
        "3. Start with a 2–4 sentence introductory paragraph. The focus keyword\n"
        "   MUST appear within the first two sentences.\n"
        "4. Use at least 3 H2 subheadings. At least one H2 MUST contain the\n"
        "   exact focus keyword.\n"
        "5. Every paragraph must be 2–4 sentences. No single-sentence paragraphs.\n"
        "   No paragraphs longer than 4 sentences.\n"
        "6. Do NOT begin the article with an H1 heading. The title is handled\n"
        "   separately by the system.\n"
        "7. Include exactly 1 internal markdown link: [anchor text]({{INTERNAL_URL}})\n"
        "   Use {{INTERNAL_URL}} as the literal placeholder — the system will\n"
        "   replace it.\n"
        "8. Include exactly 1 external markdown link to a relevant authority\n"
        "   source (e.g., official documentation, Wikipedia, .gov, .edu). Do\n"
        "   not add rel=\"nofollow\".\n"
        "9. End with a concrete, actionable conclusion under an H2 heading such\n"
        "   as \"## Final Thoughts\" or \"## Wrapping Up\".\n\n"
        "SEO META RULES:\n"
        "10. seo_title: Begin with or place the focus keyword near the start.\n"
        "    Include exactly one number. Maximum 55 characters total.\n"
        "11. meta_description: MUST contain the focus keyword. Must be 130–150\n"
        "    characters. Write it as a compelling call-to-action.\n"
        f'12. focus_keyword: Return the EXACT keyword provided: "{resolved_focus_keyword}"\n\n'
        "IMAGE PROMPTS:\n"
        "13. hero_image_prompt: A detailed prompt for generating a hero image\n"
        "    relevant to the article topic. No text in the image.\n"
        "14. detail_image_prompt: A detailed prompt for a secondary in-article\n"
        "    image. Include an alt-text suggestion that contains the focus keyword.\n\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY valid JSON. No markdown code fences. No commentary outside\n"
        "the JSON object. The response must start with {{ and end with }}."
    )

    def _request(client: Any, deepseek_model: str, messages: list[dict[str, str]], temperature: float) -> str:
        try:
            response = client.chat.completions.create(
                model=deepseek_model,
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            raise GenerationError(f"DeepSeek request failed: {exc}") from exc

        if not response.choices:
            raise GenerationError("DeepSeek returned no choices.")
        raw_content = response.choices[0].message.content
        if not isinstance(raw_content, str):
            raise GenerationError("DeepSeek returned non-text content.")
        return raw_content

    max_attempts = _read_env_positive_int(
        "DEEPSEEK_ARTICLE_ATTEMPTS",
        MAX_SEO_GENERATION_ATTEMPTS,
    )
    initial_temperature = _read_env_float(
        "DEEPSEEK_INITIAL_TEMPERATURE",
        DEFAULT_DEEPSEEK_INITIAL_TEMPERATURE,
    )
    retry_temperature = _read_env_float(
        "DEEPSEEK_RETRY_TEMPERATURE",
        DEFAULT_DEEPSEEK_RETRY_TEMPERATURE,
    )

    try:
        client, deepseek_model = _build_deepseek_client()
    except Exception as exc:
        raise GenerationError(
            f"article_request: failed to initialize DeepSeek client: {exc}"
        ) from exc

    last_stage = "request"
    last_errors: list[str] = []
    best_effort_payload: dict[str, str] | None = None
    for attempt in range(1, max_attempts + 1):
        feedback_block = ""
        if last_errors:
            feedback_block = (
                "\n\nYour previous attempt failed these validations. "
                "You MUST fix them:\n"
                + "\n".join(f"- {error}" for error in last_errors)
                + "\n\nDo not repeat these mistakes."
            )
        full_prompt = base_user_prompt + feedback_block

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ]
        temperature = initial_temperature if attempt == 1 else retry_temperature

        try:
            raw_content = _request(
                client=client,
                deepseek_model=deepseek_model,
                messages=messages,
                temperature=temperature,
            )
        except GenerationError as exc:
            last_stage = "request"
            last_errors = [str(exc)]
            continue

        try:
            parsed = parse_article_response(raw_content)
        except GenerationError as exc:
            last_stage = "parse"
            last_errors = [str(exc)]
            continue

        best_effort_payload = dict(parsed)

        validation_errors = run_hard_validations(parsed=parsed, focus_keyword=resolved_focus_keyword)
        if validation_errors:
            last_stage = "validation"
            last_errors = validation_errors
            continue

        fixed = run_soft_fixes(parsed=parsed, focus_keyword=resolved_focus_keyword)
        return fixed

    error_summary = "; ".join(last_errors) if last_errors else "Unknown failure."
    raise ArticleValidationError(
        (
            f"article_{last_stage}: generation failed after {max_attempts} attempts. "
            f"Last errors: {error_summary}"
        ),
        errors=last_errors,
        payload=best_effort_payload,
    )


def generate_vibe_bank(blog_profile: str, count: int = 12) -> list[str]:
    """Generate a niche-matched list of vibe/topic ideas for a blog profile."""
    load_dotenv()

    if not blog_profile or not blog_profile.strip():
        raise GenerationError("blog_profile is required for vibe generation.")
    if count <= 0:
        raise GenerationError("count must be greater than zero.")

    system_prompt = (
        "You generate concise, niche-matched blog topic vibes. "
        "Return valid JSON only and no markdown fences."
    )
    user_prompt = (
        f"Blog Domain Context: {blog_profile.strip()}\n\n"
        f"Generate {count} distinct vibe/topic suggestions for this blog domain.\n"
        "Return exactly one JSON object in this format:\n"
        '{"vibes": ["...", "..."]}\n\n'
        "Rules:\n"
        "- Each vibe should be specific and publishable as a blog topic.\n"
        "- Keep each vibe between 3 and 120 characters.\n"
        "- Avoid duplicates.\n"
        "- Output JSON only."
    )

    try:
        client, deepseek_model = _build_deepseek_client()
        response = client.chat.completions.create(
            model=deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,
        )
    except Exception as exc:
        raise GenerationError(f"DeepSeek vibe generation failed: {exc}") from exc

    if not response.choices:
        raise GenerationError("DeepSeek returned no vibe choices.")

    raw_content = response.choices[0].message.content
    if not isinstance(raw_content, str):
        raise GenerationError("DeepSeek returned non-text vibe content.")
    return parse_vibe_response(raw_content, max_count=count)


def _safe_kind_name(image_kind: str) -> str:
    sanitized = "".join(
        char if char.isalnum() else "_" for char in image_kind.lower().strip()
    )
    sanitized = sanitized.strip("_")
    return sanitized or "image"


def _extract_image_url(result_payload: Any) -> str:
    if isinstance(result_payload, dict):
        images = result_payload.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                url = first.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()

        image = result_payload.get("image")
        if isinstance(image, dict):
            url = image.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()

        url = result_payload.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()

    raise GenerationError("Fal.ai response did not include an image URL.")


def _guess_extension_from_url(url: str) -> str:
    extension = Path(urlparse(url).path).suffix.lower()
    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        return extension
    return ".jpg"


def generate_image(prompt: str, image_kind: str, out_dir: Path) -> Path:
    """Generate and download an image via Fal.ai."""
    load_dotenv()

    if not prompt or not prompt.strip():
        raise GenerationError("Image prompt is required.")

    fal_key = os.getenv("FAL_KEY", "").strip()
    if not fal_key:
        raise GenerationError("Missing FAL_KEY in environment.")
    os.environ["FAL_KEY"] = fal_key

    fal_model = os.getenv("FAL_MODEL", "fal-ai/flux/dev").strip()

    try:
        import fal_client
    except ImportError as exc:
        raise GenerationError(
            "fal-client package is required for image generation. Install dependencies."
        ) from exc

    try:
        result = fal_client.subscribe(fal_model, arguments={"prompt": prompt.strip()})
    except Exception as exc:
        raise GenerationError(f"Fal.ai generation failed: {exc}") from exc

    payload = result.get("data") if isinstance(result, dict) and "data" in result else result
    image_url = _extract_image_url(payload)

    out_dir.mkdir(parents=True, exist_ok=True)
    extension = _guess_extension_from_url(image_url)
    filename = f"{_safe_kind_name(image_kind)}_{uuid.uuid4().hex[:10]}{extension}"
    output_path = out_dir / filename

    try:
        response = requests.get(image_url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GenerationError(f"Failed to download generated image: {exc}") from exc

    output_path.write_bytes(response.content)
    return output_path
