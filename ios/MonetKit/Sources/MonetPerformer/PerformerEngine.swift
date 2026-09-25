import Foundation
import MonetProtocol
import MonetStudio

/// Timing constants transcribed exactly from performer-render spec §11.1.
/// Do not "round" these — the reveal/draw pacing is a UX contract, not a
/// tuning knob a builder should feel free to adjust without a product call.
public enum PerformerConstants {
    public static let holdAfterWordsMS: Double = 267
    public static let minPointsPerFrame = 24
    public static let maxPointsPerFrame = 240
    public static let targetPixelsPerSecond: Double = 9000
    public static let travelSpeedMultiplier: Double = 6.0
    public static let penLiftThreshold: Double = 2.0
    public static let interStrokePauseMS: Double = 0
    public static let penSettleDelayMS: Double = 0
    public static let easeMinSpeedRatio: Double = 0.75
    public static let holdEventMS: Double = 167
    public static let maxEventHoldMS: Double = 5000
    public static let wordDelayMS: Double = 150.0 / 3.0
    public static let frameDelayMS: Double = 1000.0 / 60.0
}

/// The per-frame output of `PerformerEngine.tick`: reducer events to apply
/// (in order) plus, when a `'strokes'` item's whole batch finishes, the
/// batch id to acknowledge back to the server as `animation_done`
/// (performer-render spec §11.4, "fires onStrokesComplete(batchId)").
public struct PerformerTickResult: Equatable, Sendable {
    public var events: [StudioEvent]
    public var completedBatchID: Int?

    public init(events: [StudioEvent] = [], completedBatchID: Int? = nil) {
        self.events = events
        self.completedBatchID = completedBatchID
    }
}

/// Drives the stroke/text/pen playback pipeline forward one frame at a time
/// (performer-render spec §11). Pure with respect to its inputs — given the
/// same `(state, now)` it produces the same `StudioEvent`s — but holds a
/// small amount of internal timing state (last-word-reveal time, per-phase
/// timers) that a plain `(State, Event) -> State` reducer can't express,
/// since the "which phase are we in / when did it start" bookkeeping isn't
/// itself part of `StudioState`. The caller is responsible for applying the
/// returned events to `StudioState` via `StudioReducer.reduce` before the
/// next tick (the engine reads `state.performance` fresh each call).
public final class PerformerEngine: @unchecked Sendable {
    private let clock: any PerformerClock
    private var lastWordRevealTime: TimeInterval?
    private var stageEnteredAt: TimeInterval?
    private var lastFrameTime: TimeInterval?
    private var strokePointIndex: Int = 0
    private var travelPath: [Point] = []
    private var travelIndex: Int = 0
    private var phase: StrokePhase = .penTravel

    private enum StrokePhase {
        case interStrokePause
        case penTravel
        case penSettle
        case drawing
    }

    public init(clock: any PerformerClock = SystemPerformerClock()) {
        self.clock = clock
    }

    /// Advances playback by one frame against `state.performance`. Call this
    /// from a display-link/timer callback, then apply the returned events via
    /// `StudioReducer.reduce` and store the result before the next call.
    public func tick(state: StudioState) -> PerformerTickResult {
        let now = clock.now()
        defer { lastFrameTime = now }

        if state.performance.onStage == nil {
            resetPerFrameCursors()
            guard !state.performance.buffer.isEmpty else { return PerformerTickResult() }
            return PerformerTickResult(events: [.advanceStage])
        }

        switch state.performance.onStage {
        case .words:
            return tickWords(state: state, now: now)
        case .event:
            return tickEvent(state: state, now: now)
        case let .strokes(_, strokes):
            return tickStrokes(strokes: strokes, state: state, now: now)
        case nil:
            return PerformerTickResult()
        }
    }

    private func resetPerFrameCursors() {
        lastWordRevealTime = nil
        stageEnteredAt = nil
        strokePointIndex = 0
        travelPath = []
        travelIndex = 0
        phase = .interStrokePause
    }

    private func tickWords(state: StudioState, now: TimeInterval) -> PerformerTickResult {
        guard case let .words(_, text) = state.performance.onStage else { return PerformerTickResult() }
        let totalWords = text.split(separator: " ").count
        if state.performance.wordIndex < totalWords {
            let last = lastWordRevealTime ?? now
            if (now - last) * 1000 >= PerformerConstants.wordDelayMS {
                lastWordRevealTime = now
                return PerformerTickResult(events: [.revealWord])
            }
            return PerformerTickResult()
        }
        let enteredHold = stageEnteredAt ?? now
        if stageEnteredAt == nil { stageEnteredAt = now }
        if (now - enteredHold) * 1000 >= PerformerConstants.holdAfterWordsMS {
            return PerformerTickResult(events: [.stageComplete])
        }
        return PerformerTickResult()
    }

