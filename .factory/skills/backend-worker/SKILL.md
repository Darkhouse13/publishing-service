---
name: backend-worker
description: Handles backend foundation features (FastAPI, SQLAlchemy, CRUD, Providers).
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving:
- FastAPI routers and dependencies
- SQLAlchemy ORM models and migrations (Alembic)
- CRUD service layer logic
- Pydantic request/response schemas
- Provider abstraction interfaces and concrete implementations (LLM, Image, WordPress)
- Backend encryption and security (Fernet)
- Celery task skeleton

## Required Skills

- None

## Work Procedure

1. **Test-Driven Development (TDD):**
   - Write tests first (red) in `backend/tests/`. Cover the expected behavior, including edge cases (e.g., duplicate slug, missing fields, invalid auth).
   - Ensure tests fail initially.
   - Implement the feature in `backend/app/` (models, schemas, services, then api) to make tests pass (green).
   - All tests MUST use an in-memory SQLite database (`sqlite+aiosqlite://`).

2. **Async Implementation:**
   - Use `AsyncSession` for all database interactions.
   - Use `httpx.AsyncClient` for all HTTP requests (including providers).
   - All provider methods MUST be async.

3. **Security & Validation:**
   - Use Fernet encryption from `app/crypto.py` for sensitive credentials.
   - Ensure Pydantic schemas correctly validate inputs and mask outputs.
   - Never return decrypted secrets in API responses.

4. **Manual Verification:**
   - Start the FastAPI server locally: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
   - Use `curl` or `httpx` to verify API endpoints manually.
   - For database operations, verify state using the service layer or direct query if necessary.
   - For providers, verify that they are correctly instantiated and use the correct (decrypted) credentials.

5. **Lint & Typecheck:**
   - Run `python -m pytest tests/ -v`.
   - Ensure all function signatures are fully typed.

## Example Handoff

```json
{
  "salientSummary": "Implemented Blog CRUD with soft-delete and auto-config creation. Verified with 8 passing tests and manual curl requests for create/list/delete flows.",
  "whatWasImplemented": "Created Blog SQLAlchemy model, Pydantic schemas, and BlogService. Implemented FastAPI router with soft-delete logic and a post-creation hook for default pipeline_config. Added Fernet encryption for wp_app_password.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "python -m pytest backend/tests/test_blogs.py",
        "exitCode": 0,
        "observation": "8 tests passed (create, list, get, update, soft-delete, duplicates, validation errors)."
      },
      {
        "command": "curl -X POST /api/v1/blogs -d '{\"name\": \"Test Blog\", ...}'",
        "exitCode": 0,
        "observation": "Successfully created blog, response contained masked password and 201 status."
      }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {
        "file": "backend/tests/test_blogs.py",
        "cases": [
          { "name": "test_create_blog_success", "verifies": "Blog creation returns 201 and persists to DB." },
          { "name": "test_create_blog_duplicate_slug", "verifies": "Creating blog with existing slug returns 409." },
          { "name": "test_blog_soft_delete", "verifies": "DELETE sets is_active=False and omits from list." }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Blocking database/ORM issues (e.g., complex migration conflict).
- Requirement ambiguity (e.g., unclear field validation).
- Environment blockers (e.g., missing dependencies not in pyproject.toml).
