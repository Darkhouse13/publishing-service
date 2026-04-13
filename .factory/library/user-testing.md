# User Testing

Testing surface, required testing skills/tools, and resource cost classification for the publishing service.

## Validation Surface
- **API:** The primary surface is the REST API at `/api/v1/`.
- **Tools:** Use `httpx` test client (via `client` fixture in conftest.py) and `curl` for behavioral verification.
- **Environment:** Local execution using in-memory SQLite for tests, file-based SQLite for dev.
- **No browser UI:** This mission is API-only. No agent-browser testing needed.

## Test Infrastructure
- **Test runner:** `cd backend && python3 -m pytest tests/ -v`
- **Fixtures:** `db_session` (in-memory SQLite AsyncSession), `client` (httpx test client) in `conftest.py`
- **Mock providers:** `MockLLMProvider`, `MockImageProvider`, `MockWordPressProvider` in `backend/tests/helpers.py`
- **Coverage:** 275 existing tests must keep passing; new tests added per feature

## Validation Concurrency
- **Max Concurrent Validators:** 5
- **Rationale:** API testing is lightweight — httpx test client against in-memory SQLite. Each validator instance consumes ~100 MB RAM. Dev server adds ~200 MB. On a machine with 7.7 GB total RAM, ~4 GB available, headroom is comfortable for 5 concurrent validators.

## Key Test Patterns
- **Unit tests (services):** Mock providers, test business logic in isolation
- **Integration tests (pipeline):** Mock all providers, test full pipeline flow with real DB
- **API tests:** httpx test client, verify response shapes and DB records
- **Migration tests:** Fresh SQLite DB, apply migrations, verify schema
