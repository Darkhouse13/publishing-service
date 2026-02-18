# Automating WF

Automation toolkit for:
- Trends collection
- PinClicks scraping and ranking
- WordPress draft/publish
- Pinterest bulk CSV export

## Repository Structure

- `src/automating_wf/`: canonical application package
- `tests/`: test suite
- `docs/`: project docs
- `scripts/`: utility scripts (for example theme zip builder)
- `assets/theme/`: WordPress theme source files
- `assets/media/`: heavy media assets
- `artifacts/`: generated outputs (runtime data, exports, reports, zips)

## Backward Compatibility

Root-level module names (for example `app.py`, `pinterest_engine.py`, `uploader.py`) are kept as compatibility shims and forward to `src/automating_wf`.

This preserves existing commands and imports while allowing package-based internal structure.

## Common Commands

- `python app.py`
- `python pinterest_engine.py --blog THE_SUNDAY_PATIO`
- `python wp_onboarding.py --help`
- `python -m pytest -q`

## Output Paths

- Pinterest CSV default: `artifacts/exports/pinterest_bulk_upload_{blog_suffix}.csv`
- Theme zip output: `artifacts/theme/the-sunday-patio.zip`

You can override paths with environment variables where supported.
