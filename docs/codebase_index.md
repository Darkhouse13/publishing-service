# Codebase Index

## Project Overview

**automating-wf** is a Pinterest-to-WordPress content automation toolkit. It scrapes Pinterest Trends and PinClicks data, uses LLM analysis (DeepSeek) to identify high-signal keywords, generates SEO-optimized articles with AI images (Fal.ai), validates and repairs content quality, publishes to WordPress, and exports Pinterest bulk-upload CSVs. It supports three blog brands and offers both a Streamlit UI and a CLI interface.

---

## Current File Structure

```
Automating_WF/
├── .env.example                          # Environment variable template
├── .gitignore
├── README.md
├── pyproject.toml                        # Package metadata (Python >=3.11, pytest, CLI scripts)
│
├── src/automating_wf/                    # Application package (see below)
├── tests/                                # pytest suite
├── docs/                                 # Documentation
├── scripts/                              # Build utilities
├── assets/theme/                         # WordPress theme files
└── artifacts/                            # Runtime output (gitignored)
    ├── runtime/
    ├── exports/
    ├── reports/
    └── theme/
```

### src/automating_wf/ Package

```
src/automating_wf/
├── __init__.py                           # Empty
│
├── analysis/
│   ├── __init__.py                       # Empty
│   ├── pinterest.py                      # LLM keyword analysis → BrainOutput
│   ├── pinclicks.py                      # Rank PinClicks keywords by frequency/engagement/intent
│   └── trends.py                         # Parse & rank Pinterest Trends CSV exports
│
├── config/
│   ├── __init__.py                       # Empty
│   ├── blogs.py                          # Blog profiles, category keywords, vibe generation
│   └── paths.py                          # Artifact directory definitions
│
├── content/
│   ├── __init__.py                       # Empty
│   ├── generators.py                     # DeepSeek article generation + Fal.ai image generation
│   ├── validator.py                      # Article validation + LLM repair loop
│   └── single_article_flow.py            # Orchestrates generate → validate → image
│
├── design/
│   ├── __init__.py                       # Empty
│   └── pinterest.py                      # Pillow-based Pinterest pin image rendering (center_strip)
│
├── engine/
│   ├── __init__.py                       # Empty
│   ├── config.py                         # EngineRunOptions + phase result dataclasses
│   └── pipeline.py                       # Full bulk pipeline orchestration (CLI + sync functions)
│
├── export/
│   ├── __init__.py                       # Empty
│   └── pinterest_csv.py                  # Build & append Pinterest bulk-upload CSV rows
│
├── models/
│   ├── __init__.py                       # Empty
│   └── pinterest.py                      # All dataclasses (PinRecord, BrainOutput, CsvRow, etc.)
│
├── prompts/
│   ├── __init__.py                       # Empty
│   ├── pinterest_analysis.md             # System prompt for Pinterest SEO analysis
│   └── article_validator_repair.md       # System prompt for article repair critic
│
├── scrapers/
│   ├── __init__.py                       # Empty
│   ├── pinclicks.py                      # Playwright scraper for PinClicks top-pins
│   ├── trends.py                         # Playwright scraper for Pinterest Trends CSV export
│   ├── subprocess_runner.py              # Subprocess wrapper (avoids Streamlit event-loop conflict)
│   └── file_parser.py                    # Smart CSV/XLS parser with header auto-detection
│
├── ui/
│   ├── __init__.py                       # Empty
│   ├── streamlit_app.py                  # Main Streamlit app (tabs: Single Article + Bulk Pipeline)
│   └── bulk_pipeline.py                  # 4-stage bulk wizard UI
│
└── wordpress/
    ├── __init__.py                       # Empty
    ├── uploader.py                       # WP REST API: publish posts, upload media, manage categories
    └── onboarding.py                     # WP site setup: categories, theme, plugins, SEO config
```

### Other Directories

