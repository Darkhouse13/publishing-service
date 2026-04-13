"""WordPress provider sub-package.

Concrete WordPress provider implementations (WP REST API, etc.) belong here.
Import the base ABC from this package::

    from app.providers.wordpress import WordPressProvider
"""

from app.providers.base import WordPressProvider

__all__ = ["WordPressProvider"]
