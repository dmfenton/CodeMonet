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

    private let socket: StudioWebSocketClient
    private let rest: CodeMonetRESTClient
    private let performer = PerformerEngine()
    private let tokenProvider: any TokenProviding
    private var displayLink: CADisplayLink?
    private var socketTask: Task<Void, Never>?
    private var strokesFetchTask: Task<Void, Never>?

    public init(environment: CodeMonetEnvironment, tokenProvider: any TokenProviding) {
        socket = StudioWebSocketClient(baseURL: environment.wsBaseURL)
        rest = CodeMonetRESTClient(baseURL: environment.apiBaseURL, tokenProvider: tokenProvider)
        self.tokenProvider = tokenProvider
    }

    /// Opens the WebSocket and starts consuming its event stream. Safe to
    /// call once per app session; reconnects are the socket's own
    /// responsibility (net-auth spec §9.1).
    public func connect() {
        guard socketTask == nil else { return }
        socketTask = Task { [weak self] in
            guard let self else { return }
            guard let token = await self.tokenProvider.currentToken() else { return }
            await self.socket.connect(token: token, traceID: nil)
            for await event in await self.socket.events() {
                await self.handle(event)
            }
        }
    }

    public func disconnect() {
        socketTask?.cancel()
        socketTask = nil
        Task { await socket.disconnect() }
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
    public func endStroke() {
        let points = state.currentStroke
        apply(.endStroke)
        guard points.count >= 2 else { return }
        send(.stroke(points: points))
    }

    // MARK: - Inbound

    private func handle(_ event: StudioSocketEvent) async {
        switch event {
        case .connected:
            connected = true
        case let .message(message):
            await route(message)
        case .disconnected:
            connected = false
        case .decodeFailure:
            break
        }
    }

    private func route(_ message: ServerMessage) async {
        if case let .agentStrokesReady(count, batchID, pieceNumber) = message {
            await handleStrokesReady(count: count, batchID: batchID, pieceNumber: pieceNumber)
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

    /// Protocol-state spec §6.2: guards, then fetches+clears the server's
    /// pending-stroke queue, cancelling any prior in-flight fetch for a
    /// superseded batch.
    private func handleStrokesReady(count: Int, batchID: Int, pieceNumber: Int) async {
        guard let signal = MessageRouter.routeStrokesReady(
            count: count, batchID: batchID, pieceNumber: pieceNumber, state: state
        ) else { return }
        if let sync = signal.pieceNumberSyncEvent { apply(sync) }

        strokesFetchTask?.cancel()
        strokesFetchTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let response = try await self.rest.pendingStrokes()
                    self.apply(.enqueueStrokes(response.strokes))
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
