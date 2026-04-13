# Environment

Environment variables, external dependencies, and setup notes for the publishing service backend.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

## Environment Variables
- `DATABASE_URL`: Async SQLAlchemy connection string (e.g., `sqlite+aiosqlite:///./dev.db`).
- `REDIS_URL`: Redis connection string for broker and results (e.g., `redis://localhost:6379/0`).
- `ENCRYPTION_KEY`: Fernet key for credential storage (generated on init).
- `DEBUG`: Boolean flag for dev mode.

## External Dependencies
- **DeepSeek API:** Requires an `api_key` for the DeepSeekProvider.
- **OpenAI API:** Requires an `api_key` for the OpenAIProvider.
- **Fal.ai API:** Requires an `api_key` for the FalProvider.
- **WordPress REST API:** Requires `url`, `username`, and `app_password` for each blog.
