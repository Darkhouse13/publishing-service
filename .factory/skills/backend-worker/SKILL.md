---
name: backend-worker
description: Handles backend features: models, schemas, services, API endpoints, pipeline services, Celery tasks, and tests.
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving:
- FastAPI routers, dependencies, and API endpoints
- SQLAlchemy ORM models, relationships, and Alembic migrations
- CRUD and pipeline service layer logic
- Pydantic request/response schemas
- Provider abstraction interfaces and concrete implementations (LLM, Image, WordPress)
- Celery task implementations
- Pipeline orchestration (single article, bulk)
- Prompt template files
- Test files (unit, integration, API)
- Backend encryption and security (Fernet)

## Required Skills

- None

## Work Procedure

1. **Read Reference Code First:**
   - Before implementing any algorithm, read the corresponding file in `src/automating_wf/` to understand the logic.
   - Port the algorithm, not the code. Rewrite cleanly using the new architecture.
   - Never copy-paste old code with its `load_dotenv()` and `os.getenv()` patterns.

2. **Test-Driven Development (TDD):**
   - Write tests FIRST (red) in `backend/tests/`. Cover expected behavior, edge cases, error paths.
   - Ensure tests fail initially.
   - Implement the feature in `backend/app/` to make tests pass (green).
   - All tests MUST use in-memory SQLite (`sqlite+aiosqlite://`).
   - Use mock providers from `backend/tests/helpers.py` (MockLLMProvider, MockImageProvider, MockWordPressProvider).

3. **Async Implementation:**
   - Use `AsyncSession` for all database interactions.
   - Use `httpx.AsyncClient` for all HTTP requests.
   - All service methods MUST be `async def`.
   - Only Celery task entry points use `asyncio.run()`.

4. **Database Updates at Each Status Transition:**
   - When implementing pipeline flows, commit/flush to DB at each status change.
   - If the worker crashes, the article/run status must reflect the last completed step.

5. **Error Handling:**
   - Errors caught per-article, not per-run. One failing article doesn't kill the bulk run.
   - On any pipeline failure: set status to "failed", populate error_message.

6. **Security & Validation:**
   - Use Fernet encryption from `app/crypto.py` for sensitive credentials.
   - Ensure Pydantic schemas correctly validate inputs and mask outputs.
   - Never return decrypted secrets in API responses.
   - No `os.getenv()` or `load_dotenv()` — all config from Settings class or DB.

7. **Logging:**
   - INFO: pipeline step transitions
   - DEBUG: LLM prompts and raw responses
   - WARNING: retries
   - ERROR: failures

8. **Manual Verification:**
   - Start the FastAPI server: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Use `curl` or `httpx` to verify API endpoints manually for sanity checks.
   - For pipeline features, verify that status transitions are observable in the DB.

9. **Run Full Test Suite:**
   - `cd backend && python3 -m pytest tests/ -v` — ALL tests must pass (existing + new).
   - `cd backend && python3 -m ruff check app tests` — no lint errors.
   - Ensure no regression in existing tests.

## Example Handoff

```json
{
  "salientSummary": "Implemented ArticleGenerator service with retry loop, hard validations, soft fixes, and prompt templates. All 15 new tests pass. Verified with MockLLMProvider covering success, retry, and failure cases.",
  "whatWasImplemented": "Created backend/app/services/article_generator.py with ArticleGenerator class and ArticlePayload dataclass. Created backend/app/prompts/article_generation.py with system and user prompt templates. Created backend/tests/test_article_generator.py with 15 test cases covering generation, validation, retry, and soft fix scenarios.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "cd backend && python3 -m pytest tests/test_article_generator.py -v",
        "exitCode": 0,
        "observation": "15 tests passed covering generation, retry, validation, soft fixes."
      },
      {
        "command": "cd backend && python3 -m pytest tests/ -v",
        "exitCode": 0,
        "observation": "All 290 tests passed (275 existing + 15 new)."
      }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {
        "file": "backend/tests/test_article_generator.py",
        "cases": [
          { "name": "test_generate_success", "verifies": "Valid LLM response produces ArticlePayload." },
          { "name": "test_retry_on_validation_failure", "verifies": "Retries with error feedback on failed validation." },
          { "name": "test_raises_after_max_attempts", "verifies": "ArticleGenerationError after 5 failed attempts." },
          { "name": "test_soft_fix_truncates_seo_title", "verifies": "seo_title truncated to 60 chars." }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Blocking database/ORM issues (e.g., complex migration conflict).
- Requirement ambiguity (e.g., unclear field validation rules).
- Environment blockers (e.g., missing dependency not in pyproject.toml).
- Feature depends on an API endpoint or data model that doesn't exist yet from another feature.
- Cannot complete work within mission boundaries (backend/ only).
