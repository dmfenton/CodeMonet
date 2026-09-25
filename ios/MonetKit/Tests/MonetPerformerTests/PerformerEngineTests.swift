import Testing
@testable import MonetProtocol
@testable import MonetPerformer
@testable import MonetStudio

@Suite("PerformerEngine")
struct PerformerEngineTests {
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

    @Test("synthesizeTravelPath starts and ends at the given points")
    func travelPathEndpoints() {
        let start = Point(x: 0, y: 0)
        let end = Point(x: 100, y: 0)
        let path = PerformerEngine.synthesizeTravelPath(from: start, to: end)
        #expect(path.first == start)
        #expect(path.last == end)
        #expect(path.count >= 2)
    }

    @Test("batchPoints respects the max-points-per-frame bound")
    func batchPointsRespectsMax() {
        let points = (0 ..< 1000).map { Point(x: Double($0), y: 0) }
        var index = 0
        let batch = PerformerEngine.batchPoints(points, startIndex: &index, targetPixels: 1_000_000)
        #expect(batch.count <= PerformerConstants.maxPointsPerFrame)
        #expect(index == batch.count)
    }
}
