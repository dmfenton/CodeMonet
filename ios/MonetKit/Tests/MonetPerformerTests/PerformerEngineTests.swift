import Foundation
@testable import MonetPerformer
@testable import MonetProtocol
@testable import MonetStudio
import Testing

@Suite("PerformerEngine")
struct PerformerEngineTests {
    // MARK: - Stage advance / idle

    @Test("advances an empty stage to the next buffered item")
    func advancesStage() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        var state = StudioState()
        state.performance.buffer = [.words(id: "w1", text: "hello world")]
        let result = engine.tick(state: state)
        #expect(result.events == [.advanceStage])
    }

    @Test("does nothing when both stage and buffer are empty")
    func idleWhenEmpty() {
        let engine = PerformerEngine(clock: ManualPerformerClock())
        let result = engine.tick(state: StudioState())
        #expect(result.events.isEmpty)
        #expect(result.completedBatchID == nil)
    }

    // MARK: - §11.5 travel path synthesis, §11.6 batching

    @Test("synthesizeTravelPath starts and ends at the given points")
    func travelPathEndpoints() {
        let start = Point(x: 0, y: 0)
        let end = Point(x: 100, y: 0)
        let path = PerformerEngine.synthesizeTravelPath(from: start, to: end)
        #expect(path.first == start)
        #expect(path.last == end)
        #expect(path.count >= 2)
    }

    @Test("batchPoints respects the max-points-per-frame bound (§11.1/§11.6: 240)")
    func batchPointsRespectsMax() {
        let points = (0 ..< 1000).map { Point(x: Double($0), y: 0) }
        var index = 0
        let batch = PerformerEngine.batchPoints(points, startIndex: &index, targetPixels: 1_000_000)
        #expect(batch.count == PerformerConstants.maxPointsPerFrame)
        #expect(batch.count <= PerformerConstants.maxPointsPerFrame)
        #expect(index == batch.count)
    }

    @Test("batchPoints never emits fewer than the min-points-per-frame bound (§11.1/§11.6: 24) when points remain")
    func batchPointsRespectsMin() {
        // Every point is 1px from the last, so a zero pixel budget would stop
        // immediately after the first point if the min-count floor weren't enforced.
        let points = (0 ..< 100).map { Point(x: Double($0), y: 0) }
        var index = 0
        let batch = PerformerEngine.batchPoints(points, startIndex: &index, targetPixels: 0)
        #expect(batch.count == PerformerConstants.minPointsPerFrame)
        #expect(index == PerformerConstants.minPointsPerFrame)
    }

    @Test("batchPoints stops exactly at the array bound when it's smaller than the min floor")
    func batchPointsStopsAtArrayBound() {
        let points = (0 ..< 5).map { Point(x: Double($0), y: 0) }
        var index = 0
        let batch = PerformerEngine.batchPoints(points, startIndex: &index, targetPixels: 0)
        #expect(batch.count == 5)
        #expect(index == 5)
    }

    // MARK: - §11.1/§11.4 exact easing formula

    @Test(
        "easing formula is exactly 0.75 + 0.25*sin(progress*pi) (§11.1 EASE_MIN_SPEED_RATIO, §11.4)",
        arguments: [
            (progress: 0.0, expected: 0.75),
            (progress: 0.5, expected: 1.0),
            (progress: 1.0, expected: 0.75),
            (progress: 0.25, expected: 0.75 + 0.25 * (2.0.squareRoot() / 2.0)),
        ]
    )
    func easingFormulaExact(progress: Double, expected: Double) {
        let actual = PerformerEngine.easingMultiplier(progress: progress)
        #expect(abs(actual - expected) < 1e-9)
        // Restated directly against the spec's own constants, not just the helper's algebra.
        let restated = PerformerConstants.easeMinSpeedRatio
            + (1 - PerformerConstants.easeMinSpeedRatio) * sin(progress * Double.pi)
        #expect(abs(actual - restated) < 1e-12)
    }

    @Test("travel speed is exactly TARGET_PIXELS_PER_SECOND * TRAVEL_SPEED_MULTIPLIER = 54000 (§11.1)")
    func travelSpeedConstant() {
        let travelSpeed = PerformerConstants.targetPixelsPerSecond * PerformerConstants.travelSpeedMultiplier
        #expect(travelSpeed == 54000)
    }

    // MARK: - §11.4 the 5-phase per-stroke sequence, timed with ManualPerformerClock

    @Test("first stroke of an item skips inter-stroke-pause and (with no travel target) draws with no penTravelComplete noise")
    func firstStrokeSkipsPauseAndTravel() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 10, y: 0)]),
            points: [Point(x: 0, y: 0), Point(x: 10, y: 0)]
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])
        state.performance.strokeIndex = 0
        state.performance.travelTarget = nil
        state.performance.penPosition = nil

        let result = engine.tick(state: state)
        #expect(result.events == [
            .strokeProgressBatch(
                points: [Point(x: 0, y: 0), Point(x: 10, y: 0)],
                style: nil
            ),
        ])
    }

    @Test("pen travel within PEN_LIFT_THRESHOLD is skipped and falls through to drawing in the same tick")
    func closeTravelSkipsInSameTick() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 1, y: 0), Point(x: 20, y: 0)]),
            points: [Point(x: 1, y: 0), Point(x: 20, y: 0)]
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])
        state.performance.strokeIndex = 0
        state.performance.travelTarget = Point(x: 1, y: 0)
        state.performance.penPosition = Point(x: 0, y: 0) // 1px away: within the 2px threshold

        let result = engine.tick(state: state)
        #expect(result.events == [
            .penTravelComplete,
            .strokeProgressBatch(points: stroke.points, style: nil),
        ])
    }

    @Test("real pen travel dispatches batches gated by frameDelayMs and ends exactly at the target")
    func realTravelReachesTargetExactly() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 500, y: 500), Point(x: 520, y: 500)]),
            points: [Point(x: 500, y: 500), Point(x: 520, y: 500)]
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])
        state.performance.strokeIndex = 0
        let target = Point(x: 500, y: 500)
        state.performance.travelTarget = target
        state.performance.penPosition = Point(x: 0, y: 0) // far away: real travel required

        var sawTravelBatch = false
        var travelCompleted = false
        var lastPenPosition: Point?
        for _ in 0 ..< 500 where !travelCompleted {
            let result = engine.tick(state: state)
            for event in result.events {
                state = StudioReducer.reduce(state, event)
                switch event {
                case .penTravelBatch:
                    sawTravelBatch = true
                    lastPenPosition = state.performance.penPosition
                case .penTravelComplete:
                    travelCompleted = true
                default:
                    break
                }
            }
            clock.advance(by: PerformerConstants.frameDelayMS / 1000)
        }

        #expect(sawTravelBatch)
        #expect(travelCompleted)
        #expect(lastPenPosition == target)
    }

    @Test("frame-delay gate blocks a second dispatch before a full frame has elapsed")
    func frameDelayGateBlocksRapidTicks() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: []),
            points: (0 ..< 500).map { Point(x: Double($0), y: 0) }
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])
        state.performance.strokeIndex = 0

        let first = engine.tick(state: state)
        #expect(!first.events.isEmpty) // first dispatch is never gated (no prior dispatch time)
        for event in first.events { state = StudioReducer.reduce(state, event) }

        // Advance by far less than one frame: the gate must block a second dispatch.
        clock.advance(by: (PerformerConstants.frameDelayMS / 1000) * 0.1)
        let blocked = engine.tick(state: state)
        #expect(blocked.events.isEmpty)

        // Advance the remainder of a full frame: now it must dispatch again.
        clock.advance(by: (PerformerConstants.frameDelayMS / 1000) * 0.95)
        let unblocked = engine.tick(state: state)
        #expect(!unblocked.events.isEmpty)
    }

    @Test("full multi-stroke run: inter-stroke pause, travel, settle, draw, stage complete with the batch id")
    func fullMultiStrokeRun() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let strokeA = PendingStroke(
            batchId: 42,
            path: Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 10, y: 0)], color: "#123456"),
            points: [Point(x: 0, y: 0), Point(x: 10, y: 0)]
        )
        let strokeB = PendingStroke(
            batchId: 42,
            path: Path(type: .line, points: [Point(x: 300, y: 300), Point(x: 310, y: 300)]),
            points: [Point(x: 300, y: 300), Point(x: 310, y: 300)]
        )
        var state = StudioState()
        state.performance.buffer = [.strokes(id: "strokes_42", strokes: [strokeA, strokeB])]

        var strokeCompleteCount = 0
        var travelBatchSeen = false
        var completedBatchID: Int?
        for _ in 0 ..< 2000 where completedBatchID == nil {
            let result = engine.tick(state: state)
            for event in result.events {
                state = StudioReducer.reduce(state, event)
                if event == .strokeComplete { strokeCompleteCount += 1 }
                if case .penTravelBatch = event { travelBatchSeen = true }
            }
            completedBatchID = result.completedBatchID
            clock.advance(by: PerformerConstants.frameDelayMS / 1000)
        }

        #expect(strokeCompleteCount == 2)
        #expect(travelBatchSeen) // strokeA ends far from strokeB's start
        #expect(completedBatchID == 42)
        #expect(state.strokes.map(\.points) == [strokeA.path.points, strokeB.path.points])
        #expect(state.performance.agentStroke.isEmpty)
        #expect(state.performance.penDown == false)
        #expect(state.performance.onStage == nil)
    }
}
