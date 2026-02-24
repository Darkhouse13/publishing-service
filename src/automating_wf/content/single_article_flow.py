from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automating_wf.content.generators import (
    ArticleValidationError,
    GenerationError,
    generate_article,
    generate_image,
)
from automating_wf.content.validator import (
    ArticleValidationFinalError,
    ArticleValidatorError,
    load_repair_system_prompt,
    validate_article_with_repair,
)


DEFAULT_VALIDATOR_ARTIFACT_ROOT = Path("tmp") / "single_article_validator"


@dataclass(slots=True)
class SingleArticleDraftResult:
    article_payload: dict[str, str]
    hero_image_path: Path
    detail_image_path: Path
    validator_repaired: bool
    validator_attempts_used: int
    validator_artifact_dir: Path


class SingleArticleDraftError(GenerationError):
    """Raised when the single-article draft flow fails before image generation."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: str,
        generation_errors: list[str] | None = None,
        validator_errors: list[str] | None = None,
        validator_attempts: list[dict[str, Any]] | None = None,
        payload: dict[str, str] | None = None,
        validator_artifact_dir: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_stage = str(failure_stage or "").strip() or "article_failed"
        self.generation_errors = list(generation_errors or [])
        self.validator_errors = list(validator_errors or [])
        self.validator_attempts = list(validator_attempts or [])
        self.payload = dict(payload) if isinstance(payload, dict) else None
        self.validator_artifact_dir = Path(validator_artifact_dir) if validator_artifact_dir is not None else None


def _topic_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return normalized or "topic"


def _validator_artifact_dir(topic: str, root: Path | None) -> Path:
    base_dir = Path(root) if root is not None else DEFAULT_VALIDATOR_ARTIFACT_ROOT
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_dir = base_dir / run_stamp / _topic_slug(topic)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _build_article_failed_error(
    message: str,
    *,
    generation_errors: list[str] | None = None,
    validator_errors: list[str] | None = None,
    validator_attempts: list[dict[str, Any]] | None = None,
    payload: dict[str, str] | None = None,
    validator_artifact_dir: Path | None = None,
) -> SingleArticleDraftError:
    return SingleArticleDraftError(
        str(message),
        failure_stage="article_failed",
        generation_errors=generation_errors,
        validator_errors=validator_errors,
        validator_attempts=validator_attempts,
        payload=payload,
        validator_artifact_dir=validator_artifact_dir,
    )


def generate_single_article_draft(
    *,
    topic: str,
    vibe: str,
    blog_profile: str,
    out_dir: Path,
    focus_keyword: str | None = None,
    repair_system_prompt: str | None = None,
    validator_artifact_root: Path | None = None,
) -> SingleArticleDraftResult:
    """Generate a single draft with validator repair before any image generation."""
    topic_text = str(topic or "").strip()
    if not topic_text:
        raise GenerationError("Topic is required.")
    profile_text = str(blog_profile or "").strip()
    if not profile_text:
        raise GenerationError("blog_profile is required.")

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = _validator_artifact_dir(topic_text, validator_artifact_root)

    prompt = str(repair_system_prompt or "").strip()
    if not prompt:
        prompt = load_repair_system_prompt()

    generation_errors: list[str] = []
    article_payload: dict[str, str] | None = None
    try:
        article_payload = generate_article(
            topic=topic_text,
            vibe=vibe,
            blog_profile=profile_text,
            focus_keyword=focus_keyword,
        )
    except ArticleValidationError as exc:
        generation_errors = list(exc.errors or [])
        if not isinstance(exc.payload, dict):
            raise _build_article_failed_error(
                str(exc),
                generation_errors=generation_errors,
                validator_artifact_dir=artifact_dir,
            ) from exc
        article_payload = dict(exc.payload)
    except GenerationError as exc:
        raise _build_article_failed_error(
            str(exc),
            validator_artifact_dir=artifact_dir,
        ) from exc

    resolved_focus_keyword = str(
        focus_keyword or (article_payload or {}).get("focus_keyword", "")
    ).strip()
    try:
        validator_result = validate_article_with_repair(
            article_payload=dict(article_payload or {}),
            focus_keyword=resolved_focus_keyword,
            blog_profile=profile_text,
            repair_system_prompt=prompt,
            artifact_dir=artifact_dir,
        )
    except ArticleValidationFinalError as exc:
        validator_errors = list(exc.errors or [])
        if not validator_errors:
            validator_errors = [str(exc)]
        raise _build_article_failed_error(
            str(exc),
            generation_errors=generation_errors,
            validator_errors=validator_errors,
            validator_attempts=list(getattr(exc, "attempts", []) or []),
            payload=dict(getattr(exc, "last_payload", {}) or {}) or article_payload,
            validator_artifact_dir=artifact_dir,
        ) from exc
    except ArticleValidatorError as exc:
        raise _build_article_failed_error(
            str(exc),
            generation_errors=generation_errors,
            validator_errors=[str(exc)],
            payload=article_payload,
            validator_artifact_dir=artifact_dir,
        ) from exc

    repaired_payload = dict(validator_result.article_payload)
    hero_image_path = generate_image(
        prompt=repaired_payload["hero_image_prompt"],
        image_kind="hero",
        out_dir=output_dir,
    )
    detail_image_path = generate_image(
        prompt=repaired_payload["detail_image_prompt"],
        image_kind="detail",
        out_dir=output_dir,
    )
    return SingleArticleDraftResult(
        article_payload=repaired_payload,
        hero_image_path=Path(hero_image_path),
        detail_image_path=Path(detail_image_path),
        validator_repaired=bool(validator_result.repaired),
        validator_attempts_used=int(validator_result.attempts_used),
        validator_artifact_dir=artifact_dir,
    )
