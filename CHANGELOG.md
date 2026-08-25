# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Publish Code Monet's app-owned Fenton Platform tenant manifest only by explicit dispatch from `main`, with exact source verification during activation.
- Replace custom TestFlight certificate-import and keychain cleanup shell with the pinned maintained Apple Actions importer while retaining explicit signing-identity validation.

### Fixed

- Replace PID-based Platform bootstrap locking with kernel-backed locking that safely survives stale files and PID reuse.
- Serialize shared Platform source fetches across isolated worktrees and run the tenant contract when CodeMonet's shared OAuth constants change.

## [1.39.3] - 2026-08-23

### Fixed

- Temporarily add the isolated signing keychain to Xcode's user search list during TestFlight archives, then restore the runner's original search list before deleting the CI keychain.

## [1.39.2] - 2026-08-23

### Fixed

- Resolve the imported Apple Distribution identity explicitly from the isolated CI keychain and pass that identity and keychain to Xcode during archive and export.

## [1.39.1] - 2026-08-23

### Changed

- Upgrade the supported JavaScript toolchain to ESLint 10, Vite 8, TypeScript 6, Vitest 4, jsdom 30, and current compatible type packages.
- Consolidate TypeScript linting on one flat ESLint configuration and explicitly approve only the pinned lifecycle scripts required by Sentry, Skia, esbuild, and macOS file watching.
- Update the uv GitHub Action and keep WebSockets on the newest 16.x release required by `google-genai`.
- Keep automated dependency updates reviewable as individual PRs and run JavaScript audits without requiring the private Python platform checkout.

### Fixed

- Restore Expo SDK 57's exact native compatibility set, including `react-native-svg` 15.15.4, and enforce it in CI.

## [1.39.0] - 2026-08-23

### Added

- Add npm, Python, repository, secret, configuration, and runtime-container security scanning with weekly Dependabot updates.

### Changed

- Move CodeMonet sign-in to shared Fenton Identity OAuth with PKCE, RS256 API verification, and rotating platform refresh tokens.
- Replace the static Anthropic API key with short-lived AWS workload identity federation, including the independent visual critique runtime.
- Upgrade Expo to SDK 57, React Native to 0.86, Python to 3.12, and refresh locked JavaScript and Python dependencies.

### Security

- Disable app-local password, refresh, and magic-link endpoints in production and remove higher-precedence Anthropic credential sources from Claude subprocesses.

## [1.38.2] - 2026-07-25

### Security

- Remove the unused system pip with its fixable advisories and add a backend image health probe so standalone deployments retain the same liveness signal as Compose.

## [1.38.1] - 2026-07-25

### Security

- Replace `python-jose` with PyJWT, pin container bases, run production services as non-root, and remove npm from the Node runtime image.
- Remove obsolete nested lockfiles from the pre-workspaces package layout and update CI runtimes and actions to Node 24-compatible releases.

## [1.38.0] - 2026-06-10

### Added

- Stamp-based painterly stroke renderer: variable width with taper, bristle texture, dry-brush breakup over canvas tooth, per-stamp broken color, watercolor wet edges, impasto lighting, and canvas grain (server `painting.py`, ported to web canvas and Skia Atlas via `shared/renderer/stamping.ts`)
- `critique_canvas` compares the canvas against the active `imagine` reference with a painter's rubric; the reference image stays visible in every agent turn
- Overwork circuit breaker: after 3 consecutive failed critiques the agent is directed to repaint failed regions with opaque masses instead of adding texture
- Homepage hero replays a real recorded artwork (Poplars at Dusk) being painted stroke by stroke — deterministic, no model calls — with phase-synced captions, a brush-tip indicator, title card, and loop
- `scripts/render-study.py` + `studies/` for fast visual iteration on the paint pipeline; `--json` exports stroke data for replay

### Changed

