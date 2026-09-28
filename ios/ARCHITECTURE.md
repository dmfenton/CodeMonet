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
| `MonetRender` | `Mulberry32` PRNG, `StampDynamics`/`BrushPreset` data tables, `PathSampling`, `CanvasRenderer` (CoreGraphics), `RenderStudyDocument`, `PNGWriter`, program-painting performance playback (`PerformanceParser`/`PerformancePlayer`, §7) | `MonetProtocol` |
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
`connected`-gated UI element (Home's composer Begin/Surprise me, the easel's
Watch/Continue, Studio's nudge bar) stays permanently disabled. A live 4001 (WS) or a
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
| `ios/CodeMonet/Features/Home/`, `ios/CodeMonet/Features/Gallery/` | 6. home+gallery UI |
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

### 6. Home+Gallery UI (home panel, composer, recent row, gallery grid with authenticated thumbnails)
- **ownedPaths**: `ios/CodeMonet/Features/Home/`, `ios/CodeMonet/Features/Gallery/`
- **specFiles**: `scratchpad/specs/ux.md` §5, §7.2, §8, §9.2 (authenticated images), §10 (7, 11 apply directly)
- **instructions**: (Historical; superseded by §8.) Replace the skeleton's placeholder `HomeView`/`GalleryView`. Gallery needs real thumbnail loading via `CodeMonetRESTClient.thumbnailData(pieceID:)` (already provided) and a 2-column grid. The New Canvas sheet this package originally owned was folded into Home's composer (`HomeComposer`: prompt, style chips, canvas-size menu, Surprise me, Begin) and deleted in the redesign.
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

## 7. Program painting (live performances)

Program painting (`docs/program-painting.md`) renders on the server; clients
play each version's **performance** (`{asset_base}performance.bin`): the exact
pixels each paint op changed, in paint order, with one-hand timing. The iOS
keyframe reveal (`reveal.json` + `kf_NN.jpg` along brush footprints —
`RevealPlan`, `RasterRevealSink`, `RevealManifest`/`RevealOp`) is gone; the
app reads neither file. No `Package.swift`/`project.yml` change was needed.

- **`MonetProtocol`**: `PaintingVersionRef` (`init.painting`,
  `painting_version`), `PaintingLiveRef` (`painting_live`,
  `init.painting_live`), `PaintingVersionSummary`. `ServerMessage` has
  `.paintingVersion(ref, stages:, ops:)`, `.paintingLive(ref)`,
  `.paintingLiveFailed(pieceNumber:, assetBase:)`; `InitPayload.paintingLive`
  (absent/null/malformed → `nil`).
- **`MonetStudio`** (mirrors `shared/src/canvas/reducer.ts` and
  `web/src/test/paintingReducer.test.ts`): `PaintingState` is `base` (shown),
  `playing` (a recorded version performing over `base` — one this client did
  not watch live, e.g. after a reconnect) and `live: LivePainting?` (`ref`,
  `confirmed`, `played`). Events `.paintingLive`, `.paintingLiveFailed`,
  `.paintingLiveDone`, `.paintingVersion`, `.paintingPlaybackDone`. A
  `painting_version` whose `asset_base` matches the live run confirms it
  without replaying (settles to `base` if its stream already played);
  `settlePainting` makes a confirmed run or a playing version the base and
  drops an unconfirmed run. `.initialize` seeds `live` from
  `init.painting_live` for the current piece when it isn't the current
  version. `isPaintingPerforming` (a playing version, or a live run not yet
  played) drives `agentStatus == .drawing`. `StageBar.segments(stages:
  active:)` takes `StageSpec`s (label + weight). Tests:
  `PaintingStateReducerTests`, `LivePaintingReducerTests`, `StageBarTests`.
- **`MonetRender`** (port of `shared/src/renderer/performance.ts`):
  `Performance.swift` — `PerformanceParser` (incremental frames),
  `decodePerformancePatches` (20-byte LE records), `performancePatchFits`
  (bounds checks: the stream is untrusted program output),
  `performanceOrderThreshold`, `performancePlaybackRate` (+
  `performanceMaxBehindMs` = 60 s). `PerformancePlayer` — the picture buffer
  (`RGBAPixels`, base drawn in, white when blank) and the paste loop:
  in-flight patches paste pixels whose 4x4 block order (0 → 255) ≤
  `1 + progress·254`, finished patches paste whole; never plays past what has
  arrived or into a chunk whose atlases aren't decoded. Atlases
  (`PerformanceAtlas.decode`, ImageIO WebP → RGBA; order = red channel) are
  decoded lazily — the playing chunk + `decodeLookahead` — and released once
  played, so a long complete stream never holds every decoded atlas. Headers
  and atlases over `RGBAPixels.maxPixelCount` (4096²) are refused.
  `PaintingAssetURL` (asset URL joining) and `PaintingImageDecoder` live
  here too. Tests: `PerformanceTests.swift` — the TS stream tests plus real
  streams generated by the server's paint library
  (`Tests/Fixtures/performance/`: v1 over blank, v2 a revision; playback
  matches a PIL-decoded paste and `final.png`).
- **`MonetNetworking`**: `PaintingAssetClient.byteStream(at:)` streams a
  (possibly growing) asset's bytes as they arrive (delegate `URLSession`,
  idle timeout above the server's 270 s follow bound); non-2xx →
  `FetchError.http`. Plus `imageData`/`text` for `final.png`/`painting.py`.
- **App** (`CodeMonet/Features/Studio/PaintingPerformanceController.swift`,
  glue, not unit-tested): maps `PaintingState` to a target — blank, a still
  version (`final.png`), a performance (live run or playing version over
  `base`), or holding a played live run until the server confirms/fails it
  — and per `TimelineView` tick advances the player (studio rates: 3× for a
  first version, 1× for a revision; gallery replay 4×), decodes atlases off
  the main thread, and reports `.paintingPlaybackDone` / `.paintingLiveDone`.
  A version without a stream (recorded before performances) shows its
  `final.png` and reports done; a live run whose stream can't be read
  reports done and holds the picture. A superseded performance's stream is
  cancelled; `idle()` stops streams when the canvas leaves paint mode or
  disappears. Final pictures are cached (4, LRU) so settling never flashes.
  `StudioView`'s stage bar shows the streamed stages (sized by hand time,
  current = the playing chunk's) while performing, else the version's
  `stages` labels. `GalleryPieceDetailView`'s replay plays each version's
  `performance.bin` (v1 over blank, each later version over the previous
  version's `final.png`), or its `final.png` when it has none.
- **Gallery raster viewing**: a `.raster` gallery piece opened in the studio
  shows its `final.png` via `GalleryRasterImageView` (`StudioState
  .viewingImageURL`, set by `.loadCanvas` from the REST `GET /gallery/{n}
  /strokes` payload's `format`/`image_url`).

## 8. Redesign (Fenton palette, notebook, versions)

The app now uses the Fenton paper/ink/forest palette
(`CodeMonet/DesignSystem/CodeMonetDesignSystem.swift`), a native `BrandMark`
drawn from `brand/mark.svg`, and system serif/monospaced type roles
(`MonetStyle.swift`). Screens:

- **Home** (`Features/Home`): brand header + account menu (sign out), "on the
  easel" row (`HomeSelectors.easel`), one composer (`HomeComposer`: prompt,
  Paint/Plotter chips, canvas-size menu, Surprise me, Begin) that replaces the
  New Canvas sheet (deleted, with `ActiveModal`), and a recent row.
- **Studio** (`Features/Studio`): top bar (back, title, status pill, menu with
  New piece / Gallery / Draw on canvas / Pause), canvas in a paper mat, stage
  bar (`MonetStudio.StageBar`: streamed stages while performing, else the
  version's `stages`) and
  version chips (tap an older version to pin its `final.png` over the live
  canvas), the notebook (`MonetStudio.Notebook`) and an always-visible nudge
  bar with pause/resume. The action bar, LiveStatus, message stream and nudge
  sheet are gone. `StudioView` owns the `PaintingPerformanceController` (§7),
  which publishes the performing stages for the stage bar.
- **Gallery** (`Features/Gallery`): filters, featured latest piece, grid, and
  `GalleryPieceDetailView` (meta, prompt, version replay through a second
  `PaintingPerformanceController`, `painting.py` sheet, "Open in studio").

Contract changes (all additive on the wire; flagged per §4 rule 1):

- `ServerMessage.paintingVersion` gained `ops: Int? = nil`; `StudioEvent
  .paintingVersion` carries `stages`/`ops` (defaults `[]`/`nil`) into the
  version history only — playback is unchanged.
- `InitPayload` gained `title`, `prompt` (top-level, else `painting.prompt`)
  and `paintingVersions` (`painting.versions`); `GalleryPieceStrokes` gained
  `title`, `prompt`, `strokeCount`, `versions`. New `PaintingVersionSummary`.
- `AgentMessage` gained `version` (stamped by the reducer: work toward vN is
  everything after v(N-1) arrived) and `AgentMessageType.userNudge`.
- `StudioState` gained `versions` (seeded from `init`, accumulated from
  `painting_version`, reset on `clear`/`new_canvas`), `title` (`init.title`,
  then `piece_title` — see §9), `prompt`; events `.setTitle`/`.setPrompt`.
- `MessageRouter` archives pending thinking when a tool call starts, so the
  notebook interleaves thought and tool lines.
- `StudioState.notebook` is the notebook's own log (bounded to
  `maxNotebookEntries` = 200 entries, a tool call's started/completed pair
  counting once), separate from the 50-message `messages` status window.
  `init` for the same piece (non-empty notebook) keeps it, merges versions and
  keeps an omitted title/prompt; a different piece seeds it from the payload's
  prompt and monologue.
- Additive `versions` arrays decode element-wise (`LossyArray`): a malformed
  entry is skipped, never failing `init` or the gallery detail.
- `PaintingAssetClient.text(at:)` fetches a version's `painting.py`.

## 9. Live status and title (`turn_state`, `piece_title`)

- `ServerMessage.turnState(active:)` (`{"type": "turn_state", "active": Bool}`,
  sent when an agent turn starts and ends — always `false` after a turn, even
  a failed one) and `InitPayload.turnActive` (`init.turn_active`, absent →
  `false`) set `StudioState.turnActive`.
- `StudioSelectors.agentStatus` keeps its priority (paused > error > thinking >
  executing > drawing) but returns `.thinking` instead of `.idle` while
  `turnActive`: the painter is working through a silent gap, or the client
  reconnected mid-turn. The Studio pill and Home easel line
  (`StudioPresentation.statusPill`) apply the same rule.
- `ServerMessage.pieceTitle(pieceNumber:title:)` (`{"type": "piece_title",
  "piece_number", "title"}`, sent after `name_piece` stores the title) sets
  `StudioState.title` only for the current piece. It is the single live
  authority: the client no longer reads titles out of `name_piece` tool
  calls; `init.title` seeds the title on connect.
