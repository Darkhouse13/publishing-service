from __future__ import annotations

from _module_shim import load

_module = load(__name__, "automating_wf.scrapers.subprocess_runner")

if __name__ == "__main__":
    _module.main()
