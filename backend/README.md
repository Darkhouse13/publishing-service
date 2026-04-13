# Publishing Service Backend

The backend foundation for the publishing service, providing a REST API for blog management, credential storage, and provider abstractions.

## Technology Stack
- **FastAPI:** High-performance web framework for the API layer.
- **SQLAlchemy 2.0:** Async ORM with support for SQLite and PostgreSQL.
- **Pydantic v2:** Data validation and settings management.
- **Celery & Redis:** Async background task infrastructure.
- **Alembic:** Database migrations.
- **Cryptography (Fernet):** Secure encryption at rest for sensitive credentials.

## Project Structure
- `app/api/`: FastAPI routers and endpoints.
- `app/models/`: SQLAlchemy ORM models.
- `app/services/`: Business logic layer.
- `app/providers/`: Abstract base classes and concrete provider implementations (LLM, Image, WordPress).
- `app/tasks/`: Celery task definitions.
- `app/core/`: Core configuration, database setup, and crypto utilities.

## Local Setup
1. **Initialize Environment:**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
2. **Setup .env:**
   The `.env` file is automatically created with a generated `ENCRYPTION_KEY` and SQLite `DATABASE_URL` by `.factory/init.sh`.
3. **Run Migrations:**
   ```bash
   alembic upgrade head
   ```
4. **Start API Server:**
   ```bash
   uvicorn app.main:app --port 8000 --reload
   ```

## Testing
Run the comprehensive test suite (275+ tests) using pytest:
```bash
pytest tests/ -v
```

## Docker Deployment
Production deployment is supported via Docker Compose:
```bash
docker-compose up -d
```
Includes API, Celery worker, PostgreSQL, and Redis.
