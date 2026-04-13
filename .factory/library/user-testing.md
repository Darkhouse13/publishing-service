# User Testing

Testing surface, required testing skills/tools, and resource cost classification for the publishing service.

## Validation Surface
- **API:** The primary surface is the REST API at `/api/v1/`.
- **Tools:** Use `curl` or `httpx` for behavioral verification.
- **Environment:** Local execution using SQLite for development and tests.

## Validation Concurrency
- **Max Concurrent Validators:** 5
- **Rationale:** The API is lightweight and runs with SQLite locally, consuming minimal RAM (~300 MB per instance). On a machine with 16GB RAM, we have plenty of headroom for parallel execution.
