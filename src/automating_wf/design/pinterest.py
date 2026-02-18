from __future__ import annotations

import json
import os
import random
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from automating_wf.models.pinterest import BrainOutput


PIN_WIDTH = 1000
PIN_HEIGHT = 1500
DEFAULT_PIN_IMAGE_ATTEMPTS = 2
TEXT_BOX_X_MARGIN = 80
TEXT_BOX_TOP = 120
TEXT_BOX_BOTTOM = 1180
TEXT_MAX_LINES = 4
TEXT_START_SIZE = 92
TEXT_MIN_SIZE = 38
JPEG_QUALITY = 92


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


def _pillow_packaged_fallback_font_path() -> Path | None:
    try:
        from PIL import ImageFont
    except ImportError:
        return None

    # Pillow ships with DejaVuSans.ttf in most distributions.
    font_path = Path(ImageFont.__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"
    if font_path.exists():
        return font_path
    return None


def resolve_font_path(blog_suffix: str) -> Path | None:
    font_map = _load_font_map()
    normalized_suffix = (blog_suffix or "").strip().upper()
    configured = font_map.get(normalized_suffix) or font_map.get("default")
    if isinstance(configured, str) and configured.strip():
        candidate = Path(configured).expanduser()
        if candidate.exists():
            return candidate
    return _pillow_packaged_fallback_font_path()


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
    font_path: Path | None,
    max_width: int,
    max_height: int,
    max_lines: int,
) -> tuple[list[str], Any, bool]:
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise ImageDesignError("Pillow is required for font rendering.") from exc

    words = text.split()
    if not words:
        font = ImageFont.load_default()
        return [""], font, False

    def _load_font(size: int) -> Any:
        if font_path and font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
        return ImageFont.load_default()

    last_lines: list[str] = []
    last_font: Any = _load_font(TEXT_MIN_SIZE)
    for font_size in range(TEXT_START_SIZE, TEXT_MIN_SIZE - 1, -2):
        font = _load_font(font_size)
        avg_char_width = max(12, int(font_size * 0.56))
        wrap_width = max(8, max_width // avg_char_width)
        wrapped = textwrap.wrap(text, width=wrap_width, break_long_words=False)
        if len(wrapped) > max_lines:
            last_lines = wrapped
            last_font = font
            continue

        line_heights = []
        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_heights.append(max(1, bbox[3] - bbox[1]))
        text_height = sum(line_heights) + max(0, len(wrapped) - 1) * int(font_size * 0.25)
        too_wide = any((draw.textbbox((0, 0), line, font=font)[2] > max_width) for line in wrapped)
        if not too_wide and text_height <= max_height:
            return wrapped, font, False
        last_lines = wrapped
        last_font = font

    # Truncate fallback after minimum-size exhaustion.
    collapsed = " ".join(words)
    truncated = collapsed
    while len(truncated) > 8:
        truncated = truncated[:-1].rstrip()
        test_value = truncated + "..."
        wrapped = textwrap.wrap(test_value, width=max(8, max_width // 20), break_long_words=False)
        if len(wrapped) <= max_lines:
            return wrapped, last_font, True
    return last_lines[:max_lines], last_font, True


def _apply_readability_overlay(base_image: Any) -> Any:
    from PIL import Image

    overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    width, height = base_image.size
    pixels = overlay.load()

    for y in range(height):
        alpha = 0
        top_band = int(height * 0.24)
        bottom_band = int(height * 0.34)
        if y <= top_band:
            alpha = int(170 * (1 - (y / max(1, top_band))))
        elif y >= height - bottom_band:
            distance = y - (height - bottom_band)
            alpha = int(200 * (distance / max(1, bottom_band)))
        pixels_row_alpha = max(0, min(200, alpha))
        for x in range(width):
            pixels[x, y] = (0, 0, 0, pixels_row_alpha)

    return Image.alpha_composite(base_image.convert("RGBA"), overlay)


def _render_overlay_text(
    *,
    image: Any,
    text: str,
    blog_suffix: str,
) -> tuple[Any, bool, str]:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    font_path = resolve_font_path(blog_suffix=blog_suffix)
    max_width = PIN_WIDTH - (TEXT_BOX_X_MARGIN * 2)
    max_height = TEXT_BOX_BOTTOM - TEXT_BOX_TOP
    lines, font, truncated = _fit_text_to_box(
        draw=draw,
        text=text,
        font_path=font_path,
        max_width=max_width,
        max_height=max_height,
        max_lines=TEXT_MAX_LINES,
    )

    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(max(1, bbox[3] - bbox[1]))
    line_gap = max(8, int(getattr(font, "size", 40) * 0.24))
    total_height = sum(line_heights) + max(0, len(lines) - 1) * line_gap
    y_cursor = TEXT_BOX_TOP + max(0, (max_height - total_height) // 2)

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = TEXT_BOX_X_MARGIN + max(0, (max_width - line_width) // 2)
        # Shadow improves contrast on bright/generated surfaces.
        draw.text((x + 2, y_cursor + 2), line, font=font, fill=(0, 0, 0, 210))
        draw.text((x, y_cursor), line, font=font, fill=(255, 255, 255, 245))
        y_cursor += line_height + line_gap

    font_used = str(font_path) if font_path else "PIL_DEFAULT"
    return image, truncated, font_used


def generate_pinterest_image(
    *,
    brain_output: BrainOutput,
    blog_suffix: str,
    run_dir: Path,
    max_attempts: int = DEFAULT_PIN_IMAGE_ATTEMPTS,
) -> Path:
    if not brain_output.image_generation_prompt.strip():
        raise ImageDesignError("image_generation_prompt is required.")

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ImageDesignError("Pillow is required for Pinterest image processing.") from exc

    _ensure_dir(run_dir)
    base_image_path = _build_base_image(
        prompt=brain_output.image_generation_prompt,
        out_dir=run_dir,
        max_attempts=max_attempts,
    )

    with Image.open(base_image_path) as source_image:
        fitted = ImageOps.fit(
            source_image.convert("RGB"),
            (PIN_WIDTH, PIN_HEIGHT),
            method=Image.Resampling.LANCZOS,
        )
    composited = _apply_readability_overlay(fitted)
    rendered, was_truncated, font_used = _render_overlay_text(
        image=composited,
        text=brain_output.pin_text_overlay,
        blog_suffix=blog_suffix,
    )

    output_path = run_dir / f"pin_final_{uuid.uuid4().hex[:10]}.jpg"
    rendered.convert("RGB").save(output_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    metadata = {
        "base_image_path": str(base_image_path),
        "output_path": str(output_path),
        "dimensions": {"width": PIN_WIDTH, "height": PIN_HEIGHT},
        "pin_text_overlay": brain_output.pin_text_overlay,
        "overlay_truncated": was_truncated,
        "font_used": font_used,
    }
    (run_dir / "pin_design_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
