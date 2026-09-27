/// Tracks a foreground Resume across WebSocket reconnects. The store sends
/// only after init and keeps the request until a server `paused: false` frame.
struct ForegroundResumeState {
    struct Attempt: Equatable {
        let connection: Int
        let request: Int
    }

    private(set) var initialized = false
    private(set) var pending = false
    private var sending = false
    private var connectionGeneration = 0
    private var requestGeneration = 0

    mutating func connected() {
        connectionGeneration += 1
        initialized = false
    }

    mutating func receivedInit() { initialized = true }

    mutating func disconnected() {
        connectionGeneration += 1
        initialized = false
    }

    mutating func request() {
        requestGeneration += 1
        pending = true
    }

    mutating func cancel() {
        requestGeneration += 1
        pending = false
    }

    mutating func acknowledged() { pending = false }

    mutating func beginSend() -> Attempt? {
        guard pending, initialized, !sending else { return nil }
        sending = true
        return Attempt(connection: connectionGeneration, request: requestGeneration)
    }

    func isCurrent(_ attempt: Attempt) -> Bool {
        pending && initialized
            && attempt.connection == connectionGeneration
            && attempt.request == requestGeneration
    }

    /// A changed connection or request needs another send after the old one
    /// has finished. An ordinary send failure waits for the next init frame.
    mutating func finishSend(_ attempt: Attempt) -> Bool {
        sending = false
        return pending && initialized && !isCurrent(attempt)
    }
}