```
tests/
├── test_article_validator.py             # Validator repair loop, patch parsing, debug artifacts
├── test_bulk_pipeline_resume.py          # Bulk pipeline resume stage detection
├── test_category_assignment.py           # Category suggestion scoring logic
├── test_engine_config.py                 # EngineRunOptions construction from env/UI
├── test_generators_parser.py             # Article response JSON parsing
├── test_generators_seo.py               # Hard validations, soft fixes, retry logic, keyword derivation
├── test_pinclicks_analysis.py            # PinClicks keyword ranking
├── test_pinterest_analysis.py            # Keyword scoring, tiebreak, field truncation
├── test_pinterest_design.py              # Font resolution, center-strip rendering, fallback policies
├── test_pinterest_engine.py              # Caching, winner processing, CSV operations
├── test_pinterest_engine_phases.py       # Phase orchestration, subprocess integration, CSV recovery
├── test_pinterest_exporter.py            # CSV export, board mapping, row formatting
├── test_pinterest_scraper.py             # PinClicks scraper error classification, retry logic
├── test_pinterest_trends_analysis.py     # Trends CSV parsing and ranking
├── test_pinterest_trends_scraper.py      # Trends scraper integration
├── test_scraper_subprocess.py            # Subprocess runner JSON-RPC interface
├── test_single_article_flow.py           # Draft flow success/error/fallback paths
├── test_uploader_flow.py                 # WordPress upload, media handling, cross-blog links
├── test_vibe_sampling.py                 # Vibe bank generation and sampling
└── test_wp_onboarding.py                 # WordPress onboarding actions

docs/
├── implementation_plan.md                # PinClicks resilience improvements plan
├── pinterest_engine.md                   # Engine configuration & workflow reference
├── rank_math_rest_meta_snippet.php       # PHP snippet for Rank Math REST API meta fields
└── seo_env_config.md                     # Cross-blog linking & external sources config

scripts/
├── __init__.py                           # Package marker
└── build_theme_zip.py                    # Validates PHP files → creates theme ZIP

assets/theme/the-sunday-patio/
├── style.css                             # Theme metadata + fallback CSS (Tailwind, Playfair Display, Inter)
├── functions.php                         # Theme setup, menus, widgets, Tailwind CDN, Google Fonts
├── header.php                            # HTML head + navigation bar
├── footer.php                            # Footer with brand info + navigation grid
├── index.php                             # Homepage: hero section + 3-column card grid
├── archive.php                           # Category/tag archive listing
├── single.php                            # Single post detail page
├── page.php                              # Static page template
└── sidebar.php                           # Widget area with search + categories fallback
```

---

## Core Routes / Flows

### Route 1 — Single Article Flow (Streamlit UI)

**Entry:** `streamlit run src/automating_wf/ui/streamlit_app.py` → "Single Article" tab

**Steps:**
1. **Blog Selection** — User picks a blog from sidebar (`config/blogs.py` → `BLOG_CONFIGS`)
2. **Vibe Suggestions** — LLM generates topic ideas (`content/generators.py` → `generate_vibe_bank()`)
3. **Topic Input** — User types or selects a topic
4. **Category Fetch** — WordPress categories loaded via REST API (`wordpress/uploader.py` → `list_categories()`)
5. **Category Suggestion** — Auto-suggests best category (`config/blogs.py` → `suggest_primary_category()`)
6. **Generate Draft** — Orchestrated by `content/single_article_flow.py` → `generate_single_article_draft()`:
   - a. `content/generators.py` → `generate_article()` — DeepSeek LLM generates SEO article (up to 5 attempts, temperature 0.6→0.2)
   - b. `content/generators.py` → `run_hard_validations()` — Word count >=600, keyword count 5-9, first paragraph + H2 inclusion, numbered SEO title
   - c. `content/generators.py` → `run_soft_fixes()` — Truncate fields, inject keyword, split long paragraphs
   - d. `content/validator.py` → `validate_article_with_repair()` — LLM repair loop (up to 2 attempts) using JSON patch operations
   - e. `content/generators.py` → `generate_image()` x2 — Fal.ai generates hero + detail images
7. **Preview** — Article markdown + images displayed in Streamlit
8. **Publish** — `wordpress/uploader.py` → `publish_post()` — Uploads media, creates WP post via REST API

```
User (Streamlit)
  │
  ├─ Sidebar: Blog selection, vibe refresh, category fetch
  │    ├── config/blogs.py        (blog profiles, category keywords)
  │    ├── content/generators.py  (generate_vibe_bank)
  │    └── wordpress/uploader.py  (list_categories)
  │
  ├─ "Generate Draft" button
  │    └── content/single_article_flow.py
  │         ├── content/generators.py    (generate_article + generate_image x2)
  │         └── content/validator.py     (validate_article_with_repair)
  │              └── prompts/article_validator_repair.md
  │
  └─ "Publish to WordPress" button
       └── wordpress/uploader.py  (resolve_category_id + publish_post)
```

---

