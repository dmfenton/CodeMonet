# Code Monet iOS — Architecture

This is the frozen-contract document for the native SwiftUI rewrite. It is
not a slavish port of the React Native app — it keeps the UX close (per the
ux/net-auth/protocol-state/performer-render specs in
`scratchpad/specs/` at the time this was written) while using native
idioms, a value-type reducer core, and a local Swift package (`MonetKit`)
that builds and tests without a simulator.

Read this file before touching anything under `ios/`. If you're a parallel
builder, find your work package in §5, read only the spec files it lists,
and work only inside your `ownedPaths`.

## 1. Module graph

```
                    ┌────────────────┐
                    │  MonetProtocol │  Codable wire types (no deps)
                    └───────┬────────┘
              ┌─────────────┼─────────────┬──────────────┐
              ▼             ▼             ▼              ▼
      ┌───────────────┐ ┌─────────┐ ┌────────────┐ ┌────────────────┐
      │  MonetStudio   │ │MonetRender│MonetNetworking│  (app target)  │
      │ (pure reducer) │ └────┬────┘ └─────┬──────┘ └────────────────┘
      └───────┬────────┘      │            │
              ▼                │            │
      ┌────────────────┐       │            │
      │ MonetPerformer  │       │            │
      └────────────────┘       │            │
                                ▼            │
                       ┌────────────────┐    │
                       │  monet-render  │    │
                       │  (executable)  │    │
                       └────────────────┘    │
                                              │
   FentonPlatform (vendor/platform.dmfenton.net/swift)
     FentonMobileCore  ◄───────────────────────┘ (MonetNetworking, Services/AuthService)
     FentonDesignSystem ◄── CodeMonet/DesignSystem
```

`MonetKit` (`ios/MonetKit`) is a standalone SwiftPM package, `swift-tools-version 5.10`,
platforms `[.iOS(.v17), .macOS(.v14)]`. Every target in it builds and tests
with plain `swift build`/`swift test` on macOS — **no simulator, no Xcode
project, no UIKit/SwiftUI import anywhere in `MonetKit/Sources`.** That's
what lets `test-kit` be the fast inner loop for five of the seven work
packages below.

The `CodeMonet` Xcode app target (`ios/CodeMonet`) is the only place UIKit/
SwiftUI/CoreGraphics-as-a-live-renderer-surface code lives. It depends on
every `MonetKit` product plus `FentonDesignSystem`/`FentonMobileCore` from
the vendored `FentonPlatform` package.

| Target | What it is | Depends on |
|---|---|---|
| `MonetProtocol` | Codable wire types: `ServerMessage`/`ClientMessage` discriminated unions, `Path`, `DrawingStyleConfig`, `GalleryEntry`, `AgentMessage`, etc. | — |
| `MonetStudio` | Pure `StudioState` + `StudioReducer.reduce(state, event) -> state`, `MessageRouter` (impure translation layer, server message -> events), `StudioSelectors` (derived `AgentStatus` etc.) | `MonetProtocol` |
| `MonetPerformer` | `PerformerEngine`: stroke/text/pen playback pacing, driven by an injected `PerformerClock` | `MonetProtocol`, `MonetStudio` |
| `MonetRender` | `Mulberry32` PRNG, `StampDynamics`/`BrushPreset` data tables, `PathSampling`, `CanvasRenderer` (CoreGraphics), `RenderStudyDocument`, `PNGWriter` | `MonetProtocol` |
| `MonetNetworking` | `CodeMonetEnvironment`, `CodeMonetRESTClient` (wraps `FentonMobileCore.MobileAPIClient`), `StudioWebSocketClient`, `TraceSpanBuffer` | `MonetProtocol`, `FentonMobileCore` |
| `monet-render` (executable) | CLI: `RenderStudyDocument` JSON -> PNG, the Swift parity lane for `scripts/render-study.py` | `MonetRender`, `MonetProtocol` |
| `CodeMonet` (app) | SwiftUI app: `App/`, `Features/*`, `DesignSystem/`, `Services/` | all of the above + `FentonDesignSystem` |

## 2. Data flow

