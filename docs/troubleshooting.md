# Troubleshooting

## Docker container shows "unhealthy"

The healthcheck uses `curl` but `python:3.11-slim` doesn't include it. The app is likely fine - verify with:

```bash
uv run python scripts/remote.py shell "docker exec drawing-agent python -c 'import urllib.request; print(urllib.request.urlopen(\"http://localhost:8000/health\").read())'"
```

## SQLite database locking

SQLite doesn't handle concurrent writers. If you get "database is locked" errors:

1. Don't run Python scripts that write to DB while the app is running
2. Use `scripts/remote.py shell` with sqlite3 for direct DB access
3. Or stop the container first: `uv run python scripts/remote.py shell "docker stop drawing-agent"`

## SSM commands timing out

If `scripts/remote.py` commands timeout:

1. Check instance health: `aws ec2 describe-instance-status --instance-ids <id>`
2. Instance may be undersized (t3.micro only has 1GB RAM)
3. Current production uses t3.small (2GB RAM)

## Container commands slow

`uv run` inside the container is slow (~30s) because it syncs the venv. For quick DB operations, use sqlite3 directly:

```bash
uv run python scripts/remote.py shell "sqlite3 /home/ec2-user/data/codemonet/drawing_agent.db 'SELECT * FROM users;'"
```

## Missing tools in slim image

`python:3.11-slim` doesn't include: `curl`, `pkill`, `sqlite3`, etc. Use Python or install via apt if needed.
