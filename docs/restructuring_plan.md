# Plan: Clean Up Repo Structure — Remove All Root-Level Shims

## Context

The repo has 22 root-level `.py` shim files + `_module_shim.py` that are 3-line forwarders to the real code in `src/automating_wf/`. All 20 test files import from these old root-level module names. This plan removes every shim, updates every import and every `patch()` target string, fixes the subprocess invocation, and ensures zero breakage.

---

## Execution Order

### Step 1 — Update `pyproject.toml`

Add `pythonpath = ["src"]` so pytest can resolve `automating_wf.*` imports, and add CLI script entry points.

**File:** `pyproject.toml`
```toml
[project.scripts]
pinterest-engine = "automating_wf.engine.pipeline:main"
wp-onboarding = "automating_wf.wordpress.onboarding:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

No entry for Streamlit (it uses `streamlit run <file>`) or `build_theme` (stays as `python scripts/build_theme_zip.py`).

---

### Step 2 — Fix subprocess invocation in `engine/pipeline.py`

**File:** `src/automating_wf/engine/pipeline.py`

Line 139: change `"-m", "scraper_subprocess"` → `"-m", "automating_wf.scrapers.subprocess_runner"`

Also inject `PYTHONPATH` into the subprocess env so the child process can find the package even without an editable install:

```python
src_dir = str(Path(__file__).resolve().parents[3])
python_path = env.get("PYTHONPATH", "")
if src_dir not in python_path.split(os.pathsep):
    env["PYTHONPATH"] = src_dir + (os.pathsep + python_path if python_path else "")
