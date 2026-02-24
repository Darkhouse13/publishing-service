from __future__ import annotations

import json
import os
import random
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from automating_wf.config.blogs import BLOG_CONFIGS
from automating_wf.models.pinterest import BrainOutput


PIN_WIDTH = 1000
PIN_HEIGHT = 1500
DEFAULT_PIN_IMAGE_ATTEMPTS = 2
JPEG_QUALITY = 92

SUPPORTED_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
WINDOWS_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/trebucbd.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/calibrib.ttf"),
    Path("C:/Windows/Fonts/verdanab.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/calibri.ttf"),
    Path("C:/Windows/Fonts/verdana.ttf"),
)
MACOS_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Helvetica.ttc"),
    Path("/Library/Fonts/Arial.ttf"),
)
LINUX_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)
WINDOWS_SERIF_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/georgia.ttf"),
    Path("C:/Windows/Fonts/GARA.TTF"),
    Path("C:/Windows/Fonts/cambria.ttc"),
    Path("C:/Windows/Fonts/times.ttf"),
)
MACOS_SERIF_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
    Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Georgia.ttf"),
)
LINUX_SERIF_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
)

TEMPLATE_MODE_CENTER_STRIP = "center_strip"
TEMPLATE_MODE_NONE = "none"
TEMPLATE_FAILURE_POLICY_TEMPLATE_OR_NONE = "template_or_none"
TEMPLATE_FAILURE_POLICY_FAIL = "fail"

DEFAULT_TEMPLATE_MODE = TEMPLATE_MODE_CENTER_STRIP
DEFAULT_TEMPLATE_FAILURE_POLICY = TEMPLATE_FAILURE_POLICY_TEMPLATE_OR_NONE

CENTER_STRIP_HEIGHT = 270
CENTER_STRIP_BOTTOM_MARGIN = 80

CENTER_STRIP_BACKGROUND = (246, 246, 246)
CENTER_STRIP_LINE = (218, 218, 218)
HEADLINE_TEXT_COLOR = (88, 90, 94)
BYLINE_TEXT_COLOR = (103, 103, 103)

HEADLINE_MAX_LINES = 2
HEADLINE_START_SIZE = 78
HEADLINE_MIN_SIZE = 44
HEADLINE_MIN_RENDER_SIZE = 44
HEADLINE_MAX_WIDTH = PIN_WIDTH - 140
HEADLINE_TOP_PADDING = 28
HEADLINE_BOTTOM_GAP = 18

BYLINE_START_SIZE = 38
BYLINE_MIN_SIZE = 22
BYLINE_MAX_LINES = 1
BYLINE_MAX_WIDTH = PIN_WIDTH - 200
BYLINE_BOTTOM_PADDING = 24


class ImageDesignError(RuntimeError):
    """Raised when Pinterest image generation or styling fails."""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _extract_image_url(payload: Any) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("images"), list) and payload["images"]:
            first = payload["images"][0]
            if isinstance(first, dict):
                url = first.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
        image = payload.get("image")
        if isinstance(image, dict):
            url = image.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        url = payload.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    raise ImageDesignError("Image provider response did not include an image URL.")


