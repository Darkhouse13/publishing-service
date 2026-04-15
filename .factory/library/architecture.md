# Architecture — Frontend Dashboard

## Overview
A Next.js 14+ App Router frontend dashboard that consumes the existing FastAPI backend API. The design is neo-brutalist: thick black borders, solid offset shadows, yellow accent, uppercase typography, zero border-radius.

## Tech Stack
- **Next.js 14** with App Router (server components by default, client where needed)
- **TypeScript** strict mode — no `any` except unavoidable API parsing
- **Tailwind CSS** — custom design tokens, no component libraries
- **SWR** — data fetching with fallback/mock support, refreshInterval for polling

## Directory Structure
```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx          # Root layout (Sidebar + children)
│   │   ├── page.tsx            # Redirects to /dashboard
│   │   ├── globals.css         # Grid pattern, scrollbar, animations
│   │   ├── dashboard/page.tsx
│   │   ├── connections/page.tsx
│   │   ├── connections/new/page.tsx
│   │   ├── connections/[id]/page.tsx
│   │   ├── credentials/page.tsx
│   │   ├── runs/page.tsx
│   │   ├── runs/new/page.tsx
│   │   ├── runs/[id]/page.tsx
│   │   ├── articles/page.tsx
│   │   ├── articles/new/page.tsx
│   │   └── articles/[id]/page.tsx
│   ├── components/
│   │   ├── layout/             # Sidebar, PageHeader, SectionHeading
│   │   ├── ui/                 # Button, Card, Badge, Input, Select, Textarea, Table, Toggle, ProgressBar, ProgressRing, StatCard, TabBar, LiveDot
│   │   ├── dashboard/          # ActivityItem
│   │   ├── connections/        # BlogCard, BlogSettingsForm
│   │   ├── credentials/         # CredentialRow
│   │   ├── runs/               # RunRow, ArticleCard
│   │   └── articles/           # ArticlePreview, SEOSidebar, PinPreview
│   ├── lib/
│   │   ├── api.ts              # Fetch wrapper, API client
│   │   ├── types.ts            # TypeScript interfaces
│   │   ├── utils.ts            # Formatting helpers
│   │   └── mock-data.ts        # Realistic fixtures
│   └── hooks/
│       ├── useBlogs.ts
│       ├── useCredentials.ts
│       ├── useRuns.ts
│       ├── useArticles.ts
│       └── usePolling.ts
```

## Design System
### Colors
- `base`: #000000 (borders, primary text, dark buttons)
- `panel`: #f2f1eb (page background, input backgrounds)
- `accent`: #ffcc00 (active nav, highlights, primary CTAs)
- `muted`: #666666 (secondary text, timestamps)
- `error`: #ff4444 (failure states, error badges)
- `white`: #ffffff (card backgrounds)

### Typography
- Font: Helvetica Neue, Helvetica, Arial, sans-serif
- Headings: font-weight 900 (font-black), uppercase, tracking-tighter
- Body: font-weight 700 (font-bold)
- Labels: uppercase, tracking-widest

### Borders & Shadows
- Standard border: `border-[3px] border-base`
- Thin border: `border-[2px] border-base`
- Shadows: `shadow-solid-sm` (4px), `shadow-solid-md` (8px), `shadow-solid-lg` (12px)
- Border-radius: ZERO everywhere

### Interactive States
- Card hover: `hover:-translate-y-1 hover:shadow-solid-lg`
- Button hover: `hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]`
- Button active: `active:translate-x-[4px] active:translate-y-[4px] active:shadow-none`
- Active nav: `bg-accent` (yellow background)

## API Integration
- Next.js rewrites: `/api/:path*` → `${NEXT_PUBLIC_API_URL}/api/:path*`
- API client calls `/api/v1/...` (proxied, no CORS)
- SWR `fallback` for mock data
- Polling via SWR `refreshInterval: 3000`

## Data Flow
1. Page component renders with SWR `fallback` (mock data)
2. User sees populated UI immediately
3. SWR revalidates in background, updates UI if real data differs
4. Form submissions call API directly
5. Polling for active runs uses SWR with conditional `refreshInterval`

## Docker Full-Stack Deployment

### Architecture
```
Browser → nginx:80 → frontend:3000 (Next.js standalone)
                  → api:8000 (FastAPI)
                         → db:5432 (PostgreSQL)
                         → redis:6379 (Redis)
              worker (Celery) → redis → api
```

### Services
- **nginx:alpine** — Reverse proxy on port 80. Routes `/api/*` → `api:8000`, everything else → `frontend:3000`.
- **frontend** — Next.js standalone build. Receives requests via nginx; API calls proxied through Next.js rewrites or direct to nginx `/api/*`.
- **api** — FastAPI with Alembic migrations run on startup via `entrypoint.sh`. Serves `/api/v1/*`.
- **worker** — Celery worker consuming from Redis. No migration entrypoint (depends on api having started).
- **db** — PostgreSQL 16-alpine with healthcheck.
- **redis** — Redis 7-alpine with healthcheck.

### CORS
FastAPI CORSMiddleware configured with `CORS_ORIGINS` from environment. In Docker, defaults to `["http://localhost", "http://frontend:3000", "http://nginx"]`.

### Environment Variables (Production)
- `DATABASE_URL=postgresql+asyncpg://publishing:{password}@db:5432/publishing`
- `REDIS_URL=redis://redis:6379/0`
- `ENCRYPTION_KEY` — Fernet key for credential encryption
- `CORS_ORIGINS` — JSON array of allowed origins
- `POSTGRES_USER`, `POSTGRES_PASSWORD` — DB credentials

## State Management
- SWR for server state (blogs, runs, articles, credentials)
- React `useState` for local UI state (tab selection, form fields)
- No global state management library needed
