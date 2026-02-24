# Implementation Plan

[Overview]
Improve PinClicks keyword acquisition reliability so the pipeline does not fail with “No viable keywords found from PinClicks analysis” when `/pins` search-box entry intermittently fails.

The current pipeline fails early for some keywords because `pinterest_scraper._search_keyword_on_pins_page()` is brittle against UI/DOM variation and raises `ScraperError` after limited retry paths. When this happens repeatedly for multiple trend candidates, phase 2 produces only skipped keywords, `rank_pinclicks_keywords()` receives no usable scrape results, and the UI shows a generic “No viable keywords found from PinClicks analysis.” This creates high false-negative failure rates even when PinClicks still has data for the keyword.

The implementation should harden PinClicks scraping by introducing resilient navigation and search fallback flows, better diagnostics, and deterministic skip classification while preserving existing phase boundaries (`collect_trends_candidates_sync` -> `collect_pinclicks_data_sync` -> `run_winner_generation_sync`). The strategy is to keep the existing export-first architecture intact, but add controlled fallback routes: (1) direct top-pins URL loading using the existing `build_top_pins_url()` helper, (2) improved search-input targeting + verification logic, and (3) structured failure reasons surfaced to UI/manifest. This reduces keyword loss and makes remaining failures actionable.

[Types]
Add lightweight failure metadata types so PinClicks scrape failures are explicit and machine-readable across engine/UI boundaries.

Define a new typed payload shape for phase-2 skipped items in `engine_config.py` using dataclass-backed conventions already used in the codebase:

- `PinClicksSkipReason` (string enum-like constants, implemented as module constants for compatibility):
  - `search_input_not_found`
  - `search_input_rejected`
  - `direct_top_pins_navigation_failed`
  - `export_download_failed`
  - `no_records_extracted`
  - `captcha_checkpoint_required`
  - `authentication_failed`
  - `unknown_scrape_failure`

- `PinClicksSkipDetail` (dict-compatible structure in runtime payloads):
  - `keyword: str` (required, non-empty)
  - `reason: str` (required, one of constants above)
  - `error: str` (required, human-readable summary)
  - `attempts: int` (required, >=1)
  - `used_headed_fallback: bool` (required)
  - `source_stage: str` (required, always `"pinclicks"`)

Validation rules:
- `keyword` must be trimmed and non-empty.
- `reason` must be normalized to a known constant; otherwise fallback to `unknown_scrape_failure`.
- `attempts` must reflect outer `scrape_seed(..., max_attempts=...)` loop attempts.

Relationship updates:
- `PinClicksResults.skipped` remains `list[dict[str, Any]]` for backward compatibility, but entries are normalized to `PinClicksSkipDetail` shape.

[Files]
Modify scraper/engine/UI/test files to add resilient scrape fallbacks and richer skip reporting without changing phase contracts.

- Existing files to modify:
  - `pinterest_scraper.py`
    - Add robust keyword-application strategy with multi-step fallbacks.
    - Add direct top-pins URL fallback path using `build_top_pins_url(seed_keyword)`.
    - Add structured error classification helper(s).
    - Emit richer artifact logs per attempt/fallback branch.
  - `pinterest_engine.py`
    - Normalize scrape failure details into structured skip payloads.
    - Keep manifest status `scrape_failed` but include reason codes under `details`.
  - `bulk_ui.py`
    - Improve skipped keyword rendering to show reason code + concise message.
    - Keep existing warning UX while adding actionable detail.
  - `engine_config.py`
    - Add constants / documentation comments for skip reason vocabulary.
  - `tests/test_pinterest_scraper.py`
    - Add tests for fallback order and reason classification.
  - `tests/test_pinterest_engine_phases.py`
    - Add assertions that `collect_pinclicks_data_sync()` returns structured skipped entries.
  - `tests/test_pinclicks_analysis.py`
    - Add edge-case tests to ensure ranking behavior is predictable when many keywords are skipped and only a subset is rankable.

- New files to create:
  - None required.

- Files to delete/move:
  - None.

- Configuration updates:
  - No mandatory new env vars.
  - Optional (non-breaking) env toggles may be introduced if needed for safe rollout, e.g. `PINCLICKS_DIRECT_URL_FALLBACK=1` (default enabled).

