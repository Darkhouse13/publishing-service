# User Testing — Frontend Dashboard

## Validation Surface

The user testing validator verifies Mission 3's frontend dashboard by opening pages in a browser (agent-browser) and visually confirming design tokens and functionality.

## Tool: agent-browser

Used for all user-facing verification. The validator opens `http://localhost:3000` pages in a headless browser and inspects rendered HTML/CSS.

## Pages to Test

All 11 pages must render and navigate correctly:
- `/dashboard` — stat cards, recent activity, sidebar nav
- `/connections` — blog card grid, toggle, add button
- `/connections/new` — add blog form
- `/connections/[id]` — 5 tabs, save functionality
- `/credentials` — table with masked secrets, status badges
- `/runs` — filter bar, runs table, blinking dots
- `/runs/new` — create run form
- `/runs/[id]` — progress ring, article cards with step bars
- `/articles` — articles table
- `/articles/new` — single article form
- `/articles/[id]` — two-column layout, SEO sidebar panels

## Design Token Verification

Every page must pass these checks:
- **Zero border-radius**: DevTools inspection shows `border-radius: 0px` on all elements
- **Colors**: base=#000000, panel=#f2f1eb, accent=#ffcc00, muted=#666666, error=#ff4444
- **Borders**: 3px solid black on cards, inputs, buttons
- **Shadows**: solid offset shadows (4px, 8px, 12px)
- **Typography**: headings font-weight 900, body font-weight 700, ALL labels uppercase
- **Active nav**: yellow (#ffcc00) background on current page nav item

## Functional Verification

### Navigation
- Sidebar nav highlights active item
- Pages navigate correctly via sidebar links
- Back buttons and breadcrumbs work

### Forms
- Required field validation blocks empty submission
- Error messages appear inline (not toasts) in error color
- Submit fires correct API path (visible in network tab)

### Polling
- Active runs pages auto-refresh every 3-5 seconds
- Progress ring and step bars update without page reload
- Polling stops when run reaches terminal state

### Empty States
- No data pages show appropriate "NO X" messages in muted color

## Resource Cost Classification

- Each agent-browser instance: ~300 MB RAM
- Frontend dev server: ~200 MB RAM
- Max concurrent validators: **3** (on this machine with ~6GB available headroom after baseline)
- Validation parallelization: validate 3 pages concurrently, sequential across milestones

## Mock Data

Pages render with SWR fallback data. Mock data in `src/lib/mock-data.ts` provides realistic fixtures. No backend needed for visual validation — API paths visible in network tab even if they 404.

## Skipping External APIs

The validation does NOT test external APIs (DeepSeek, Fal.ai). Only frontend UI and API integration paths are verified. External API behavior is out of scope for this mission.