```

---

### Step 3 — Update all 20 test files (imports + patch targets)

Every `from old_module import ...` becomes `from automating_wf.subpackage.module import ...`.
Every `patch("old_module.func")` string becomes `patch("automating_wf.subpackage.module.func")`.

#### Import mapping (old → new):

| Old Module | New Module |
|-----------|-----------|
| `app` (streamlit functions) | `automating_wf.ui.streamlit_app` |
| `app` (blog config re-exports) | `automating_wf.config.blogs` |
| `bulk_ui` | `automating_wf.ui.bulk_pipeline` |
| `engine_config` | `automating_wf.engine.config` |
| `generators` | `automating_wf.content.generators` |
| `validator` | `automating_wf.content.validator` |
| `single_article_flow` | `automating_wf.content.single_article_flow` |
| `pinterest_engine` | `automating_wf.engine.pipeline` |
| `pinterest_analysis` | `automating_wf.analysis.pinterest` |
| `pinclicks_analysis` | `automating_wf.analysis.pinclicks` |
| `pinterest_trends_analysis` | `automating_wf.analysis.trends` |
| `pinterest_scraper` | `automating_wf.scrapers.pinclicks` |
| `pinclicks_scraper` | `automating_wf.scrapers.pinclicks` |
| `pinterest_trends_scraper` | `automating_wf.scrapers.trends` |
| `scraper_subprocess` | `automating_wf.scrapers.subprocess_runner` |
| `pinterest_file_parser` | `automating_wf.scrapers.file_parser` |
| `pinterest_design` | `automating_wf.design.pinterest` |
| `pinterest_exporter` | `automating_wf.export.pinterest_csv` |
| `pinterest_models` | `automating_wf.models.pinterest` |
| `uploader` | `automating_wf.wordpress.uploader` |
| `wp_onboarding` | `automating_wf.wordpress.onboarding` |

#### Per-file changes:

**test_article_validator.py** — `from validator` → `from automating_wf.content.validator`; ~10 patch strings `"validator.*"` → `"automating_wf.content.validator.*"`

**test_bulk_pipeline_resume.py** — `from bulk_ui` → `from automating_wf.ui.bulk_pipeline`

**test_category_assignment.py** — `from app import suggest_primary_category` → `from automating_wf.config.blogs import suggest_primary_category`

**test_engine_config.py** — `from engine_config` → `from automating_wf.engine.config`

**test_generators_parser.py** — `from generators` → `from automating_wf.content.generators`

**test_generators_seo.py** — `from generators` → `from automating_wf.content.generators`; ~5 patch strings `"generators.*"` → `"automating_wf.content.generators.*"`

**test_pinclicks_analysis.py** — `from pinclicks_analysis` → `from automating_wf.analysis.pinclicks`; `from pinterest_models` → `from automating_wf.models.pinterest`

**test_pinterest_analysis.py** — `from pinterest_analysis` → `from automating_wf.analysis.pinterest`; `from pinterest_models` → `from automating_wf.models.pinterest`; ~4 patch strings

**test_pinterest_design.py** — `from pinterest_design` → `from automating_wf.design.pinterest`; `from pinterest_models` → `from automating_wf.models.pinterest`; ~11 patch strings

**test_pinterest_engine.py** — 4 import sources change; **~45 patch strings** `"pinterest_engine.*"` → `"automating_wf.engine.pipeline.*"` (highest-risk file)

**test_pinterest_engine_phases.py** — 4 import sources change; **~25 patch strings** `"pinterest_engine.*"` → `"automating_wf.engine.pipeline.*"`

**test_pinterest_exporter.py** — `from pinterest_exporter` → `from automating_wf.export.pinterest_csv`; `from pinterest_models` → `from automating_wf.models.pinterest`

**test_pinterest_scraper.py** — `from pinterest_scraper` → `from automating_wf.scrapers.pinclicks`; ~4 patch strings

**test_pinterest_trends_analysis.py** — `from pinterest_trends_analysis` → `from automating_wf.analysis.trends`

**test_pinterest_trends_scraper.py** — `from pinterest_trends_scraper` → `from automating_wf.scrapers.trends`; ~12 patch strings

**test_scraper_subprocess.py** — `import scraper_subprocess` → `from automating_wf.scrapers import subprocess_runner as scraper_subprocess`

**test_single_article_flow.py** — 3 import sources change; ~14 patch strings `"single_article_flow.*"` → `"automating_wf.content.single_article_flow.*"`

**test_uploader_flow.py** — `import uploader` → `from automating_wf.wordpress import uploader`; **~30 patch strings** `"uploader.*"` → `"automating_wf.wordpress.uploader.*"`

**test_vibe_sampling.py** — Split: streamlit functions from `automating_wf.ui.streamlit_app`, blog config functions from `automating_wf.config.blogs`

**test_wp_onboarding.py** — `from wp_onboarding` → `from automating_wf.wordpress.onboarding`; ~6 patch strings

**CHECKPOINT: Run `python -m pytest tests/ -q` — must pass with shims still present.**

---

### Step 4 — Delete all 23 root-level files

```
_module_shim.py  app.py  bulk_ui.py  generators.py  validator.py
single_article_flow.py  pinterest_engine.py  engine_config.py
pinterest_analysis.py  pinclicks_analysis.py  pinterest_trends_analysis.py
pinterest_scraper.py  pinclicks_scraper.py  pinterest_trends_scraper.py
scraper_subprocess.py  pinterest_file_parser.py  pinterest_design.py
pinterest_exporter.py  pinterest_models.py  uploader.py
wp_onboarding.py  build_theme.py
```

**CHECKPOINT: Run `python -m pytest tests/ -q` — must still pass.**

---

### Step 5 — Update README.md

Update command examples:
- `streamlit run app.py` → `streamlit run src/automating_wf/ui/streamlit_app.py`
- `python pinterest_engine.py --blog X` → `python -m automating_wf.engine.pipeline --blog X`
- `python wp_onboarding.py --help` → `python -m automating_wf.wordpress.onboarding --help`
- `python build_theme.py` → `python scripts/build_theme_zip.py`

Remove the "backward compatibility" / shim documentation section.

---

### Step 6 — Update docs/codebase_index.md

- Remove entire root-level shims section from file structure
- Remove `_module_shim.py` reference
- Update all 5 route entry points to new commands
- Remove structural issues #1, #2, #3, #5 (shim-related)

---

### Step 7 — Clean caches

Delete `__pycache__/` and `.pytest_cache/` directories.

**FINAL: Run `python -m pytest tests/ -v` — all tests green.**

---

## Files Modified

| File | Action |
|------|--------|
| `pyproject.toml` | Edit (add pythonpath + scripts) |
| `src/automating_wf/engine/pipeline.py` | Edit (line 139 subprocess path + PYTHONPATH env) |
| `tests/test_article_validator.py` | Edit (imports + ~10 patch targets) |
| `tests/test_bulk_pipeline_resume.py` | Edit (imports) |
| `tests/test_category_assignment.py` | Edit (imports) |
| `tests/test_engine_config.py` | Edit (imports) |
| `tests/test_generators_parser.py` | Edit (imports) |
| `tests/test_generators_seo.py` | Edit (imports + ~5 patch targets) |
| `tests/test_pinclicks_analysis.py` | Edit (imports) |
| `tests/test_pinterest_analysis.py` | Edit (imports + ~4 patch targets) |
| `tests/test_pinterest_design.py` | Edit (imports + ~11 patch targets) |
| `tests/test_pinterest_engine.py` | Edit (imports + **~45 patch targets**) |
| `tests/test_pinterest_engine_phases.py` | Edit (imports + **~25 patch targets**) |
| `tests/test_pinterest_exporter.py` | Edit (imports) |
| `tests/test_pinterest_scraper.py` | Edit (imports + ~4 patch targets) |
| `tests/test_pinterest_trends_analysis.py` | Edit (imports) |
| `tests/test_pinterest_trends_scraper.py` | Edit (imports + ~12 patch targets) |
| `tests/test_scraper_subprocess.py` | Edit (imports) |
| `tests/test_single_article_flow.py` | Edit (imports + ~14 patch targets) |
| `tests/test_uploader_flow.py` | Edit (imports + **~30 patch targets**) |
| `tests/test_vibe_sampling.py` | Edit (imports split) |
| `tests/test_wp_onboarding.py` | Edit (imports + ~6 patch targets) |
| `README.md` | Edit (update commands) |
| `docs/codebase_index.md` | Edit (remove shims, update routes) |

## Files Deleted (23)

All root-level `.py` shim files + `_module_shim.py` (listed above in Step 4).

## Verification

1. After Step 3: `python -m pytest tests/ -q` passes (shims still present)
2. After Step 4: `python -m pytest tests/ -q` passes (shims deleted)
3. After Step 7: `python -m pytest tests/ -v` all green