### Route 2 — Bulk Pipeline Flow (Streamlit UI, 4 stages)

**Entry:** `streamlit run src/automating_wf/ui/streamlit_app.py` → "Bulk Pipeline" tab → `ui/bulk_pipeline.py`

**Stage 1 — Configuration** (`_render_stage_config`)
- User selects blog, enters seed keywords, sets filters (region, range, top_n)
- Configures PinClicks max records, target article count, publish status
- Optional: resume from previous run ID
- Validates board mapping (`export/pinterest_csv.py` → `validate_board_mapping_for_blog()`)
- Builds `EngineRunOptions` from form data (`engine/config.py` → `EngineRunOptions.from_ui()`)

**Stage 2 — Trends Collection** (`_render_stage_trends`)
- Calls `engine/pipeline.py` → `collect_trends_candidates_sync()`
  - Launches subprocess → `scrapers/subprocess_runner.py` → `scrapers/trends.py` → Playwright browser scrapes Pinterest Trends
  - Downloads CSV exports per seed keyword
  - `scrapers/file_parser.py` parses CSV with header auto-detection
  - `analysis/trends.py` → `analyze_trends_exports()` ranks by trend_index (50%), growth (30%), consistency (20%)
- Returns `TrendCandidates` with ranked keywords
- User selects/deselects keywords via checkboxes

**Stage 3 — PinClicks Analysis** (`_render_stage_pinclicks`)
- Calls `engine/pipeline.py` → `collect_pinclicks_data_sync()`
  - For each selected keyword: subprocess → `scrapers/pinclicks.py` → Playwright scrapes PinClicks top-pins
  - `analysis/pinclicks.py` → `rank_pinclicks_keywords()` scores by frequency (50%), engagement (35%), intent (15%)
- Returns `PinClicksResults` with winners + skipped keywords (with skip reasons)
- User reviews winner table and selects article count

**Stage 4 — Generation + Publishing** (`_render_stage_generation`)
- Calls `engine/pipeline.py` → `run_winner_generation_sync()` for each winner:
  - a. `analysis/pinterest.py` → `analyze_seed()` — LLM analysis producing `BrainOutput` (primary keyword, image prompt, pin text, etc.)
  - b. `content/generators.py` → `generate_article()` — Article generation with SEO validation
  - c. `content/validator.py` → `validate_article_with_repair()` — Quality repair loop
  - d. `design/pinterest.py` → `generate_pinterest_image()` — Pillow renders 1000x1500 pin with center-strip overlay
  - e. `content/generators.py` → `generate_image()` — Fal.ai hero image
  - f. `wordpress/uploader.py` → `publish_post()` — Publish to WordPress
  - g. `export/pinterest_csv.py` → `append_csv_row()` — Append to Pinterest bulk-upload CSV
- Progress callback updates UI in real-time
- Results classified as: completed / partial (WP ok, CSV failed) / failed_pre_publish
- CSV download + retry CSV replay available

```
Stage 1: Config
  └── engine/config.py (EngineRunOptions)
       │
Stage 2: Trends ──────────────────────────────────────────────────
  └── engine/pipeline.py → collect_trends_candidates_sync()
       ├── scrapers/subprocess_runner.py (subprocess isolation)
       ├── scrapers/trends.py (Playwright browser)
       ├── scrapers/file_parser.py (CSV parsing)
       └── analysis/trends.py (rank candidates)
            │
Stage 3: PinClicks ───────────────────────────────────────────────
  └── engine/pipeline.py → collect_pinclicks_data_sync()
       ├── scrapers/subprocess_runner.py (subprocess isolation)
       ├── scrapers/pinclicks.py (Playwright browser)
       └── analysis/pinclicks.py (rank keywords)
            │
Stage 4: Generation + Publish ────────────────────────────────────
  └── engine/pipeline.py → run_winner_generation_sync()
       ├── analysis/pinterest.py (LLM keyword analysis → BrainOutput)
       ├── content/generators.py (article + image generation)
       ├── content/validator.py (validation + repair)
       ├── design/pinterest.py (pin image rendering)
       ├── wordpress/uploader.py (publish to WP)
       └── export/pinterest_csv.py (CSV append)
```

---

### Route 3 — CLI Pinterest Engine (headless)

**Entry:** `python -m automating_wf.engine.pipeline --blog THE_SUNDAY_PATIO [seeds...]`

Same three phases as the bulk pipeline but driven by CLI arguments:

