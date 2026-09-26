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
/// (performer-render spec §11, exact control flow ported from
/// `shared/src/hooks/usePerformer.ts`). Pure with respect to its inputs —
/// given the same `(state, now)` it produces the same `StudioEvent`s — but
/// holds a small amount of internal timing state (last-reveal times,
/// per-phase timers) that a plain `(State, Event) -> State` reducer can't
/// express, since the "which phase are we in / when did it start" bookkeeping
/// isn't itself part of `StudioState`. The caller is responsible for applying
/// the returned events to `StudioState` via `StudioReducer.reduce` before the
/// next tick (the engine reads `state.performance` fresh each call).
///
/// Two timers (`lastWordRevealTime`, `lastPointBatchDispatchTime`)
/// deliberately persist for the engine's entire lifetime rather than
/// resetting per buffer item, mirroring `usePerformer.ts`'s
/// `lastWordTimeRef`/`lastStrokeTimeRef` (never cleared on `ADVANCE_STAGE`).
/// That is what makes the *first* word of a chunk, and the *first* point
/// batch of a stroke sequence, appear immediately rather than waiting a full
/// `wordDelayMS`/`frameDelayMS` after nothing has happened yet — `nil` (no
/// prior dispatch recorded) is treated as "infinitely long ago".
public final class PerformerEngine: @unchecked Sendable {
    private let clock: any PerformerClock

    // Word/event hold timers (protocol-state spec §11.2-11.3).
    private var lastWordRevealTime: TimeInterval?
    private var stageEnteredAt: TimeInterval?

    // Stroke playback cursors (spec §11.4) — reset once per buffer item.
    private var strokePointIndex: Int = 0
    private var travelPath: [Point] = []
    private var travelIndex: Int = 0
    private var interStrokePauseEnteredAt: TimeInterval?
    private var penSettleEnteredAt: TimeInterval?
    /// Whether phase 2 (pen travel) has already been decided (synthesized a
    /// path, or determined no travel is needed) for the *current* stroke.
    /// Without this, a stroke whose own drawing sets `penPosition` for the
    /// first time (i.e. it started with `penPosition == nil`) could cause
    /// phase 2's init check to spuriously re-fire mid-draw on a later tick,
    /// since its guard (`travelTarget != nil && travelPath.isEmpty &&
    /// penPosition != nil`) would newly evaluate true. One resolution per
    /// stroke, exactly like the per-stroke phase-1/phase-3 timers.
    private var travelPhaseDecided = false

    /// Time of the last actually-dispatched point batch (travel or drawing),
    /// shared across both phases and never reset between strokes or buffer
    /// items — see the type-level doc comment.
    private var lastPointBatchDispatchTime: TimeInterval?

    public init(clock: any PerformerClock = SystemPerformerClock()) {
        self.clock = clock
    }

    /// Advances playback by one frame against `state.performance`. Call this
    /// from a display-link/timer callback, then apply the returned events via
    /// `StudioReducer.reduce` and store the result before the next call.
    public func tick(state: StudioState) -> PerformerTickResult {
        let now = clock.now()

        guard let stage = state.performance.onStage else {
            resetPerItemCursors()
            guard !state.performance.buffer.isEmpty else { return PerformerTickResult() }
            return PerformerTickResult(events: [.advanceStage])
        }

        switch stage {
        case .words:
            return tickWords(state: state, now: now)
        case .event:
            return tickEvent(state: state, now: now)
        case let .strokes(_, strokes):
            return tickStrokes(strokes: strokes, state: state, now: now)
        }
    }

    /// Cleared whenever the stage goes empty (about to advance to a new
    /// buffer item) — mirrors `usePerformer.ts`'s reset block in its
    /// `onStage === null` branch. `lastWordRevealTime`/
    /// `lastPointBatchDispatchTime` are deliberately NOT reset here; see the
    /// type-level doc comment.
    private func resetPerItemCursors() {
        stageEnteredAt = nil
        resetPerStrokeCursors()
    }

    private func resetPerStrokeCursors() {
        strokePointIndex = 0
        travelPath = []
        travelIndex = 0
        interStrokePauseEnteredAt = nil
        penSettleEnteredAt = nil
        travelPhaseDecided = false
    }

    // MARK: - 'words' item (spec §11.2)

