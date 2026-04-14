# Environment

## Frontend Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend runs on `http://localhost:3000`.

## Backend Connection

The frontend proxies API requests through Next.js rewrites to avoid CORS:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000` (FastAPI)

Next.js config rewrites `/api/:path*` to `${NEXT_PUBLIC_API_URL}/api/:path*`.

## Environment Variables

`frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Mock Data Strategy

All pages use SWR `fallback` prop for mock data during development. Mock data in `src/lib/mock-data.ts` has realistic fixtures for all entity types. API client is typed and works with both mock data and real backend.

## Ports

- Frontend: 3000 (never start on other ports)
- Backend: 8000 (read-only, do not modify)

## Off-Limits

- `backend/` directory — do not read or modify
- `src/` directory — do not read or modify
- Root-level configs (docker-compose, .env, .env.example)
