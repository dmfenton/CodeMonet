# Code Monet - Development Instructions

## Project Overview

Code Monet is an autonomous AI artist application with:

- **Backend**: Python 3.12+ with FastAPI, Claude Agent SDK, WebSocket support
- **iOS**: Native SwiftUI app (`ios/`), XcodeGen-generated project + `ios/MonetKit` Swift package. See `ios/ARCHITECTURE.md`.
- **Web**: Vite web app, TypeScript, React

## Environment Setup

- `.env` file lives in **project root** (not server/)
- Config loads from both `../.env` and `.env` so it works from any directory
- Production Claude auth uses Anthropic AWS workload identity; static Anthropic keys are unsupported

## Package Management

**This project uses npm workspaces.**

### Workspace Structure

```
/                    # Root npm workspace
├── web/             # Vite web app
├── shared/          # Shared TypeScript library (web only)
├── server/          # Python backend (uses uv, not npm)
└── ios/             # Native SwiftUI app — separate toolchain (XcodeGen + Swift),
                      # not an npm workspace. See ios/ARCHITECTURE.md, ios/Makefile.
```

### Key Rules

1. **Always use npm** - Run `npm install` from project root
2. **Build shared after changes** - Run `cd shared && npm run build` after modifying shared/
3. **Install from root** - Run `npm install` from project root, not subdirectories

### Adding Dependencies

```bash
# Add to specific workspace
npm install <package> -w web
npm install <package> -w shared

# Add to root (dev tools, etc.)
npm install <package>
```

### Common Issues

**Stale shared library** - Rebuild:

```bash
cd shared && npm run build
```

**Dependency issues** - Clean reinstall:

```bash
rm -rf node_modules web/node_modules shared/node_modules package-lock.json
npm install
```

### Python Server Setup

The server uses `uv` for dependency management (not npm).

```bash
cd server

# Install all dependencies including dev tools (pytest, mypy, ruff, pre-commit)
uv sync --extra dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run mypy .
```

**Common issues:**

- `pytest-asyncio` not found -> Run `uv sync --extra dev`
- `pre-commit` not found -> Run `uv sync --extra dev`
- Tests fail with import errors -> Rebuild shared library: `cd shared && npm run build`

See [docs/claude-sandbox.md](docs/claude-sandbox.md) for Claude Code sandbox configuration.

## Git Workflow

**Always use Pull Requests** - never push directly to main, even if you have bypass permissions.

1. Create a feature branch
2. Make commits on the branch
3. Push the branch and create a PR with `gh pr create`
4. Wait for review/approval before merging

This ensures code review happens and keeps the workflow consistent.

### Branch Strategy

- **`main`** is the source of truth. All features and fixes should be merged here via PRs.
- **`release/*` branches** are temporary, created only for cutting releases. They should not diverge from main - tag releases directly from main when possible.
- Never do long-running work on release branches. If a hotfix is needed, make it on main first, then cherry-pick or create a new release from main.

### Branch Protection

The `main` branch is protected with these rules:

| Rule                              | Setting                   |
| --------------------------------- | ------------------------- |
| Required status checks            | CI Success, Codex review gate |
| Require branches to be up to date | Yes                       |
| Require conversation resolution   | Yes                       |
| Enforce for admins                | No (can bypass if needed) |
| Force pushes                      | Blocked                   |

PRs to main require both "CI Success" and "Codex review gate" to pass before
merging. The Codex gate also requires every Codex review thread to be resolved.

**Important:** Even though admin bypass is enabled, always use PRs. Never push directly to main.

### CI Path Filters

CI jobs only run when relevant code changes:

| Job                | Runs when these paths change                     |
| ------------------ | ------------------------------------------------ |
| Server (Python)    | `server/**`                                      |
| Frontend (web)     | `web/**`, `shared/**`, `package*.json`            |
| Replay Tests       | `web/**`, `shared/**`, `package*.json`            |
| iOS (Swift)        | `ios/**`, `fenton-platform.lock`                  |
| Docker Build       | `server/**` (after Server job passes)            |

The "CI Success" job consolidates results - it passes if all jobs either pass or are appropriately skipped.

## Development Servers

### Live Reload (IMPORTANT)

The Python server and Vite web app both have **live reload enabled by default** - they auto-restart on file changes:

- **Python server**: Uvicorn with watchfiles (reload=True in dev mode)
- **Vite web app**: Metro-free Vite dev server with HMR

**DO NOT manually restart servers after code changes.** Just save the file and wait 1-2 seconds.

