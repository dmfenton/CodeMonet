import Foundation
import MonetNetworking
import MonetPerformer
import MonetProtocol
import MonetStudio
import Observation
import QuartzCore

/// The live, mutable owner of `StudioState` — the only place in the app that
/// holds one. Wires: `StudioWebSocketClient` -> `MessageRouter` ->
/// `StudioReducer` -> `PerformerEngine` -> (rendered by SwiftUI/MonetRender)
/// (see ../../ARCHITECTURE.md's data-flow diagram). Every other type in the
/// pipeline is either a pure function (`StudioReducer`) or independently
/// testable (`MessageRouter`, `PerformerEngine`) — this class's own job is
/// just to drive them with real I/O and expose the result to SwiftUI.
@MainActor
@Observable
public final class StudioStore {
    public private(set) var state = StudioState()
    /// Whether the WebSocket is currently open (ux spec §1.3: gates
    /// PromptInput submit, Surprise Me, the Continue card, and the Home
    /// screen's "Connecting…" hint). Server-push-driven state has no
    /// equivalent signal, so this mirrors `StudioSocketEvent.connected`/
    /// `.disconnected` directly.
    public private(set) var connected = false

    /// Fires on a live `4001`/auth-failure close, or a REST 401/403
    /// (protocol-state spec §1.2, net-auth spec §9.2 point 2, §6) — the app
    /// shell wires this to `AuthService.signOut(ifBearerTokenMatches:)`.
    /// Not wired here: `StudioStore` only knows `TokenProviding`, never the
    /// concrete `AuthService`. Carries the bearer token the failing
    /// call/socket actually used, so a stale event from a connection already
    /// superseded by a reconnect holding a freshly rotated token can't
    /// incorrectly sign out a session that's actually fine.
    public var onAuthenticationFailure: (@Sendable (String) async -> Void)?

    private let socket: StudioWebSocketClient
    private var rest: CodeMonetRESTClient
    private let traceBuffer: TraceSpanBuffer
    @ObservationIgnored private var performer = PerformerEngine()
    private let tokenProvider: any TokenProviding
    private var displayLink: CADisplayLink?
    private var socketTask: Task<Void, Never>?
    private var strokesFetchTask: Task<Void, Never>?
    /// The current drawing session's trace id (net-auth spec §8.1
    /// `newSession()`), generated once per `connect()` and reused across
    /// automatic/foreground reconnects so server-side spans keep
    /// correlating with the same client session until the studio is left.
    private var currentTraceID: String?
    /// The bearer token most recently handed to `socket.connect`/
    /// `reconnectIfTokenChanged` — see `onAuthenticationFailure`'s doc
    /// comment.
    private var currentToken: String?
    /// Human strokes this device has sent but not yet seen echoed back
    /// (protocol-state spec §7.1). `endStroke()` draws the stroke locally
    /// immediately (no round-trip latency) and records its signature here;
    /// when the server's `human_stroke` broadcast for the same path arrives,
    /// it's recognized as this device's own echo and consumed instead of
    /// being appended a second time. A stroke from another of this user's
    /// connections (protocol-state spec §1.1's multi-connection fact) won't
    /// match anything here, so it's still added normally. Bounded defensively
    /// — an echo that never arrives (e.g. the send silently dropped because
    /// the socket wasn't open) would otherwise leak forever.
    private var pendingSelfStrokes: [Path] = []
    private static let maxPendingSelfStrokes = 32
    /// The direction this device just sent with `new_canvas`, applied as the
    /// piece's prompt once the server's `new_canvas` confirms the new piece
    /// (see `startNewPiece`).
    var pendingPrompt: String?

