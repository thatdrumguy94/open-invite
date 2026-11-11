# ==============================================================================
# Multi-Stage Production Dockerfile for Event Invitation Management System
# Python 3.12-slim Runtime with Non-Root Security
# ==============================================================================

# --- Stage 1: Build & Dependency Wheel Installation ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install minimal build tools for any packages requiring C compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment to isolate dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Minimal Production Runtime ---
FROM python:3.12-slim AS runner

# Install only the runtime shared libraries needed for PostgreSQL and TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy isolated virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Create non-root user and group for runtime isolation
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy application source code and scripts
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create local storage and database instance directories with non-root ownership
RUN mkdir -p /app/uploads /app/instance && chown -R appuser:appgroup /app/uploads /app/instance

# Switch to non-root execution
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD sh -c 'if [ "${TLS_ENABLED:-false}" = "true" ] || [ -n "${SSL_CERTFILE:-}" ]; then curl -fk https://localhost:5000/health; else curl -f http://localhost:5000/health; fi || exit 1'

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--workers=3", "--bind=0.0.0.0:5000", "--chdir=/app/src", "wsgi:app"]