- Public showcase replaced with five new works: The Great Wave (after Hokusai), Poplars at Dusk, The Lily Pond, Village Nocturne, Field of Poppies
- Agent-facing canvas images are JPEG-encoded (textured renders exceeded the SDK's 1MB message buffer); SDK buffer raised to 16MB
- Quality gate generalized: removed wave-specific structural helpers and critique-keyword repair forcing

### Fixed

- Malformed model-emitted hex colors no longer crash a render mid-turn (shorthand and 8-digit alpha hex now parse; garbage falls back to gray)

## [1.37.3] - 2026-04-02

### Fixed

- Agent orchestrator auto-pauses on unrecoverable API errors (credit balance, auth, billing) to prevent CPU-burning retry loops
- Transient errors now clear the wake event to prevent immediate retries

### Changed

- Homepage hero drawings replaced with real user paintings from public gallery

## [1.37.2] - 2026-02-09

### Fixed

- LiveStatus stuck on "Thinking" during executing/drawing — status now driven by performance model only
- Missing tool labels for imagine, sign_canvas, and name_piece (showed generic "Executing...")

### Changed

- LiveStatus header shows tool-specific icon, label, and color when a tool event is active

## [1.37.1] - 2026-02-09

### Fixed

- Pen bouncing during brush stroke animation by removing redundant server-side bristle expansion (client already handles this via getBristleOutlines)

## [1.37.0] - 2026-02-09

### Changed

- iOS app rendering engine switched from react-native-svg to @shopify/react-native-skia for GPU-accelerated drawing
- Renderer picker removed from home panel — Skia is now the sole iOS renderer (SVG/Freehand remain available in web)

### Fixed

- iOS ANR (Application Not Responding) during stroke animation by memoizing completed strokes layer — prevents re-serializing 700+ SVG elements to GPU on every 60fps frame

### Removed

- Stroke settling effect (85% opacity fade-in on newly committed strokes) — removed to fix iOS performance
- SvgRenderer, FreehandSvgRenderer, and associated SVG components from iOS app (replaced by SkiaRenderer)

## [1.36.0] - 2026-02-08

### Added

- Animation realism: pen travel with ease-in-out interpolation between strokes, inter-stroke pauses (200ms), and pen settle delays (50ms) for natural drawing cadence
- Speed easing within each stroke (sine curve: slow→fast→slow) to mimic hand movement
- Stroke settling effect: newly committed strokes render at 85% opacity for 200ms before fading to full
- Velocity-based pen pressure simulation in freehand stroke tails (closer points = thicker stroke)
- Curvature-adaptive point density on server: curved segments get more points (slower animation), straight segments fewer (faster)
- Smooth Catmull-Rom→Bezier curves for plotter mode agent strokes
- `fetchStrokesWithRetry` shared utility replacing the old pending strokes polling pattern

### Changed

- Extracted `useSettlingStrokes` hook and `applyVelocityPressure` utility into shared library (deduplicated from 4 and 2 renderer files respectively)
- Replaced `STROKES_READY`/`PendingStrokesInfo`/`usePendingStrokes` pattern with simpler REST-based fetch with retry and abort support

### Removed

- `interpolate_polyline` (replaced by `interpolate_polyline_adaptive`)
- `usePendingStrokes` hook and `PendingStrokesInfo` type
- `handleAgentStrokesReady` WebSocket handler

## [1.35.15] - 2026-02-08

### Fixed

- Pending strokes not re-fetched after WebSocket reconnection — batch tracker (`lastFetchedBatchRef`) never reset on reconnect, causing canvas to stay idle (especially on iOS which aggressively kills background connections)

### Added

- Production tracing events at key stroke pipeline stages (`strokes.ready`, `strokes.fetch_start`, `strokes.fetch_complete`, `strokes.fetch_error`, `strokes.enqueued`) for visibility via `/diagnose`

## [1.35.14] - 2026-02-07

### Fixed

- WebSocket auth token stripped by nginx proxy — query params lost when proxy_pass uses variable (regression from v1.35.5 DNS fix)

## [1.35.13] - 2026-02-07

### Fixed

- WebSocket stays stuck on "Connecting..." after token refresh due to stale close event race condition

## [1.35.12] - 2026-02-07

### Fixed

- Submit button on iOS HomePanel not responding when keyboard is open (restore ScrollView with keyboardShouldPersistTaps)

## [1.35.11] - 2026-02-07

### Fixed

- Allow typing drawing prompt while WebSocket is connecting (submit still requires connection)
- Fix prompt input focus on iOS (ScrollView + KeyboardAvoidingView conflict)

## [1.35.10] - 2026-02-07

### Fixed

- Prompt text input on mobile home screen could not be focused/selected

## [1.35.9] - 2026-02-01

### Fixed

- Drawing style toggle (plotter/paint) now works correctly — style is applied locally and sent with new canvas instead of via separate WebSocket message

### Removed

- Removed unused `set_style` WebSocket message type and server handler

## [1.35.8] - 2026-01-31

### Fixed

- Home button works when viewing paused gallery piece

## [1.35.7] - 2026-01-31

### Added

- Production-to-dev sync script (`scripts/sync-prod.py`) for automated database and workspace transfer
- Disable interaction on completed canvases

### Fixed

- Composite paint mode strokes individually for correct layering
- Add home button to gallery screen when in studio

## [1.35.6] - 2026-01-31

### Fixed

- Gallery piece viewing is now read-only via REST — no longer overwrites current WIP canvas
- Restart nginx container on release deploy

## [1.35.5] - 2026-01-29

### Fixed

- Strip /api/ prefix when proxying to backend via nginx

## [1.35.4] - 2026-01-28

### Fixed

- Update Umami analytics website ID

## [1.35.3] - 2026-01-27

### Changed

- Optimized stroke animation for smoother rendering with reduced CPU usage
- Server interpolation now produces fewer points (0.2 vs 0.5 points/pixel) with automatic deduplication of sub-pixel movements
- Stroke animation batches multiple points per frame for consistent visual speed (~300px/sec)
- Added InProgressStroke component with body/tail caching to minimize freehand recalculations during animation

## [1.35.2] - 2026-01-26

### Fixed

- Freehand strokes now render correctly when server sends null for unset style properties (opacity)

## [1.35.1] - 2026-01-25

### Fixed

- Pause/resume buttons now respond immediately with optimistic UI updates instead of waiting for server confirmation
- Fixed "Object is not a function" crash in Canvas gesture handlers caused by stale closures during rapid state changes
- Events (like "Drawing paths...") now permanently replace thinking text in mobile LiveStatus instead of allowing it to return after the event completes
- Freehand stroke color now displays correctly on first render in FreehandSvgRenderer

## [1.35.0] - 2026-01-24

### Added

- Live WIP preview on Continue card shows current drawing strokes instead of placeholder

## [1.34.0] - 2026-01-24

### Added

- Renderer picker in HomePanel for switching between SVG and Freehand renderers
- FreehandSvgRenderer using perfect-freehand library for natural brush stroke outlines
- RendererContext for managing renderer configuration across app
- Renderer abstraction layer in shared library (`shared/src/renderer/`)
- `--renderer` option in visual-flow-test.py for testing different renderers
- Public thumbnail endpoint `/public/gallery/{user_id}/{piece_id}/thumbnail.png` for consistent gallery rendering
- `pathToSvgDScaled` utility in shared library for scaled SVG path rendering

### Fixed

- Web homepage gallery images now render identically to mobile (switched from client-side SVG to server PNG thumbnails)
- Mobile ContinueCard now uses correct 4:3 canvas aspect ratio (was 16:9)
- Mobile ContinueCard thumbnails now load correctly in Expo web mode via `useAuthenticatedImage` hook
- Event text (svg, imagine, etc.) now displaces thinking text in LiveStatus instead of overlapping
- Gallery image selection now correctly loads the selected image instead of a previously cached one
- Home screen now shows "Work in progress" placeholder instead of stale gallery thumbnail when there's an active drawing

## [1.33.4] - 2026-01-24

### Added

- Agent automatically pauses when all clients disconnect to save API costs
- Agent automatically resumes when client reconnects (if paused due to disconnect)
- User-initiated pauses are preserved across reconnections

### Fixed

- Idle animation now turns off when agent starts drawing, not when first stroke completes
- Event text (svg, imagine, draw_paths) now displays in mobile LiveStatus during tool execution

## [1.33.3] - 2026-01-23

### Added

- Continue option now appears on home screen when a session is paused mid-drawing (even if no strokes rendered yet)

### Changed

- App now stays on canvas when backgrounded instead of returning to home screen
- Agent auto-resumes on foreground if it was running before backgrounding

## [1.33.2] - 2026-01-23

### Fixed

- Single-point strokes now render as visible circles instead of invisible zero-length paths
- Stroke widths clamped to [0.5, 30] range to prevent rendering artifacts
- Brush expansion points clamped to canvas boundaries preventing out-of-bounds strokes

### Added

- Painting experiment scripts for stroke correctness analysis

## [1.33.1] - 2026-01-22

### Fixed

- nginx now re-resolves Docker container IPs every 10s, eliminating 502 errors after container restarts

## [1.33.0] - 2026-01-21

### Changed

- HomePanel layout reordered: Start Drawing section now at top, Continue section below with smaller 16:9 thumbnail
- Removed "More options" toggle - style picker and Surprise Me button always visible

### Documentation

- Reduced CLAUDE.md from 41KB to 18KB by extracting detailed docs to modular files
- Added docs/infrastructure.md, docs/database.md, docs/auth.md, docs/ios-deployment.md, docs/observability.md, docs/analytics.md, docs/troubleshooting.md, docs/claude-sandbox.md

## [1.32.0] - 2026-01-21

### Added

- `scripts/app-screenshot.py` - Playwright-based screenshot tool for debugging Expo web app with mobile viewport simulation
- `/app-screenshot` Claude command for capturing mobile app screenshots during development
- Centralized API client (`app/src/api/client.ts`) with authenticated fetch and image source helpers
- `useAuthenticatedImage` hook for loading images with authentication (blob URL workaround for web)
- Gallery images now load via authenticated API on both native and web platforms
- `/sync-prod` Claude command for syncing production data to local development
- Structured JSON logging for CloudWatch compatibility with category detection and trace ID correlation
- `scripts/logs.sh` - Local development log convenience script
- `scripts/logs-prod.sh` - Production log operations via CloudWatch/SSM

### Changed

- Consolidated `/diagnose` and `/logs` Claude skills into unified `/diagnose` command
- Renamed `/dev-mobile` to `/dev`, added `/dev-web` for Vite web development
- Gallery thumbnails now use authenticated image loading instead of public token URLs
- Centralized image rendering into new `rendering.py` module for consistency and reduced duplication
- Logging configuration moved from inline `basicConfig` to dedicated `logging_config.py` module

### Fixed

- Gallery thumbnails and share previews now render with correct drawing styles (paint mode shows actual colors)
- OG social sharing images now respect the artwork's drawing style

### Documentation

- Added module architecture documentation to `server/CLAUDE.md` covering agent/, tools/, workspace/, types/, and routes/ packages

## [1.31.0] - 2026-01-20

### Fixed

- Gallery stroke rendering now uses actual stroke colors, widths, and opacity instead of hardcoded values
- Gallery path rendering now correctly handles all path types (line, quadratic, cubic, polyline)

### Changed

- Refactored `workspace_state.py` into modular `workspace/` package with 4 focused modules
- Refactored `types.py` into modular `types/` package with 6 focused modules
- Refactored `main.py` routes into modular `routes/` package with 11 focused modules
- Refactored `tools.py` into modular `tools/` package with focused submodules for maintainability

## [1.30.0] - 2026-01-20

### Added

- Static Open Graph image (1200x630) for improved social media link previews
- Complete Open Graph and Twitter Card meta tags with image dimensions and alt text

### Changed

- App now pauses agent and returns to home screen when going to background
- Umami analytics database moved to EBS volume for persistence

### Fixed

- Stroke animation no longer triggers on home screen (was firing behind HomePanel)
- Server no longer sends `agent_strokes_ready` notification when agent is paused

## [1.29.1] - 2026-01-20

### Changed

- Gallery listing now scans piece files directly instead of using `_index.json` index file
- Simplified gallery architecture by removing redundant state tracking

## [1.29.0] - 2026-01-20

### Added

- `scripts/ws-client.py` - Terminal WebSocket client for testing agent interactions (view, test, watch, start, pause, resume, nudge, clear, status commands)
- Animation done signaling: Client signals server when stroke animation completes
- Debug log forwarding infrastructure (dev mode only)

### Fixed

- `sign_canvas` tool now triggers stroke animation (was appearing instantly instead of animating)
- Fixed dev model name from invalid `claude-haiku-4-20250414` to `claude-haiku-4-5-20251001`

### Changed

- Agent uses Claude Haiku in dev mode for cost reduction, Opus in production
- Agent loop only runs on explicit user actions (nudge, resume, new_canvas) - no automatic retries
- Agent waits for animation_done signal from client (with timeout fallback) instead of fixed sleep
- Redesigned app launch experience with new HomePanel showing last canvas thumbnail, quick prompt input, and expandable options
- App now always starts on HomePanel instead of directly entering canvas view
- Replaced ActionBar "New" button with "Home" button for navigating back from studio

## [1.28.0] - 2026-01-19

### Added

- `sign_canvas` tool: Agent can sign completed pieces with "Code Monet" signature in elegant cursive script
- `name_piece` tool: Agent can give evocative titles to completed artwork before saving
- Piece titles stored in gallery entries and displayed with artwork
- Agent now follows a finishing ritual: sign the canvas, name the piece, then mark done

## [1.27.3] - 2026-01-19

### Fixed

- Nginx OG image route now correctly strips `/api/` prefix when proxying to backend

## [1.27.2] - 2026-01-19

### Added

- OG image endpoint for social sharing (`/public/gallery/{user_id}/{piece_id}/og-image.png`)
- Renders gallery pieces to 1200x630 PNG for iMessage, Twitter, etc. previews
- Nginx proxy caching for OG images (7-day cache)

## [1.27.1] - 2026-01-19

### Fixed

- SSR server crash on startup due to Express 5 incompatible catch-all middleware syntax

## [1.27.0] - 2026-01-19

### Added

- SSR production deployment with containerized Node.js server
- `web-ssr` ECR repository for SSR container images
- `/ssr-health` endpoint for SSR server health monitoring
- Graceful SSR fallback to static SPA on 502/503/504 errors

### Changed

- Release workflow now builds and deploys both backend and SSR containers
- nginx routes page requests to SSR server (static assets served directly)

### Infrastructure

- IAM policy updated to allow ECR push for `web-ssr` repository

## [1.26.3] - 2026-01-19

### Fixed

- Nginx now serves from `web/client` directory (SSR build output location)
- Remove unsupported `awslogs-stream-prefix` option from docker-compose logging
- Remove obsolete `version: '3.8'` from docker-compose.prod.yml

## [1.26.2] - 2026-01-19

### Fixed

- Release workflow now syncs deploy config from S3 to server before running docker-compose (fixes v1.26.1 deployment failure where server had stale docker-compose.prod.yml)

## [1.26.1] - 2026-01-19

### Fixed

- Docker Compose image reference now includes repository name (`/drawing-agent`) for correct ECR pull
- Release workflow now uses `--force-recreate` to ensure containers are recreated with new images

## [1.26.0] - 2026-01-19

### Added

- Server-side rendering (SSR) for SEO and LLM accessibility
- Express SSR server with Vite integration for development and production
- Individual gallery piece pages at `/gallery/:userId/:pieceId` with unique metadata
- Full gallery listing page at `/gallery`
- Dynamic meta tags and Open Graph metadata per artwork
- JSON-LD structured data (schema.org VisualArtwork) for rich search results
- `/sitemap.xml` endpoint listing all public gallery pieces
- `/robots.txt` endpoint for search engine crawler guidance
- React Router v6 for SSR-compatible client-side navigation

### Fixed

- AI now sees brush-expanded strokes in paint mode (was seeing original paths while users saw expanded brush effects)
- Mobile thinking display now shows all streamed words progressively (was only showing first chunk due to closure capture bug in timer callback)
- Release workflow now correctly updates IMAGE_TAG in `/home/ec2-user/.env` (was incorrectly using `/home/ec2-user/data`)
- Release workflow now re-authenticates with ECR before pulling images to prevent expired token errors
- Release workflow migrations now use correct database (fetches DATABASE_URL from SSM to pass to one-off container)

## [1.25.1] - 2026-01-18

### Fixed

- Public gallery endpoint now correctly handles gallery index stored as plain list (was expecting `{"pieces": [...]}` wrapper)

## [1.25.0] - 2026-01-18

### Added

- Brush presets for paint-like stroke rendering with 12 brush types:
  - Oil brushes: `oil_round`, `oil_flat`, `oil_filbert` (visible bristle texture)
  - Watercolor: translucent strokes with soft edges
  - Dry brush: scratchy, broken stroke texture
  - Palette knife: sharp edges, thick paint application
  - Ink: pressure-sensitive calligraphy style
  - Pencil, charcoal: sketching tools
  - Marker, airbrush, splatter: special effects
- Server-side brush stroke expansion with bristle sub-strokes, velocity-based width variation, and edge noise
- `brush` parameter in `draw_paths` and `generate_svg` tools (paint mode only)
- `BRUSHES` list available in `generate_svg` code for iterating brush names
- Public gallery opt-in: users can share their artwork on the homepage via `PUT /settings/gallery`
- `GET /settings/gallery` endpoint to check current gallery visibility setting
- `gallery_public` column on users table (default: false, opt-in required)

### Changed

- Public gallery now aggregates artwork from all opted-in users instead of single featured user
- Public gallery strokes endpoint now validates user has opted in before serving artwork

### Removed

- `homepage_featured_email` configuration setting (replaced by user opt-in)

### Fixed

- Race condition where agent strokes could be silently dropped if `agent_strokes_ready` message arrived before `piece_state` update

## [1.24.0] - 2026-01-18

### Added

- CloudWatch Logs integration for centralized application logging
- Log query commands in diagnose.py (`logs`, `logs-errors`, `logs-user`, `logs-search`)
- `/logs` Claude skill for querying production logs
- Logrotate configuration for application log files (daily, 7 days, max 100MB)
- CloudWatch alarms for high error rates (>10 errors in 5 minutes)

### Infrastructure

- CloudWatch Log Groups: `/drawing-agent/app` (30 days), `/drawing-agent/errors` (90 days), `/drawing-agent/containers` (14 days)
- Metric filters for error counting and auth failures
- CloudWatch agent config for file-based log collection

## [1.23.0] - 2026-01-18

### Added

- Shared `useProgressiveText` hook for word-by-word text reveal animation
- CI path filters to skip jobs when relevant code doesn't change

### Changed

- Release workflow now uses explicit SSM deployment instead of Watchtower for more reliable deployments
- Simplified mobile `LiveStatus` and web `StatusOverlay` to use shared hook

### Fixed

- Stroke animation not starting when agent begins thinking immediately after draw_paths completes
- Bionic reading display showing all text at once instead of progressive word-by-word reveal
- CI migration check failing on fresh database (now creates data directory and runs migrations first)

## [1.22.0] - 2026-01-17

### Fixed

- Recovered missing commits from PRs #106 and #107 that were lost during branch reconciliation
- Removed gallery count badge from action bar button

### Documentation

- Corrected README architecture description (sandboxed → in-process MCP tools)
- Clarified branch strategy in CLAUDE.md (main is source of truth, release branches are temporary)

## [1.21.6] - 2026-01-17

### Fixed

- Cross-canvas rendering bug where strokes from previous canvas could render on new canvas
- Added `piece_id` to `agent_strokes_ready` messages and `/strokes/pending` endpoint for canvas-scoped stroke fetching
- Thinking text accumulation bug - thinking now clears when new iteration starts
- Server now clears pending strokes when `new_canvas()` is called

### Added

- Comprehensive render flow tests covering status transitions, thinking lifecycle, and multi-turn scenarios
- Render debug logging in `useStrokeAnimation` and `StrokeRenderer` for troubleshooting

## [1.21.2] - 2026-01-17

### Fixed

- Updated Claude Agent SDK parameter from `working_directory` to `cwd` (SDK breaking change)

## [1.21.1] - 2026-01-17

### Changed

- Renamed `generate_image` tool to `imagine` for clearer semantics
- Removed `view_reference_image` tool (agents use filesystem `Read` tool instead)

### Fixed

- Corrected inaccuracies in README and fixed Makefile module paths

### Documentation

- Added comprehensive agent tools reference with event streaming details

## [1.21.0] - 2026-01-17

### Added

- Floating particles animation on empty canvas (idle state visual enhancement)
- Image generation tool (`imagine`) using Google Gemini API
- Filesystem and bash tools for agent workspace operations (Read, Write, Glob, Grep, Bash)
- `GOOGLE_API_KEY` config setting (optional, enables image generation tools)

### Changed

- Consolidated WebSocket message types from 18 to 13 for cleaner architecture:
  - Merged `status` + `paused` → `agent_state` (single message for agent state)
  - Merged `piece_count` + `piece_complete` → `piece_state` (single message with completed flag)
  - Separated `GalleryEntry` (metadata only) from `SavedCanvas` (includes strokes)
  - Removed redundant `thinking` message (content already streamed via `thinking_delta`)
- Removed unused code: `executor.py`, `PenMessage`, `ExecutionState`

### Fixed

- In-progress agent strokes now render with their actual color, width, and opacity in paint mode

## [1.20.0] - 2026-01-16

### Fixed

- Race condition when setting drawing style with new canvas (style now sent atomically)

### Changed

- Extracted shared StylePicker component from StartPanel and NewCanvasModal
- Added testIDs to NewCanvasModal style picker buttons for E2E testing

### Added

- Unit tests for handle_new_canvas and handle_set_style handlers

## [1.19.0] - 2026-01-16

### Added

- Swappable drawing styles: plotter (monochrome pen) and paint (full color palette)
- DrawingStyleType enum and DrawingStyleConfig for style management
- Path model extended with optional color, stroke_width, opacity properties
- Style-aware code helpers (line(), polyline(), etc.) with style kwargs
- set_style WebSocket handler for runtime style switching
- Drawing style persisted in workspace and included in init/load_canvas messages
- robots.txt for web crawler control

### Changed

- Agent prompts dynamically generated based on active drawing style
- draw_paths and generate_svg tools support style parameters
- Canvas components render strokes with effective style (color, width, opacity)
- General `hasInProgressEvents()` function gates drawing until all preceding events complete

### Fixed

- Agent no longer auto-continues after piece completion (respects user intent)
- StatusOverlay keeps thinking text visible during executing/drawing states
- Drawing waits for tool execution to complete before starting animation
- Jest moduleNameMapper updated for @code-monet/shared

## [1.18.2] - 2026-01-16

### Changed

- Upgraded TestFlight CI to macOS 26 with Xcode 26 (iOS 26 SDK)

## [1.18.1] - 2026-01-16

### Fixed

- SSM environment variable name mismatch: docker-compose now uses `CODE_MONET_ENV` (was `DRAWING_AGENT_ENV`)

## [1.18.0] - 2026-01-16

### Added

- Dev auto-auth for E2E testing: app auto-authenticates in dev builds when no valid token exists
- Agent draw E2E test (`agent-draw.yaml`): validates agent can draw strokes on canvas
- TestID on `LiveStatus` component for E2E completion detection
- Analytics subdomain (`analytics.monet.dmfenton.net`) for Umami dashboard
- Umami tracking script on web frontend

### Changed

- Canvas no longer auto-clears after piece completion (strokes remain visible)
- `save_to_gallery()` saves current canvas without clearing
- Moved Umami analytics from path-based proxy to dedicated subdomain (BASE_PATH not supported in prebuilt Docker image)

### Fixed

- Gallery stroke count now uses cached `num_strokes` property instead of empty strokes array

## [1.17.0] - 2026-01-16

### Changed

- Extended login session durations: access tokens now last 1 day (was 30 min), refresh tokens last 1 year (was 90 days)
- Split agent message display into two areas: LiveStatus (always visible) shows streaming thoughts and current action; MessageStream (collapsible) shows message history

### Fixed

- Thinking status now displays immediately when agent starts thinking, before streaming text arrives
- LiveStatus moved above canvas in mobile app for better visibility during agent activity

## [1.15.0] - 2026-01-16

### Changed

- Redesigned mobile app color palette to match web homepage aesthetic
- Updated theme from soft impressionist tones to bold, vibrant accents (rose, violet, teal)
- Splash screen redesigned with gradient orbs and floating animations
- StatusOverlay (bionic reading) moved from canvas overlay to dedicated strip above canvas
- "Thoughts" panel now collapsible, starts collapsed by default
- Added message count badge to collapsed thoughts panel header
- Extracted `StrokeRenderer` class from `useStrokeAnimation` hook for testability
- Added 19 unit tests covering stroke rendering logic (batch tracking, retry, animation sequence)

## [1.14.1] - 2026-01-15

### Added

- Self-hosted Umami analytics for privacy-friendly web traffic tracking
- Analytics dashboard at `/analytics/` (IP-restricted to admin)
- `deploy/start-services.sh` for bootstrapping services with SSM secrets

## [1.14.0] - 2026-01-15

### Added

- Maestro E2E tests for iOS simulator (auth, action-bar, canvas, websocket flows)
- `make e2e` and `make e2e-install` targets for E2E testing
- TestIDs on all interactive components for reliable E2E selection
- E2E testing documentation in CLAUDE.md

## [1.13.4] - 2026-01-14

### Changed

- Switched from pnpm to npm workspaces for better React Native compatibility
- Simplified metro.config.js (removed pnpm-specific workarounds)
- Updated Expo SDK 54 dependencies for React 19.1.0

### Added

- `/screenshot` Claude command for iOS simulator debugging

## [1.13.3] - 2026-01-14

### Added

- Version meta tag in index.html (`<meta name="version" content="X.Y.Z">`)
- `__APP_VERSION__` global JS variable for runtime version access

### Fixed

- Release workflow uses `/api/version` endpoint (SPA routing broke `/version`)

## [1.13.2] - 2026-01-14

### Added

- `/web-version` endpoint to check deployed web version

### Fixed

- Web cache busting: HTML now served with no-cache headers
- S3 sync uses `--exact-timestamps` to detect content changes when file size matches

## [1.13.1] - 2026-01-14

### Added

- TestFlight builds now skip when no iOS changes detected (compares app/, shared/, dependencies)
- Manual "Force build" option for TestFlight workflow

### Fixed

- Homepage canvas and thought stream layout stability (prevents CLS during animations)

## [1.13.0] - 2026-01-14

### Added

- Code Monet marketing homepage with live canvas preview and AI artwork gallery
- Web authentication via magic link email (6-digit code verification)
- Public gallery API (`/public/gallery`, `/public/gallery/{user_id}/{piece_id}/strokes`)
- Nginx configuration for serving static web frontend
- Automated web frontend deployment (S3 sync + EC2 systemd timer)
- "About the Artist" and "About the Creator" sections on homepage
- Bionic Reading StatusOverlay for agent thinking display (web and mobile)
- `bionicWord()` and `chunkWords()` utilities in shared library
- StatusOverlay shows executing/drawing/paused status with animations

### Changed

- Web routing uses URL paths (`/` for homepage, `/studio` for authenticated app)
- Simplified web auth to magic link only (removed password authentication)
- Agent now pauses execution while client animates drawing strokes
- `queue_strokes()` returns `(batch_id, total_points)` tuple for animation timing

### Security

- Path traversal protection on public gallery API (validates user_id and piece_id)

## [1.10.0] - 2026-01-11

### Added

- CLI commands for user management: `user list`, `user workspace USER_ID`
- CLI command for workspace inspection: `workspace list`
- Shared `useStrokeAnimation` hook for web and React Native

### Changed

- Decoupled agent drawing from client rendering for improved reliability
- Agent now queues pre-interpolated strokes and notifies clients via WebSocket
- Clients fetch and animate strokes locally via REST API (`GET /strokes/pending`)
- Strokes persist across client reconnections
- Persistence is now entirely server-side; client no longer triggers saves
- Auto-save pieces to gallery when agent marks them done via orchestrator
- Removed legacy single-user state management code (`state.py`, `workspace.py`, `handlers.py`)

### Fixed

- Double piece_count increment when completing pieces (was incremented in both agent.py and workspace_state.py)

## [1.9.3] - 2026-01-11

### Changed

- Upgraded drawing agent from Claude Sonnet 4 to Claude Opus 4.5

### Fixed

- Gallery and workspace data now persists across container restarts (moved to mounted volume)

## [1.9.1] - 2026-01-11

### Fixed

- Magic link verification now works with expo-router (verify token directly instead of redirect)
- Rate limiting checks X-Forwarded-For header for clients behind proxy
- Consistent buffer limit for span re-add on flush failure

### Changed

- Move AuthProvider and ThemeProvider to expo-router layout for all routes

## [1.9.0] - 2026-01-11

### Added

- Distributed tracing from React Native app to AWS X-Ray
- `POST /traces` endpoint for receiving client spans
- WebSocket connection trace ID propagation
- App lifecycle tracing (launch, foreground, background)
- User action tracing (pause, resume, clear, nudge)

## [1.8.1] - 2026-01-11

### Fixed

- Add keyboard avoidance to StartPanel text input

## [1.8.0] - 2026-01-11

### Added

- Redesigned mobile start screen with hero layout

### Changed

- Optimize pen lifts for continuous path drawing (performance improvement)

## [1.7.6] - 2026-01-11

### Fixed

- Add explicit canvas dimensions (800x600) to agent prompts and tools
- Fix broken tests and lint errors, add missing test coverage

## [1.7.5] - 2026-01-11

### Added

- Inject canvas image into tool results after drawing (agent sees result of its work)
- Scrollable code previews for generate_svg tool in message stream

## [1.7.4] - 2026-01-10

### Fixed

- Pass ANTHROPIC_API_KEY to Claude Agent SDK subprocess (fixes "invalid api key" error)

## [1.6.0] - 2026-01-05

### Added

- SSM Parameter Store for secrets and config (no more `.env` files)
- App fetches from SSM at startup using IAM role credentials
- Same code path for local dev and prod (`DRAWING_AGENT_ENV=dev|prod`)
- Terraform manages SSM parameters with placeholder values (secrets updated via CLI)

### Changed

- EC2 instance metadata_options in Terraform (hop limit 2 for container SSM access)
- Removed secrets from docker-compose.prod.yml

## [1.5.2] - 2026-01-05

### Fixed

- Add expo-router route for `auth/callback` deep link (fixes "unmatched route" error)

## [1.5.1] - 2026-01-05

### Fixed

- Magic link verification: fix timezone-naive vs aware datetime comparison (SQLite stores naive)

## [1.5.0] - 2026-01-05

### Added

- S3-based config deployment: deploy/ files auto-sync on release, downloaded on EC2 boot
- Terraform-managed S3 bucket for config files with versioning and public access block

## [1.4.2] - 2026-01-05

### Added

- Shareable canvas URLs with Open Graph and Twitter Card meta tags for social media virality
- Public share endpoints at `/s/{token}` with SSR HTML preview page
- Preview image generation at `/s/{token}/preview.png` for social media cards
- Share management endpoints (`POST /s/create`, `GET /s/my-shares`, `DELETE /s/{token}`)
- Apple Smart App Banner on share pages for iOS install prompts
- Release workflow verifies deployment by checking `/version` endpoint

### Fixed

- Watchtower ECR auth: use `credsStore` (not `credHelpers`) with ECR credential helper for IAM-based auth (no tokens, no expiry)

## [1.4.1] - 2026-01-05

### Added

- `/version` endpoint returning app version, commit, and build time
- Docker image labels with OCI metadata (version, revision, created)
- ECR credential helper for automatic Docker auth (no more token expiry)

## [1.4.0] - 2026-01-05

### Added

- OpenTelemetry tracing with AWS X-Ray integration
- ADOT Collector sidecar in docker-compose for trace export
- `/diagnose` skill for querying X-Ray traces from Claude Code
- `scripts/diagnose.py` CLI for trace debugging (recent, errors, trace, path)
- Trace ID included in 500 error responses for debugging

### Changed

- Global exception handler now logs trace IDs for correlation

## [1.3.6] - 2026-01-04

### Fixed

- Add expo-router route for magic link Universal Links (fixes "unmatched route" error)
- Remove TestFlight group assignment (use manual distribution to avoid internal group error)

## [1.3.5] - 2026-01-04

### Fixed

- Add production URL fallback for TestFlight builds (fixes network errors)
- Add beta app feedback email for TestFlight external distribution

## [1.3.4] - 2026-01-04

### Fixed

- Add beta app description for TestFlight external distribution

## [1.3.3] - 2026-01-04

### Fixed

- Add changelog for TestFlight external distribution (required by App Store Connect)
- Correct Alpha group name capitalization

## [1.3.2] - 2026-01-04

### Fixed

- Add `EXPO_PUBLIC_API_URL` for production builds (was falling back to dev IP)
- Auto-distribute TestFlight builds to Alpha group
- Fixed IPA artifact path in CI workflow

## [1.3.1] - 2026-01-04

### Fixed

- Fastlane paths updated to match Expo prebuild output (`CodeMonet` not `DrawingAgent`)

## [1.3.0] - 2026-01-04

### Added

- Magic link 6-digit code verification for local development
- `POST /auth/magic-link/verify-code` endpoint for code-based auth
- Code displayed in email template alongside link
- Code logged in dev mode for easy local testing
- iOS autofill hints (`textContentType`) for email and one-time code fields
- Terraform IAM user for local SES access (minimal permissions)
- Fast Refresh on web via `@expo/metro-runtime`

### Changed

- Config now ignores extra environment variables (AWS credentials)

## [1.2.3] - 2026-01-04

### Added

- Web fallback for magic link verification at `/auth/verify`
- HTML page with app deep link redirect for desktop/web browsers
- `setTokensFromCallback` auth method for deep link token handling
- Support for `codemonet://auth/callback` custom URL scheme

### Fixed

- Magic link now works when clicked in desktop email clients

## [1.2.2] - 2026-01-04

### Added

- Rate limiting on magic link endpoint (3 req/15min per email, 10 req/min per IP)
- Automatic cleanup of expired magic link tokens
- `ses_configuration_set` to config.py for environment-specific SES settings

## [1.2.1] - 2026-01-04

### Fixed

- Magic link verification errors now displayed to users in AuthScreen

### Changed

- Updated CLAUDE.md with magic link authentication documentation

## [1.2.0] - 2026-01-04

### Added

- iOS Universal Links for magic link deep linking
- Apple App Site Association (AASA) endpoint at `/.well-known/apple-app-site-association`
- Deep link handler in React Native app for `/auth/verify` path
- `associatedDomains` configuration for iOS

### Changed

- Magic link is now the default sign-in method in the app
- AuthScreen supports magic link, password sign-in, and sign-up modes

## [1.1.1] - 2026-01-04

### Changed

- Rebranded from "Drawing Agent" to "Code Monet"
- Updated email templates, FastAPI title, and app name
- Fixed magic link base URL to use monet.dmfenton.net

## [1.1.0] - 2026-01-04

### Added

- Magic link (passwordless) authentication via email
- AWS SES integration for sending authentication emails
- SES infrastructure in Terraform (domain verification, DKIM, SPF, DMARC)
- `magic_link_tokens` database table for secure token storage
- `/auth/magic-link` endpoint to request magic links
- `/auth/magic-link/verify` endpoint to exchange tokens for JWT

### Security

- Magic link tokens use 256-bit cryptographic randomness
- Tokens expire after 15 minutes and are single-use
- User enumeration prevented (same response for existing/non-existing emails)

## [1.0.2] - 2026-01-04

### Added

- ECR vulnerability scanning on push
- EBS encryption at rest for data volume
- Secure file permissions (700/600) for database
- `db_utils.py` for local database operations
- `remote.py` for SSM-based server management
- Keep a Changelog format and `/release` command
- Code reviewer now requires changelog updates

### Changed

- SSH access restricted to specific IP (via tfvars)
- Password now required for create-user commands (no defaults)

### Security

- Removed default passwords from scripts
- Added encrypted EBS volume for database storage

## [1.0.1] - 2026-01-03

### Fixed

- Dockerfile health check and dependency installation
- JWT_SECRET environment variable configuration

### Added

- Graceful shutdown handling for containerized deployment
- Watchtower auto-deployment (30s polling)

## [1.0.0] - 2026-01-03

### Added

- JWT-based authentication with refresh tokens
- Invite code system for controlled registration
- Multi-user workspace isolation
- Filesystem-based workspace storage (gallery per user)
- AWS infrastructure (EC2, ECR, Route53, CloudWatch)
- Docker Compose production deployment with nginx + certbot
- GitHub Actions CI/CD pipeline
- Daily EBS snapshots with 7-day retention

### Changed

- Migrated from in-memory to SQLite database
- Migrated workspace storage from database to filesystem

### Features

- Autonomous AI artist powered by Claude Agent SDK
- Real-time canvas updates via WebSocket
- Python-based SVG generation
- Canvas rasterization for agent vision
- React Native mobile app with Expo

[Unreleased]: https://github.com/dmfenton/sketchpad/compare/v1.38.0...HEAD
[1.38.0]: https://github.com/dmfenton/sketchpad/compare/v1.37.7...v1.38.0
[1.37.3]: https://github.com/dmfenton/sketchpad/compare/v1.37.2...v1.37.3
[1.37.2]: https://github.com/dmfenton/sketchpad/compare/v1.37.1...v1.37.2
[1.37.1]: https://github.com/dmfenton/sketchpad/compare/v1.37.0...v1.37.1
[1.37.0]: https://github.com/dmfenton/sketchpad/compare/v1.36.0...v1.37.0
[1.36.0]: https://github.com/dmfenton/sketchpad/compare/v1.35.15...v1.36.0
[1.35.15]: https://github.com/dmfenton/sketchpad/compare/v1.35.14...v1.35.15
[1.35.14]: https://github.com/dmfenton/sketchpad/compare/v1.35.13...v1.35.14
[1.35.13]: https://github.com/dmfenton/sketchpad/compare/v1.35.12...v1.35.13
[1.35.12]: https://github.com/dmfenton/sketchpad/compare/v1.35.11...v1.35.12
[1.35.11]: https://github.com/dmfenton/sketchpad/compare/v1.35.10...v1.35.11
[1.35.10]: https://github.com/dmfenton/sketchpad/compare/v1.35.9...v1.35.10
[1.35.9]: https://github.com/dmfenton/sketchpad/compare/v1.35.8...v1.35.9
[1.35.8]: https://github.com/dmfenton/sketchpad/compare/v1.35.7...v1.35.8
[1.35.7]: https://github.com/dmfenton/sketchpad/compare/v1.35.6...v1.35.7
[1.35.6]: https://github.com/dmfenton/sketchpad/compare/v1.35.5...v1.35.6
[1.35.5]: https://github.com/dmfenton/sketchpad/compare/v1.35.4...v1.35.5
[1.35.4]: https://github.com/dmfenton/sketchpad/compare/v1.35.3...v1.35.4
[1.35.3]: https://github.com/dmfenton/sketchpad/compare/v1.35.2...v1.35.3
[1.35.2]: https://github.com/dmfenton/sketchpad/compare/v1.35.1...v1.35.2
[1.35.1]: https://github.com/dmfenton/sketchpad/compare/v1.35.0...v1.35.1
[1.35.0]: https://github.com/dmfenton/sketchpad/compare/v1.34.0...v1.35.0
[1.26.0]: https://github.com/dmfenton/sketchpad/compare/v1.25.2...v1.26.0
[1.21.2]: https://github.com/dmfenton/sketchpad/compare/v1.21.1...v1.21.2
[1.21.1]: https://github.com/dmfenton/sketchpad/compare/v1.21.0...v1.21.1
[1.21.0]: https://github.com/dmfenton/sketchpad/compare/v1.20.0...v1.21.0
[1.20.0]: https://github.com/dmfenton/sketchpad/compare/v1.19.0...v1.20.0
[1.19.0]: https://github.com/dmfenton/sketchpad/compare/v1.18.2...v1.19.0
[1.18.2]: https://github.com/dmfenton/sketchpad/compare/v1.18.1...v1.18.2
[1.18.1]: https://github.com/dmfenton/sketchpad/compare/v1.18.0...v1.18.1
[1.18.0]: https://github.com/dmfenton/sketchpad/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/dmfenton/sketchpad/compare/v1.16.0...v1.17.0
[1.14.1]: https://github.com/dmfenton/sketchpad/compare/v1.14.0...v1.14.1
[1.14.0]: https://github.com/dmfenton/sketchpad/compare/v1.13.4...v1.14.0
[1.13.4]: https://github.com/dmfenton/sketchpad/compare/v1.13.3...v1.13.4
[1.13.3]: https://github.com/dmfenton/sketchpad/compare/v1.13.2...v1.13.3
[1.13.2]: https://github.com/dmfenton/sketchpad/compare/v1.13.1...v1.13.2
[1.13.1]: https://github.com/dmfenton/sketchpad/compare/v1.13.0...v1.13.1
[1.13.0]: https://github.com/dmfenton/sketchpad/compare/v1.10.0...v1.13.0
[1.10.0]: https://github.com/dmfenton/sketchpad/compare/v1.9.3...v1.10.0
[1.9.3]: https://github.com/dmfenton/sketchpad/compare/v1.9.1...v1.9.3
[1.9.1]: https://github.com/dmfenton/sketchpad/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/dmfenton/sketchpad/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/dmfenton/sketchpad/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/dmfenton/sketchpad/compare/v1.7.6...v1.8.0
[1.7.6]: https://github.com/dmfenton/sketchpad/compare/v1.7.5...v1.7.6
[1.7.5]: https://github.com/dmfenton/sketchpad/compare/v1.7.4...v1.7.5
[1.7.4]: https://github.com/dmfenton/sketchpad/compare/v1.7.3...v1.7.4
[1.6.0]: https://github.com/dmfenton/sketchpad/compare/v1.5.2...v1.6.0
[1.5.2]: https://github.com/dmfenton/sketchpad/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/dmfenton/sketchpad/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/dmfenton/sketchpad/compare/v1.4.2...v1.5.0
[1.4.2]: https://github.com/dmfenton/sketchpad/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/dmfenton/sketchpad/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/dmfenton/sketchpad/compare/v1.3.6...v1.4.0
[1.3.6]: https://github.com/dmfenton/sketchpad/compare/v1.3.5...v1.3.6
[1.3.5]: https://github.com/dmfenton/sketchpad/compare/v1.3.4...v1.3.5
[1.3.4]: https://github.com/dmfenton/sketchpad/compare/v1.3.3...v1.3.4
[1.3.3]: https://github.com/dmfenton/sketchpad/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/dmfenton/sketchpad/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/dmfenton/sketchpad/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/dmfenton/sketchpad/compare/v1.2.3...v1.3.0
[1.2.3]: https://github.com/dmfenton/sketchpad/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/dmfenton/sketchpad/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/dmfenton/sketchpad/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/dmfenton/sketchpad/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/dmfenton/sketchpad/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/dmfenton/sketchpad/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/dmfenton/sketchpad/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/dmfenton/sketchpad/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dmfenton/sketchpad/releases/tag/v1.0.0
