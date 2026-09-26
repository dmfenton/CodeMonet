import Foundation
import MonetProtocol

/// Close codes the server sends with protocol meaning (protocol-state spec
/// §1.1, net-auth spec §9.1). Any other code (including transport errors)
/// gets the generic fixed-delay reconnect.
public enum StudioSocketCloseReason: Equatable, Sendable {
    /// Missing/invalid token, or user not found/inactive. Do not
    /// auto-reconnect; the caller should attempt `restoreSession()` and
    /// reconnect with a fresh token, or sign out (net-auth spec §9.2).
    case authenticationFailed
    /// `MAX_CONNECTIONS_PER_USER` exceeded, or any other close code, or a
    /// transport-level error. Reconnect after `reconnectInterval`.
    case other(code: Int?)
}

/// Events the app-level `StudioStore` observes from the socket. Intentionally
/// coarse (not a full delegate protocol) since there is exactly one
/// consumer per socket instance.
public enum StudioSocketEvent: Sendable {
    case connected
    case message(ServerMessage)
    case disconnected(StudioSocketCloseReason)
    /// A frame that failed to decode as JSON/`ServerMessage`. Logged, never
    /// fatal — the socket stays open (protocol-state spec §1.3 step 7).
    case decodeFailure(String)
}

/// Owns one WebSocket connection lifecycle (net-auth spec §9, protocol-state
/// spec §1). `URLSessionWebSocketTask`-based; reconnect policy and the
/// stale-socket guard are this type's responsibility so `StudioStore` can
/// stay a thin consumer of `events`.
///
/// Reconnect policy (net-auth spec §1.2's "consider adding capped
/// exponential backoff — nothing server-side requires the fixed 3s
/// interval"): any close *other* than `4001` schedules an automatic
/// reconnect using the same token/trace id last given to `connect`, with
/// full-jitter exponential backoff (`base * 2^attempt`, capped at
/// `maxReconnectInterval`, then a uniform random delay in `[0, capped]`) —
/// an improvement over the RN app's fixed 3000ms retry. The attempt counter
/// resets whenever a frame is actually received (protocol-state spec §1.3:
/// a live connection always gets an `init` message as its first frame, so
/// this is a reasonable proxy for "the reconnect succeeded"). `4001`
/// (auth failure) never auto-reconnects here — protocol-state spec §1.2 /
/// net-auth spec §9.2 requires a fresh token first, which only the caller
/// (holding a `TokenProviding`) can supply.
public actor StudioWebSocketClient {
    public struct Configuration: Sendable {
        /// Base delay for the first automatic-reconnect attempt.
        public var reconnectInterval: TimeInterval
        /// Upper bound the exponential backoff never exceeds (net-auth spec
        /// §1.2's "capped at ~30s").
        public var maxReconnectInterval: TimeInterval
        public init(reconnectInterval: TimeInterval = 3.0, maxReconnectInterval: TimeInterval = 30.0) {
            self.reconnectInterval = reconnectInterval
            self.maxReconnectInterval = maxReconnectInterval
        }
    }

    private let baseURL: URL
    private let configuration: Configuration
    private let session: URLSession
    /// Injected so tests can assert backoff scheduling without a real
    /// 30-second wait; defaults to a real `Task.sleep`.
    private let sleeper: any Sleeping
    /// Injected source of `[0, 1)` randomness for jitter; defaults to
    /// `Double.random`. Swapped in tests for a deterministic value.
    private let jitterSource: @Sendable () -> Double

    private var task: URLSessionWebSocketTask?
    private var generation: Int = 0
    private var continuation: AsyncStream<StudioSocketEvent>.Continuation?
    private var lastToken: String?
    private var lastTraceID: String?
    /// Number of consecutive automatic reconnects attempted since the last
    /// time a frame was received (or since the last explicit `connect`).
    /// `internal`, not `private`, so `@testable import` tests can observe it
    /// without exposing it as part of the public contract.
    private(set) var reconnectAttempt: Int = 0
    private var reconnectTask: Task<Void, Never>?

    public init(
        baseURL: URL,
        configuration: Configuration = Configuration(),
        session: URLSession = .shared,
        sleeper: any Sleeping = SystemSleeper(),
        jitterSource: @escaping @Sendable () -> Double = { Double.random(in: 0 ..< 1) }
    ) {
        self.baseURL = baseURL
        self.configuration = configuration
        self.session = session
        self.sleeper = sleeper
        self.jitterSource = jitterSource
    }

    /// A cold stream of connection lifecycle + message events. Call `connect`
    /// to start actually producing events; the stream itself never
    /// terminates on its own (matches "one connection per session, reconnect
    /// forever" — net-auth spec §9.1).
    public func events() -> AsyncStream<StudioSocketEvent> {
        AsyncStream { continuation in
            self.continuation = continuation
        }
    }

    /// Opens a new connection with `token`/`traceID` as query params
    /// (net-auth spec §9). Also the entry point for an app-triggered
    /// reconnect (e.g. after a foreground token refresh, net-auth spec
    /// §9.1's "on reconnect after a token refresh: open a fresh socket with
    /// the new token") — calling this while already connected/connecting
    /// replaces the prior socket via a fresh `generation`, so a late event
    /// from the abandoned socket is ignored (protocol-state spec §1.2's
    /// stale-connection guard), and resets the automatic-reconnect backoff.
    public func connect(token: String, traceID: String?) {
        lastToken = token
        lastTraceID = traceID
        reconnectAttempt = 0
        reconnectTask?.cancel()
        reconnectTask = nil
        openSocket(token: token, traceID: traceID)
    }

    /// Like `connect(token:traceID:)`, but a no-op when `token` matches the
    /// last token given *and* a socket task is currently believed live —
    /// avoids opening a duplicate connection on an app-triggered reconnect
    /// (e.g. a foreground transition) that didn't actually rotate the token
    /// (net-auth spec §9.1). Callers that need an unconditional fresh socket
    /// (the initial `connect`) should keep using `connect` directly.
    public func reconnectIfTokenChanged(token: String, traceID: String?) {
        guard task == nil || token != lastToken else { return }
        connect(token: token, traceID: traceID)
    }

    public func disconnect() {
        generation += 1
        reconnectTask?.cancel()
        reconnectTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    public func send(_ message: ClientMessage) async throws {
        guard let task else { return }
        let data = try JSONEncoder().encode(message)
        let text = String(decoding: data, as: UTF8.self)
        try await task.send(.string(text))
    }

    private func openSocket(token: String, traceID: String?) {
        generation += 1
        let currentGeneration = generation
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        var query = [URLQueryItem(name: "token", value: token)]
        if let traceID { query.append(URLQueryItem(name: "trace_id", value: traceID)) }
        components?.queryItems = query
        guard let url = components?.url else { return }

        // Guard against duplicate concurrent connections (net-auth spec
        // §9.1): a prior socket that's still CONNECTING/OPEN is abandoned
        // rather than closed otherwise, leaking a live connection every
        // time `connect`/`reconnectWithLatestToken` fires while one is
        // already up (e.g. a foreground transition that didn't actually
        // need a new token).
        task?.cancel(with: .goingAway, reason: nil)

        let newTask = session.webSocketTask(with: url)
        task = newTask
        newTask.resume()
        continuation?.yield(.connected)
        receiveLoop(task: newTask, generation: currentGeneration)
    }

    private func receiveLoop(task: URLSessionWebSocketTask, generation: Int) {
        Task {
            do {
                let message = try await task.receive()
                guard self.generation == generation else { return } // stale-socket guard
                self.reconnectAttempt = 0 // a live frame proves this connection is good
                switch message {
                case let .string(text):
                    self.handleFrame(text)
                case let .data(data):
                    self.handleFrame(String(decoding: data, as: UTF8.self))
                @unknown default:
                    break
                }
                self.receiveLoop(task: task, generation: generation)
            } catch {
                guard self.generation == generation else { return }
                // A dead socket is not a connection: let reconnectIfTokenChanged reopen it.
                if self.task === task { self.task = nil }
                let closeCode = task.closeCode
                let reason = Self.closeReason(rawCloseCode: closeCode == .invalid ? nil : closeCode.rawValue)
                self.continuation?.yield(.disconnected(reason))
                if case .other = reason {
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handleFrame(_ text: String) {
        do {
            let message = try JSONDecoder().decode(ServerMessage.self, from: Data(text.utf8))
            continuation?.yield(.message(message))
        } catch {
            continuation?.yield(.decodeFailure(text))
        }
    }

    /// Schedules one automatic reconnect attempt using the last known
    /// token/trace id. A no-op if `connect` was never called (nothing to
    /// retry) — this only fires from `receiveLoop`, which can't run before a
    /// first `connect`, so that guard is defense-in-depth, not a real path.
    private func scheduleReconnect() {
        guard let token = lastToken else { return }
        let traceID = lastTraceID
        let attempt = reconnectAttempt
        reconnectAttempt += 1
        let delay = Self.backoffDelay(
            attempt: attempt,
            base: configuration.reconnectInterval,
            cap: configuration.maxReconnectInterval,
            jitter: jitterSource()
        )
        let generationAtSchedule = generation
        reconnectTask = Task { [weak self, sleeper] in
            await sleeper.sleep(seconds: delay)
            guard let self else { return }
            await self.reconnectIfStillCurrent(generation: generationAtSchedule, token: token, traceID: traceID)
        }
    }

    private func reconnectIfStillCurrent(generation: Int, token: String, traceID: String?) {
        // A newer explicit `connect`/`disconnect` already bumped `generation`
        // since this attempt was scheduled — don't race it with a stale retry.
        guard self.generation == generation else { return }
        openSocket(token: token, traceID: traceID)
    }

    /// Maps a raw WS close code to protocol meaning (protocol-state spec
    /// §1.1, net-auth spec §9.1). `nil` covers a transport-level error with
    /// no close code at all. Pure/`static` so it's directly unit-testable
    /// without a real socket.
    static func closeReason(rawCloseCode: Int?) -> StudioSocketCloseReason {
        rawCloseCode == 4001 ? .authenticationFailed : .other(code: rawCloseCode)
    }

    /// Full-jitter exponential backoff (`base * 2^attempt`, capped, then a
    /// uniform draw over `[0, capped]`) — the AWS-recommended formula that
    /// avoids a reconnect-storm thundering herd better than capped backoff
    /// alone. `jitter` must be in `[0, 1)`; the result is always `>= 0`.
    static func backoffDelay(attempt: Int, base: TimeInterval, cap: TimeInterval, jitter: Double) -> TimeInterval {
        guard base > 0, cap > 0 else { return 0 }
        let exponential = base * pow(2, Double(max(0, attempt)))
        let capped = min(exponential, cap)
        return capped * min(max(jitter, 0), 1)
    }
}

/// Abstracts `Task.sleep` so reconnect-backoff scheduling is testable without
/// real wall-clock waits.
public protocol Sleeping: Sendable {
    func sleep(seconds: TimeInterval) async
}

public struct SystemSleeper: Sleeping {
    public init() {}
    public func sleep(seconds: TimeInterval) async {
        guard seconds > 0 else { return }
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
    }
}
