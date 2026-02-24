from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from automating_wf.models.pinterest import BrainOutput, KeywordCandidate, PinRecord, SeedScrapeResult


WEIGHT_TITLE = 3.0
WEIGHT_DESCRIPTION = 2.0
WEIGHT_TAG = 1.0
MIN_FREQUENCY = 3
MAX_SUPPORTING_TERMS = 5
MAX_ANALYSIS_ATTEMPTS = 3
PIN_TEXT_OVERLAY_MIN_WORDS = 2
PIN_TEXT_OVERLAY_MAX_WORDS = 6
PIN_TEXT_OVERLAY_MAX_CHARS = 32

REQUIRED_OUTPUT_KEYS = (
    "primary_keyword",
    "image_generation_prompt",
    "pin_text_overlay",
    "pin_title",
    "pin_description",
)

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "this",
    "that",
    "it",
    "as",
    "from",
    "your",
    "you",
    "our",
    "their",
    "how",
    "why",
    "what",
    "when",
}

SEASONAL_TERMS = {
    "spring",
    "summer",
    "autumn",
    "fall",
    "winter",
    "holiday",
    "christmas",
    "new year",
    "back to school",
}


class AnalysisError(RuntimeError):
    """Raised when keyword analysis or LLM generation fails."""


class InsufficientSignalError(AnalysisError):
    """Raised when no candidate satisfies the minimum frequency threshold."""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _tokenize_english(text: str) -> list[str]:
    lowered = text.casefold()
    tokens = re.findall(r"[a-z][a-z0-9']*", lowered)
    return [token for token in tokens if len(token) > 1]


def _term_is_valid(term: str) -> bool:
    tokens = term.split()
    if not tokens:
        return False
    if all(token in STOPWORDS for token in tokens):
        return False
    if len(term) < 3:
        return False
    if len(tokens) == 1 and tokens[0] in STOPWORDS:
        return False
    return True


def _collect_terms(tokens: list[str]) -> list[str]:
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


def _record_engagement_score(record: PinRecord) -> float:
    engagement = record.engagement or {}
    score_total = engagement.get("score_total")
    if isinstance(score_total, (int, float)):
        return float(score_total)
    numeric_values = [
        float(value)
        for value in engagement.values()
        if isinstance(value, (int, float))
    ]
    return sum(numeric_values)


