"""ImageGeneratorService — image generation and download via provider.

Calls ImageProvider.generate() with prompt and dimensions, downloads the
image from the returned URL via httpx, saves to output_dir with naming
convention ``{image_kind}_{uuid_hex[:10]}.jpg``, and returns the absolute
local path.

Ported from ``src/automating_wf/design/pinterest.py`` image generation
logic but rewritten cleanly against the new async provider architecture.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WIDTH: int = 1024
DEFAULT_HEIGHT: int = 1024
FILE_EXTENSION: str = ".jpg"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImageDownloadError(RuntimeError):
    """Raised when image generation or download fails."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_filename(image_kind: str) -> str:
    """Build a filename following the ``{image_kind}_{uuid_hex[:10]}.jpg`` convention.

    Args:
        image_kind: The kind of image (e.g. ``"hero"``, ``"detail"``).

    Returns:
        A filename string like ``"hero_a1b2c3d4e5.jpg"``.
    """
    hex_part = uuid.uuid4().hex[:10]
    return f"{image_kind}_{hex_part}{FILE_EXTENSION}"


# ---------------------------------------------------------------------------
# ImageGeneratorService
# ---------------------------------------------------------------------------


class ImageGeneratorService:
    """Image generation and download service.

    Uses an :class:`ImageProvider` to generate images and downloads the
    result to a local directory.

    Parameters:
        provider: An :class:`ImageProvider` instance for image generation.
    """

    def __init__(self, provider: ImageProvider) -> None:
        self._provider = provider

    async def generate_image(
        self,
        *,
        prompt: str,
        image_kind: str,
        output_dir: Path,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> str:
        """Generate an image, download it, and save to disk.

        Args:
            prompt: Text description of the desired image.
            image_kind: Kind of image (e.g. ``"hero"``, ``"detail"``).
                Used in the output filename.
            output_dir: Directory to save the downloaded image.
            width: Desired image width in pixels.
            height: Desired image height in pixels.

        Returns:
            Absolute local file path of the saved image.

        Raises:
            ImageDownloadError: If the provider fails or the download fails.
        """
        # --- Call provider ---
        try:
            result = await self._provider.generate(
                prompt,
                width=width,
                height=height,
            )
        except Exception as exc:
            logger.error(
                "Image provider failed for kind=%s: %s", image_kind, exc
            )
            raise ImageDownloadError(
                f"Image provider failed: {exc}"
            ) from exc

        image_url = result.url
        logger.debug(
            "Image provider returned URL=%s for kind=%s", image_url, image_kind
        )

        # --- Download image ---
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
                response.raise_for_status()
                image_bytes = response.content  # type: ignore[assignment]
        except Exception as exc:
            logger.error(
                "Failed to download image from %s: %s", image_url, exc
            )
            raise ImageDownloadError(
                f"Failed to download image from {image_url}: {exc}"
            ) from exc

        # --- Save to disk ---
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = _build_filename(image_kind)
        file_path = output_dir / filename
        file_path.write_bytes(image_bytes)

        logger.info(
            "Image saved: kind=%s, path=%s, size=%d bytes",
            image_kind,
            file_path,
            len(image_bytes),
        )

        return str(file_path.resolve())