    private func tickWords(state: StudioState, now: TimeInterval) -> PerformerTickResult {
        guard case let .words(_, text) = state.performance.onStage else { return PerformerTickResult() }
        let totalWords = text.split(whereSeparator: { $0.isWhitespace }).count
        if state.performance.wordIndex < totalWords {
            let elapsedMS = lastWordRevealTime.map { (now - $0) * 1000 } ?? .infinity
            if elapsedMS >= PerformerConstants.wordDelayMS {
                lastWordRevealTime = now
                return PerformerTickResult(events: [.revealWord])
            }
            return PerformerTickResult()
        }
        let holdStart = stageEnteredAt ?? now
        stageEnteredAt = holdStart
        if (now - holdStart) * 1000 >= PerformerConstants.holdAfterWordsMS {
            stageEnteredAt = nil
            return PerformerTickResult(events: [.stageComplete])
        }
        return PerformerTickResult()
    }

    // MARK: - 'event' item (spec §11.3)

    private func tickEvent(state: StudioState, now: TimeInterval) -> PerformerTickResult {
        let holdStart = stageEnteredAt ?? now
        stageEnteredAt = holdStart
        let heldMS = (now - holdStart) * 1000
        let canAdvance = heldMS >= PerformerConstants.holdEventMS && !state.performance.buffer.isEmpty
        let mustAdvance = heldMS >= PerformerConstants.maxEventHoldMS
        if canAdvance || mustAdvance {
            stageEnteredAt = nil
            return PerformerTickResult(events: [.stageComplete])
        }
        return PerformerTickResult()
    }

    // MARK: - 'strokes' item (spec §11.4 — the 5-phase per-stroke sequence)

    private func tickStrokes(strokes: [PendingStroke], state: StudioState, now: TimeInterval) -> PerformerTickResult {
        guard state.performance.strokeIndex < strokes.count else {
            return PerformerTickResult(events: [.stageComplete], completedBatchID: strokes.first?.batchId)
        }

        // Phase 1 — inter-stroke pause. Only ever "entered" (non-nil) for a
        // stroke that follows a completed one; the very first stroke of an
        // item skips it entirely (spec: "skipped for the very first stroke").
        if isPausingBetweenStrokes(now: now) {
            return PerformerTickResult()
        }

        // Phase 2 — pen travel: decide (once per stroke) whether travel is
        // needed, then advance it if so. An in-progress travel is the
        // terminal phase for this tick, whether or not it actually dispatched
        // a batch (the frame-delay gate may still be waiting) — matches
        // usePerformer.ts's `break` after the travel-animate block.
        let travelDecisionEvents = resolveTravelDecision(state: state, now: now)
        if let travelResult = advanceTravel(now: now, events: travelDecisionEvents) {
            return travelResult
        }

        // Phase 3 — pen settle.
        if isSettlingAfterTravel(now: now) {
            return PerformerTickResult(events: travelDecisionEvents)
        }

        // Phase 4 — drawing / Phase 5 — stroke complete.
        let stroke = strokes[state.performance.strokeIndex]
        return tickDrawPhase(
            stroke: stroke,
            strokeIndex: state.performance.strokeIndex,
            totalStrokes: strokes.count,
            now: now,
            events: travelDecisionEvents
        )
    }

    private func isPausingBetweenStrokes(now: TimeInterval) -> Bool {
        guard let pauseStart = interStrokePauseEnteredAt else { return false }
        if (now - pauseStart) * 1000 >= PerformerConstants.interStrokePauseMS {
            interStrokePauseEnteredAt = nil
            return false
        }
        return true
    }

    /// Decides, once per stroke, whether pen travel is needed: populates
    /// `travelPath` when a real move is required, or returns a
    /// `.penTravelComplete` event when the target is already close enough
    /// (spec §11.4 phase 2's `PEN_LIFT_THRESHOLD` check). No decision (and no
    /// event) is made at all when there's no travel target yet, e.g. an
    /// item's very first stroke.
    private func resolveTravelDecision(state: StudioState, now: TimeInterval) -> [StudioEvent] {
        guard !travelPhaseDecided,
              let target = state.performance.travelTarget,
              let start = state.performance.penPosition else { return [] }
        travelPhaseDecided = true
        guard Self.distance(start, target) > PerformerConstants.penLiftThreshold else {
            return [.penTravelComplete]
        }
        travelPath = Self.synthesizeTravelPath(from: start, to: target)
        travelIndex = 0
        return []
    }

