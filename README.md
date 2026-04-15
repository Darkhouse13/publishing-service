# Automating WF

Pinterest-to-WordPress content automation toolkit. Scrapes Pinterest Trends and PinClicks data, uses LLM analysis (DeepSeek) to identify high-signal keywords, generates SEO-optimized articles with AI images (Fal.ai), validates and repairs content quality, publishes to WordPress, and exports Pinterest bulk-upload CSVs.

Supports three blog brands and offers both a Streamlit UI and a CLI interface.

## Requirements

- Python >= 3.11
- [Playwright](https://playwright.dev/python/) browsers (for scraping)
- API keys: DeepSeek, Fal.ai, WordPress REST API credentials

## Installation

```bash
pip install -e .
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your credentials.

## Quick Start

```bash
# Launch the Streamlit web app (main interface)
streamlit run src/automating_wf/ui/streamlit_app.py

# Or if streamlit isn't on PATH:
python -m streamlit run src/automating_wf/ui/streamlit_app.py
```

The app has two tabs:
- **Single Article** — generate an individual SEO blog draft and publish to WordPress
- **Bulk Pipeline** — run the full Trends → PinClicks → Generation → Publish workflow

## CLI Commands

```bash
# Pinterest bulk pipeline (headless)
pinterest-engine --blog THE_SUNDAY_PATIO [seed keywords...]

# Resume a previous run
pinterest-engine --blog THE_SUNDAY_PATIO --resume 20260224_143000

# WordPress site onboarding (categories, pages, theme, plugins)
wp-onboarding --help

# Build WordPress theme ZIP
python scripts/build_theme_zip.py

# Run tests
python -m pytest -q
```

## Repository Structure

```
Automating_WF/
├── src/automating_wf/          # Application package
│   ├── analysis/               # LLM keyword analysis, PinClicks ranking, Trends ranking
│   ├── config/                 # Blog profiles, category keywords, artifact paths
│   ├── content/                # Article generation, validation/repair, single-article flow
│   ├── design/                 # Pillow-based Pinterest pin image rendering
│   ├── engine/                 # Pipeline orchestration (config + 3-phase pipeline)
│   ├── export/                 # Pinterest bulk-upload CSV builder
│   ├── models/                 # Dataclasses (PinRecord, BrainOutput, CsvRow, etc.)
│   ├── prompts/                # LLM system prompts (analysis + validator)
│   ├── scrapers/               # Playwright scrapers (PinClicks, Trends, subprocess runner)
│   ├── ui/                     # Streamlit app + bulk pipeline wizard
│   └── wordpress/              # WP REST API uploader + onboarding
├── tests/                      # pytest suite
├── docs/                       # Documentation and reference
├── scripts/                    # Build utilities (theme ZIP builder)
├── assets/theme/               # WordPress theme source files
└── artifacts/                  # Runtime output (gitignored)
```

## Pipeline Flow

### Bulk Pipeline (4 stages)

1. **Configuration** — Select blog, enter seed keywords, set filters (region, range, top-N), target article count
2. **Trends Collection** — Playwright scrapes Pinterest Trends → CSV parsing → hybrid ranking (trend index 50%, growth 30%, consistency 20%)
3. **PinClicks Analysis** - real Brave with the persistent `PinFlow` profile scrapes PinClicks top-pins per keyword and scores by frequency (50%), engagement (35%), intent (15%)
   - First run requires a one-time manual PinClicks login in the `PinFlow` Brave profile
   - Normal automated runs reuse that session and launch Brave off-screen instead of using headless mode
4. **Generation + Publishing** — For each winner keyword:
   - LLM analysis → `BrainOutput` (primary keyword, image prompt, pin text)
   - DeepSeek article generation with SEO validation
   - LLM repair loop for content quality
   - Pillow renders 1000×1500 Pinterest pin image
   - Fal.ai generates hero image
   - Publishes to WordPress via REST API
   - Appends row to per-run Pinterest bulk-upload CSV

### Single Article Flow

Blog selection → vibe suggestions → topic input → category suggestion → article generation with validation → image generation → preview → publish to WordPress.

## Supported Blogs

| Blog | Env Suffix | Niche |
|------|-----------|-------|
| The Weekend Folio | `THE_WEEKEND_FOLIO` | Lifestyle / weekend planning |
| Your Midnight Desk | `YOUR_MIDNIGHT_DESK` | Editorial recipes / food |
| The Sunday Patio | `THE_SUNDAY_PATIO` | Outdoor living / gardening |

## Environment Variables

See `.env.example` for the full list. Key groups:

| Group | Examples |
|-------|---------|
| API Keys | `DEEPSEEK_API_KEY`, `FAL_KEY` |
| WordPress | `WP_URL_<SUFFIX>`, `WP_USER_<SUFFIX>`, `WP_KEY_<SUFFIX>` |
| PinClicks Auth | `PINCLICKS_USERNAME`, `PINCLICKS_PASSWORD` |
| Trends Filters | `PINTEREST_TRENDS_FILTER_REGION`, `PINTEREST_TRENDS_FILTER_RANGE` |
| Pin Design | `PINTEREST_PIN_TEMPLATE_MODE`, `PINTEREST_FONT_MAP_JSON` |
| CSV Export | `PINTEREST_CSV_CADENCE_MINUTES` |
| Publishing | `WP_POST_STATUS`, `WP_TIMEZONE`, `WP_SEO_PLUGIN` |

## Output Paths

- Per-run Pinterest CSV: `tmp/pinterest_engine/<run_id>/pinterest_bulk_upload_<blog_suffix>.csv`
- Theme ZIP: `artifacts/theme/yourmidnightdesk.zip`
- Run artifacts: `tmp/pinterest_engine/<run_id>/` (manifest, trends, pinclicks, images)

Artifact base paths can be overridden via environment variables (see `src/automating_wf/config/paths.py`).

## Frontend Dashboard (Next.js 14)

A neo-brutalist web dashboard for monitoring and managing the publishing pipeline.

### Tech Stack

- **Framework:** Next.js 14 (App Router, TypeScript strict mode)
- **Styling:** Tailwind CSS 3 with custom design tokens
- **Data Fetching:** SWR with inline mock data fallback for development
- **Design:** Neo-brutalist (3px black borders, zero border-radius, yellow accent #ffcc00, uppercase typography, grid-pattern backgrounds)

### Frontend Setup

```bash
cd frontend
npm install
npm run dev    # Development server on http://localhost:3000
npm run build  # Production build
npm run lint  # ESLint check
```

### Dashboard Pages

| Route | Description |
|-------|-------------|
| `/dashboard` | Overview: 3 stat cards (blogs, articles this week, active runs) + recent activity |
| `/connections` | Blog connections grid with toggle switches |
| `/connections/new` | Add new blog connection form |
| `/connections/[id]` | Blog settings with 5 tabs (Connection, AI Personality, Categories, Pinterest, Pipeline) |
| `/credentials` | API key management table with masked secrets |
| `/runs` | Generation runs table with status filtering and live polling |
| `/runs/new` | Start a new generation run |
| `/runs/[id]` | Run detail with progress ring and article cards |
| `/articles` | All articles table |
| `/articles/new` | Create article with vibe selection and live progress |
| `/articles/[id]` | Article detail with SEO sidebar and Pinterest preview |

### Design Tokens

```js
// tailwind.config.ts
colors: {
  panel:    '#f2f1eb',   // page background
  white:    '#ffffff',   // card/panel backgrounds
  black:    '#000000',   // borders, text
  accent:   '#ffcc00',   // highlights, active states
  error:    '#ff4444',   // error states
  muted:    '#888888',   // secondary text
}
borderWidth: { DEFAULT: '1px', '2': '2px', '3': '3px' }
borderRadius: { NONE: '0' }  // zero border-radius everywhere
shadow: {
  solid:      '3px 3px 0px #000000',
  'solid-lg': '5px 5px 0px #000000',
  'accent':   '3px 3px 0px #ffcc00',
}
```

### API Proxy

The frontend proxies API requests through Next.js rewrites to avoid CORS:

```js
// next.config.js rewrites
'/api/:path*' → 'http://localhost:8000/api/:path*'
```

For development without the backend running, all SWR hooks include `fallbackData` with realistic mock data.

## Docker Full-Stack Deployment

A complete `docker compose up` starts the entire stack behind an nginx reverse proxy.

### Services

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| nginx | nginx:alpine | 80 | Reverse proxy routing /api/* → api:8000, /* → frontend:3000 |
| frontend | Next.js standalone | 3000 (internal) | Next.js 14 dashboard |
| api | FastAPI + Alembic | 8000 (internal) | Backend REST API |
| worker | Celery + Redis | — | Background job processor |
| db | postgres:16-alpine | 5432 | PostgreSQL database |
| redis | redis:7-alpine | 6379 | Redis message broker |

### Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and ENCRYPTION_KEY

# 2. Build and start all services
docker compose build
docker compose up -d

# 3. Verify the stack
bash scripts/smoke-test.sh http://localhost
```

### Environment Variables

```bash
POSTGRES_USER=publishing
POSTGRES_PASSWORD=CHANGE_ME_TO_A_STRONG_PASSWORD
ENCRYPTION_KEY=CHANGE_ME_GENERATE_A_FERNET_KEY
PORT=80
```

Generate an ENCRYPTION_KEY:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Development (with hot reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

This overlay exposes ports 80, 3000, 8000, 5432, 6379 and mounts source volumes for hot reload.

### CORS

FastAPI CORS middleware is configured via `CORS_ORIGINS`. In Docker, defaults to:
```
["http://localhost", "http://frontend:3000", "http://nginx"]
```

Override via the `CORS_ORIGINS` environment variable.

## Troubleshooting

### Streamlit shutdown traceback on Windows

Symptom: You stop Streamlit and see `Stopping...`, then a traceback ending with `RuntimeError: Event loop is closed`.

This is a benign shutdown-time warning if your expected artifacts were generated. Press `Ctrl+C` once, then wait for shutdown. Do not press `Ctrl+C` repeatedly.

If the terminal appears stuck, end the process from Task Manager or `taskkill /PID <streamlit_pid> /F`.
