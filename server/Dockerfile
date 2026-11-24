# Platform's shared Python runtime (python/Dockerfile.runtime), pinned by digest: the scanned
# Python 3.12 Alpine base every Fenton API starts from. The build stage uses the same image, so
# the copied virtual environment links against the exact interpreter that runs it. Pulling it
# needs ECR read access (scripts/docker-build.sh logs in when the image is not local).
ARG FENTON_RUNTIME_IMAGE=573988763875.dkr.ecr.us-east-1.amazonaws.com/fenton-python-runtime@sha256:92d5d68a07d8de5f89dc8647d96444d27fbc95b5906734a50d28bd72dc9c0f25
FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS claude-cli

WORKDIR /opt/claude
COPY server/claude-cli/package*.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && cp node_modules/@anthropic-ai/claude-code-linux-*-musl/claude ./claude \
    && ./claude --version

FROM ${FENTON_RUNTIME_IMAGE} AS build

WORKDIR /app/server

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/

RUN apk add --no-cache build-base git

COPY server/pyproject.toml server/uv.lock server/alembic.ini ./
COPY server/code_monet/ code_monet/
COPY server/alembic/ alembic/

# The tagged Platform libraries uv.lock records come from the `platform-src` build context that
# scripts/docker-build.sh fetches; uv still checks the exact commit. Nothing private is fetched here.
RUN --mount=type=bind,from=platform-src,target=/platform-src \
    GIT_CONFIG_COUNT=2 \
    GIT_CONFIG_KEY_0=url.file:///platform-src.insteadOf \
    GIT_CONFIG_VALUE_0=https://github.com/dmfenton/platform.git \
    GIT_CONFIG_KEY_1=safe.directory \
    GIT_CONFIG_VALUE_1=* \
    UV_PYTHON=/usr/local/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --no-dev --no-cache

FROM ${FENTON_RUNTIME_IMAGE}

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
COPY --from=build /app/server/.venv ./.venv
COPY --from=claude-cli /opt/claude/claude /usr/local/bin/claude
# The public site's page heads are rendered by the web build's own bundle
# (see code_monet/prerender.py). It is built before this image (CI and the
# release run `npm run build -w web`) so its template references exactly the
# asset hashes nginx serves from the same build.
COPY --from=claude-cli /usr/local/bin/node /usr/local/bin/node
COPY web/dist/prerender/ /app/web/dist/prerender/

# Alpine installs the SDK source distribution, which has no bundled CLI.
# Verify the SDK resolves the separately locked musl executable.
RUN .venv/bin/python -c "import subprocess; from claude_agent_sdk import ClaudeAgentOptions; from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport; cli = SubprocessCLITransport('', ClaudeAgentOptions())._find_cli(); assert cli == '/usr/local/bin/claude', cli; subprocess.run([cli, '--version'], check=True)"

# Persistent data lives on the /app/data volume. Config paths are relative
# (data/drawing_agent.db, data/agent_workspace/users) and resolve from this
# WORKDIR, so data/ must be the volume, not a directory inside the image.
RUN mkdir -p /app/data/logs && ln -s /app/data /app/server/data

# bash: the Claude CLI's Bash tool refuses to run without bash or zsh.
# The runtime already removed pip, setuptools and wheel; prove nothing reinstalled them, then
# create the non-root runtime user.
RUN apk upgrade --no-cache \
    && apk add --no-cache bash libstdc++ \
    && node --version \
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
ENV PATH="/app/server/.venv/bin:${PATH}"

# Keep the image independently health-aware when it runs outside Compose.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# Production entrypoint: uvicorn without reload, stopping cleanly (exit 0) when idle.
CMD ["/app/server/.venv/bin/python", "-m", "code_monet.serve"]
