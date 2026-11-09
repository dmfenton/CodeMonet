# Observability (Tracing)

## Overview

**Production tracing is disabled** (since 2026-11, for cost). `dmfenton/platform.dmfenton.net`
`ops/deploy/release-assets/codemonet-compose.yml` sets `OTEL_ENABLED=false` on `drawing-agent`, so
the server exports no spans and `POST /traces` accepts client spans but records none
(`{"received": 0}`). Use CloudWatch logs (`diagnose.py logs`) for production debugging.

The instrumentation remains and can be re-enabled:

- **App**: Instrumented with opentelemetry-python (FastAPI, SQLAlchemy, logging)
- **Collector**: the platform `otel-collector` (`ops/deploy/otel-config.yaml`) receives OTLP and
  exports to X-Ray; it currently has a Chef-only pipeline that drops other services' spans
- **Console**: View traces in AWS X-Ray console

To re-enable in production, restore a CodeMonet pipeline in the platform collector config, set
`OTEL_ENABLED: "true"` and `OTEL_EXPORTER_ENDPOINT: http://otel-collector:4318` in
`codemonet-compose.yml`, then redeploy CodeMonet (the platform config release does not recreate
`drawing-agent`).

## Diagnose CLI

Use the `/diagnose` skill, or run `scripts/diagnose.py` directly:

```bash
# === Trace commands (X-Ray) ===

# Service status (quick health check, last 5 min)
uv run python scripts/diagnose.py status

# Traffic summary with stats
uv run python scripts/diagnose.py summary 60

# Recent error traces
uv run python scripts/diagnose.py errors 60

# All recent traces
uv run python scripts/diagnose.py recent 30

# WebSocket session traces
uv run python scripts/diagnose.py ws 120

# Slow traces (>1s duration, useful for finding WS sessions)
uv run python scripts/diagnose.py slow 1 180

# Traces for specific endpoint
uv run python scripts/diagnose.py path /auth/callback 60

# Full trace details (including stack traces)
uv run python scripts/diagnose.py trace <trace_id>

# === Log commands (CloudWatch Logs) ===

# Recent application logs
uv run python scripts/diagnose.py logs 30

# Error/warning logs only
uv run python scripts/diagnose.py logs-errors 60

# Logs for a specific user
uv run python scripts/diagnose.py logs-user 42 60

# Search logs for a pattern
uv run python scripts/diagnose.py logs-search "magic link" 60

# Filter logs by category
uv run python scripts/diagnose.py logs --category auth --md
```

**Output formats:**

- `--md` / `--markdown` - Markdown tables (for Claude to read)
- `--json` - JSON output (for scripts)
- Default: Rich terminal tables

**Log categories:** auth, agent, websocket, workspace, system, http

Example with markdown output:

```bash
uv run python scripts/diagnose.py status --md
uv run python scripts/diagnose.py logs-errors --md
```

## Trace IDs in Errors

500 errors include trace_id in the response:

```json
{ "detail": "Internal Server Error", "trace_id": "abc123..." }
```

Use this ID to look up the full trace with stack trace:

```bash
uv run python scripts/diagnose.py trace <trace_id>
```

## Environment Variables

```bash
# Enable tracing (default false; currently false in production too)
OTEL_ENABLED=true

# Collector endpoint (set automatically in docker-compose)
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4318

# AWS region for X-Ray
AWS_REGION=us-east-1
```

## Viewing in AWS Console

1. Go to AWS Console -> CloudWatch -> X-Ray traces -> Traces
2. Filter by service name "drawing-agent"
3. Click a trace to see segment timeline and details
4. Error traces show exception stack traces
