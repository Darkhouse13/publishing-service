# ---------------------------------------------------------------------------
# Multi-stage Dockerfile for the Publishing Service backend
# ---------------------------------------------------------------------------

# ---- Builder stage --------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install -e ".[dev]" 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install .

# Copy source code
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini

# Re-install with source available
RUN pip install --no-cache-dir --prefix=/install -e ".[dev]"

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser alembic/ alembic/
COPY --chown=appuser:appuser alembic.ini alembic.ini
COPY --chown=appuser:appuser pyproject.toml .

# Create artifacts directory
RUN mkdir -p /app/artifacts && chown appuser:appuser /app/artifacts

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Default environment (can be overridden in docker-compose)
ENV DATABASE_URL="sqlite+aiosqlite:///./dev.db" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"] || exit 1

# Run migrations then start the API server
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