    private func tickEvent(state: StudioState, now: TimeInterval) -> PerformerTickResult {
        let enteredAt = stageEnteredAt ?? now
        if stageEnteredAt == nil { stageEnteredAt = now }
        let heldMS = (now - enteredAt) * 1000
        let canAdvance = heldMS >= PerformerConstants.holdEventMS && !state.performance.buffer.isEmpty
        let mustAdvance = heldMS >= PerformerConstants.maxEventHoldMS
        if canAdvance || mustAdvance {
            return PerformerTickResult(events: [.stageComplete])
        }
        return PerformerTickResult()
    }

    private func tickStrokes(strokes: [PendingStroke], state: StudioState, now: TimeInterval) -> PerformerTickResult {
        guard state.performance.strokeIndex < strokes.count else {
            return PerformerTickResult(events: [.stageComplete], completedBatchID: strokes.first?.batchId)
        }
        let stroke = strokes[state.performance.strokeIndex]
        let elapsed = (lastFrameTime.map { now - $0 }) ?? (1.0 / 60.0)

        switch phase {
        case .interStrokePause:
            phase = .penTravel
            return tickStrokes(strokes: strokes, state: state, now: now)

        case .penTravel:
            guard let target = state.performance.travelTarget else {
                phase = .penSettle
                return PerformerTickResult(events: [.penTravelComplete])
            }
            let start = state.performance.penPosition ?? target
            if distance(start, target) <= PerformerConstants.penLiftThreshold {
                phase = .penSettle
                return PerformerTickResult(events: [.penTravelComplete])
            }
            if travelPath.isEmpty {
                travelPath = Self.synthesizeTravelPath(from: start, to: target)
                travelIndex = 0
            }
            let budget = elapsed * PerformerConstants.targetPixelsPerSecond * PerformerConstants.travelSpeedMultiplier
            let batch = Self.batchPoints(travelPath, startIndex: &travelIndex, targetPixels: budget)
            if travelIndex >= travelPath.count {
                phase = .penSettle
                return PerformerTickResult(events: [.penTravelBatch(batch), .penTravelComplete])
            }
            return PerformerTickResult(events: [.penTravelBatch(batch)])

        case .penSettle:
            phase = .drawing
            strokePointIndex = 0
            return tickStrokes(strokes: strokes, state: state, now: now)

        case .drawing:
            let points = stroke.points
            guard !points.isEmpty else {
                phase = .interStrokePause
                return PerformerTickResult(events: [.strokeComplete])
            }
            let progress = Double(strokePointIndex) / Double(max(1, points.count - 1))
            let easing = PerformerConstants.easeMinSpeedRatio
                + (1 - PerformerConstants.easeMinSpeedRatio) * sin(progress * .pi)
            let budget = elapsed * PerformerConstants.targetPixelsPerSecond * easing
            let style: PartialStrokeStyle? = strokePointIndex == 0
                ? PartialStrokeStyle(color: stroke.path.color, strokeWidth: stroke.path.strokeWidth, opacity: stroke.path.opacity)
                : nil
            let batch = Self.batchPoints(points, startIndex: &strokePointIndex, targetPixels: budget)
            if strokePointIndex >= points.count {
                phase = .interStrokePause
                return PerformerTickResult(events: [.strokeProgressBatch(points: batch, style: style), .strokeComplete])
            }
            return PerformerTickResult(events: [.strokeProgressBatch(points: batch, style: style)])
        }
    }

    /// `synthesizeTravelPath` (performer-render spec §11.5).
    static func synthesizeTravelPath(from start: Point, to end: Point) -> [Point] {
        let dist = distance(start, end)
        let numPoints = max(2, Int((dist * 0.3).rounded(.up)))
        return (0 ... numPoints).map { i in
            let t = Double(i) / Double(numPoints)
            let eased = t < 0.5 ? 2 * t * t : 1 - pow(-2 * t + 2, 2) / 2
            return Point(x: start.x + (end.x - start.x) * eased, y: start.y + (end.y - start.y) * eased)
        }
    }

    /// Shared per-frame point batching (performer-render spec §11.6).
    static func batchPoints(_ points: [Point], startIndex: inout Int, targetPixels: Double) -> [Point] {
        var batch: [Point] = []
        var accumulated: Double = 0
        var i = startIndex
        while i < points.count, batch.count < PerformerConstants.maxPointsPerFrame {
            let point = points[i]
            if let last = batch.last {
                accumulated += distance(last, point)
                if accumulated > targetPixels, batch.count >= PerformerConstants.minPointsPerFrame { break }
            }
            batch.append(point)
            i += 1
        }
        startIndex = i
        return batch
    }

    private static func distance(_ a: Point, _ b: Point) -> Double {
        ((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)).squareRoot()
    }

    private func distance(_ a: Point, _ b: Point) -> Double {
        Self.distance(a, b)
    }
}
