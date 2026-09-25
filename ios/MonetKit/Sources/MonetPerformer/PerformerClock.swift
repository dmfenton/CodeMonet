import Foundation

/// A source of monotonic time for `PerformerEngine`, injected so playback
/// pacing is deterministic and testable (performer-render spec §11: "Swift:
/// a `CADisplayLink` or `Timer` at 1000/60 ≈ 16.67ms"). Units are seconds,
/// matching `DispatchTime`/`CACurrentMediaTime` conventions.
public protocol PerformerClock: Sendable {
    func now() -> TimeInterval
}

/// Production clock backed by `Date`. The app target drives ticks from a
/// `CADisplayLink`/`Timer`; this clock only supplies "what time is it".
public struct SystemPerformerClock: PerformerClock {
    public init() {}
    public func now() -> TimeInterval { Date().timeIntervalSinceReferenceDate }
}

/// A manually-advanced clock for tests: deterministic, no wall-clock
/// dependency, and lets a test assert exact behavior at exact simulated
/// times.
public final class ManualPerformerClock: PerformerClock, @unchecked Sendable {
    private var current: TimeInterval
    private let lock = NSLock()

    public init(start: TimeInterval = 0) {
        current = start
    }

    public func now() -> TimeInterval {
        lock.lock()
        defer { lock.unlock() }
        return current
    }

    public func advance(by interval: TimeInterval) {
        lock.lock()
        current += interval
        lock.unlock()
    }
}
