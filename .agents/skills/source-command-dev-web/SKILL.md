---
name: "source-command-dev-web"
description: "Start dev servers (server + Vite web app)"
---

# source-command-dev-web

Use this skill when the user asks to run the migrated source command `dev-web`.

## Command Template

Start the development servers using `make dev-web` (Python server + Vite web app).

Run `make dev-web` in foreground. This will:

1. Kill any existing processes on ports 8000 and 5173
2. Start the Python server on :8000
3. Start the Vite web app on :5173

The user can Ctrl+C to stop both servers cleanly.

If servers are stuck, run `make dev-stop` first to force-kill by port.

**Note:** For the Expo mobile app instead, use `/dev`.
