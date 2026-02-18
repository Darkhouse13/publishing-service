from __future__ import annotations

import os
from pathlib import Path


ARTIFACTS_ROOT = Path(os.getenv("AUTOMATING_WF_ARTIFACTS_ROOT", "artifacts")).resolve()
RUNTIME_ROOT = Path(os.getenv("AUTOMATING_WF_RUNTIME_ROOT", ARTIFACTS_ROOT / "runtime")).resolve()
EXPORTS_ROOT = Path(os.getenv("AUTOMATING_WF_EXPORTS_ROOT", ARTIFACTS_ROOT / "exports")).resolve()
REPORTS_ROOT = Path(os.getenv("AUTOMATING_WF_REPORTS_ROOT", ARTIFACTS_ROOT / "reports")).resolve()
THEME_ARTIFACTS_ROOT = Path(os.getenv("AUTOMATING_WF_THEME_ARTIFACTS_ROOT", ARTIFACTS_ROOT / "theme")).resolve()


def ensure_runtime_dirs() -> None:
    for path in (ARTIFACTS_ROOT, RUNTIME_ROOT, EXPORTS_ROOT, REPORTS_ROOT, THEME_ARTIFACTS_ROOT):
        path.mkdir(parents=True, exist_ok=True)
