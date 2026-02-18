from __future__ import annotations

from _module_shim import load

_module = load(__name__, "scripts.build_theme_zip")

if __name__ == "__main__":
    _module.main()
