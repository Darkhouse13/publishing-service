from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from automating_wf.content.generators import KEYWORD_COUNT_MAX, KEYWORD_COUNT_MIN


MAX_REPAIR_ATTEMPTS = 2
MAX_CONTEXT_PARAGRAPHS = 16
MAX_CONTEXT_CHARS = 420
ALLOWED_PATCH_OPS = {"replace_h2", "replace_paragraph"}
H2_PATTERN = re.compile(r"^\s{0,3}##(?!#)\s*(.*?)\s*#*\s*$")
REPAIR_PROMPT_ENV_KEY = "ARTICLE_VALIDATOR_REPAIR_PROMPT"
REPAIR_PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "article_validator_repair.md"


class ArticleValidatorError(RuntimeError):
    """Raised when validator setup, parsing, or patch application fails."""


class ArticleValidationFinalError(ArticleValidatorError):
    """Raised when article repair fails after exhausting allowed attempts."""

    def __init__(
        self,
        message: str,
        *,
        errors: list[str] | None = None,
        attempts_used: int = 0,
        attempts: list[dict[str, Any]] | None = None,
        last_payload: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = list(errors or [])
        self.attempts_used = int(attempts_used)
        self.attempts = list(attempts or [])
        self.last_payload = dict(last_payload or {})


@dataclass(slots=True)
class ValidatorRuleReport:
    focus_keyword: str
    keyword_count: int
    keyword_count_min: int
    keyword_count_max: int
    h2_total_count: int
    h2_keyword_match_count: int
    errors: list[str]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidatorAttemptReport:
    attempt: int
    trigger_errors: list[str]
    request_instructions: list[str]
    raw_response: str = ""
    parsed_patches: list[dict[str, Any]] = field(default_factory=list)
    apply_error: str = ""
    post_rule_report: ValidatorRuleReport | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.post_rule_report is not None:
            payload["post_rule_report"] = self.post_rule_report.to_dict()
        return payload


@dataclass(slots=True)
class ValidatorResult:
    passed: bool
    repaired: bool
    attempts_used: int
    article_payload: dict[str, str]
    rule_report: ValidatorRuleReport
    attempts: list[ValidatorAttemptReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "repaired": bool(self.repaired),
            "attempts_used": int(self.attempts_used),
            "article_payload": dict(self.article_payload),
            "rule_report": self.rule_report.to_dict(),
            "attempts": [item.to_dict() for item in self.attempts],
        }


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


def load_repair_system_prompt() -> str:
    """Load validator repair system prompt from env override or bundled prompt file."""
    load_dotenv()
    env_prompt = str(os.getenv(REPAIR_PROMPT_ENV_KEY, "")).strip()
    if env_prompt:
        return env_prompt

    prompt_file = REPAIR_PROMPT_FILE
    try:
        file_prompt = prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        file_prompt = ""
    except Exception as exc:
        raise ArticleValidatorError(
            f"Failed to read validator repair prompt file '{prompt_file}': {exc}"
        ) from exc

    if file_prompt:
        return file_prompt

    raise ArticleValidatorError(
        "Validator repair prompt is missing. Set ARTICLE_VALIDATOR_REPAIR_PROMPT or "
        "populate src/automating_wf/prompts/article_validator_repair.md."
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _maybe_write_debug(artifact_dir: Path | None, filename: str, payload: Any) -> None:
    if artifact_dir is None:
        return
    try:
        _write_json(artifact_dir / filename, payload)
    except Exception:
        return


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


def _build_openai_client() -> tuple[Any, str]:
    load_dotenv()
    provider = os.getenv("PINTEREST_ANALYSIS_PROVIDER", "deepseek").strip().casefold()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ArticleValidatorError("openai package is required for validator repair calls.") from exc

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("PINTEREST_ANALYSIS_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        if not api_key:
            raise ArticleValidatorError("Missing OPENAI_API_KEY for validator provider=openai.")
        return OpenAI(api_key=api_key), model

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("PINTEREST_ANALYSIS_MODEL", "").strip() or os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
    if not api_key:
        raise ArticleValidatorError("Missing DEEPSEEK_API_KEY for validator provider=deepseek.")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com"), model


def _keyword_pattern(focus_keyword: str) -> re.Pattern[str]:
    escaped = re.escape(focus_keyword.strip())
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


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


def _extract_h2_segments(article_markdown: str) -> list[_H2Segment]:
    segments: list[_H2Segment] = []
    for line_index, line in enumerate(article_markdown.splitlines()):
        match = H2_PATTERN.match(line)
        if not match:
            continue
        heading = match.group(1).strip()
        segments.append(_H2Segment(index=len(segments), line_index=line_index, text=heading))
    return segments


def _extract_paragraph_segments(article_markdown: str) -> list[_ParagraphSegment]:
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


def _build_rule_report(article_markdown: str, focus_keyword: str) -> ValidatorRuleReport:
    keyword = str(focus_keyword or "").strip()
    errors: list[str] = []
    if not keyword:
        errors.append("focus_keyword is required.")
        return ValidatorRuleReport(
            focus_keyword="",
            keyword_count=0,
            keyword_count_min=KEYWORD_COUNT_MIN,
            keyword_count_max=KEYWORD_COUNT_MAX,
            h2_total_count=0,
            h2_keyword_match_count=0,
            errors=errors,
            passed=False,
        )

    keyword_re = _keyword_pattern(keyword)
    keyword_count = len(keyword_re.findall(str(article_markdown or "")))
    h2_segments = _extract_h2_segments(article_markdown)
    h2_keyword_match_count = sum(1 for segment in h2_segments if keyword_re.search(segment.text))

    if keyword_count < KEYWORD_COUNT_MIN:
        errors.append(
            f"Keyword count {keyword_count} is below minimum {KEYWORD_COUNT_MIN}."
        )
    if keyword_count > KEYWORD_COUNT_MAX:
        errors.append(
            f"Keyword count {keyword_count} exceeds maximum {KEYWORD_COUNT_MAX}."
        )
    if h2_keyword_match_count <= 0:
        errors.append("At least one H2 heading must contain the exact focus keyword.")

    return ValidatorRuleReport(
        focus_keyword=keyword,
        keyword_count=keyword_count,
        keyword_count_min=KEYWORD_COUNT_MIN,
        keyword_count_max=KEYWORD_COUNT_MAX,
        h2_total_count=len(h2_segments),
        h2_keyword_match_count=h2_keyword_match_count,
        errors=errors,
        passed=len(errors) == 0,
    )


def _truncate(value: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _targeted_instructions(rule_report: ValidatorRuleReport) -> list[str]:
    instructions: list[str] = []
    if rule_report.h2_keyword_match_count <= 0:
        instructions.append(
            f"Rewrite one existing H2 heading so it includes the exact phrase '{rule_report.focus_keyword}'."
        )
    if rule_report.keyword_count < rule_report.keyword_count_min:
        instructions.append(
            "Increase exact keyword occurrences by editing existing paragraphs only."
        )
    if rule_report.keyword_count > rule_report.keyword_count_max:
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
    rule_report: ValidatorRuleReport,
    blog_profile: str,
) -> str:
    h2_segments = _extract_h2_segments(article_markdown)
    paragraph_segments = _extract_paragraph_segments(article_markdown)
    keyword_re = _keyword_pattern(focus_keyword)

    h2_lines = [
        f"- index={segment.index} text={_truncate(segment.text)}"
        for segment in h2_segments
    ]
    paragraph_lines = [
        (
            f"- index={segment.index} keyword_hits={len(keyword_re.findall(segment.text))} "
            f"text={_truncate(segment.text)}"
        )
        for segment in paragraph_segments[:MAX_CONTEXT_PARAGRAPHS]
    ]

    instructions = _targeted_instructions(rule_report)
    return (
        "You must patch an existing markdown article with minimal section edits.\n\n"
        f"Blog profile: {blog_profile.strip()}\n"
        f"Focus keyword (exact phrase): {focus_keyword}\n\n"
        "Failed validation rules:\n"
        + "\n".join(f"- {item}" for item in rule_report.errors)
        + "\n\nTargeted fixes required:\n"
        + "\n".join(f"- {item}" for item in instructions)
        + "\n\nCurrent counts:\n"
        f"- keyword_count={rule_report.keyword_count}\n"
        f"- allowed_range={rule_report.keyword_count_min}-{rule_report.keyword_count_max}\n"
        f"- h2_keyword_matches={rule_report.h2_keyword_match_count}\n\n"
        "Existing H2 headings (ATX only):\n"
        + ("\n".join(h2_lines) if h2_lines else "- none")
        + "\n\nPlain-text paragraph candidates:\n"
        + ("\n".join(paragraph_lines) if paragraph_lines else "- none")
        + "\n\n"
        "Return JSON only with this schema:\n"
        '{"patches":[{"op":"replace_h2","target_index":0,"text":"## ..."},{"op":"replace_paragraph","target_index":1,"text":"..."}]}\n'
        "Allowed ops: replace_h2, replace_paragraph.\n"
        "Do not regenerate the whole article. Do not add new sections. Only patch by index.\n\n"
        "Current article markdown:\n"
        f"{article_markdown}"
    )


def _parse_patch_response(raw_response: str) -> list[dict[str, Any]]:
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
        raise ArticleValidatorError(f"Could not parse repair JSON: {last_error}")

    patches = payload.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ArticleValidatorError("Repair JSON must include a non-empty 'patches' array.")

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
        except Exception as exc:
            raise ArticleValidatorError("Patch target_index must be an integer.") from exc
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


def _rejoin_lines(lines: list[str], had_trailing_newline: bool) -> str:
    text = "\n".join(lines)
    if had_trailing_newline:
        return text + "\n"
    return text


def _normalize_h2_text(value: str) -> str:
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
    collapsed = " ".join(str(value or "").split()).strip()
    if not collapsed:
        raise ArticleValidatorError("replace_paragraph patch text cannot be empty.")
    return collapsed


def _apply_patch(article_markdown: str, patch: dict[str, Any]) -> str:
    op = str(patch.get("op", "")).strip()
    target_index = int(patch.get("target_index", -1))
    raw_text = str(patch.get("text", "")).strip()
    lines = article_markdown.splitlines()
    had_trailing_newline = article_markdown.endswith("\n")

    if op == "replace_h2":
        segments = _extract_h2_segments(article_markdown)
        if target_index >= len(segments):
            raise ArticleValidatorError(
                f"replace_h2 target_index={target_index} is out of range (total={len(segments)})."
            )
        segment = segments[target_index]
        lines[segment.line_index] = _normalize_h2_text(raw_text)
        return _rejoin_lines(lines, had_trailing_newline)

    if op == "replace_paragraph":
        segments = _extract_paragraph_segments(article_markdown)
        if target_index >= len(segments):
            raise ArticleValidatorError(
                "replace_paragraph target_index="
                f"{target_index} is out of range (total={len(segments)})."
            )
        segment = segments[target_index]
        replacement = _normalize_paragraph_text(raw_text)
        updated_lines = lines[: segment.start_line] + [replacement] + lines[segment.end_line :]
        return _rejoin_lines(updated_lines, had_trailing_newline)

    raise ArticleValidatorError(f"Unsupported patch op '{op}'.")


def _apply_patches(article_markdown: str, patches: list[dict[str, Any]]) -> str:
    updated = article_markdown
    for patch in patches:
        updated = _apply_patch(updated, patch)
    return updated


def _normalize_payload(article_payload: dict[str, str], focus_keyword: str) -> dict[str, str]:
    if not isinstance(article_payload, dict):
        raise ArticleValidatorError("article_payload must be a dict.")

    normalized = {str(key): str(value) for key, value in article_payload.items()}
    article_markdown = str(
        normalized.get("article_markdown", normalized.get("content_markdown", ""))
    ).strip()
    if not article_markdown:
        raise ArticleValidatorError("article_payload must include non-empty article_markdown/content_markdown.")
    normalized["article_markdown"] = article_markdown
    normalized["content_markdown"] = article_markdown

    keyword = str(focus_keyword or normalized.get("focus_keyword", "")).strip()
    if not keyword:
        raise ArticleValidatorError("focus_keyword is required for validator.")
    normalized["focus_keyword"] = keyword
    return normalized


def validate_article_with_repair(
    *,
    article_payload: dict[str, str],
    focus_keyword: str,
    blog_profile: str,
    repair_system_prompt: str,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    artifact_dir: Path | None = None,
) -> ValidatorResult:
    """Validate and minimally repair an article payload using a short LLM patch loop."""
    prompt = str(repair_system_prompt or "").strip()
    if not prompt:
        raise ArticleValidatorError("repair_system_prompt is required.")
    if max_repair_attempts <= 0:
        raise ArticleValidatorError("max_repair_attempts must be >= 1.")

    artifacts = Path(artifact_dir) if artifact_dir is not None else None
    payload = _normalize_payload(article_payload, focus_keyword)
    markdown = payload["article_markdown"]
    rule_report = _build_rule_report(markdown, payload["focus_keyword"])
    _maybe_write_debug(artifacts, "validator_rule_report.json", rule_report.to_dict())

    if rule_report.passed:
        result = ValidatorResult(
            passed=True,
            repaired=False,
            attempts_used=0,
            article_payload=payload,
            rule_report=rule_report,
            attempts=[],
        )
        _maybe_write_debug(artifacts, "validator_final.json", result.to_dict())
        return result

    client, model = _build_openai_client()
    attempts: list[ValidatorAttemptReport] = []
    current_markdown = markdown
    current_report = rule_report

    for attempt in range(1, max_repair_attempts + 1):
        instructions = _targeted_instructions(current_report)
        user_prompt = _build_user_prompt(
            article_markdown=current_markdown,
            focus_keyword=payload["focus_keyword"],
            rule_report=current_report,
            blog_profile=blog_profile,
        )
        attempt_report = ValidatorAttemptReport(
            attempt=attempt,
            trigger_errors=list(current_report.errors),
            request_instructions=instructions,
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            prompt
                            + "\n\nYou fix only specified sections. Return JSON only."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            if not getattr(response, "choices", None):
                raise ArticleValidatorError("Repair model returned no choices.")
            raw_response = str(response.choices[0].message.content or "").strip()
            attempt_report.raw_response = raw_response
            patches = _parse_patch_response(raw_response)
            attempt_report.parsed_patches = patches
            current_markdown = _apply_patches(current_markdown, patches)
            payload["article_markdown"] = current_markdown
            payload["content_markdown"] = current_markdown
            current_report = _build_rule_report(current_markdown, payload["focus_keyword"])
            attempt_report.post_rule_report = current_report
        except Exception as exc:
            attempt_report.apply_error = str(exc)

        attempts.append(attempt_report)
        _maybe_write_debug(
            artifacts,
            f"validator_attempt_{attempt}.json",
            attempt_report.to_dict(),
        )

        if current_report.passed:
            result = ValidatorResult(
                passed=True,
                repaired=True,
                attempts_used=attempt,
                article_payload=payload,
                rule_report=current_report,
                attempts=attempts,
            )
            _maybe_write_debug(artifacts, "validator_final.json", result.to_dict())
            return result

    final_result = ValidatorResult(
        passed=False,
        repaired=True,
        attempts_used=max_repair_attempts,
        article_payload=payload,
        rule_report=current_report,
        attempts=attempts,
    )
    _maybe_write_debug(artifacts, "validator_final.json", final_result.to_dict())
    raise ArticleValidationFinalError(
        (
            "article_validator: repair failed after "
            f"{max_repair_attempts} attempts. Last errors: "
            + "; ".join(current_report.errors)
        ),
        errors=current_report.errors,
        attempts_used=max_repair_attempts,
        attempts=[item.to_dict() for item in attempts],
        last_payload=payload,
    )
