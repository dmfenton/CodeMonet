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
public actor StudioWebSocketClient {
    public struct Configuration: Sendable {
        public var reconnectInterval: TimeInterval
        public init(reconnectInterval: TimeInterval = 3.0) {
            self.reconnectInterval = reconnectInterval
        }
    }

    private let baseURL: URL
    private let configuration: Configuration
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var generation: Int = 0
    private var continuation: AsyncStream<StudioSocketEvent>.Continuation?

    public init(baseURL: URL, configuration: Configuration = Configuration(), session: URLSession = .shared) {
        self.baseURL = baseURL
        self.configuration = configuration
        self.session = session
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
    /// (net-auth spec §9). Guards against duplicate concurrent connections —
    /// calling this while already connected/connecting replaces the prior
    /// socket via a fresh `generation`, so a late event from the abandoned
    /// socket is ignored (protocol-state spec §1.2's stale-connection guard).
    public func connect(token: String, traceID: String?) {
        generation += 1
        let currentGeneration = generation
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        var query = [URLQueryItem(name: "token", value: token)]
        if let traceID { query.append(URLQueryItem(name: "trace_id", value: traceID)) }
        components?.queryItems = query
        guard let url = components?.url else { return }

        let newTask = session.webSocketTask(with: url)
        task = newTask
        newTask.resume()
        continuation?.yield(.connected)
        receiveLoop(task: newTask, generation: currentGeneration)
    }

    public func disconnect() {
        generation += 1
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    public func send(_ message: ClientMessage) async throws {
        guard let task else { return }
        let data = try JSONEncoder().encode(message)
        let text = String(decoding: data, as: UTF8.self)
        try await task.send(.string(text))
    }

    private func receiveLoop(task: URLSessionWebSocketTask, generation: Int) {
        Task {
            do {
                let message = try await task.receive()
                guard self.generation == generation else { return } // stale-socket guard
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
                let closeCode = task.closeCode
                let reason: StudioSocketCloseReason = closeCode.rawValue == 4001
                    ? .authenticationFailed
                    : .other(code: closeCode == .invalid ? nil : closeCode.rawValue)
                self.continuation?.yield(.disconnected(reason))
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
}