def _guess_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def _load_font_map() -> dict[str, Any]:
    load_dotenv()
    raw = os.getenv("PINTEREST_FONT_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _load_template_mode() -> str:
    load_dotenv()
    raw = os.getenv("PINTEREST_PIN_TEMPLATE_MODE", "").strip().casefold()
    if raw in {TEMPLATE_MODE_CENTER_STRIP, TEMPLATE_MODE_NONE}:
        return raw
    return DEFAULT_TEMPLATE_MODE


def _load_template_failure_policy() -> str:
    load_dotenv()
    raw = os.getenv("PINTEREST_PIN_TEMPLATE_FAILURE_POLICY", "").strip().casefold()
    if raw in {TEMPLATE_FAILURE_POLICY_TEMPLATE_OR_NONE, TEMPLATE_FAILURE_POLICY_FAIL}:
        return raw
    return DEFAULT_TEMPLATE_FAILURE_POLICY


def _pillow_packaged_fallback_font_path() -> Path | None:
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    font_path = Path(ImageFont.__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"
    if font_path.exists():
        return font_path
    return None


def _iter_os_font_candidates() -> list[tuple[Path, str]]:
    if sys.platform.startswith("win"):
        return [(path, "os_windows") for path in WINDOWS_FONT_CANDIDATES]
    if sys.platform == "darwin":
        return [(path, "os_macos") for path in MACOS_FONT_CANDIDATES]
    return [(path, "os_linux") for path in LINUX_FONT_CANDIDATES]


def _iter_os_serif_font_candidates() -> list[tuple[Path, str]]:
    if sys.platform.startswith("win"):
        return [(path, "os_windows_serif") for path in WINDOWS_SERIF_FONT_CANDIDATES]
    if sys.platform == "darwin":
        return [(path, "os_macos_serif") for path in MACOS_SERIF_FONT_CANDIDATES]
    return [(path, "os_linux_serif") for path in LINUX_SERIF_FONT_CANDIDATES]


def _is_scalable_font_path(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.suffix.casefold() not in SUPPORTED_FONT_SUFFIXES:
        return False
    try:
        from PIL import ImageFont
    except ImportError:
        return False

    try:
        font = ImageFont.truetype(str(path), size=max(40, HEADLINE_MIN_SIZE))
    except Exception:
        return False
    return bool(getattr(font, "size", 0))


def _resolve_font_path_with_source(blog_suffix: str) -> tuple[Path | None, str, list[str]]:
    attempts: list[str] = []
    font_map = _load_font_map()
    normalized_suffix = (blog_suffix or "").strip().upper()
    for key in (normalized_suffix, "default"):
        configured = font_map.get(key)
        if not isinstance(configured, str) or not configured.strip():
            continue
        candidate = Path(configured).expanduser()
        attempts.append(f"env:{key}:{candidate}")
        if _is_scalable_font_path(candidate):
            return candidate, f"env:{key}", attempts

    packaged = _pillow_packaged_fallback_font_path()
    if packaged is not None:
        attempts.append(f"pillow_packaged:{packaged}")
        if _is_scalable_font_path(packaged):
            return packaged, "pillow_packaged", attempts

    for candidate, source in _iter_os_font_candidates():
        attempts.append(f"{source}:{candidate}")
        if _is_scalable_font_path(candidate):
            return candidate, source, attempts

    return None, "missing", attempts


def _resolve_serif_font_path_with_source() -> tuple[Path | None, str]:
    for candidate, source in _iter_os_serif_font_candidates():
        if _is_scalable_font_path(candidate):
            return candidate, source
    return None, "missing"


def resolve_font_path(blog_suffix: str) -> Path | None:
    font_path, _, _ = _resolve_font_path_with_source(blog_suffix=blog_suffix)
    return font_path


def _resolve_blog_display_name(*, blog_suffix: str, blog_name: str) -> str:
    provided = str(blog_name or "").strip()
    if provided:
        return provided
    normalized = str(blog_suffix or "").strip().upper()
    for name, config in BLOG_CONFIGS.items():
        suffix = str(config.get("wp_env_suffix", "")).strip().upper()
        if suffix == normalized:
            return str(name).strip()
    return normalized or "Blog"


def _normalize_headline_text(value: str) -> str:
    compact = " ".join(str(value or "").split()).strip()
    return compact.upper()


def _build_base_image(prompt: str, out_dir: Path, max_attempts: int) -> Path:
    load_dotenv()
    fal_key = os.getenv("FAL_KEY", "").strip()
    if not fal_key:
        raise ImageDesignError("Missing FAL_KEY in environment.")
    os.environ["FAL_KEY"] = fal_key
    fal_model = os.getenv("FAL_MODEL_PIN", "").strip() or os.getenv("FAL_MODEL", "fal-ai/flux/dev").strip()

    try:
        import fal_client
    except ImportError as exc:
        raise ImageDesignError("fal-client is required for Pinterest image generation.") from exc

    _ensure_dir(out_dir)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fal_client.subscribe(fal_model, arguments={"prompt": prompt.strip()})
            payload = result.get("data") if isinstance(result, dict) and "data" in result else result
            image_url = _extract_image_url(payload)
            response = requests.get(image_url, timeout=120)
            response.raise_for_status()
            extension = _guess_extension(image_url)
            file_path = out_dir / f"pin_base_{uuid.uuid4().hex[:10]}{extension}"
            file_path.write_bytes(response.content)
            return file_path
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(random.uniform(1.4, 3.4))
    raise ImageDesignError(f"Failed to generate Pinterest base image after {max_attempts} attempts: {last_error}")


def _fit_text_to_box(
    *,
    draw: Any,
    text: str,
    font_path: Path,
    max_width: int,
    max_height: int,
    max_lines: int,
    start_size: int,
    min_size: int,
) -> tuple[list[str], Any, bool, int]:
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise ImageDesignError("Pillow is required for font rendering.") from exc

    words = text.split()
    if not words:
        raise ImageDesignError("Text input is empty after normalization.")

    def _load_font(size: int) -> Any:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception as exc:
            raise ImageDesignError(f"Could not load scalable font '{font_path}'.") from exc

    last_lines: list[str] = []
    last_font: Any = _load_font(min_size)
    last_font_size = min_size
    for font_size in range(start_size, min_size - 1, -2):
        font = _load_font(font_size)
        avg_char_width = max(10, int(font_size * 0.55))
        wrap_width = max(6, max_width // avg_char_width)
        wrapped = textwrap.wrap(text, width=wrap_width, break_long_words=False)
        if len(wrapped) > max_lines:
            last_lines = wrapped
            last_font = font
            last_font_size = font_size
            continue
        line_heights = [
            max(
                1,
                draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1],
            )
            for line in wrapped
        ]
        line_gap = max(6, int(font_size * 0.22))
        text_height = sum(line_heights) + max(0, len(wrapped) - 1) * line_gap
        too_wide = any((draw.textbbox((0, 0), line, font=font)[2] > max_width) for line in wrapped)
        if not too_wide and text_height <= max_height:
            return wrapped, font, False, font_size
        last_lines = wrapped
        last_font = font
        last_font_size = font_size

    tokens = text.split()
    while len(tokens) > 1:
        tokens = tokens[:-1]
        candidate = " ".join(tokens).strip() + "..."
        avg_char_width = max(10, int(last_font_size * 0.55))
        wrapped = textwrap.wrap(candidate, width=max(6, max_width // avg_char_width), break_long_words=False)
        too_wide = any((draw.textbbox((0, 0), line, font=last_font)[2] > max_width) for line in wrapped)
        if len(wrapped) <= max_lines and not too_wide:
            return wrapped, last_font, True, last_font_size

    if last_lines:
        return last_lines[:max_lines], last_font, True, last_font_size
    raise ImageDesignError("Could not fit text in configured template area.")


def _fit_base_to_canvas(base_image_path: Path) -> Any:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ImageDesignError("Pillow is required for Pinterest image processing.") from exc
    with Image.open(base_image_path) as source_image:
        return ImageOps.fit(
            source_image.convert("RGB"),
            (PIN_WIDTH, PIN_HEIGHT),
            method=Image.Resampling.LANCZOS,
        )


def _compose_center_strip_background(fitted: Any) -> tuple[Any, dict[str, int]]:
    from PIL import ImageDraw

    # Keep one continuous scene to avoid duplicated objects introduced by split-panel recropping.
    canvas = fitted.copy().convert("RGB")
    strip_top = PIN_HEIGHT - CENTER_STRIP_HEIGHT - CENTER_STRIP_BOTTOM_MARGIN
    strip_bottom = strip_top + CENTER_STRIP_HEIGHT

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(0, strip_top), (PIN_WIDTH, strip_bottom)], fill=CENTER_STRIP_BACKGROUND)
    draw.line([(0, strip_top), (PIN_WIDTH, strip_top)], fill=CENTER_STRIP_LINE, width=2)
    draw.line([(0, strip_bottom - 1), (PIN_WIDTH, strip_bottom - 1)], fill=CENTER_STRIP_LINE, width=2)
    return canvas, {"strip_top": strip_top, "strip_bottom": strip_bottom}


def _render_center_strip_template(
    *,
    fitted: Any,
    pin_title: str,
    blog_name: str,
    blog_suffix: str,
) -> tuple[Any, dict[str, Any]]:
    from PIL import ImageDraw

    canvas, strip = _compose_center_strip_background(fitted)
    draw = ImageDraw.Draw(canvas)

    headline = _normalize_headline_text(pin_title)
    if not headline:
        raise ImageDesignError("pin_title is empty; cannot render center-strip headline.")

    headline_font_path, font_source, font_attempts = _resolve_font_path_with_source(blog_suffix=blog_suffix)
    if headline_font_path is None:
        attempts_hint = "; ".join(font_attempts) if font_attempts else "no candidates found"
        raise ImageDesignError(
            "No scalable font could be resolved for center-strip headline. "
            f"Resolution attempts: {attempts_hint}"
        )

    serif_font_path, serif_source = _resolve_serif_font_path_with_source()
    byline_font_path = serif_font_path or headline_font_path
    byline_font_source = serif_source if serif_font_path else font_source

    strip_top = int(strip["strip_top"])
    strip_bottom = int(strip["strip_bottom"])

    byline_box_top = strip_bottom - BYLINE_BOTTOM_PADDING - 62
    byline_box_height = 60
    byline_lines, byline_font, byline_truncated, byline_size = _fit_text_to_box(
        draw=draw,
        text=blog_name,
        font_path=byline_font_path,
        max_width=BYLINE_MAX_WIDTH,
        max_height=byline_box_height,
        max_lines=BYLINE_MAX_LINES,
        start_size=BYLINE_START_SIZE,
        min_size=BYLINE_MIN_SIZE,
    )
    byline_line = byline_lines[0]
    byline_bbox = draw.textbbox((0, 0), byline_line, font=byline_font)
    byline_width = byline_bbox[2] - byline_bbox[0]
    byline_height = byline_bbox[3] - byline_bbox[1]
    byline_x = (PIN_WIDTH - byline_width) // 2
    byline_y = max(strip_top + 6, byline_box_top + max(0, (byline_box_height - byline_height) // 2))

    headline_box_top = strip_top + HEADLINE_TOP_PADDING
    headline_max_height = max(70, byline_y - headline_box_top - HEADLINE_BOTTOM_GAP)
    headline_lines, headline_font, headline_truncated, headline_size = _fit_text_to_box(
        draw=draw,
        text=headline,
        font_path=headline_font_path,
        max_width=HEADLINE_MAX_WIDTH,
        max_height=headline_max_height,
        max_lines=HEADLINE_MAX_LINES,
        start_size=HEADLINE_START_SIZE,
        min_size=HEADLINE_MIN_SIZE,
    )
    if headline_size < HEADLINE_MIN_RENDER_SIZE:
        raise ImageDesignError(
            f"Headline font size {headline_size} is below readability threshold {HEADLINE_MIN_RENDER_SIZE}."
        )

    headline_heights: list[int] = []
    for line in headline_lines:
        bbox = draw.textbbox((0, 0), line, font=headline_font)
        headline_heights.append(max(1, bbox[3] - bbox[1]))
    headline_gap = max(8, int(headline_size * 0.25))
    headline_total_height = sum(headline_heights) + max(0, len(headline_lines) - 1) * headline_gap
    headline_y = headline_box_top + max(0, (headline_max_height - headline_total_height) // 2)

    headline_rendered_lines: list[str] = []
    for line in headline_lines:
        bbox = draw.textbbox((0, 0), line, font=headline_font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = (PIN_WIDTH - line_width) // 2
        draw.text((x, headline_y), line, font=headline_font, fill=HEADLINE_TEXT_COLOR)
        headline_rendered_lines.append(line)
        headline_y += line_height + headline_gap

    draw.text((byline_x, byline_y), byline_line, font=byline_font, fill=BYLINE_TEXT_COLOR)
    return canvas, {
        "font_used": str(headline_font_path),
        "font_resolution_source": font_source,
        "font_resolution_stage": font_source,
        "font_resolution_attempts": font_attempts,
        "font_point_size": headline_size,
        "font_used_byline": str(byline_font_path),
        "font_byline_source": byline_font_source,
        "font_byline_size": byline_size,
        "overlay_truncated": bool(headline_truncated or byline_truncated),
        "headline_text_rendered": "\n".join(headline_rendered_lines),
        "byline_text_rendered": byline_line,
    }


def generate_pinterest_image(
    *,
    brain_output: BrainOutput,
    blog_suffix: str,
    run_dir: Path,
    max_attempts: int = DEFAULT_PIN_IMAGE_ATTEMPTS,
    blog_name: str = "",
) -> Path:
    if not brain_output.image_generation_prompt.strip():
        raise ImageDesignError("image_generation_prompt is required.")

    _ensure_dir(run_dir)
    base_image_path = _build_base_image(
        prompt=brain_output.image_generation_prompt,
        out_dir=run_dir,
        max_attempts=max_attempts,
    )

    fitted = _fit_base_to_canvas(base_image_path=base_image_path)
    template_mode = _load_template_mode()
    failure_policy = _load_template_failure_policy()
    resolved_blog_name = _resolve_blog_display_name(
        blog_suffix=blog_suffix,
        blog_name=blog_name,
    )

    metadata: dict[str, Any] = {
        "base_image_path": str(base_image_path),
        "dimensions": {"width": PIN_WIDTH, "height": PIN_HEIGHT},
        "background_composition": "continuous_base",
        "pin_text_overlay": brain_output.pin_text_overlay,
        "headline_text_source": "pin_title",
        "template_mode": template_mode,
        "text_rendered": False,
        "text_fallback_reason": "",
        "headline_text_rendered": "",
        "byline_text_rendered": "",
        "overlay_truncated": False,
        "font_used": "",
        "font_resolution_source": "",
        "font_resolution_stage": "",
        "font_resolution_attempts": [],
        "font_point_size": 0,
    }

    rendered = fitted
    if template_mode == TEMPLATE_MODE_CENTER_STRIP:
        try:
            rendered, details = _render_center_strip_template(
                fitted=fitted,
                pin_title=brain_output.pin_title,
                blog_name=resolved_blog_name,
                blog_suffix=blog_suffix,
            )
            metadata.update(details)
            metadata["text_rendered"] = True
        except Exception as exc:
            reason = str(exc)
            metadata["text_fallback_reason"] = reason
            if failure_policy == TEMPLATE_FAILURE_POLICY_FAIL:
                raise
            rendered = fitted
    elif template_mode == TEMPLATE_MODE_NONE:
        metadata["text_fallback_reason"] = "template_mode_none"
        rendered = fitted
    else:
        metadata["text_fallback_reason"] = f"unknown_template_mode:{template_mode}"
        if failure_policy == TEMPLATE_FAILURE_POLICY_FAIL:
            raise ImageDesignError(f"Unsupported template mode: {template_mode}")
        rendered = fitted

    output_path = run_dir / f"pin_final_{uuid.uuid4().hex[:10]}.jpg"
    rendered.convert("RGB").save(output_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    metadata["output_path"] = str(output_path)
    (run_dir / "pin_design_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