The native iOS app has no live reload — rebuild and relaunch it in Xcode or
via `make ios-build` after Swift changes.

### Starting Dev Servers

```bash
make dev-web   # Server + Vite web app (foreground, Ctrl+C to stop)
make dev-stop  # Force-kill any stuck servers by port
```

**Ports:**

- Python server: http://localhost:8000
- Vite web: http://localhost:5173

Both have live reload - no restarts needed for code changes.

**Only restart if:**

- Changed dependencies (pyproject.toml, package.json)
- Server crashed
- Stale behavior after 5+ seconds post-save

**Stuck ports?** Run `make dev-stop` to force-kill by port, then start again.

### Simulator Screenshots (Debugging)

Use `/screenshot` to capture the native iOS app's Simulator screen when debugging mobile issues.

Screenshots are saved to `screenshots/` (gitignored) and displayed for analysis.

### App Screenshots (Web)

Use `/app-screenshot` or `scripts/app-screenshot.py` to capture the Vite web app:

```bash
# Basic screenshot
uv run python scripts/app-screenshot.py

# With auth (loads user workspace)
uv run python scripts/app-screenshot.py --auth

# Wait for content and specific selector
uv run python scripts/app-screenshot.py --auth --wait 3 --selector "[data-testid='canvas-view']"

# Custom viewport (iPhone 15 Pro Max)
uv run python scripts/app-screenshot.py --viewport 430x932
```

**Prerequisites:** `cd server && uv sync --extra dev && uv run playwright install chromium`

### Debug API Endpoints

```bash
# Check agent state
curl localhost:8000/debug/agent

# Get recent logs (default 100 lines)
curl "localhost:8000/debug/logs?lines=50"
```

The `/debug/agent` endpoint returns:

- `paused`, `status`, `container_id`
- `piece_count`, `stroke_count`
- `pending_nudges`, `connected_clients`
- `notes` and `monologue_preview` (first 500 chars)

### WebSocket Remote Control (`scripts/ws-client.py`)

Control the agent from terminal without the UI:

```bash
# Check current state
uv run python scripts/ws-client.py status

# Pause the agent (stops drawing)
uv run python scripts/ws-client.py pause

# Resume the agent
uv run python scripts/ws-client.py resume

# Clear canvas
uv run python scripts/ws-client.py clear

# Watch all WebSocket events (debug)
uv run python scripts/ws-client.py watch

# Save current canvas to file
uv run python scripts/ws-client.py view output.png

# Start new canvas with prompt
uv run python scripts/ws-client.py start "draw a cat"
```

### Art Benchmark (`scripts/art-benchmark.py`)

Runs fixed painter prompts (Turner storm, Hockney pool, Cézanne, Bruegel) through the
live agent and saves each piece, every painting version, a full event trace, and a
contact sheet to `screenshots/benchmarks/<label>-<timestamp>/`. Use it to measure any
change to the paint prompt, library, or model:

```bash
cd server && uv run python ../scripts/art-benchmark.py --label my-change --timeout 1500
```

Iterate on the paint library itself by writing a painting program and running
`python -m code_monet.paintlib.runner --program p.py --out DIR --width 1600 --height 1200`
(from `server/`), then look at `DIR/preview.jpg`.

### Render Studies (`scripts/render-study.py`)

The fast iteration loop for renderer/visual work — sandbox code → paint render →
PNG, no agent or API calls:

```bash
cd server

# Server-side render (painting.py) to screenshots/studies/<stem>.png
uv run python ../scripts/render-study.py ../studies/monet_lilies.py

# ALSO render via the web client (stamping.ts) and produce a labeled
# side-by-side with a diff heatmap + mean-diff metric.
# Requires the Vite dev server (make dev-web or make web).
uv run python ../scripts/render-study.py ../studies/brush_swatches.py --compare
```

`--compare` drives the dev-only `/replay` route (web/src/pages/ReplayPage.tsx),
which renders the exported paths through the production StampCanvasLayer.
Use it to verify painting.py / stamping.ts parity — what users actually see is
the client render. `--json out.json` exports paths for manual replay
(`http://localhost:5173/replay?src=...`).

### Visual Flow Testing (`scripts/visual-flow-test.py`)

Watch a full agent run end-to-end and produce judgeable artifacts:

```bash
# From repo root (or use cd server + ../scripts/...)
uv run --project server python scripts/visual-flow-test.py "draw a simple line"

# Show browser window for debugging
uv run --project server python scripts/visual-flow-test.py "draw a cat" --no-headless
```

