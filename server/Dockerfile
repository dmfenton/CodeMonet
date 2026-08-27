FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df AS build

WORKDIR /app/server

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/

RUN apk add --no-cache build-base

COPY server/pyproject.toml server/uv.lock server/alembic.ini ./
COPY server/code_monet/ code_monet/
COPY server/alembic/ alembic/
COPY vendor/platform.dmfenton.net/python /app/vendor/platform.dmfenton.net/python

RUN uv sync --frozen --no-dev --no-cache

FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df

# Build args for version info
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown
ARG APP_BUILD_TIME=unknown

# Labels for container inspection
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${APP_COMMIT}"
LABEL org.opencontainers.image.created="${APP_BUILD_TIME}"
LABEL org.opencontainers.image.title="code-monet"
LABEL org.opencontainers.image.description="Code Monet - Autonomous AI artist"

WORKDIR /app/server

COPY server/pyproject.toml server/uv.lock server/alembic.ini ./
COPY server/code_monet/ code_monet/
COPY server/alembic/ alembic/
COPY vendor/platform.dmfenton.net/python /app/vendor/platform.dmfenton.net/python
COPY --from=build /app/server/.venv ./.venv

# Create logs directory for structured logging
RUN mkdir -p /app/server/data/logs

# Remove the unused system package installer, then create the non-root runtime user.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/python3.12/site-packages/pip* \
        /usr/local/lib/python3.12/site-packages/setuptools* \
        /usr/local/lib/python3.12/site-packages/wheel* \
        /usr/local/bin/pip* /usr/local/bin/wheel \
    && test ! -e /usr/local/bin/uv \
    && ! command -v pip \
    && ! command -v wheel \
    && /bin/busybox adduser -D -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Set production mode and version info as env vars
ENV DEV_MODE=false
ENV APP_VERSION=${APP_VERSION}
ENV APP_COMMIT=${APP_COMMIT}
ENV APP_BUILD_TIME=${APP_BUILD_TIME}
ENV PATH="/app/.venv/bin:${PATH}"

# Keep the image independently health-aware when it runs outside Compose.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# Run uvicorn directly (no reload in production)
CMD ["/app/server/.venv/bin/uvicorn", "code_monet.main:app", "--host", "0.0.0.0", "--port", "8000"]
