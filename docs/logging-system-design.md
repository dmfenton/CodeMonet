# Logging System Design

Design document for an intentional, structured logging system with CloudWatch.

## Architecture

```
┌──────────────────────────────────────┐
│           Application                │
│  ┌─────────────────────────────────┐ │
│  │     Structured JSON Logger      │ │
│  └──────────────┬──────────────────┘ │
└─────────────────┼────────────────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
┌─────▼─────┐         ┌───────▼───────┐
│  stdout   │         │  Log Files    │
│           │         │ /app/data/logs│
└───────────┘         └───────┬───────┘
                              │
                  ┌───────────▼───────────┐
                  │   CloudWatch Agent    │
                  │   (on EC2 host)       │
                  └───────────┬───────────┘
                              │
                  ┌───────────▼───────────┐
                  │   CloudWatch Logs     │
                  │  (Logs Insights)      │
                  └───────────────────────┘
```

## Log Categories

| Category    | Logger Name            | Purpose                          | Typical Level |
| ----------- | ---------------------- | -------------------------------- | ------------- |
| `auth`      | `code_monet.auth`      | Authentication, sessions, tokens | INFO          |
| `agent`     | `code_monet.agent`     | AI agent turns, tool calls       | INFO          |
| `websocket` | `code_monet.websocket` | WS connections, messages         | INFO          |
| `drawing`   | `code_monet.drawing`   | Canvas operations, paths         | DEBUG         |
| `workspace` | `code_monet.workspace` | User workspace lifecycle         | INFO          |
| `system`    | `code_monet.system`    | Startup, shutdown, config        | INFO          |
| `http`      | `code_monet.http`      | HTTP requests (non-WS)           | INFO          |

## Structured Log Format

### JSON Schema

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "category": "auth",
  "logger": "code_monet.auth.routes",
  "message": "User signed in",
  "user_id": 42,
  "trace_id": "1-abc123...",
  "extra": {
    "email": "user@example.com",
    "method": "magic_link"
  }
}
```

### Fields

| Field       | Required | Description                           |
| ----------- | -------- | ------------------------------------- |
| `timestamp` | Yes      | ISO 8601 with milliseconds            |
| `level`     | Yes      | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `category`  | Yes      | Log category (auth, agent, etc.)      |
| `logger`    | Yes      | Full logger name                      |
| `message`   | Yes      | Human-readable message                |
| `user_id`   | No       | User context if available             |
| `trace_id`  | No       | X-Ray trace ID for correlation        |
| `extra`     | No       | Category-specific structured data     |

### Implementation

```python
# server/code_monet/logging_config.py
import json
import logging
from datetime import datetime, UTC
from opentelemetry import trace

class StructuredFormatter(logging.Formatter):
    """JSON formatter for CloudWatch compatibility."""

    CATEGORY_MAP = {
        "code_monet.auth": "auth",
        "code_monet.agent": "agent",
        "code_monet.connections": "websocket",
        "code_monet.user_handlers": "websocket",
        "code_monet.orchestrator": "agent",
        "code_monet.tools": "agent",
        "code_monet.workspace_state": "workspace",
        "code_monet.registry": "workspace",
        "code_monet.main": "http",
        "code_monet.shutdown": "system",
        "code_monet.config": "system",
    }

    def format(self, record: logging.LogRecord) -> str:
        # Determine category from logger name
        category = "system"
        for prefix, cat in self.CATEGORY_MAP.items():
            if record.name.startswith(prefix):
                category = cat
                break

        # Get trace ID if available
        span = trace.get_current_span()
        trace_id = None
        if span.is_recording():
            ctx = span.get_span_context()
            trace_id = f"1-{format(ctx.trace_id, '032x')}"

        log_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "category": category,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add user_id if present
        if hasattr(record, "user_id"):
            log_record["user_id"] = record.user_id

        # Add trace_id if available
        if trace_id:
            log_record["trace_id"] = trace_id

        # Add extra fields
        extra = {}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                extra[key] = value
        if extra:
            log_record["extra"] = extra

        return json.dumps(log_record)