**Output:** `screenshots/flow-{timestamp}/` — start with `report.md`:
- `report.md`: event timeline (thinking text, tool calls, critique verdicts,
  stroke batches) aligned with screenshots, plus client-lag stats
- `contact-sheet.png`: one-glance grid of the whole run
- Interval frames `001-000000ms.png` PLUS event-triggered frames
  (`-strokes-batchN`, `-critique`, `-state-*`, `-final`)
- `canvas-*-batchN.png`: canvas-only crops per stroke batch
- `final-canvas.png` + `server-render.png` + `parity.png`: client (stamping.ts)
  vs server (painting.py) side-by-side with diff heatmap
- `events.json` (compacted), `summary.txt`, `timelapse.mp4`

The web app exposes `window.__CM_DEV_STATE__` in dev (strokes painted, queue
depth, revealed chars); the report uses it to flag when the client performance
lags the server — if the run timed out mid-piece, parity.png compares an
incomplete client canvas.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--interval N` | 1.0 | Screenshot interval in seconds |
| `--timeout N` | 120 | Max test duration in seconds |
| `--output DIR` | auto | Custom output directory |
| `--expo-port N` | 5173 | Vite dev server port |
| `--web` | auto | Force Vite-web mode (auto for port 5173) |
| `--viewport WxH` | per app | 390x844 mobile, 1280x900 web |
| `--no-headless` | false | Show browser window |
| `--no-clear` | false | Skip clearing canvas |
| `--no-video` | false | Skip timelapse video |

### Full Development Loop

The complete cycle for UI changes: **Investigate -> Plan -> Code -> Test -> Verify -> Loop**

Uses Claude skills (`/command`), scripts, and tools together.

#### 1. Investigate

| Method | Use For |
|--------|---------|
| `/diagnose` | X-Ray traces, CloudWatch logs, service health |
| `ws-client.py status` | Current agent state (paused, piece count) |
| `ws-client.py watch` | Live WebSocket event stream |
| Task tool (Explore) | Open-ended codebase searches |

```bash
# Direct script usage
uv run python scripts/ws-client.py status
uv run python scripts/ws-client.py watch
```

#### 2. Plan

Use `EnterPlanMode` for non-trivial changes. Consider:
- Which codebase? `ios/CodeMonet` (native iOS, Swift) vs `web/src/` (web) vs `shared/src/` (web only)
- Rebuild shared after changes: `cd shared && npm run build`

#### 3. Code

Implement the fix. Run typecheck / build:

```bash
npm run -w web typecheck    # Web app
npm run -w shared build     # Rebuild shared if changed
make ios-kit-test           # MonetKit Swift package (fast, no simulator)
make ios-build              # Full Xcode Simulator build, if project.yml or app target changed
```

#### 4. Remote Control (Set Up Test State)

| Method | Use For |
|--------|---------|
| `/remote` | Run commands on production server via SSM |
| `ws-client.py pause` | Stop agent drawing |
| `ws-client.py clear` | Empty the canvas |
| `ws-client.py start "prompt"` | Start new canvas with direction |
| `ws-client.py resume` | Resume paused agent |

```bash
# Check state, then pause
uv run python scripts/ws-client.py status
uv run python scripts/ws-client.py pause
```

#### 5. Screenshot & Verify

| Method | Use For |
|--------|---------|
| `/app-screenshot` | Capture the Vite web app (port 5173) |
| `/screenshot` | Capture the native iOS app in Simulator |

```bash
# Web app
/app-screenshot --auth --wait 3

