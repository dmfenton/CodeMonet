FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df AS build

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/

RUN apk add --no-cache build-base

COPY pyproject.toml uv.lock alembic.ini ./
COPY code_monet/ code_monet/
COPY alembic/ alembic/

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

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
COPY pyproject.toml uv.lock alembic.ini ./
COPY code_monet/ code_monet/
COPY alembic/ alembic/
COPY --from=build /app/.venv ./.venv

# Create logs directory for structured logging
RUN mkdir -p /app/data/logs

# Create non-root user for security (reduces blast radius of container escape)
RUN /bin/busybox adduser -D -u 1000 appuser \
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

# Run uvicorn directly (no reload in production)
CMD ["uv", "run", "uvicorn", "code_monet.main:app", "--host", "0.0.0.0", "--port", "8000"]