    public init(environment: CodeMonetEnvironment, tokenProvider: any TokenProviding) {
        socket = StudioWebSocketClient(baseURL: environment.wsBaseURL)
        rest = CodeMonetRESTClient(baseURL: environment.apiBaseURL, tokenProvider: tokenProvider)
        traceBuffer = TraceSpanBuffer(baseURL: environment.apiBaseURL)
        self.tokenProvider = tokenProvider
        // Net-auth spec §6: a 401/403 on `/strokes/pending` polling funnels
        // into `onAuthenticationFailure`, same as a live WS 4001. Reassigned
        // (not passed above) since the closure needs `self`, not fully
        // initialized until every stored property has a value.
        rest = CodeMonetRESTClient(
            baseURL: environment.apiBaseURL,
            tokenProvider: tokenProvider,
            onUnauthorized: { [weak self] token in await self?.onAuthenticationFailure?(token) }
        )
    }

    /// Opens the WebSocket and starts consuming its event stream. Safe to
    /// call once per app session; reconnects after a transient failure are
    /// the socket's own responsibility (net-auth spec §9.1, §1.2's capped
    /// exponential backoff). Starts a fresh trace-span session and its
    /// 10s auto-flush timer (net-auth spec §8.1).
    public func connect() {
        guard socketTask == nil else { return }
        let traceID = TraceSpanBuffer.newTraceID()
        currentTraceID = traceID
        Task { await traceBuffer.startAutoFlush() }
        socketTask = Task { [weak self] in
            guard let self else { return }
            guard let token = await self.tokenProvider.currentToken() else {
                // No session yet (net-auth spec §9.1: skip connecting
                // entirely). `socketTask` guards "currently connecting/
                // connected", not "connect() was ever called" — leaving it
                // set here would permanently disable every future
                // `connect()` call once the guard above sees it non-nil,
                // since nothing else ever clears it (`disconnect()` has no
                // caller in the shipped app). Clear it so a later
                // `connect()`, once a token becomes available, can actually
                // open the socket.
                self.socketTask = nil
                return
            }
            self.currentToken = token
            self.recordSpan(name: "ws.connect")
            // Subscribe before opening the socket: `openSocket` yields `.connected`
            // into the continuation synchronously after the task starts, and that
            // continuation is only created by `events()`. Calling `connect` first
            // would drop the very first `.connected` event, leaving `connected`
            // false forever on a cold launch (see StudioStore tests).
            let stream = await self.socket.events()
            await self.socket.connect(token: token, traceID: traceID)
            for await event in stream {
                await self.handle(event)
            }
        }
    }

    /// Seeds the reducer-owned gallery from a REST fetch; later `gallery_update`
    /// pushes keep replacing it, so views always read live state.
    public func applyFetchedGallery(_ gallery: [GalleryEntry]) {
        apply(.setGallery(gallery))
    }

    /// Session ended: drop the socket, pending work, and every piece of the
    /// previous user's studio state so a new sign-in never sees it.
    public func resetForSessionEnd() {
        disconnect()
        stopPlayback()
        performer = PerformerEngine()
        state = StudioState()
    }

    public func disconnect() {
        strokesFetchTask?.cancel()
        strokesFetchTask = nil
        socketTask?.cancel()
        socketTask = nil
        Task { await socket.disconnect() }
        Task { await traceBuffer.stopAutoFlush() }
    }

    /// Opens a fresh socket using whatever `tokenProvider.currentToken()`
    /// returns right now (net-auth spec §9.1: "on reconnect after a token
    /// refresh: open a fresh socket with the new token; don't try to
    /// upgrade/re-auth an existing connection"). Intended to be called by
    /// the app shell's foreground hook, after `AuthService
    /// .refreshSessionOnForeground()` has had a chance to rotate the token —
    /// this is the "something you provide" the scenePhase observer calls
    /// (net-auth spec §9.2 point 1). A no-op before the first `connect()`
    /// (nothing to reconnect yet); reuses the current trace session rather
    /// than starting a new one, since this is still the same studio visit.
    ///
    /// `async`, awaited all the way through by `handleAppWillEnterForeground`
    /// — a prior version fired this as a detached `Task` and let the app
    /// shell send `.resume` synchronously right after, racing the reconnect:
    /// the resume could reach the stale pre-background socket (or be
    /// silently dropped) before this method replaced it. Awaiting here
    /// guarantees the fresh socket's task is in place first.
    public func reconnectWithLatestToken() async {
        guard socketTask != nil else { return }
        guard let token = await tokenProvider.currentToken() else { return }
        currentToken = token
        recordSpan(name: "ws.connect")
        await socket.reconnectIfTokenChanged(token: token, traceID: currentTraceID)
    }