```
engine/pipeline.py → main()
  ├── argparse: --blog, --resume, positional seed keywords
  ├── EngineRunOptions.from_env(blog_suffix)
  │
  ├── Phase 1: collect_trends_candidates_sync(opts)
  │    (same as Bulk Stage 2)
  │
  ├── Phase 2: collect_pinclicks_data_sync(opts, selected_keywords, run_id)
  │    (same as Bulk Stage 3)
  │
  └── Phase 3: run_winner_generation_sync(opts, winners, run_id)
       (same as Bulk Stage 4)
```

**Artifacts:** Written to `tmp/pinterest_engine/<run_id>/`:
- `trends_analysis/` — Raw records, top keywords JSON
- `pinclicks_analysis/` — Keyword scores, winner selections
- `manifest.jsonl` — Per-keyword status tracking (enables resume)
- `run_summary.json` — Final summary with CSV path

**Resume:** `python -m automating_wf.engine.pipeline --blog THE_SUNDAY_PATIO --resume 20260224_143000`

---

### Route 4 — WordPress Onboarding

**Entry:** `python -m automating_wf.wordpress.onboarding --help`

```
wordpress/onboarding.py
  └── OnboardingConfig.from_env()
       ├── Category creation (from blog profile)
       ├── Page creation (About, Contact, Privacy Policy)
       ├── Theme activation
       ├── Plugin management
       ├── SEO plugin setup (Rank Math)
       ├── Comment status configuration
       └── Timezone setup
```

Uses WordPress REST API via internal `_WPClient` helper.

---

### Route 5 — Theme Build

**Entry:** `python scripts/build_theme_zip.py`

```
scripts/build_theme_zip.py → main()
  ├── Validates required files exist:
  │    style.css, functions.php, header.php, footer.php,
  │    sidebar.php, index.php, archive.php, single.php, page.php
  │
  └── Creates ZIP: artifacts/theme/the-sunday-patio.zip
```

---

## Data Models

All defined in `src/automating_wf/models/pinterest.py`:

| Model | Purpose | Produced By | Consumed By |
|-------|---------|-------------|-------------|
| `PinRecord` | Single scraped pin (title, desc, tags, engagement) | scrapers/pinclicks | analysis/pinterest |
| `SeedScrapeResult` | Collection of PinRecords for one seed keyword | scrapers/pinclicks | analysis/pinterest |
| `TrendExportRecord` | One row from Trends CSV (keyword, trend_index, growth) | analysis/trends | analysis/trends (ranking) |
| `TrendKeywordCandidate` | Ranked trend keyword with hybrid score | analysis/trends | engine/pipeline (Phase 1→2) |
| `PinClicksExportRecord` | Pin data from PinClicks export | scrapers/pinclicks | analysis/pinclicks |
| `PinClicksKeywordScore` | Ranked keyword with freq/engagement/intent scores | analysis/pinclicks | engine/pipeline (Phase 2→3) |
| `KeywordCandidate` | Intermediate keyword candidate with frequency/weight | analysis/pinterest | analysis/pinterest (internal) |
| `BrainOutput` | LLM analysis output (primary keyword, image prompt, pin text, cluster) | analysis/pinterest | engine/pipeline (Phase 3) |
| `CsvRow` | One row for Pinterest bulk-upload CSV | export/pinterest_csv | CSV file output |
| `RunManifestEntry` | Per-keyword status tracking for pipeline runs | engine/pipeline | engine/pipeline (resume) |

**Phase result models** in `engine/config.py`:

| Model | Purpose |
|-------|---------|
| `EngineRunOptions` | Runtime config for all phases (blog, seeds, filters, limits) |
| `TrendCandidates` | Phase 1 output (run_id, ranked keywords, raw count) |
| `PinClicksResults` | Phase 2 output (winners + skipped with reasons) |
| `GenerationResults` | Phase 3 output (completed/partial/failed lists, CSV path) |

---

## Configuration Layer

### Environment Variables (.env)

