from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load(current_name: str, target: str):
    src_dir = Path(__file__).resolve().parent / "src"
    src_str = str(src_dir)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    module = importlib.import_module(target)
    sys.modules[current_name] = module
    return module