    /// Call from the app shell's background-transition hook (net-auth spec
    /// §8.1: "flush on background transition"). Records the transition as a
    /// trace span, then flushes immediately rather than waiting for the
    /// next 10s tick.
    public func handleAppDidEnterBackground() async {
        recordSpan(name: "app.background")
        await traceBuffer.flush()
    }

    /// Call from the app shell's foreground-transition hook, alongside (and
    /// after) `AuthService.refreshSessionOnForeground()`, and awaited to
    /// completion *before* the caller sends anything else (e.g. `.resume`)
    /// over the socket — see `reconnectWithLatestToken()`.
    public func handleAppWillEnterForeground() async {
        recordSpan(name: "app.foreground")
        await reconnectWithLatestToken()
    }

    // MARK: - Outbound

    public func send(_ message: ClientMessage) {
        Task { try? await socket.send(message) }
    }

    public func startStroke(at point: Point) {
        apply(.startStroke(point))
    }

    public func addStrokePoint(_ point: Point) {
        apply(.addPoint(point))
    }

    /// Local-only "leave gallery-view mode" event (protocol-state spec
    /// §5.4 `CLEAR_VIEWING`, ux spec §1.1's Gallery/Studio -> Home
    /// transitions). Added post-hoc to close a gap both the Studio and
    /// Home+Gallery UI packages flagged: they had no public way to
    /// dispatch a client-only `StudioEvent` (`viewingPiece`/`savedCanvas`
    /// are shared, authoritative state only `StudioStore` can mutate).
    /// `StudioReducer.reduce`'s `.clearViewing` case is a no-op when
    /// `viewingPiece` is already `nil`, so this is safe to call
    /// unconditionally.
    public func clearViewing() {
        apply(.clearViewing)
    }

    /// A program-painting reveal this device was animating has fully
    /// drawn its final image (program-painting spec §4.1) — dispatched by
    /// `CanvasView`'s `PaintingRevealController` once its playback loop
    /// finishes. Mirrors `clearViewing()`'s pattern of exposing a
    /// client-local `StudioEvent` publicly; the reducer itself guards
    /// against a stale/superseded `assetBase`.
    public func paintingPlaybackDone(assetBase: String) {
        apply(.paintingPlaybackDone(assetBase: assetBase))
    }

    /// Persists the user's Plotter/Paint choice into the shared,
    /// session-lived `StudioState.drawingStyle` (protocol-state spec's
    /// canonical "current style" slot, matching RN's
    /// `canvasState.drawingStyle`) rather than a per-view `@State`, so the
    /// choice survives Home <-> Studio round trips instead of resetting to
    /// Plotter every time Home is recreated. Mirrors `clearViewing()`'s
    /// pattern for exposing a client-only `StudioEvent` publicly.
    public func setStyle(_ style: DrawingStyleType) {
        apply(.setStyle(style, style == .paint ? .paint : .plotter))
    }

    /// Applies a gallery piece fetched via REST (`GalleryView.select`,
    /// mirroring RN's `handleGallerySelect`'s `GET /gallery/{n}/strokes`
    /// round-trip). Converts to the same `.loadCanvas` event the WS
    /// `load_canvas` message drives, so both paths reduce identically.
    public func applyLoadedGalleryPiece(_ strokes: GalleryPieceStrokes) {
        apply(.loadCanvas(LoadCanvasPayload(
            strokes: strokes.strokes,
            pieceNumber: strokes.pieceNumber,
            canvasWidth: strokes.canvasWidth,
            canvasHeight: strokes.canvasHeight,
            drawingStyle: strokes.drawingStyle,
            styleConfig: strokes.styleConfig,
            format: strokes.format,
            imageURL: strokes.imageURL
        )))
    }