def score_keyword_candidates(
    records: list[PinRecord],
    *,
    min_frequency: int = MIN_FREQUENCY,
) -> list[KeywordCandidate]:
    candidate_freq: dict[str, int] = defaultdict(int)
    candidate_weighted: dict[str, float] = defaultdict(float)
    candidate_engagement: dict[str, float] = defaultdict(float)
    title_hits: dict[str, int] = defaultdict(int)
    description_hits: dict[str, int] = defaultdict(int)
    tag_hits: dict[str, int] = defaultdict(int)

    for record in records:
        engagement_score = _record_engagement_score(record)
        field_terms = (
            (_collect_terms(_tokenize_english(record.title or "")), WEIGHT_TITLE, title_hits),
            (
                _collect_terms(_tokenize_english(record.description or "")),
                WEIGHT_DESCRIPTION,
                description_hits,
            ),
            (
                _collect_terms(_tokenize_english(" ".join(record.tags or []))),
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


def _load_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "pinterest_analysis.md"
    if not prompt_path.exists():
        raise AnalysisError(f"Missing prompt file: {prompt_path}")
    content = prompt_path.read_text(encoding="utf-8").strip()
    if not content:
        raise AnalysisError(f"Prompt file is empty: {prompt_path}")
    return content


def _build_openai_client() -> tuple[Any, str]:
    load_dotenv()
    provider = os.getenv("PINTEREST_ANALYSIS_PROVIDER", "deepseek").strip().casefold()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AnalysisError("openai package is required for LLM analysis.") from exc

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("PINTEREST_ANALYSIS_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        if not api_key:
            raise AnalysisError("Missing OPENAI_API_KEY for openai analysis provider.")
        return OpenAI(api_key=api_key), model

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("PINTEREST_ANALYSIS_MODEL", "").strip() or os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
    if not api_key:
        raise AnalysisError("Missing DEEPSEEK_API_KEY for deepseek analysis provider.")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com"), model


def _parse_llm_json(raw_content: str) -> dict[str, Any]:
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise AnalysisError("LLM returned empty analysis content.")

    stripped = raw_content.strip()
    candidates = [stripped]
    extracted = _extract_first_json_object(stripped)
    if extracted:
        candidates.append(extracted)

    last_error = "no JSON object found"
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            continue
        if not isinstance(payload, dict):
            last_error = "payload is not an object"
            continue
        return payload
    raise AnalysisError(f"Could not parse analysis JSON: {last_error}")


def _validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_OUTPUT_KEYS:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty key: {key}")
    pin_title = payload.get("pin_title", "")
    if isinstance(pin_title, str) and len(pin_title) > 100:
        errors.append("pin_title exceeds 100 characters")
    pin_description = payload.get("pin_description", "")
    if isinstance(pin_description, str) and len(pin_description) > 500:
        errors.append("pin_description exceeds 500 characters")
    pin_text_overlay = payload.get("pin_text_overlay", "")
    if isinstance(pin_text_overlay, str):
        errors.extend(_validate_pin_text_overlay(pin_text_overlay))
    return errors


def _truncate_with_ellipsis(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    truncated = value[: limit - 3].rstrip()
    return f"{truncated}..."


def _tokenize_overlay(value: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z0-9&']+", value) if token]


def _validate_pin_text_overlay(value: str) -> list[str]:
    errors: list[str] = []
    normalized = " ".join(str(value).split())
    words = normalized.split()
    if len(words) < PIN_TEXT_OVERLAY_MIN_WORDS:
        errors.append(
            f"pin_text_overlay must have at least {PIN_TEXT_OVERLAY_MIN_WORDS} words"
        )
    if len(words) > PIN_TEXT_OVERLAY_MAX_WORDS:
        errors.append(
            f"pin_text_overlay exceeds {PIN_TEXT_OVERLAY_MAX_WORDS} words"
        )
    if len(normalized) > PIN_TEXT_OVERLAY_MAX_CHARS:
        errors.append(
            f"pin_text_overlay exceeds {PIN_TEXT_OVERLAY_MAX_CHARS} characters"
        )
    return errors


def _coerce_pin_text_overlay(value: str, primary_keyword: str) -> str:
    tokens = _tokenize_overlay(value)
    fallback_tokens = _tokenize_overlay(primary_keyword)
    if not fallback_tokens:
        fallback_tokens = ["Easy", "Ideas"]
    if not tokens:
        tokens = fallback_tokens.copy()

    tokens = tokens[:PIN_TEXT_OVERLAY_MAX_WORDS]
    fallback_index = 0
    while len(tokens) < PIN_TEXT_OVERLAY_MIN_WORDS:
        if fallback_index < len(fallback_tokens):
            tokens.append(fallback_tokens[fallback_index])
            fallback_index += 1
            continue
        tokens.append("Ideas")

    max_count = min(PIN_TEXT_OVERLAY_MAX_WORDS, len(tokens))
    for count in range(max_count, PIN_TEXT_OVERLAY_MIN_WORDS - 1, -1):
        candidate = " ".join(tokens[:count]).strip()
        if len(candidate) <= PIN_TEXT_OVERLAY_MAX_CHARS:
            return candidate

    first = tokens[0][: max(1, PIN_TEXT_OVERLAY_MAX_CHARS - 2)]
    second_budget = max(1, PIN_TEXT_OVERLAY_MAX_CHARS - len(first) - 1)
    second = tokens[1][:second_budget]
    candidate = f"{first} {second}".strip()
    if len(candidate) > PIN_TEXT_OVERLAY_MAX_CHARS:
        candidate = candidate[:PIN_TEXT_OVERLAY_MAX_CHARS].rstrip()
    if " " not in candidate:
        split_at = max(1, min(len(candidate) - 1, len(candidate) // 2))
        candidate = f"{candidate[:split_at]} {candidate[split_at:]}".strip()
    return candidate


def _coerce_length_limits(payload: dict[str, Any]) -> dict[str, Any]:
    fixed = dict(payload)
    pin_title = str(fixed.get("pin_title", "")).strip()
    pin_description = str(fixed.get("pin_description", "")).strip()
    primary_keyword = str(fixed.get("primary_keyword", "")).strip()
    pin_text_overlay = str(fixed.get("pin_text_overlay", "")).strip()
    fixed["pin_title"] = _truncate_with_ellipsis(pin_title, 100)
    fixed["pin_description"] = _truncate_with_ellipsis(pin_description, 500)
    fixed["pin_text_overlay"] = _coerce_pin_text_overlay(
        pin_text_overlay,
        primary_keyword,
    )
    return fixed


def _infer_seasonal_angle(primary_keyword: str, supporting_terms: list[str]) -> str:
    haystack = " ".join([primary_keyword, *supporting_terms]).casefold()
    for seasonal_term in sorted(SEASONAL_TERMS):
        if seasonal_term in haystack:
            return seasonal_term
    return ""


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def analyze_seed(
    *,
    scrape_result: SeedScrapeResult,
    blog_suffix: str,
    run_dir: Path,
    min_frequency: int = MIN_FREQUENCY,
    supporting_terms_count: int = MAX_SUPPORTING_TERMS,
) -> BrainOutput:
    if not scrape_result.records:
        raise AnalysisError("Cannot analyze an empty scrape result.")
    _ensure_dir(run_dir)

    candidates = score_keyword_candidates(
        scrape_result.records,
        min_frequency=min_frequency,
    )
    _write_json(run_dir / "candidate_scores.json", [item.to_dict() for item in candidates])
    _write_json(run_dir / "analysis_input.json", scrape_result.to_dict())

    if not candidates:
        raise InsufficientSignalError(
            f"No term reached frequency>={min_frequency} for seed '{scrape_result.seed_keyword}'."
        )

    primary_candidate = candidates[0]
    supporting_terms = [
        item.term for item in candidates[1 : 1 + max(1, supporting_terms_count)]
    ]
    cluster_label = primary_candidate.term
    seasonal_angle = _infer_seasonal_angle(primary_candidate.term, supporting_terms)

    prompt = _load_prompt()
    llm_input_payload = {
        "blog_suffix": blog_suffix,
        "seed_keyword": scrape_result.seed_keyword,
        "primary_candidate": primary_candidate.to_dict(),
        "supporting_terms": supporting_terms,
        "seasonal_angle": seasonal_angle,
        "records": [record.to_dict() for record in scrape_result.records],
    }

    client, model = _build_openai_client()
    max_attempts = _read_positive_int_env(
        "PINTEREST_ANALYSIS_ATTEMPTS",
        MAX_ANALYSIS_ATTEMPTS,
    )
    last_errors: list[str] = []
    last_payload: dict[str, Any] | None = None

    for attempt in range(1, max_attempts + 1):
        correction = ""
        if attempt > 1 and last_errors:
            correction = (
                "\n\nCorrection requirements:\n"
                + "\n".join(f"- {item}" for item in last_errors)
                + "\nReturn JSON only."
            )

        user_content = (
            "Analyze this deterministic keyword evidence and produce exactly one JSON object.\n\n"
            + json.dumps(llm_input_payload, ensure_ascii=False)
            + correction
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            last_errors = [f"LLM request failed: {exc}"]
            continue

        if not getattr(response, "choices", None):
            last_errors = ["LLM returned no choices."]
            continue

        raw_content = response.choices[0].message.content
        run_dir.joinpath(f"llm_attempt_{attempt}.txt").write_text(
            str(raw_content), encoding="utf-8"
        )

        try:
            payload = _parse_llm_json(str(raw_content))
        except AnalysisError as exc:
            last_errors = [str(exc)]
            continue

        validation_errors = _validate_payload(payload)
        if not validation_errors:
            last_payload = payload
            break
        last_errors = validation_errors
        last_payload = payload

    if last_payload is None:
        raise AnalysisError(
            "Analysis failed after retries: "
            + ("; ".join(last_errors) if last_errors else "unknown error")
        )

    payload = _coerce_length_limits(last_payload)
    strict_errors = _validate_payload(payload)
    if strict_errors:
        raise AnalysisError(
            "Analysis output is invalid after truncation fallback: "
            + "; ".join(strict_errors)
        )

    primary_keyword = str(payload["primary_keyword"]).strip() or primary_candidate.term
    output = BrainOutput(
        primary_keyword=primary_keyword,
        image_generation_prompt=str(payload["image_generation_prompt"]).strip(),
        pin_text_overlay=str(payload["pin_text_overlay"]).strip(),
        pin_title=str(payload["pin_title"]).strip(),
        pin_description=str(payload["pin_description"]).strip(),
        cluster_label=str(payload.get("cluster_label", "")).strip() or cluster_label,
        supporting_terms=supporting_terms,
        seasonal_angle=seasonal_angle,
    )
    _write_json(run_dir / "brain_output.json", output.to_dict())
    return output