```
WebSocket frame (JSON)
  -> StudioWebSocketClient (MonetNetworking): decode -> MonetProtocol.ServerMessage
       (unrecognized `type` -> .unknown, never a crash)
  -> StudioStore.route(_:) (CodeMonet/Services)
       .agentStrokesReady -> MessageRouter.routeStrokesReady (guards) -> REST fetch
                              -> GET /strokes/pending -> .enqueueStrokes event
       everything else     -> MessageRouter.route (MonetStudio): assigns
                              AgentMessage ids/timestamps, resolves tool-name
                              labels -> [StudioEvent]
  -> StudioReducer.reduce(StudioState, StudioEvent) -> StudioState  (MonetStudio, pure)
  -> StudioStore.state (published, @MainActor @Observable)
  -> PerformerEngine.tick(state:) (MonetPerformer), driven by a CADisplayLink
       in StudioStore -> more [StudioEvent] fed back through the same reduce
       step, plus `animation_done` sent back over the socket when a stroke
       batch finishes playing
  -> SwiftUI (CodeMonet/Features/Studio/CanvasView etc.) reads StudioStore.state
       -> MonetRender.CanvasRenderer renders committed strokes to a CGImage
```

Outbound (`ClientMessage`) follows the reverse path: a SwiftUI view calls
`StudioStore.send(_:)`, which JSON-encodes via `MonetProtocol.ClientMessage`
and hands it to `StudioWebSocketClient`.

Auth is a separate, parallel flow: `AuthService` (CodeMonet/Services) wraps
`FentonMobileCore.AuthenticationController`, adds the identity-mapping check
and DEBUG dev-token bootstrap the net-auth spec requires (§0.1-0.2, §3.4,
§4), and exposes `bearerToken` to both `StudioStore` (WS auth) and
`CodeMonetRESTClient` (REST auth) via `MonetNetworking.TokenProviding`.