    /// Applies `.setPaused` to local state immediately, *alongside* (not
    /// instead of) the `send(.pause)`/`send(.resume(...))` the caller sends
    /// over the wire — ux spec §1.2's optimistic-update pattern, matched
    /// from both reference clients. The server is still the source of
    /// truth; its own `paused` broadcast just applies this event again
    /// (idempotent).
    public func setPausedLocally(_ paused: Bool) {
        apply(.setPaused(paused))
    }

    /// Finishes the in-progress human stroke (ux spec §6.2: a tap/no-drag,
    /// fewer than 2 points, is discarded — nothing is dispatched or sent).
    ///
    /// Draws the stroke locally right away (no round-trip latency) and
    /// records its signature in `pendingSelfStrokes` so the server's
    /// `human_stroke` broadcast for this same stroke — every connection of
    /// this user gets it, including the one that sent it (protocol-state
    /// spec §1.1, §7.1) — is recognized as an echo and consumed instead of
    /// appended a second time. This is the fix for §7.1's "double stroke"
    /// quirk: dedupe by stroke identity (structural equality: same points,
    /// same author/type) rather than the RN app's un-deduped double-`ADD_STROKE`.
    public func endStroke() {
        let points = state.currentStroke
        apply(.endStroke)
        guard points.count >= 2 else { return }
        let path = Path(type: .polyline, points: points, author: .human)
        apply(.addStroke(path))
        pendingSelfStrokes.append(path)
        if pendingSelfStrokes.count > Self.maxPendingSelfStrokes {
            pendingSelfStrokes.removeFirst(pendingSelfStrokes.count - Self.maxPendingSelfStrokes)
        }
        send(.stroke(points: points))
    }

    // MARK: - Inbound

    private func handle(_ event: StudioSocketEvent) async {
        switch event {
        case .connected:
            connected = true
            recordSpan(name: "ws.connected")
        case let .message(message):
            await route(message)
        case let .disconnected(reason):
            connected = false
            switch reason {
            case .authenticationFailed:
                recordSpan(name: "ws.auth_error")
                strokesFetchTask?.cancel()  // don't keep polling against a dead session
                if let token = currentToken {
                    await onAuthenticationFailure?(token)
                }
            case let .other(code):
                recordSpan(name: "ws.disconnect", attributes: code.map { ["close_code": String($0)] } ?? [:])
            }
        case .decodeFailure:
            break
        }
    }

    private func route(_ message: ServerMessage) async {
        if case let .agentStrokesReady(count, batchID, pieceNumber) = message {
            await handleStrokesReady(count: count, batchID: batchID, pieceNumber: pieceNumber)
            return
        }
        if case let .humanStroke(path) = message, consumeIfSelfEcho(path) {
            return
        }
        // `UUID` rather than the sequential `idCounter` here: `nextID` must
        // be a plain synchronous, non-isolated closure (it's called from
        // `MessageRouter`, which knows nothing about `@MainActor`), so it
        // can't reach into this MainActor-isolated instance's counter.
        let environment = RoutingEnvironment(
            now: { Date().timeIntervalSince1970 * 1000 },
            nextID: { UUID().uuidString }
        )
        for studioEvent in MessageRouter.route(message, environment: environment) {
            apply(studioEvent)
        }
        if case .newCanvas = message {
            applyPendingPrompt()
        }
    }

    /// Returns `true` (and consumes the matching entry) when `path` is this
    /// device's own stroke echoing back — see `endStroke()`.
    private func consumeIfSelfEcho(_ path: Path) -> Bool {
        guard let index = pendingSelfStrokes.firstIndex(of: path) else { return false }
        pendingSelfStrokes.remove(at: index)
        return true
    }

