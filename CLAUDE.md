# Code Monet - Development Instructions

## Project Overview

Code Monet is an autonomous AI artist application with:

- **Backend**: Python 3.12+ with FastAPI, Claude Agent SDK, WebSocket support
- **Frontend**: React Native with Expo, TypeScript, react-native-svg

## Environment Setup

- `.env` file lives in **project root** (not server/)
- Config loads from both `../.env` and `.env` so it works from any directory
- Production Claude auth uses Anthropic AWS workload identity; static Anthropic keys are unsupported

## Package Management

**This project uses npm workspaces.**

### Workspace Structure

```
/                    # Root workspace
├── app/             # React Native app (Expo)
├── web/             # Vite web app
├── shared/          # Shared TypeScript library
└── server/          # Python backend (uses uv, not npm)
```

### Key Rules

1. **Always use npm** - Run `npm install` from project root
2. **Build shared after changes** - Run `cd shared && npm run build` after modifying shared/
3. **Install from root** - Run `npm install` from project root, not subdirectories

### Adding Dependencies

```bash
# Add to specific workspace
npm install <package> -w app
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
rm -rf node_modules app/node_modules web/node_modules shared/node_modules package-lock.json
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
| Required status checks            | CI Success                |
| Require branches to be up to date | Yes                       |
| Enforce for admins                | No (can bypass if needed) |
| Force pushes                      | Blocked                   |

PRs to main require the "CI Success" check to pass before merging.

**Important:** Even though admin bypass is enabled, always use PRs. Never push directly to main.

### CI Path Filters

CI jobs only run when relevant code changes:

| Job                | Runs when these paths change                     |
| ------------------ | ------------------------------------------------ |
| Server (Python)    | `server/**`                                      |
| App (React Native) | `app/**`, `web/**`, `shared/**`, `package*.json` |
| Replay Tests       | `app/**`, `web/**`, `shared/**`, `package*.json` |
| Docker Build       | `server/**` (after Server job passes)            |

The "CI Success" job consolidates results - it passes if all jobs either pass or are appropriately skipped.

## Development Servers

### Live Reload (IMPORTANT)

Both servers have **live reload enabled by default** - they auto-restart on file changes:

- **Python server**: Uvicorn with watchfiles (reload=True in dev mode)
- **React Native app**: Expo with Metro bundler hot reload

**DO NOT manually restart servers after code changes.** Just save the file and wait 1-2 seconds.

### Starting Dev Servers

```bash
make dev       # Server + Expo app (foreground, Ctrl+C to stop)
make dev-web   # Server + Vite web app (foreground, Ctrl+C to stop)
make dev-stop  # Force-kill any stuck servers by port
```

**Ports:**

- Python server: http://localhost:8000
- Expo app: http://localhost:8081
- Vite web: http://localhost:5173

Both have live reload - no restarts needed for code changes.

**Only restart if:**

- Changed dependencies (pyproject.toml, package.json)
- Server crashed
- Stale behavior after 5+ seconds post-save

**Stuck ports?** Run `make dev-stop` to force-kill by port, then start again.

### Simulator Screenshots (Debugging)

Use `/screenshot` to capture the iOS simulator screen when debugging mobile issues.

Screenshots are saved to `screenshots/` (gitignored) and displayed for analysis.

### App Screenshots (Web/Expo)

Use `/app-screenshot` or `scripts/app-screenshot.py` to capture the Expo app running in web mode:

```bash
# Basic screenshot
uv run python scripts/app-screenshot.py --expo-port 5173

# With auth (loads user workspace)
uv run python scripts/app-screenshot.py --auth --expo-port 5173

# Wait for content and specific selector
uv run python scripts/app-screenshot.py --auth --wait 3 --selector "[data-testid='canvas-view']"

# Custom viewport (iPhone 15 Pro Max)
uv run python scripts/app-screenshot.py --viewport 430x932
```

**Ports:** Use `--expo-port 5173` for Vite web, `--expo-port 8081` for Expo web.

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

# Use Vite web app (port 5173) instead of Expo (8081)
uv run --project server python scripts/visual-flow-test.py "draw shapes" --expo-port 5173

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
| `--expo-port N` | 8081 | App port (8081 mobile, 5173 web) |
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
- Which codebase? `app/src/` (mobile) vs `web/src/` (web) vs `shared/src/`
- Rebuild shared after changes: `cd shared && npm run build`

#### 3. Code

Implement the fix. Run typecheck:

```bash
npm run -w app typecheck    # Mobile app
npm run -w web typecheck    # Web app
npm run -w shared build     # Rebuild shared if changed
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
| `/app-screenshot` | Capture Expo/Vite web app |
| `/screenshot` | Capture iOS simulator |

**Critical: Two different web servers**

| Port | Server | Codebase | Test For |
|------|--------|----------|----------|
| 8081 | Expo Web | `app/src/` | Mobile UI (HomePanel, GalleryModal, Canvas) |
| 5173 | Vite | `web/src/` | Web app (studio, homepage) |

```bash
# Mobile app (port 8081)
/app-screenshot --auth --wait 3 --expo-port 8081

# Web app (port 5173)
/app-screenshot --auth --wait 3 --expo-port 5173

# Wait for specific element
/app-screenshot --auth --selector "[data-testid='home-panel']" --expo-port 8081
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
| `/dev` | Start dev servers (server + Expo mobile on 8081) |
| `/dev-web` | Start dev servers (server + Vite web on 5173) |
| `/diagnose` | X-Ray traces and CloudWatch logs |
| `/app-screenshot` | Screenshot Expo/Vite web app |
| `/screenshot` | Screenshot iOS simulator |
| `/remote` | Run commands on prod via SSM |
| `/pr` | Create PR, run code review |
| `/release` | Cut a release |
| `/sync-prod` | Sync production data to dev |

#### Quick Reference

**TestIDs for `--selector`:**

Mobile app (port 8081):

| Element | Selector |
|---------|----------|
| HomePanel | `[data-testid="home-panel"]` |
| Canvas | `[data-testid="canvas-view"]` |
| Continue button | `[data-testid="home-continue-button"]` |
| Gallery button | `[data-testid="home-gallery"]` |
| Surprise Me | `[data-testid="home-surprise-me"]` |

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
- **Wrong screen**: Mobile app `inStudio` state. Background app returns to HomePanel.
- **Wrong port**: 8081 for mobile features, 5173 for web features.
- **Stale code**: Rebuild shared library after changes.

## Code Standards

**Python (Backend):** Type hints, ruff format/check, async/await, Pydantic. See `server/CLAUDE.md`.

**TypeScript (Frontend):** Strict mode, no `any`, functional components, named exports. See `shared/CLAUDE.md`.

## Key Architecture Decisions

1. **WebSocket for real-time**: All drawing updates stream via WebSocket at 60fps
2. **Claude Agent SDK sandbox**: Agent code executes in isolated sandbox
3. **Path-based drawing**: Agent writes code that outputs path definitions, not pixel data
4. **Stateless agent turns**: Each agent turn receives full context (canvas image + notes)

## Testing Requirements

- Backend: pytest with async support
- Frontend: Jest + React Native Testing Library
- All new features need tests
- Run `make test` before committing

## Integration & E2E Tests

Multiple test types validate different layers of the system:

```bash
make test-e2e              # Run all integration tests (SDK + replay, no iOS simulator)
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

Record-and-replay tests that validate app reducer handles real server messages correctly.

```bash
make test-record-fixture   # Record new fixtures (API key from SSM)
make test-replay           # Replay fixtures through app reducer (fast, no API)
```

**Fixtures location:** `server/tests/fixtures/` (symlinked to `app/src/__tests__/fixtures/server/`)

Re-record fixtures when:

- Agent message format changes
- New message types are added
- Reducer logic changes

### iOS Simulator Tests (Maestro)

See next section for Maestro-based E2E tests that require iOS simulator.

## E2E Testing (Maestro)

E2E tests use [Maestro](https://maestro.mobile.dev/) to test iOS simulator flows.

### Running E2E Tests

```bash
make e2e              # Run all E2E tests
make e2e-install      # Install Maestro + Java dependencies
./scripts/e2e.sh auth.yaml  # Run single test
```

### Test Structure

```
app/e2e/
├── flows/           # Test files
│   ├── auth.yaml    # Magic link flow (runs first, needs clean state)
│   ├── action-bar.yaml
│   ├── canvas.yaml
│   └── websocket.yaml
└── helpers/
    └── inject-auth.yaml  # Shared auth injection helper
```

### Key Learnings

**Simulator state:**

- `simctl erase` required before auth test - Keychain persists across app uninstall
- Auth injection uses `simctl launch` then `simctl openurl` (app must be running for deep links)

**Maestro tips:**

- Use `testID` props, not text matching (icons break text selectors)
- Use `optional: true` for dialogs that may or may not appear
- `extendedWaitUntil` with timeout for async operations
- Coordinate taps (`point: "95%,52%"`) are fragile - prefer testIDs

**iOS-specific:**

- "Open in App?" dialog appears on fresh simulator - handle with optional tap
- `back` command doesn't work for modals - use testID on close button
- Swipe gestures can interfere with subsequent button taps

### Adding TestIDs

Add `testID` prop to React Native components for E2E selection:

```tsx
<Pressable testID="my-button" onPress={handlePress}>
```

**Current testIDs:**

- AuthScreen: `email-input`, `code-input`, `auth-submit-button`
- Canvas: `canvas-view`
- StatusPill: `status-pill`
- ActionBar: `action-bar`, `action-draw`, `action-nudge`, `action-new`, `action-gallery`, `action-pause`
- StartPanel: `surprise-me-button`
- NudgeModal: `nudge-close-button`

### Rebuilding After TestID Changes

TestIDs are compiled into the native app. After adding new testIDs:

```bash
rm -rf ~/Library/Developer/Xcode/DerivedData/CodeMonet-*
cd app && npx expo prebuild --platform ios --clean
xcodebuild -workspace ios/CodeMonet.xcworkspace -scheme CodeMonet \
  -configuration Debug -sdk iphonesimulator \
  -destination "platform=iOS Simulator,id=$(xcrun simctl list devices -j | python3 -c "import sys,json; print([d['udid'] for r,devs in json.load(sys.stdin)['devices'].items() if 'iOS-18' in r for d in devs if 'iPhone 16 Pro' in d['name']][0])")" \
  build
```

## Common Tasks

### Adding a new WebSocket message type

1. Add type to `server/code_monet/types.py`
2. Add handler function in `server/code_monet/handlers.py`
3. Add to `HANDLERS` dict in `handlers.py`
4. Add type to `shared/src/types.ts`
5. Add handler in `shared/src/websocket/handlers.ts`
6. Rebuild shared: `cd shared && npm run build`

### Modifying the agent prompt

Edit `server/code_monet/agent.py` - the `SYSTEM_PROMPT` constant

### Adding new path types

1. Add type to `PathType` enum in `server/code_monet/types.py`
2. Add interpolation in `server/code_monet/interpolation.py`
3. Add SVG rendering in `app/src/components/Canvas.tsx`

## File Locations

| Directory | Description | Details |
|-----------|-------------|---------|
| `server/code_monet/` | Python backend (FastAPI, agent, WebSocket) | See `server/CLAUDE.md` |
| `app/src/` | React Native mobile app | Components, hooks, utils |
| `web/src/` | Vite web app | Canvas, debug panel, action bar |
| `shared/src/` | Shared TypeScript library | See `shared/CLAUDE.md` |

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

- Never merge a pull request until the `Codex review gate` check passes.
- Address every Codex review comment, regardless of severity, and resolve every Codex review thread before merge.
- After every push, comment `@codex review` and wait for a clean review that names the exact current head SHA.
- A clean review or green check for an earlier commit never authorizes merging a newer head.