The two flows are joined in exactly one place: `RootView`
(`CodeMonet/App/RootView.swift`) calls `StudioStore.connect()` from its
`onChange(of: environment.auth.state)` handler the moment `auth.state`
first becomes `.signedIn` — `connect()` itself no-ops on a repeat call, so
this is safe to call on every re-entry into `.signedIn` (e.g. after a
silent `refreshSessionOnForeground()` pass). Nothing else in the app calls
`connect()`; if that `onChange` wiring is ever removed or the state
transition it watches changes shape, the socket never opens and every
`connected`-gated UI element (Home's prompt/Surprise-Me/Continue card, New
Canvas's Start button) stays permanently disabled. A live 4001 (WS) or a
401/403 (REST, via `CodeMonetRESTClient`'s `onUnauthorized`) both route
through `StudioStore.onAuthenticationFailure`, which `AppEnvironment` wires
to `AuthService.signOut(ifBearerTokenMatches:)` — gated by the bearer token
the failing call actually used, so a stale event from a socket/request
already superseded by a reconnect with a freshly rotated token can't
incorrectly sign out an otherwise-healthy session.

## 3. Ownership table

| Paths | Package (§5) |
|---|---|
| `ios/MonetKit/Sources/MonetProtocol`, `ios/MonetKit/Tests/MonetProtocolTests`, `ios/MonetKit/Sources/MonetStudio`, `ios/MonetKit/Tests/MonetStudioTests` | 1. protocol+studio |
| `ios/MonetKit/Sources/MonetPerformer`, `ios/MonetKit/Tests/MonetPerformerTests` | 2. performer |
| `ios/MonetKit/Sources/MonetRender`, `ios/MonetKit/Sources/monet-render`, `ios/MonetKit/Tests/MonetRenderTests`, `scripts/render-study.py` | 3. renderer |
| `ios/MonetKit/Sources/MonetNetworking`, `ios/MonetKit/Tests/MonetNetworkingTests`, `ios/CodeMonet/Services/AuthService.swift`, `ios/CodeMonet/Services/StudioStore.swift`, `ios/CodeMonet/App/AppConfig.swift` | 4. networking+auth |
| `ios/CodeMonet/Features/Studio/` | 5. studio UI |
| `ios/CodeMonet/Features/Home/`, `ios/CodeMonet/Features/Gallery/`, `ios/CodeMonet/Features/NewCanvas/` | 6. home+gallery+new-canvas UI |
| `ios/CodeMonet/App/CodeMonetApp.swift`, `AppDelegate.swift`, `RootView.swift`, `AppEnvironment.swift`, `Navigation.swift`, `SplashView.swift`, `ios/CodeMonet/Features/Auth/`, `ios/CodeMonet/DesignSystem/`, `ios/CodeMonetTests/`, `ios/CodeMonetUITests/`, `ios/project.yml`, `ios/.swiftlint.yml`, `ios/Config/`, `ios/CodeMonet/Resources/` | 7. app shell |

`ios/MonetKit/Package.swift` and this file (`ios/ARCHITECTURE.md`) are
frozen — no work package edits them without flagging it in their report (a
genuinely-needed change, e.g. a new test target, goes through the architect/
integrator, not a silent edit).

## 4. Rules

1. **Freeze the public contracts.** Every public type/protocol/function
   signature in `MonetKit/Sources/*` and `CodeMonet/App`, `Services`,
   `DesignSystem` as they exist at this commit is load-bearing for other
   packages. You may add new internal (non-`public`) files/types within your
   `ownedPaths` freely. If you must change a frozen public signature, do it,
   but say so explicitly in your work-package report (what changed, why, who
   else's code it affects) — don't silently ship a breaking rename.
2. **No `fatalError` in a path the app executes at launch.** Stub bodies
   return empty/default values, not crashes. (Test-only code, and code paths
   genuinely unreachable at runtime such as a `switch` over a closed enum's
   impossible case, are fine.)
3. **`MonetStudio.StudioReducer.reduce` stays pure.** No `Date()`, no
   `UUID()`, no I/O, inside `reduce` itself. Non-deterministic inputs (ids,
   timestamps) are threaded in through the event's associated values or
   through `MessageRouter`'s `RoutingEnvironment` — see `StudioEvent.swift`'s
   doc comments.
4. **`MonetKit` never imports UIKit/SwiftUI/CoreGraphics-as-UI.**
   `CoreGraphics` itself is fine in `MonetRender` (it's available on both iOS
   and macOS and is how `monet-render` rasterizes without a simulator) — the
   line is "no simulator/UI-runtime dependency", not "no CoreGraphics".
5. **Run `test-kit` before every commit** if you touched `MonetKit`; run
   `build` (and `test-app` before a PR) if you touched `CodeMonet`.
6. **New files under an already-listed `sources` path need no `project.yml`
   change** — XcodeGen globs directories. Only new *targets*, new package
   dependencies, or new build settings require editing `project.yml`, which
   then needs `make generate` and a fresh `xcodebuild` to verify.

## 5. Makefile

```
make generate    # xcodegen generate — regenerate CodeMonet.xcodeproj from project.yml
make build       # xcodegen generate + xcodebuild build, unsigned, iOS Simulator
make test-kit    # cd MonetKit && swift test — fast inner loop, no simulator
make test-app    # xcodebuild test on a booted simulator (CodeMonetTests + CodeMonetUITests)
make clean       # remove the generated .xcodeproj; swift package clean
```

## 6. Work packages

Each builder works in its own git worktree on branch `feat/ios-swift`,
touching only its `ownedPaths`. Read your spec files fully before writing
code — they contain exact constants/formulas this document doesn't repeat.

### 1. Protocol + Studio reducer (fixture replay tests)
- **ownedPaths**: `ios/MonetKit/Sources/MonetProtocol/`, `ios/MonetKit/Tests/MonetProtocolTests/`, `ios/MonetKit/Sources/MonetStudio/`, `ios/MonetKit/Tests/MonetStudioTests/`
- **specFiles**: `scratchpad/specs/protocol-state.md` (all of it)
- **instructions**: Harden `ServerMessage`/`ClientMessage` decoding against every fixture in `server/tests/fixtures/*.json` (there are three; the skeleton's tests only replay `agent_turn_plotter.json`). Fill in any reducer edge cases §5 calls out that the skeleton's `StudioReducer` simplified (re-read §5.4's `LOAD_CANVAS`/`INIT` `savedCanvas` rule and §5.5's stage/buffer mechanics against your fixture replays — assert exact state at key points, not just "didn't crash"). Decide and document the self-echo (§7.1) and multi-connection (§7.2) behaviors explicitly rather than leaving them as TODOs.
- **acceptance**:
  - `cd ios/MonetKit && swift test --filter MonetProtocolTests`
  - `cd ios/MonetKit && swift test --filter MonetStudioTests`
  - All three `server/tests/fixtures/*.json` files replay through `MessageRouter.route` + `StudioReducer.reduce` without a decode failure or an `.unknown` message type.

### 2. Performer
- **ownedPaths**: `ios/MonetKit/Sources/MonetPerformer/`, `ios/MonetKit/Tests/MonetPerformerTests/`
- **specFiles**: `scratchpad/specs/performer-render.md` §9-11 (in-progress stroke rendering context, performer state machine, idle particles)
- **instructions**: The skeleton's `PerformerEngine` implements the phase state machine and constants from §11 but simplifies a few things — verify against §11.4's exact 5-phase per-stroke sequence (inter-stroke pause / travel / settle / draw) with real timed tests using `ManualPerformerClock`, not just structural ones. Add coverage for the words-chunk merge behavior (§5.5 `ENQUEUE_WORDS`, already in `MonetStudio` but the *timing* of word reveal is yours) and the idle-particle gate (§11.7, already exposed as `StudioSelectors.shouldShowIdleAnimation` — confirm it matches your playback loop's expectations).
- **acceptance**:
  - `cd ios/MonetKit && swift test --filter MonetPerformerTests`
  - A test asserting the exact easing formula (`0.75 + 0.25*sin(progress*π)`) and the point-batching bounds (24-240 pts/frame) against §11.1/§11.6's constants.

### 3. Renderer (+ monet-render CLI + `--swift` lane in `scripts/render-study.py`)
- **ownedPaths**: `ios/MonetKit/Sources/MonetRender/`, `ios/MonetKit/Sources/monet-render/`, `ios/MonetKit/Tests/MonetRenderTests/`, `scripts/render-study.py`
- **specFiles**: `scratchpad/specs/performer-render.md` §1-9, §13 (context only), §15
- **instructions**: The skeleton's `CoreGraphicsCanvasRenderer` strokes sampled points directly — it does **not** implement the perfect-freehand outline algorithm (§4) or the stamp model (§7) yet. That's this package's main job: implement `getStrokeOutlinePoints`/bristles for plotter mode and completed-plotter strokes, and the full stamp pipeline (resample -> `computeStrokeStamps` -> sprite generation -> non-uniform stamp placement, §7.6's web-exact-math recommendation) for paint mode, using the already-provided `Mulberry32`, `StampDynamics`, `BrushPreset` tables. Add the `--swift` lane to `scripts/render-study.py` per §15.3 (spawn `monet-render` as a subprocess, extend `compose_compare`).
- **acceptance**:
  - `cd ios/MonetKit && swift test --filter MonetRenderTests`
  - `cd ios/MonetKit && swift run monet-render <path-to-a-render-study-json> /tmp/out.png` produces a non-trivial PNG at the exact input `width x height`.
  - `uv run python scripts/render-study.py ../studies/<any>.py --compare --swift` (new flag) runs and prints a client/server/swift 3-way mean-diff.

### 4. Networking + auth (MonetNetworking + Services/AuthService + deep links + dev-token + trace sink)
- **ownedPaths**: `ios/MonetKit/Sources/MonetNetworking/`, `ios/MonetKit/Tests/MonetNetworkingTests/`, `ios/CodeMonet/Services/AuthService.swift`, `ios/CodeMonet/Services/StudioStore.swift`, `ios/CodeMonet/App/AppConfig.swift`
- **specFiles**: `scratchpad/specs/net-auth.md` (all of it), `scratchpad/specs/protocol-state.md` §1, §3, §6-7 (connection lifecycle, client messages, quirks)
- **instructions**: The skeleton wires the full PKCE flow, `KeychainAuthenticationStores`, the identity-mapping check (§0.2), and a DEBUG dev-token bootstrap (§4), but the `TokenBox`/two-phase-init wiring in `AuthService.init` is a known-awkward seam — clean it up if you find a better pattern (it's your file). `StudioWebSocketClient`'s reconnect policy needs the foreground-triggered `restoreSession()` hook (§9.2) wired from `RootView`/`AppEnvironment` (coordinate with package 7 on the `scenePhase` observer — that belongs in App shell, but it needs to *call* something you provide). Implement the trace-span flush timer (§8.1: auto-flush every 10s, flush on background) — the skeleton only provides `TraceSpanBuffer.flush()`, not the timer driving it.
- **acceptance**:
  - `cd ios/MonetKit && swift test --filter MonetNetworkingTests`
  - `cd ios && make build` still succeeds (app target compiles against your `Services/` changes).
  - A manual/scripted check that `-devToken` launch argument + DEBUG build signs in against `localhost:8000` with zero taps (net-auth spec §4).

### 5. Studio UI (canvas view hosting the renderer, action bar, live status, message stream, nudge sheet, pause/resume)
- **ownedPaths**: `ios/CodeMonet/Features/Studio/`
- **specFiles**: `scratchpad/specs/ux.md` §6, §7.1 (Nudge modal), §9.1 (theme), §9.4 (accessibility), §10 (native improvements 1-5, 8-9 apply directly here)
- **instructions**: Replace the skeleton's placeholder `StudioView`/`CanvasView` with the real LiveStatus (tool-colored event bubble + progressive thinking text), collapsible MessageStream (5 message-type presentations per §6.3), the full 5-button-dynamic ActionBar, and a real Nudge sheet (`.sheet` with detents, not a fake bottom sheet — ux spec §10.1). Use `StudioSelectors.agentStatus`/`shouldShowIdleAnimation` (already in `MonetStudio`) rather than re-deriving status locally. Preserve every `testID` -> `accessibilityIdentifier` from the ux spec's appendix for this screen.
- **acceptance**:
  - `cd ios && make build`
  - `cd ios && make test-app` (CodeMonetUITests still passes with your accessibility identifiers in place)
  - Manual: pause/resume, nudge send, and the draw gesture round-trip against a local server (`make dev` in the repo root).

### 6. Home+Gallery+NewCanvas UI (home panel, continue card, prompt input, surprise me, style picker, gallery grid with authenticated thumbnails)
- **ownedPaths**: `ios/CodeMonet/Features/Home/`, `ios/CodeMonet/Features/Gallery/`, `ios/CodeMonet/Features/NewCanvas/`
- **specFiles**: `scratchpad/specs/ux.md` §5, §7.2, §8, §9.2 (authenticated images), §10 (7, 11 apply directly)
- **instructions**: Replace the skeleton's placeholder `HomeView`/`GalleryView`/`NewCanvasView`. Home needs the Continue-card (live-strokes SVG-equivalent preview vs. authenticated thumbnail fallback per §5.2) and the conditional OR-divider logic (§5.2's `hasRecentWork` rule). Gallery needs real thumbnail loading via `CodeMonetRESTClient.thumbnailData(pieceID:)` (already provided) and a 2-column grid. `NewCanvasView` exists as a real, reachable sheet already (a deliberate native-improvement divergence from the RN app's unreachable one, per ux spec §7.2's note) — finish its size-profile picker.
- **acceptance**:
  - `cd ios && make build`
  - `cd ios && make test-app`
  - Manual: gallery thumbnails load against a local server with `>0` saved pieces.

### 7. App shell + auth UI + splash + design-system theme + XCUITest smoke
- **ownedPaths**: `ios/CodeMonet/App/CodeMonetApp.swift`, `AppDelegate.swift`, `RootView.swift`, `AppEnvironment.swift`, `Navigation.swift`, `SplashView.swift`, `ios/CodeMonet/Features/Auth/`, `ios/CodeMonet/DesignSystem/`, `ios/CodeMonetTests/`, `ios/CodeMonetUITests/`, `ios/project.yml`, `ios/.swiftlint.yml`, `ios/Config/`, `ios/CodeMonet/Resources/`
- **specFiles**: `scratchpad/specs/ux.md` §1-4, §9.1, §9.3-9.4, §10 (all), `scratchpad/specs/net-auth.md` §5, §7
- **instructions**: Replace the skeleton's placeholder `AuthView`/`SplashView` with the real ones (exact copy/spacing per ux spec §3-4; the splash animation sequence in §4 is a genuine multi-step animation, not the skeleton's fixed-delay placeholder). Wire `scenePhase` foreground/background handling into `StudioStore`/`AuthService` per ux spec §1.2 and net-auth spec §9.2 (coordinate with package 4 — you own the observer, they own what it calls). Finish the asset catalog (proper multi-size app icon; the skeleton ships a single 1024px universal icon, which works but isn't what `app/assets` originally provided at other sizes). Grow `CodeMonetUITests` beyond the launch smoke test into real flows once packages 5/6 land their testIDs.
- **acceptance**:
  - `cd ios && make generate && make build`
  - `cd ios && make test-app`
  - `cd ios/MonetKit && swift build && swift test` (unaffected by your changes, but must still pass — you own `Package.swift`... no, you don't; if you ever touch it, flag it)

## 7. Program painting (protocol/state/reveal-math/drawing/networking/UI landed)

Program-painting support (`docs/program-painting.md`,
`scratchpad/specs/program-painting.md` — the client contract for PR #313)
has landed end to end: `MonetKit`'s protocol/state/reveal-math layer, the
CoreGraphics reveal compositor and painting-asset networking, and their
wiring into the Studio canvas and gallery viewing (see "Wired since the
above was written" below the work-package table). No `Package.swift`/
`project.yml` change was needed — every addition is new files or additive
fields under
already-listed `sources` paths.

**Landed:**

- `MonetProtocol` (`PaintingVersion.swift`): `PaintingVersionRef`,
  `RevealOp`/`RevealKeyframe`/`RevealManifest` (custom `Codable` for the
  heterogeneous `["s"|"a", ...]` wire arrays, including the single-point
  "dot" stroke case). `ServerMessage` gained `.paintingVersion(ref,
  stages:)`; `InitPayload` gained an optional `painting` field. `Gallery.swift`
  gained `GalleryPieceFormat` (`GalleryEntry.format`,
  `GalleryPieceStrokes.format`/`.imageURL` for `GET /gallery/{n}/strokes`).
- `MonetStudio`: `PaintingState` (`base`/`playing`, `settlePainting`,
  `hasPainting`) on `StudioState` and `SavedCanvas`. `StudioEvent` gained
  `.paintingVersion`/`.paintingPlaybackDone`. `StudioReducer` implements the
  full guard chain (gallery guard, stale-piece guard, duplicate/older-version
  guard, settle-on-supersede) in `applyPaintingVersion`, plus painting resets
  on `.clear`/`new_canvas`, `.initialize` (base only, never `playing` — no
  reconnect replay), and settle-on-enter/restore-verbatim-on-exit for
  `.loadCanvas`/`.clearViewing`. `MessageRouter` routes `painting_version`
  (dropping `stages`) and adds `paint` to `ToolLabels`'
  started/completed copy. `StudioSelectors.agentStatus`/
  `shouldShowIdleAnimation` account for `painting.playing`/`hasPainting`.
  Tests: `PaintingStateReducerTests.swift` mirrors every case in
  `web/src/test/paintingReducer.test.ts`.
- `MonetRender` (`RevealPlan.swift`): a from-scratch Swift port of
  `shared/src/renderer/reveal.ts` + `app/src/renderers/revealPlan.ts` —
  `RevealPacing`/`buildRevealSchedule`/`revealProgressAt` (the stateless
  timing model) and `RevealPlan`/`RevealCursor`/`RevealSink`/
  `advanceRevealPlan` (the flattened, stateful per-frame cursor), plus
  `PaintingAssetURL.apiAssetUrl`/`paintingAssetUrl`/`galleryRasterImageUrl`.
  Pure value types and free functions — no CoreGraphics/UIKit dependency, so
  this is testable exactly like the TS original. `RevealPlanTests.swift`
  reimplements every one of `revealPlan.test.ts`'s 11 assertions
  (`buildRevealPlan`, `advanceRevealPlan`, gallery raster URLs) verbatim
  against the same fixture manifest shape.

**Wired since the above was written:**

- **`IncrementalCanvasRenderer` wiring.** `CodeMonet/Features/Studio/CanvasView.swift`
  now drives `MonetRender.IncrementalCanvasRenderer` through a private
  `IncrementalCanvasCache` held as `@State`: committed strokes are baked
  once (only the newly-appended tail of `state.strokes` each frame, not a
  full replay), and only the two in-progress strokes (human drag + agent
  stroke) are redrawn on top per `TimelineView` tick — no longer
  `CanvasRenderer.renderCommitted` over the full stroke history every
  frame. The cache fully rebakes on a canvas-size change, a
  `(pieceNumber, viewingPiece)` change (new/loaded/gallery canvas), or
  whenever `state.strokes` is shorter than what's already baked (a
  generic reset fallback, e.g. `.clear`).
- **`TOOL_ICONS`.** `StudioPresentation.KnownTool` now has a `.paint` case
  (`paintpalette.fill`/`paintpalette`), so a `paint` code-execution message
  gets a real icon instead of falling through to the generic
  "Running code" presentation.
- **Drawing — live paint-mode reveal.** `MonetRender.RasterRevealSink`
  (`RasterRevealSink.swift`) is a real `RevealSink` conformer: a
  `CoreGraphics`-backed compositor over a `plan.width x plan.height`
  bitmap context, one to one with `RevealOp` coordinates. CoreGraphics has
  no image-shader-fill primitive (Skia's `makeShaderOptions`), so each op
  is clip-then-draw instead: the op's shape (an ellipse/stroked polyline
  for a stroke op, a rect for an area op) becomes the clip path, then the
  keyframe image is drawn across the whole canvas rect. Bitmap contexts in
  this package are bottom-left-origin, un-flipped; empirically verified
  (not just documentation-derived — see the type's doc comment) that
  `CGContext.draw(_:in:)` needs **no** flip transform here, while clip
  geometry built from manifest (top-left-origin, y-down) coordinates does,
  via the same `CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty:
  height)` every other renderer in this package already uses.
  `PaintingImageDecoder` decodes a keyframe/`final.png`'s raw bytes to a
  `CGImage` via `ImageIO`. Tests: `RasterRevealSinkTests.swift` — pixel-level
  (reads `context.data` directly, never redraws through a second context,
  which would silently reintroduce an orientation ambiguity of its own).
- **Networking — painting assets.** `MonetNetworking.PaintingAssetClient`
  fetches `reveal.json` and keyframe/`final.png` images directly from
  their resolved `PaintingAssetURL`-joined URLs — no bearer auth (the
  server's own doc comment: these load "like share links"), via the same
  `HTTPTransport` protocol `CodeMonetRESTClient` uses, so it's equally
  fakeable in tests.
- **Studio canvas compositing.** `CodeMonet/Features/Studio/
  PaintingRevealController.swift` (app target, not unit-tested itself —
  glue over the two tested pieces above) drives the whole live pipeline:
  fetches `base`'s `final.png` and, when `playing` is set, `reveal.json` +
  every keyframe + `final.png`, builds a `RevealPlan`, and advances it one
  `TimelineView` tick at a time (mirrors `app/src/renderers/
  RasterRevealLayer.tsx`'s generation-counter cancellation model: a
  version superseded mid-fetch or mid-reveal never clobbers a newer one,
  and an interrupted reveal is jumped to its own fully-revealed state
  rather than left frozen, matching `MonetStudio.settlePainting`'s
  contract). `CanvasView.frame(state:canvasSize:now:)` renders this layer
  instead of the strokes layer whenever `MonetStudio.hasPainting` is true,
  and calls `StudioStore.paintingPlaybackDone(assetBase:)` once a reveal
  finishes. Known simplification vs. the RN reference: no cross-version
  `NSCache` for decoded images (RN's `IMAGE_CACHE_LIMIT`) — each version's
  assets are fetched fresh; acceptable for now (a version's assets are
  small and fetched once), flagged as a follow-up if it shows up as a
  real cost.
- **Gallery raster viewing.** A `.raster` gallery piece (no vector
  strokes — a saved program-painting piece) now actually renders:
  `LoadCanvasPayload` grew `format`/`imageURL` fields (defaulted so an
  older/partial payload still decodes), `StudioState.viewingImageURL` is
  set by `StudioReducer`'s `.loadCanvas` case when `format == .raster` and
  cleared alongside `viewingPiece` everywhere else, and
  `StudioStore.applyLoadedGalleryPiece` (the REST `GET /gallery/{n}
  /strokes` path `GalleryView.select()` actually uses) threads
  `GalleryPieceStrokes.format`/`.imageURL` through. `CanvasView` renders a
  small dedicated `GalleryRasterImageView` (fetch + decode + display, no
  animation — a saved piece has nothing to reveal) instead of the
  strokes/painting layers whenever `viewingImageURL` is set. The live WS
  `load_canvas` broadcast still never sends `format`/`image_url` (server
  only ever pushes `.strokes` pieces over it) — harmless, since the app's
  actual gallery-open flow is the REST round-trip above, not that
  message; flagged as a gap if a future flow needs the WS path too.