# Wait for specific element
/app-screenshot --auth --selector "[data-testid='canvas-view']"
```

Then use Read tool on `server/screenshots/app-*.png` to view.

#### 6. Loop Back

If screenshot shows issues:
1. `/diagnose` or `/diagnose logs` to check for errors
2. Adjust code
3. Re-run from step 4

#### 7. Ship

| Method | Use For |
|--------|---------|
| `/pr` | Create PR with code review |
| `/release` | Cut a release tag |

#### Available Skills Reference

| Skill | Purpose |
|-------|---------|
| `/dev-web` | Start dev servers (server + Vite web on 5173) |
| `/diagnose` | X-Ray traces and CloudWatch logs |
| `/app-screenshot` | Screenshot the Vite web app |
| `/screenshot` | Screenshot the native iOS app in Simulator |
| `/remote` | Run commands on prod via SSM |
| `/pr` | Create PR, run code review |
| `/release` | Cut a release |
| `/sync-prod` | Sync production data to dev |

#### Quick Reference

**TestIDs for `--selector`:**

Web studio (port 5173, `/studio`):

| Element | Selector |
|---------|----------|
| Canvas | `[data-testid="canvas-view"]` |
| Status pill | `[data-testid="status-pill"]` |
| Thinking strip | `[data-testid="thinking-strip"]` |
| Start button | `[data-testid="start-button"]` |
| Start modal input/submit | `[data-testid="start-modal-input"]` / `"start-modal-submit"` |
| Nudge input/send | `[data-testid="nudge-input"]` / `"nudge-send"` |
| Pause | `[data-testid="pause-button"]` |

**Common Issues:**

- **Agent auto-starts**: Workspaces persist. Use `ws-client.py pause` first.
- **Stale code**: Rebuild shared library after changes.

## Code Standards

**Python (Backend):** Type hints, ruff format/check, async/await, Pydantic. See `server/CLAUDE.md`.

**TypeScript (Frontend):** Strict mode, no `any`, functional components, named exports. See `shared/CLAUDE.md`.

## Key Architecture Decisions

1. **WebSocket for real-time**: All drawing updates stream via WebSocket at 60fps
2. **Claude Agent SDK sandbox**: Agent code executes in isolated sandbox
3. **Paint mode is program painting**: the agent writes a Python painting program
   (`studio/painting.py`) against `code_monet.paintlib` and runs it with the `paint`
   tool; the server renders versions (keyframes + reveal log) and clients reveal them
   stroke by stroke. See [docs/program-painting.md](docs/program-painting.md).
   Plotter mode still uses path definitions (`draw_paths` / `generate_svg`).
4. **Stateless agent turns**: Each agent turn receives full context (canvas image + notes)

## Testing Requirements

- Backend: pytest with async support
- Web: Vitest (`web/src/test/`)
- Native iOS: `swift test` in `ios/MonetKit` (see `ios/ARCHITECTURE.md`)
- All new features need tests
- Run `make test` before committing (server + web + MonetKit)

## Integration & E2E Tests

Multiple test types validate different layers of the system:

```bash
make test-e2e              # Run all integration tests (SDK + replay)
```

### API Key from SSM

E2E tests that require the Anthropic API key fetch it automatically from AWS SSM Parameter Store. This requires:

1. AWS credentials configured locally (`~/.aws/credentials` or environment variables)
2. Access to the `/code-monet/prod/` SSM path

The make targets set `CODE_MONET_ENV=prod` to enable SSM fetching. No local `.env` file needed.

### SDK Integration Tests

Tests that validate Claude Agent SDK compatibility with real API calls.

```bash
make test-e2e-sdk          # Run SDK integration tests (API key from SSM)
```

These tests catch SDK breaking changes (e.g., parameter renames) before production.

### WebSocket Message Replay Tests

Record-and-replay tests that validate the web app's reducer handles real server messages correctly.

```bash
make test-record-fixture   # Record new fixtures (API key from SSM)
make test-replay           # Replay fixtures through the web reducer (fast, no API)
```

**Fixtures location:** `server/tests/fixtures/` (symlinked to `web/src/test/fixtures/server/`)

Re-record fixtures when:

- Agent message format changes
- New message types are added
- Reducer logic changes

### Native iOS Tests

`ios/MonetKit` has its own fixture replay tests (protocol decode + reducer,
against the same `server/tests/fixtures/*.json`) — see
`ios/ARCHITECTURE.md` §1 (work package 1). Run with `make ios-kit-test`.
`ios/CodeMonetUITests` covers app-shell XCTest UI flows against a booted
Simulator (`make ios-test`); a `-devToken` launch argument marks a test as
requiring a reachable local dev server (`localhost:8000`) rather than gating
any app behavior — see `docs/ios-deployment.md`.

## Common Tasks

### Adding a new WebSocket message type

1. Add type to `server/code_monet/types.py`
2. Add handler function in `server/code_monet/handlers.py`
3. Add to `HANDLERS` dict in `handlers.py`
4. Add type to `shared/src/types.ts`
5. Add handler in `shared/src/websocket/handlers.ts`
6. Rebuild shared: `cd shared && npm run build`

### Modifying the agent prompt

- Paint mode: `server/code_monet/agent/paint_prompt.py`. Its library reference is the
  module docstring of `server/code_monet/paintlib/canvas.py` — keep that docstring
  accurate; it is what the agent learns the paint API from.
- Plotter mode: `server/code_monet/agent/prompts.py`.

### Adding new path types

1. Add type to `PathType` enum in `server/code_monet/types.py`
2. Add interpolation in `server/code_monet/interpolation.py`
3. Add rendering in `web/src/renderers/` (web) and `ios/MonetKit/Sources/MonetRender` (native iOS)

## File Locations

| Directory | Description | Details |
|-----------|-------------|---------|
| `server/code_monet/` | Python backend (FastAPI, agent, WebSocket) | See `server/CLAUDE.md` |
| `ios/CodeMonet/` | Native SwiftUI iOS app | See `ios/ARCHITECTURE.md` |
| `ios/MonetKit/` | Standalone Swift package (protocol, reducer, performer, renderer, networking) | See `ios/ARCHITECTURE.md` |
| `web/src/` | Vite web app | Canvas, debug panel, action bar |
| `shared/src/` | Shared TypeScript library (web only) | See `shared/CLAUDE.md` |

---

## Server Deployment (AWS)

Deploy to production by tagging `main`:

```bash
git checkout main && git pull origin main
git tag v1.0.0
git push origin v1.0.0
```

Use `scripts/remote.py` to manage the server via SSM:

```bash
uv run python scripts/remote.py logs       # View container logs
uv run python scripts/remote.py restart    # Restart container
uv run python scripts/remote.py migrate    # Run migrations
```

Sync production data to local dev (database + workspace):

```bash
cd server && uv run python ../scripts/sync-prod.py            # Full sync
cd server && uv run python ../scripts/sync-prod.py --db-only   # Database only
cd server && uv run python ../scripts/sync-prod.py --ws-only   # Workspace only
```

See [docs/infrastructure.md](docs/infrastructure.md) for full details on Terraform, ECR, SES, and SSR architecture.

---

## Database & Storage

- **SQLite** (via SQLAlchemy async): Auth only (users, invite codes)
- **Filesystem**: Per-user workspace data at `agent_workspace/users/{user_id}/`

```bash
uv run alembic upgrade head                        # Run migrations
uv run python -m code_monet.cli invite create      # Create invite code
uv run python -m code_monet.cli user list          # List users
```

See [docs/database.md](docs/database.md) for full CLI commands and workspace details.

---

## Authentication

**Magic Link (default):** Email -> SES -> Universal Link -> JWT

```bash
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
APPLE_TEAM_ID=PG5D259899
```

See [docs/auth.md](docs/auth.md) for API examples and Universal Links setup.

---

## iOS Deployment (TestFlight)

```bash
git tag v1.0.0 && git push origin v1.0.0
```

See [docs/ios-deployment.md](docs/ios-deployment.md) for required GitHub secrets and Fastlane setup.

---

## Observability

```bash
uv run python scripts/diagnose.py status           # Quick health check
uv run python scripts/diagnose.py errors 60        # Recent errors
uv run python scripts/diagnose.py logs 30          # Application logs
```

See [docs/observability.md](docs/observability.md) for full diagnose CLI reference.

---

## Analytics

Dashboard: https://monet.dmfenton.net/analytics/

See [docs/analytics.md](docs/analytics.md) for Umami setup.

---

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for common issues with Docker, SQLite, SSM, and the slim image.

## Codex Review Gate

The required `Codex review gate` status comes from the pinned
`dmfenton/codex-review-gate` workflow (`.github/workflows/codex-p1-gate.yml`),
which caps review at two Codex rounds per PR. Follow its procedure:

- Never merge a pull request until the `Codex review gate` check passes on its current head.
- Request the first review only after implementation and local checks are complete: comment `@codex review <!-- codex-request-generation:<full head SHA>:<full base SHA> -->`. Allow only one request per head SHA; never request after trivial pushes.
- Address every Codex review comment, regardless of severity: fix it (or reply why not), reply on the thread, and resolve it. P0/P1 findings block the gate; P2/P3 findings are advisory to the gate but still get a reply.
- If the first review reports P0/P1 findings, fix them together, push, and request one final review for the new head. A review with no blocking finding is already the final round.
- After the final round, fix any blocking findings, reply to and resolve each thread, rerun the local checks, and dispatch the gate with `gh workflow run codex-p1-gate.yml -f pr_number=<n>`. Never request a third review. The gate accepts a head that descends from the final reviewed commit with no unresolved blocking Codex thread, including later base-branch merges; the base advancing after the final review is a warning, not a block.
- Immediately before merge, re-query the live review threads and stop if any Codex thread is unresolved; never rely only on an earlier green status.