    /// Protocol-state spec §6.2: guards, then fetches+clears the server's
    /// pending-stroke queue, cancelling any prior in-flight fetch for a
    /// superseded batch.
    private func handleStrokesReady(count: Int, batchID: Int, pieceNumber: Int) async {
        guard let signal = MessageRouter.routeStrokesReady(
            count: count, batchID: batchID, pieceNumber: pieceNumber, state: state
        ) else { return }
        if let sync = signal.pieceNumberSyncEvent { apply(sync) }

        strokesFetchTask?.cancel()
        let spanID = TraceSpanBuffer.newSpanID()
        let startTime = nowMillis()
        strokesFetchTask = Task { [weak self] in
            guard let self else { return }
            // Retry until success or cancellation (a newer
            // `agent_strokes_ready` superseding this fetch, via the
            // `strokesFetchTask?.cancel()` above, or the task being torn
            // down) — never give up after a fixed attempt count. The
            // server already committed this batch; a client that stops
            // retrying after ~9s of degraded network can permanently drop
            // strokes the agent already drew, with no other resync trigger
            // while the WebSocket itself stays connected. A genuine auth
            // failure is handled separately, via `onUnauthorized` inside
            // `CodeMonetRESTClient`, not by this retry loop giving up.
            while !Task.isCancelled {
                do {
                    let response = try await self.rest.pendingStrokes()
                    self.apply(.enqueueStrokes(response.strokes))
                    self.recordSpan(
                        name: "strokes.fetch",
                        spanID: spanID,
                        startTime: startTime,
                        attributes: ["batch_id": String(batchID), "piece_number": String(pieceNumber)]
                    )
                    return
                } catch {
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
        }
    }

    func apply(_ event: StudioEvent) {
        state = StudioReducer.reduce(state, event)
    }

    // MARK: - Tracing

    private func nowMillis() -> Double {
        Date().timeIntervalSince1970 * 1000
    }

    /// Records a point-in-time span (`startTime == endTime`) against the
    /// current trace session, if any. A no-op before `connect()` has ever
    /// run (net-auth spec §8.1's spans only make sense while correlating
    /// with a live/attempted connection).
    private func recordSpan(name: String, attributes: [String: String] = [:]) {
        guard let traceID = currentTraceID else { return }
        let time = nowMillis()
        let span = ClientSpan(
            traceId: traceID,
            spanId: TraceSpanBuffer.newSpanID(),
            name: name,
            startTime: time,
            endTime: time,
            attributes: attributes
        )
        Task { await traceBuffer.record(span) }
    }

    /// Records a span with an already-known `spanID`/`startTime` (the
    /// stroke-fetch span, whose duration matters — see `handleStrokesReady`).
    private func recordSpan(name: String, spanID: String, startTime: Double, attributes: [String: String] = [:]) {
        guard let traceID = currentTraceID else { return }
        let span = ClientSpan(
            traceId: traceID,
            spanId: spanID,
            name: name,
            startTime: startTime,
            endTime: nowMillis(),
            attributes: attributes
        )
        Task { await traceBuffer.record(span) }
    }

    // MARK: - Playback loop

    /// Starts the `PerformerEngine`'s per-frame tick loop (performer-render
    /// spec §11). Call when entering the studio screen; `stopPlayback` when
    /// leaving it or backgrounding (ux spec §1.2).
    public func startPlayback() {
        stopPlayback()
        let link = CADisplayLink(target: DisplayLinkTarget { [weak self] in self?.tick() }, selector: #selector(DisplayLinkTarget.fire))
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    public func stopPlayback() {
        displayLink?.invalidate()
        displayLink = nil
    }

    private func tick() {
        guard !state.paused else { return }  // paused means no reveal progress, like the web performer
        let result = performer.tick(state: state)
        for event in result.events { apply(event) }
        if let batchID = result.completedBatchID {
            send(.animationDone(batchID: batchID))
        }
    }
}

/// `CADisplayLink` needs an `@objc` selector target; this tiny shim lets
/// `StudioStore` supply a plain closure instead of conforming itself.
private final class DisplayLinkTarget: NSObject {
    private let callback: () -> Void
    init(_ callback: @escaping () -> Void) { self.callback = callback }
    @objc func fire() { callback() }
}
