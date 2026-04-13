"""Image provider sub-package.

Concrete image provider implementations (Fal, DALL-E, etc.) belong here.
Import the base ABC from this package::

    from app.providers.image import ImageProvider
    from app.providers.image import FalProvider
"""

from app.providers.base import ImageProvider
from app.providers.image.fal import FalProvider

__all__ = ["ImageProvider", "FalProvider"]