[Functions]
Primary functional changes are in scraper fallback flow and structured failure propagation.

- New functions (proposed):
  - `pinterest_scraper.py::_classify_scrape_error(error: Exception) -> str`
    - Maps raw exceptions/messages to standardized skip reason codes.
  - `pinterest_scraper.py::_navigate_direct_top_pins(page: Any, seed_keyword: str) -> bool`
    - Attempts direct keyword route via `build_top_pins_url`; returns success flag after keyword presence verification.
  - `pinterest_scraper.py::_attempt_keyword_targeting(page: Any, seed_keyword: str) -> bool`
    - Consolidates selector fill + JS fallback + verification with deterministic return contract.

- Modified functions:
  - `pinterest_scraper.py::_search_keyword_on_pins_page(page, seed_keyword) -> None`
    - Change from “single brittle path + raise” to orchestrator calling `_attempt_keyword_targeting`, then `_navigate_direct_top_pins`, then explicit typed error.
  - `pinterest_scraper.py::_run_scrape_once(...) -> SeedScrapeResult`
    - Integrate fallback route ordering:
      1) open `/pins`
      2) apply search targeting
      3) if failed, try direct top-pins URL
      4) continue export-first parse flow
    - Capture which path succeeded for diagnostics artifact.
  - `pinterest_scraper.py::scrape_seed(...) -> SeedScrapeResult`
    - Preserve retry behavior but attach classified reason when final failure is raised.
  - `pinterest_engine.py::_collect_pinclicks_data_sync(...) -> PinClicksResults`
    - On scrape exception, parse/classify reason and append structured skipped item.
  - `bulk_ui.py::_render_stage_pinclicks(...)`
    - Render skipped items with `keyword`, `reason`, and shortened `error` string.

- Removed functions:
  - None.

[Classes]
No class hierarchy changes are required; existing dataclasses remain intact with payload-shape normalization at runtime.

- New classes:
  - None mandatory (maintain compatibility with existing `PinClicksResults.skipped: list[dict[str, Any]]`).

- Modified classes:
  - `engine_config.py::PinClicksResults`
    - No signature change; update inline docs/comments to reflect normalized skipped entry fields.

- Removed classes:
  - None.

[Dependencies]
No third-party dependency changes are expected.

All planned improvements use existing standard-library and Playwright tooling already present in the project (`re`, `json`, existing `playwright.sync_api` integration). `requirements.txt` should remain unchanged unless an explicit diagnostics utility is later requested.

[Testing]
Add focused unit tests around fallback behavior, failure classification, and user-visible skip outputs.

- `tests/test_pinterest_scraper.py`
  - Add tests for `_classify_scrape_error()` mappings.
  - Add tests to verify `_search_keyword_on_pins_page()` attempts selector path before direct URL fallback.
  - Add tests for `build_top_pins_url()` integration in fallback branch.

- `tests/test_pinterest_engine_phases.py`
  - Add/extend tests so failed scrape entries in `PinClicksResults.skipped` include `reason`, `attempts`, and `source_stage` fields.

- `tests/test_pinclicks_analysis.py`
  - Add scenario where only one scrape result is rankable and others are skipped upstream; ensure ranking still returns deterministic winners and writes expected artifacts.

- Validation strategy:
  - Run targeted test subset first:
    - `tests/test_pinterest_scraper.py`
    - `tests/test_pinterest_engine_phases.py`
    - `tests/test_pinclicks_analysis.py`
  - Then run broader engine tests if needed.

[Implementation Order]
Implement scraper resilience first, then propagate structured failure metadata upward, then update UI/tests for transparent diagnostics.

1. Add standardized scrape error classification + helper functions in `pinterest_scraper.py`.
2. Refactor keyword-entry flow to include direct top-pins URL fallback and verification checkpoints.
3. Update `scrape_seed()` and `pinterest_engine._collect_pinclicks_data_sync()` to preserve/classify failure context in structured skipped payloads.
4. Update `bulk_ui.py` skipped-keyword display to include reason codes and concise actionable messaging.
5. Add/adjust tests in scraper/engine/pinclicks-analysis suites for fallback behavior and structured skip output.
6. Execute targeted tests and confirm no regression in phase contracts/artifact outputs.
