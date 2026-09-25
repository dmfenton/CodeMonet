import Foundation
import Testing
@testable import MonetProtocol
@testable import MonetStudio

@Suite("StudioReducer")
struct StudioReducerTests {
    @Test("addStroke appends")
    func addStroke() {
        let path = Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 1, y: 1)])
        let state = StudioReducer.reduce(StudioState(), .addStroke(path))
        #expect(state.strokes == [path])
    }

    @Test("clear resets strokes/messages/performance but not size or gallery")
    func clearPreservesUnrelatedState() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 0, y: 0)])]
        state.canvasWidth = 1200
        state.gallery = [GalleryEntry(id: "a", createdAt: "", pieceNumber: 1, strokeCount: 1, width: 800, height: 600, drawingStyle: .plotter, title: nil, thumbnailToken: nil)]
        let next = StudioReducer.reduce(state, .clear)
        #expect(next.strokes.isEmpty)
        #expect(next.canvasWidth == 1200)
        #expect(next.gallery.count == 1)
    }

    @Test("loadCanvas snapshots savedCanvas only on first entry")
    func loadCanvasSnapshotsOnce() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 0, y: 0)])]
        let first = StudioReducer.reduce(state, .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 1, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil)))
        #expect(first.savedCanvas?.strokes == state.strokes)

        let second = StudioReducer.reduce(first, .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 2, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil)))
        // Still the piece-1-entry snapshot, not overwritten by the piece-2 navigation.
        #expect(second.savedCanvas?.strokes == state.strokes)
    }

    @Test("clearViewing restores savedCanvas")
    func clearViewingRestores() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 0, y: 0)])]
        state.pieceNumber = 5
        let viewing = StudioReducer.reduce(state, .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 9, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil)))
        let restored = StudioReducer.reduce(viewing, .clearViewing)
        #expect(restored.viewingPiece == nil)
        #expect(restored.strokes == state.strokes)
        #expect(restored.pieceNumber == 5)
    }

    @Test("messages array is bounded to maxMessages")
    func boundedMessages() {
        var state = StudioState()
        for i in 0 ..< (StudioState.maxMessages + 10) {
            let message = AgentMessage(id: "\(i)", type: .thinking, text: "t", timestamp: Double(i))
            state = StudioReducer.reduce(state, .addMessage(message))
        }
        #expect(state.messages.count == StudioState.maxMessages)
        #expect(state.messages.first?.id == "10")
    }

    @Test("replays the plotter fixture end to end without crashing")
    func replaysPlotterFixture() throws {
        let url = Self.fixturesDirectory.appendingPathComponent("agent_turn_plotter.json")
        let data = try Data(contentsOf: url)
        let root = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let messages = try #require(root["messages"] as? [[String: Any]])

        var state = StudioState()
        let counter = Counter()
        let environment = RoutingEnvironment(now: { Double(counter.next()) }, nextID: { "id_\(counter.next())" })

        for wrapped in messages {
            let payload = try #require(wrapped["data"])
            let payloadData = try JSONSerialization.data(withJSONObject: payload)
            let message = try JSONDecoder().decode(ServerMessage.self, from: payloadData)
            for event in MessageRouter.route(message, environment: environment) {
                state = StudioReducer.reduce(state, event)
            }
        }

        #expect(state.messages.count <= StudioState.maxMessages)
    }

    private final class Counter: @unchecked Sendable {
        private var value = 0
        func next() -> Int {
            value += 1
            return value
        }
    }

    private static var fixturesDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("server/tests/fixtures")
    }
}