```

## Infrastructure

### CloudWatch Log Groups (Terraform)

Created in [compute/infrastructure/cloudwatch_logs.tf](https://github.com/dmfenton/compute/blob/main/infrastructure/cloudwatch_logs.tf):

| Log Group               | Retention | Purpose              |
| ----------------------- | --------- | -------------------- |
| `/drawing-agent/app`    | 30 days   | All application logs |
| `/drawing-agent/errors` | 90 days   | ERROR/CRITICAL only  |

### Metric Filters

- `error-count` - Counts ERROR level logs → `DrawingAgent/ErrorCount`
- `auth-failures` - Counts auth WARNING logs → `DrawingAgent/AuthFailureCount`

### Alarms

- `drawing-agent-high-error-rate` - Alerts if >10 errors in 5 minutes

### CloudWatch Agent Config

In [compute/infrastructure/user_data.sh](https://github.com/dmfenton/compute/blob/main/infrastructure/user_data.sh), the CloudWatch agent collects:

- `/home/ec2-user/data/logs/app.log` → `/drawing-agent/app`
- `/home/ec2-user/data/logs/error.log` → `/drawing-agent/errors`

### Log Rotation

Logrotate config in `user_data.sh`:

- Daily rotation
- Keep 7 days locally
- Compress old logs
- Max 100MB per file

## Querying Logs

### Using diagnose.py

```bash
# Recent logs
uv run python scripts/diagnose.py logs 30

# Error logs only
uv run python scripts/diagnose.py logs-errors 60

# Logs for specific user
uv run python scripts/diagnose.py logs-user 42 60

# Search logs
uv run python scripts/diagnose.py logs-search "magic link" 60

# Filter by category
uv run python scripts/diagnose.py logs --category auth --md
```

### CloudWatch Logs Insights Queries

**Error rate by category:**

```
filter level = "ERROR"
| stats count(*) as errors by category
| sort errors desc
```

**Authentication failures:**

```
filter category = "auth" and level in ["WARNING", "ERROR"]
| fields @timestamp, message, extra.email
| sort @timestamp desc
| limit 50
```

**Agent tool usage:**

```
filter category = "agent" and message like /Tool use/
| parse message "Tool use: *" as tool_name
| stats count(*) as calls by tool_name
| sort calls desc
```

**User activity timeline:**

```
filter user_id = 42
| fields @timestamp, category, level, message
| sort @timestamp asc
```

**Logs with trace correlation:**

```
filter trace_id != ""
| fields @timestamp, category, message, trace_id
| sort @timestamp desc
| limit 100
```

## Migration Plan

### Phase 1: Structured Logging

1. Create `server/code_monet/logging_config.py` with JSON formatter
2. Update `main.py` to use structured formatter
3. Add `user_id` context to relevant log calls
4. Configure file handler for `/app/data/logs/app.log`
5. Test locally with JSON output

### Phase 2: Deploy Infrastructure

1. Run `terraform apply` to create log groups
2. Redeploy EC2 (or update CloudWatch agent config manually)
3. Verify logs appear in CloudWatch console

### Phase 3: Tooling

1. Test `diagnose.py logs` commands
2. Create saved queries in CloudWatch console
3. Set up dashboard if needed

## Security Considerations

1. **PII in logs** - Never log passwords, tokens, or full email addresses
2. **Log retention** - 30 days default, 90 for errors
3. **Access control** - CloudWatch Logs access via IAM only
4. **Encryption** - Logs encrypted at rest (CloudWatch default)

## Cost Estimation

| Component                 | Monthly Cost (est.) |
| ------------------------- | ------------------- |
| CloudWatch Logs ingestion | ~$0.50/GB           |
| CloudWatch Logs storage   | ~$0.03/GB/month     |
| Log Insights queries      | ~$0.005/GB scanned  |
| **Estimated total**       | **$1-5/month**      |

Based on ~100MB-1GB/month log volume at current scale.
