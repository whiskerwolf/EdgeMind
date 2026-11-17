# ==============================================================================
# EdgeMind Production Dockerfile
# Multi-stage, unprivileged non-root container for FastAPI backend
# ==============================================================================

# Stage 1: Build virtual environment
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    STATIC_ONLY="true" \
    ENVIRONMENT="production"

# Install curl for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user
RUN groupadd -g 10001 edgemind && \
    useradd -u 10001 -g edgemind -s /bin/false -m edgemind

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY --chown=edgemind:edgemind core/ /app/core/
COPY --chown=edgemind:edgemind migrations/ /app/migrations/
COPY --chown=edgemind:edgemind alembic.ini /app/alembic.ini

USER edgemind:edgemind

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "core.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
