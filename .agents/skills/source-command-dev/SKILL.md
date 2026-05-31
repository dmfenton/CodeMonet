---
name: "source-command-dev"
description: "Start dev servers (server + Expo mobile app)"
---

# source-command-dev

Use this skill when the user asks to run the migrated source command `dev`.

## Command Template

Start the development servers using `make dev` (Python server + Expo mobile app).

Run `make dev` in foreground. This will:

1. Kill any existing processes on ports 8000 and 8081
2. Start the Python server on :8000
3. Start the Expo app on :8081

The user can Ctrl+C to stop both servers cleanly.

If servers are stuck, run `make dev-stop` first to force-kill by port.

**Note:** For the Vite web app instead, use `/dev-web`.