| Group | Variables | Purpose |
|-------|-----------|---------|
| **API Keys** | `DEEPSEEK_API_KEY`, `FAL_KEY` | LLM + image generation credentials |
| **WordPress** | `WP_URL_<SUFFIX>`, `WP_USER_<SUFFIX>`, `WP_KEY_<SUFFIX>` | Per-blog WP REST API credentials |
| **DeepSeek** | `DEEPSEEK_MODEL`, `DEEPSEEK_ARTICLE_ATTEMPTS` | LLM model selection + retry count |
| **Fal.ai** | `FAL_MODEL`, `FAL_PIN_MODEL` | Image generation model selection |
| **WP Publishing** | `WP_POST_STATUS`, `WP_TIMEZONE`, `WP_SEO_PLUGIN` | Post defaults + SEO plugin |
| **PinClicks** | `PINCLICKS_USERNAME`, `PINCLICKS_PASSWORD`, `PINCLICKS_STORAGE_STATE_PATH` | Scraper auth |
| **Trends** | `PINTEREST_TRENDS_FILTER_REGION`, `PINTEREST_TRENDS_FILTER_RANGE` | Scraper filters |
| **Analysis** | `PINTEREST_ANALYSIS_PROVIDER`, `PINTEREST_ANALYSIS_MODEL` | LLM provider for analysis |
| **Pin Design** | `PINTEREST_PIN_TEMPLATE_MODE`, `PINTEREST_PIN_TEMPLATE_FAILURE_POLICY` | Pin image template config |
| **CSV Export** | `PINTEREST_CSV_PATH_TEMPLATE`, `PINTEREST_CSV_CADENCE_MINUTES` | Export path + scheduling |
| **SEO** | `CROSS_BLOG_LINK_MAP_JSON`, `SEO_EXTERNAL_SOURCES_JSON` | Cross-blog linking + authority sources |
| **Seeds** | `PINTEREST_SEED_MAP_JSON`, `PINTEREST_BOARD_MAP_JSON` | Per-blog seed keywords + board mapping |

### Blog Profiles (config/blogs.py)

Three blogs configured:

| Blog | Suffix | Niche | Fallback Category |
|------|--------|-------|-------------------|
| The Weekend Folio | `THE_WEEKEND_FOLIO` | Lifestyle/weekend planning | Weekend Living |
| Your Midnight Desk | `YOUR_MIDNIGHT_DESK` | Productivity/desk setup | Desk Setup |
| The Sunday Patio | `THE_SUNDAY_PATIO` | Outdoor living/gardening | Outdoor Living |

Each has: `profile_prompt`, `wp_env_suffix`, `fallback_category`, `deprioritized_category`, `category_keywords`.

### Artifact Paths (config/paths.py)

| Path | Default | Env Override |
|------|---------|--------------|
| `ARTIFACTS_ROOT` | `artifacts/` | `AUTOMATING_WF_ARTIFACTS_ROOT` |
| `RUNTIME_ROOT` | `artifacts/runtime/` | `AUTOMATING_WF_RUNTIME_ROOT` |
| `EXPORTS_ROOT` | `artifacts/exports/` | `AUTOMATING_WF_EXPORTS_ROOT` |
| `REPORTS_ROOT` | `artifacts/reports/` | `AUTOMATING_WF_REPORTS_ROOT` |
| `THEME_ARTIFACTS_ROOT` | `artifacts/theme/` | `AUTOMATING_WF_THEME_ARTIFACTS_ROOT` |

---

## External Dependencies

| Dependency | Purpose | Used In |
|------------|---------|---------|
| **DeepSeek / OpenAI** | LLM for keyword analysis, article generation, article repair | analysis/pinterest, content/generators, content/validator |
| **Fal.ai** | Image generation (Flux/dev model) | content/generators |
| **Playwright** | Browser automation for PinClicks + Pinterest Trends scraping | scrapers/pinclicks, scrapers/trends |
| **WordPress REST API** | Publishing posts, uploading media, managing categories | wordpress/uploader, wordpress/onboarding |
| **Pillow (PIL)** | Pinterest pin image rendering with text overlays | design/pinterest |
| **Streamlit** | Web UI framework | ui/streamlit_app, ui/bulk_pipeline |

---

## Structural Issues

1. **No `__init__.py` exports** — All subpackages under `src/automating_wf/` have no `__init__.py` files (or empty ones). Every import uses full module paths.

2. **Test/doc duplication** — `docs/implementation_plan.md` describes work that appears already implemented in the codebase.

3. **Flat test directory** — All tests in a single `tests/` directory with no subdirectory mirroring the package structure.

4. **Single theme only** — `assets/theme/` and `scripts/build_theme_zip.py` are hardcoded to "the-sunday-patio". No support for other blog themes.

5. **No dependency lockfile** — `pyproject.toml` lists no pinned dependencies. No `requirements.txt` or lock file.
