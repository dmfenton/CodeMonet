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

    /// Fires on a live `4001`/auth-failure close (protocol-state spec §1.2,
    /// net-auth spec §9.2 point 2) — the app shell should wire this to
    /// `AuthService.signOut()`. Not wired here: `StudioStore` only knows
    /// `TokenProviding`, never the concrete `AuthService`, so it can't sign
    /// anyone out itself. A plain closure (rather than a new delegate
    /// protocol) since there is exactly one real consumer.
    public var onAuthenticationFailure: (@Sendable () async -> Void)?

    private let socket: StudioWebSocketClient
    private let rest: CodeMonetRESTClient
    private let traceBuffer: TraceSpanBuffer
    private let performer = PerformerEngine()
    private let tokenProvider: any TokenProviding
    private var displayLink: CADisplayLink?
    private var socketTask: Task<Void, Never>?
    private var strokesFetchTask: Task<Void, Never>?
    /// The current drawing session's trace id (net-auth spec §8.1
    /// `newSession()`), generated once per `connect()` and reused across
    /// automatic/foreground reconnects so server-side spans keep
    /// correlating with the same client session until the studio is left.
    private var currentTraceID: String?
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

    public init(environment: CodeMonetEnvironment, tokenProvider: any TokenProviding) {
        socket = StudioWebSocketClient(baseURL: environment.wsBaseURL)
        rest = CodeMonetRESTClient(baseURL: environment.apiBaseURL, tokenProvider: tokenProvider)
        traceBuffer = TraceSpanBuffer(baseURL: environment.apiBaseURL)
        self.tokenProvider = tokenProvider
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
            guard let token = await self.tokenProvider.currentToken() else { return }
            self.recordSpan(name: "ws.connect")
            await self.socket.connect(token: token, traceID: traceID)
            for await event in await self.socket.events() {
                await self.handle(event)
            }
        }
    }

    public func disconnect() {
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
    public func reconnectWithLatestToken() {
        guard socketTask != nil else { return }
        Task { [weak self] in
            guard let self else { return }
            guard let token = await self.tokenProvider.currentToken() else { return }
            self.recordSpan(name: "ws.connect")
            await self.socket.connect(token: token, traceID: self.currentTraceID)
        }
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
    /// after) `AuthService.refreshSessionOnForeground()` — see
    /// `reconnectWithLatestToken()`.
    public func handleAppWillEnterForeground() {
        recordSpan(name: "app.foreground")
        reconnectWithLatestToken()
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
                await onAuthenticationFailure?()
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

    private func apply(_ event: StudioEvent) {
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