    /// Advances an in-progress travel path by one frame-delay-gated batch.
    /// Returns a terminal `PerformerTickResult` for this tick when travel is
    /// (or was, until this call) in progress; `nil` to fall through to phase
    /// 3/4 in the same tick (no travel needed, or none remaining).
    private func advanceTravel(now: TimeInterval, events: [StudioEvent]) -> PerformerTickResult? {
        guard !travelPath.isEmpty, travelIndex < travelPath.count else { return nil }
        var events = events
        let elapsed = lastPointBatchDispatchTime.map { now - $0 } ?? .infinity
        if elapsed * 1000 >= PerformerConstants.frameDelayMS {
            let travelSpeed = PerformerConstants.targetPixelsPerSecond * PerformerConstants.travelSpeedMultiplier
            let batch = Self.batchPoints(travelPath, startIndex: &travelIndex, targetPixels: elapsed * travelSpeed)
            if !batch.isEmpty {
                events.append(.penTravelBatch(batch))
                lastPointBatchDispatchTime = now
            }
            if travelIndex >= travelPath.count {
                travelPath = []
                travelIndex = 0
                events.append(.penTravelComplete)
                penSettleEnteredAt = now
            }
        }
        return PerformerTickResult(events: events)
    }

    private func isSettlingAfterTravel(now: TimeInterval) -> Bool {
        guard let settleStart = penSettleEnteredAt else { return false }
        if (now - settleStart) * 1000 >= PerformerConstants.penSettleDelayMS {
            penSettleEnteredAt = nil
            return false
        }
        return true
    }

    /// Phase 4 (reveal the server-pre-interpolated `points`) and, once they're
    /// exhausted, phase 5 (`STROKE_COMPLETE`, arming the next stroke's phase 1).
    private func tickDrawPhase(
        stroke: PendingStroke,
        strokeIndex: Int,
        totalStrokes: Int,
        now: TimeInterval,
        events: [StudioEvent]
    ) -> PerformerTickResult {
        var events = events
        let points = stroke.points
        guard strokePointIndex < points.count else {
            events.append(.strokeComplete)
            resetPerStrokeCursors()
            if strokeIndex + 1 < totalStrokes {
                interStrokePauseEnteredAt = now
            }
            return PerformerTickResult(events: events)
        }

        let elapsed = lastPointBatchDispatchTime.map { now - $0 } ?? .infinity
        guard elapsed * 1000 >= PerformerConstants.frameDelayMS else {
            return PerformerTickResult(events: events)
        }
        let progress = Double(strokePointIndex) / Double(max(1, points.count - 1))
        let easing = Self.easingMultiplier(progress: progress)
        let budget = elapsed * PerformerConstants.targetPixelsPerSecond * easing
        let style = strokePointIndex == 0 ? Self.leadingStyle(for: stroke.path) : nil
        let batch = Self.batchPoints(points, startIndex: &strokePointIndex, targetPixels: budget)
        if !batch.isEmpty {
            events.append(.strokeProgressBatch(points: batch, style: style))
            lastPointBatchDispatchTime = now
        }
        return PerformerTickResult(events: events)
    }

    /// The first batch of a stroke carries a style override pulled off the
    /// path (spec §11.4), but only the fields the path actually set — an
    /// all-nil override is `nil`, not an empty-but-present one (mirrors the
    /// TS `Object.keys(style ?? {}).length > 0 ? style : undefined` guard).
    private static func leadingStyle(for path: Path) -> PartialStrokeStyle? {
        guard path.color != nil || path.strokeWidth != nil || path.opacity != nil else { return nil }
        return PartialStrokeStyle(color: path.color, strokeWidth: path.strokeWidth, opacity: path.opacity)
    }

    /// The exact stroke-drawing speed-easing formula (performer-render spec
    /// §11.1 `EASE_MIN_SPEED_RATIO`, §11.4): slow (0.75x) at both ends of a
    /// stroke, full speed (1.0x) at its midpoint.
    static func easingMultiplier(progress: Double) -> Double {
        PerformerConstants.easeMinSpeedRatio
            + (1 - PerformerConstants.easeMinSpeedRatio) * sin(progress * .pi)
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
}
