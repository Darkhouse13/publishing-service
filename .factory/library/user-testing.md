# User Testing — Publishing Service

## Validation Surface

The user testing validator verifies the Docker full-stack integration and frontend-backend wiring.

## Tool: agent-browser + curl

- `curl` for API smoke tests (health, blogs, articles, credentials, runs)
- `agent-browser` for frontend page rendering verification in Docker context

## Smoke Test Flows

After `docker compose up -d`:
1. Health: `curl http://localhost/api/v1/health` → 200
2. Frontend: `curl http://localhost/dashboard` → 200
3. Blogs list: `curl http://localhost/api/v1/blogs` → 200
4. Create blog: `curl -X POST http://localhost/api/v1/blogs` with blog data → 201
5. Credentials: `curl http://localhost/api/v1/credentials` → 200
6. Runs: `curl http://localhost/api/v1/runs` → 200
7. Articles: `curl http://localhost/api/v1/articles` → 200
8. Cleanup: `curl -X DELETE http://localhost/api/v1/blogs/{id}` → 204

## Docker Stack Verification

- All 6 services must report healthy via `docker compose ps`
- nginx must route `/api/*` to api:8000
- nginx must route `/*` to frontend:3000
- Frontend at `http://localhost/dashboard` must render the neo-brutalist dashboard

## Pages to Test (via agent-browser in Docker context)

- `http://localhost/dashboard` — stat cards, sidebar nav (verify design tokens)
- `http://localhost/connections` — blog card grid
- `http://localhost/articles` — articles table
- `http://localhost/articles/new` — create article form

Note: In Docker, agent-browser tests the running nginx-served frontend. Port is 80 (or ${PORT:-80}).

## Resource Cost Classification

- Each agent-browser instance: ~300 MB RAM
- Docker stack (6 services): ~1.5 GB RAM total
- Max concurrent validators: **2** (Docker stack + agent-browser is memory-intensive)
- Validate sequentially for Docker-based testing

## External APIs

Validation does NOT test external APIs (DeepSeek, Fal.ai, WordPress.com). Only local stack API integration paths are verified.
