# Environment

## Docker Full-Stack Deployment

```bash
# Production (all 6 services via nginx on port 80)
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and ENCRYPTION_KEY
docker compose build
docker compose up -d

# Verify
bash scripts/smoke-test.sh http://localhost
```

## Local Development (without Docker)

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# http://localhost:3000 — proxies /api/* to http://localhost:8000
```

**Backend:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/v1/...
```

## Environment Variables

**Root .env.example:**
- `POSTGRES_USER`, `POSTGRES_PASSWORD` — DB credentials
- `ENCRYPTION_KEY` — Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `PORT` — nginx port (default 80)
- `CORS_ORIGINS` — JSON array of allowed origins

**Frontend (.env.local):**
- `NEXT_PUBLIC_API_URL=http://localhost:8000` (dev) or `http://api:8000` (Docker)

## Ports

- 80 — nginx reverse proxy (Docker production)
- 3000 — Next.js frontend (dev) or frontend:3000 (Docker internal)
- 5432 — PostgreSQL (dev Docker exposed)
- 6379 — Redis (dev Docker exposed)
- 8000 — FastAPI (dev) or api:8000 (Docker internal)

## Off-Limits

- `src/` — old prototype code
- `backend/app/` — do not modify unless in scope
- Root-level `tests/`, `docs/`, `assets/`
