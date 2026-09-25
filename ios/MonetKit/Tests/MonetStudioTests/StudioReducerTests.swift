import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

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

    // MARK: - §5.4 LOAD_CANVAS / CLEAR_VIEWING / INIT

    @Test("loadCanvas snapshots savedCanvas only on first entry")
    func loadCanvasSnapshotsOnce() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 0, y: 0)])]
        let first = StudioReducer.reduce(state, .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 1, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil)))
        #expect(first.savedCanvas?.strokes == state.strokes)

        let second = StudioReducer.reduce(first, .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 2, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil)))
        // Still the piece-1-entry snapshot, not overwritten by the piece-2 navigation.
        #expect(second.savedCanvas?.strokes == state.strokes)
        // The main (non-viewing) pieceNumber is untouched by LOAD_CANVAS itself.
        #expect(second.pieceNumber == state.pieceNumber)
        #expect(second.viewingPiece == 2)
    }

    @Test("loadCanvas keeps current drawingStyle/styleConfig when both omitted")
    func loadCanvasKeepsCurrentStyleWhenOmitted() {
        var state = StudioState()
        state.drawingStyle = .paint
        state.styleConfig = .paint
        let payload = LoadCanvasPayload(
            strokes: [], pieceNumber: 4, canvasWidth: 800, canvasHeight: 600, drawingStyle: nil, styleConfig: nil
        )
        let next = StudioReducer.reduce(state, .loadCanvas(payload))
        #expect(next.drawingStyle == .paint)
        #expect(next.styleConfig == .paint)
    }

    @Test("loadCanvas derives styleConfig from a bare drawingStyle name")
    func loadCanvasDerivesConfigFromStyleName() {
        let state = StudioState() // starts .plotter
        let payload = LoadCanvasPayload(
            strokes: [], pieceNumber: 4, canvasWidth: 800, canvasHeight: 600, drawingStyle: .paint, styleConfig: nil
        )
        let next = StudioReducer.reduce(state, .loadCanvas(payload))
        #expect(next.drawingStyle == .paint)
        #expect(next.styleConfig == .paint)
    }

    @Test("loadCanvas honors an explicit styleConfig over the derived default")
    func loadCanvasHonorsExplicitStyleConfig() {
        let state = StudioState()
        var customPaint = DrawingStyleConfig.paint
        customPaint.name = "Custom Paint"
        let payload = LoadCanvasPayload(
            strokes: [], pieceNumber: 4, canvasWidth: 800, canvasHeight: 600, drawingStyle: .paint, styleConfig: customPaint
        )
        let next = StudioReducer.reduce(state, .loadCanvas(payload))
        #expect(next.styleConfig.name == "Custom Paint")
    }

    @Test("clearViewing restores savedCanvas")
    func clearViewingRestores() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 0, y: 0)])]
        state.pieceNumber = 5
        let payload = LoadCanvasPayload(
            strokes: [], pieceNumber: 9, canvasWidth: 800, canvasHeight: 600, drawingStyle: .plotter, styleConfig: nil
        )
        let viewing = StudioReducer.reduce(state, .loadCanvas(payload))
        let restored = StudioReducer.reduce(viewing, .clearViewing)
        #expect(restored.viewingPiece == nil)
        #expect(restored.strokes == state.strokes)
        #expect(restored.pieceNumber == 5)
        #expect(restored.savedCanvas == nil)
    }

    @Test("clearViewing is a no-op when already not viewing a gallery piece")
    func clearViewingNoOpWhenAlreadyLive() {
        var state = StudioState()
        state.strokes = [Path(type: .line, points: [Point(x: 1, y: 1)])]
        let next = StudioReducer.reduce(state, .clearViewing)
        #expect(next == state)
    }

    @Test("clearViewing with no savedCanvas just clears viewingPiece (defensive branch)")
    func clearViewingWithoutSavedCanvas() {
        var state = StudioState()
        state.viewingPiece = 3
        state.savedCanvas = nil
        state.strokes = [Path(type: .line, points: [Point(x: 2, y: 2)])]
        let next = StudioReducer.reduce(state, .clearViewing)
        #expect(next.viewingPiece == nil)
        // Everything else left as-is — no snapshot existed to restore from.
        #expect(next.strokes == state.strokes)
    }

    @Test("initialize always resets viewingPiece/savedCanvas even mid-gallery-view")
    func initializeResetsViewingState() {
        var state = StudioState()
        state.viewingPiece = 7
        state.savedCanvas = SavedCanvas(
            strokes: [], canvasWidth: 800, canvasHeight: 600, pieceNumber: 1, drawingStyle: .plotter, styleConfig: .plotter
        )
        state.messages = [AgentMessage(id: "1", type: .thinking, text: "t", timestamp: 0)]
        state.thinking = "in progress"
        state.currentStroke = [Point(x: 0, y: 0)]

        let payload = InitPayload(
            strokes: [], gallery: [], status: "idle", paused: false, pieceNumber: 3,
            canvasWidth: 800, canvasHeight: 600, monologue: "ignored",
            drawingStyle: .paint, styleConfig: .paint
        )
        let next = StudioReducer.reduce(state, .initialize(payload))
        #expect(next.viewingPiece == nil)
        #expect(next.savedCanvas == nil)
        #expect(next.messages.isEmpty)
        #expect(next.thinking.isEmpty)
        #expect(next.currentStroke.isEmpty)
        #expect(next.drawingStyle == .paint)
        #expect(next.styleConfig == .paint)
        #expect(next.paused == false)
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

    // MARK: - §5.5 Performance buffer/stage mechanics

    @Test("enqueueWords merges into the last buffer item under the 25-word cap")
    func enqueueWordsMergesUnderCap() {
        var state = StudioState()
        state = StudioReducer.reduce(state, .enqueueWords("one two three "))
        state = StudioReducer.reduce(state, .enqueueWords("four five "))
        #expect(state.performance.buffer.count == 1)
        guard case let .words(_, text) = state.performance.buffer[0] else {
            Issue.record("expected .words")
            return
        }
        #expect(text == "one two three four five ")
    }

    @Test("enqueueWords starts a new chunk once the last buffer item reaches 25 words")
    func enqueueWordsSplitsAtCap() {
        var state = StudioState()
        let twentyFiveWords = (1 ... 25).map { "w\($0)" }.joined(separator: " ") + " "
        state = StudioReducer.reduce(state, .enqueueWords(twentyFiveWords))
        #expect(state.performance.buffer.count == 1)
        state = StudioReducer.reduce(state, .enqueueWords("overflow"))
        #expect(state.performance.buffer.count == 2, "a 26th word must start a new chunk, not extend the full one")
    }

    @Test("enqueueWords never merges into onStage, only the buffer")
    func enqueueWordsNeverMergesIntoOnStage() {
        var state = StudioState()
        state.performance.onStage = .words(id: "staged", text: "already showing")
        state = StudioReducer.reduce(state, .enqueueWords("new text"))
        #expect(state.performance.buffer.count == 1)
        guard case let .words(_, staged) = state.performance.onStage else {
            Issue.record("expected onStage to remain .words")
            return
        }
        #expect(staged == "already showing", "onStage must not be mutated by ENQUEUE_WORDS")
    }

    @Test("advanceStage is a no-op unless onStage is nil and buffer is non-empty")
    func advanceStageNoOpGuards() {
        var state = StudioState()
        let unchanged = StudioReducer.reduce(state, .advanceStage)
        #expect(unchanged == state, "empty buffer: no-op")

        state.performance.onStage = .words(id: "x", text: "hi")
        state.performance.buffer = [.words(id: "y", text: "next")]
        let stillBusy = StudioReducer.reduce(state, .advanceStage)
        #expect(stillBusy == state, "onStage occupied: no-op even with buffer waiting")
    }

    @Test("advanceStage into a words item resets revealedText but not agentStroke")
    func advanceStageIntoWordsResetsRevealedText() {
        var state = StudioState()
        state.performance.revealedText = "stale"
        state.performance.agentStroke = [Point(x: 1, y: 1)]
        state.performance.buffer = [.words(id: "w1", text: "hello world")]
        let next = StudioReducer.reduce(state, .advanceStage)
        #expect(next.performance.revealedText.isEmpty)
        #expect(next.performance.agentStroke == [Point(x: 1, y: 1)], "agentStroke only resets for a .strokes stage item")
        #expect(next.performance.wordIndex == 0)
        #expect(next.performance.travelTarget == nil)
    }

    @Test("advanceStage into a strokes item resets agentStroke/style but not revealedText")
    func advanceStageIntoStrokesResetsAgentStroke() {
        var state = StudioState()
        state.performance.revealedText = "still visible while strokes animate"
        state.performance.agentStroke = [Point(x: 1, y: 1)]
        state.performance.agentStrokeStyle = PartialStrokeStyle(color: "#fff")
        let pending = PendingStroke(batchId: 1, path: Path(type: .line, points: []), points: [])
        state.performance.buffer = [.strokes(id: "s1", strokes: [pending])]
        let next = StudioReducer.reduce(state, .advanceStage)
        #expect(next.performance.agentStroke.isEmpty)
        #expect(next.performance.agentStrokeStyle == nil)
        #expect(next.performance.revealedText == "still visible while strokes animate", "text and stroke animation can be visually simultaneous")
    }

    @Test("revealWord splits on whitespace and advances wordIndex")
    func revealWordAdvances() {
        var state = StudioState()
        state.performance.onStage = .words(id: "w", text: "one two three")
        state = StudioReducer.reduce(state, .revealWord)
        #expect(state.performance.revealedText == "one")
        state = StudioReducer.reduce(state, .revealWord)
        #expect(state.performance.revealedText == "one two")
    }

    @Test("revealWord splits on any whitespace run, not just the space character")
    func revealWordSplitsOnNewlines() {
        // Real agent thinking_delta text contains embedded newlines (paragraph
        // breaks), e.g. "\n\nFirst", matching the TS reference's `/\s+/` split
        // (shared/src/canvas/reducer.ts). A literal-space-only split would
        // treat "one\n\ntwo" as a single word.
        var state = StudioState()
        state.performance.onStage = .words(id: "w", text: "one\n\ntwo\tthree")
        state = StudioReducer.reduce(state, .revealWord)
        #expect(state.performance.revealedText == "one")
        state = StudioReducer.reduce(state, .revealWord)
        #expect(state.performance.revealedText == "one two")
        state = StudioReducer.reduce(state, .revealWord)
        #expect(state.performance.revealedText == "one two three")
    }

    @Test("revealWord is a no-op when onStage isn't a words item")
    func revealWordNoOpForNonWords() {
        var state = StudioState()
        state.performance.onStage = nil
        let next = StudioReducer.reduce(state, .revealWord)
        #expect(next == state)
    }

    @Test("strokeProgressBatch captures style only from the first non-empty batch")
    func strokeProgressBatchCapturesStyleOnce() {
        var state = StudioState()
        let firstStyle = PartialStrokeStyle(color: "#111")
        state = StudioReducer.reduce(state, .strokeProgressBatch(points: [Point(x: 0, y: 0)], style: firstStyle))
        #expect(state.performance.agentStrokeStyle?.color == "#111")

        let secondStyle = PartialStrokeStyle(color: "#222")
        state = StudioReducer.reduce(state, .strokeProgressBatch(points: [Point(x: 1, y: 1)], style: secondStyle))
        #expect(state.performance.agentStrokeStyle?.color == "#111", "style is fixed from the first point/batch of a stroke")
        #expect(state.performance.agentStroke.count == 2)
    }

    @Test("strokeProgressBatch updates penPosition only when it moved >= 2px")
    func strokeProgressBatchJitterThreshold() {
        var state = StudioState()
        state = StudioReducer.reduce(state, .strokeProgressBatch(points: [Point(x: 0, y: 0)], style: nil))
        #expect(state.performance.penPosition == Point(x: 0, y: 0))

        let tinyMove = StudioReducer.reduce(state, .strokeProgressBatch(points: [Point(x: 1, y: 0)], style: nil))
        #expect(tinyMove.performance.penPosition == Point(x: 0, y: 0), "< 2px move must not update the indicator position")

        let bigMove = StudioReducer.reduce(state, .strokeProgressBatch(points: [Point(x: 3, y: 0)], style: nil))
        #expect(bigMove.performance.penPosition == Point(x: 3, y: 0), ">= 2px move updates the indicator position")
    }

    @Test("strokeProgressBatch is a no-op for an empty batch")
    func strokeProgressBatchEmptyNoOp() {
        let state = StudioState()
        let next = StudioReducer.reduce(state, .strokeProgressBatch(points: [], style: PartialStrokeStyle(color: "#fff")))
        #expect(next == state)
    }

    @Test("strokeComplete commits the stroke, advances the index, and sets travelTarget to the next stroke's first point")
    func strokeCompleteCommitsAndLooksAhead() {
        var state = StudioState()
        let pathA = Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 1, y: 1)])
        let pathB = Path(type: .line, points: [Point(x: 5, y: 5), Point(x: 6, y: 6)])
        let strokes = [
            PendingStroke(batchId: 1, path: pathA, points: pathA.points),
            PendingStroke(batchId: 1, path: pathB, points: pathB.points),
        ]
        state.performance.onStage = .strokes(id: "s1", strokes: strokes)
        state.performance.strokeIndex = 0
        state.performance.agentStroke = [Point(x: 0, y: 0)]
        state.performance.penDown = true

        let next = StudioReducer.reduce(state, .strokeComplete)
        #expect(next.strokes == [pathA])
        #expect(next.performance.strokeIndex == 1)
        #expect(next.performance.agentStroke.isEmpty)
        #expect(next.performance.penDown == false)
        #expect(next.performance.travelTarget == Point(x: 5, y: 5), "look-ahead to the next stroke's first point")

        let last = StudioReducer.reduce(next, .strokeComplete)
        #expect(last.strokes == [pathA, pathB])
        #expect(last.performance.travelTarget == nil, "no more strokes left to travel to")
    }

    @Test("strokeComplete is a no-op when onStage isn't strokes or strokeIndex is out of range")
    func strokeCompleteNoOpGuards() {
        let notStrokes = StudioState()
        #expect(StudioReducer.reduce(notStrokes, .strokeComplete) == notStrokes)

        var outOfRange = StudioState()
        let path = Path(type: .line, points: [])
        outOfRange.performance.onStage = .strokes(id: "s", strokes: [PendingStroke(batchId: 1, path: path, points: [])])
        outOfRange.performance.strokeIndex = 5
        #expect(StudioReducer.reduce(outOfRange, .strokeComplete) == outOfRange)
    }

    @Test("penTravelBatch sets penPosition to the last point and lifts the pen")
    func penTravelBatchUpdatesPosition() {
        var state = StudioState()
        state.performance.penDown = true
        let next = StudioReducer.reduce(state, .penTravelBatch([Point(x: 1, y: 1), Point(x: 2, y: 2)]))
        #expect(next.performance.penPosition == Point(x: 2, y: 2))
        #expect(next.performance.penDown == false)
    }

    @Test("stageComplete archives onStage into bounded history and resets stage fields")
    func stageCompleteArchivesAndResets() {
        var state = StudioState()
        state.performance.onStage = .words(id: "w", text: "hi")
        state.performance.penPosition = Point(x: 1, y: 1)
        state.performance.penDown = true
        state.performance.agentStroke = [Point(x: 1, y: 1)]
        state.performance.agentStrokeStyle = PartialStrokeStyle(color: "#000")
        state.performance.travelTarget = Point(x: 9, y: 9)

        let next = StudioReducer.reduce(state, .stageComplete)
        #expect(next.performance.onStage == nil)
        #expect(next.performance.history.count == 1)
        #expect(next.performance.penPosition == nil)
        #expect(next.performance.penDown == false)
        #expect(next.performance.agentStroke.isEmpty)
        #expect(next.performance.agentStrokeStyle == nil)
        #expect(next.performance.travelTarget == nil)
    }

    @Test("stageComplete history is bounded to maxHistory, dropping oldest")
    func stageCompleteHistoryBounded() {
        var state = StudioState()
        for i in 0 ..< (PerformanceState.maxHistory + 5) {
            state.performance.onStage = .words(id: "w\(i)", text: "t")
            state = StudioReducer.reduce(state, .stageComplete)
        }
        #expect(state.performance.history.count == PerformanceState.maxHistory)
        #expect(state.performance.history.first?.id == "w5")
    }

    @Test("clearPerformance fully resets performance state")
    func clearPerformanceResets() {
        var state = StudioState()
        state.performance.buffer = [.words(id: "w", text: "t")]
        state.performance.onStage = .words(id: "s", text: "t")
        state.performance.history = [.words(id: "h", text: "t")]
        let next = StudioReducer.reduce(state, .clearPerformance)
        #expect(next.performance == PerformanceState())
    }

    // MARK: - Full fixture replay (protocol-state spec §10, §10.1)

    @Test("replays every fixture end to end: decodes cleanly, routes, reduces, matches §10.1 assertions", arguments: [
        "agent_turn_plotter.json", "agent_turn_paint.json", "text_chunking_flow.json",
    ])
    func replaysFixture(named name: String) throws {
        let messages = try Self.loadFixtureMessages(named: name)
        #expect(!messages.isEmpty)

        let result = try Self.replay(messages, fixtureName: name)

        #expect(result.finalState.messages.count <= StudioState.maxMessages)
        if let number = result.lastPieceStateNumber {
            #expect(result.finalState.pieceNumber == number)
        }

        let finalStatus = StudioSelectors.agentStatus(result.finalState)
        #expect(
            [.idle, .drawing, .thinking, .executing].contains(finalStatus),
            "\(name): recordings of successful in-progress-or-completed turns starting from paused:false never end paused/error"
        )
        #expect(result.sawThinkingOrExecuting, "\(name): the turn did something observable")

        #expect(result.finalState.thinking.count <= result.thinkingDeltaTotalLength || result.thinkingDeltaTotalLength == 0,
                "\(name): thinking can only be reset-then-reaccumulated, never exceed the total streamed")

        let agentMessageCodeExecutionCount = result.finalState.messages.count(where: { $0.type == .codeExecution })
        #expect(agentMessageCodeExecutionCount == result.codeExecutionMessageCount,
                "\(name): every code_execution wire message produces exactly one AgentMessage")

        if let count = result.lastGalleryUpdateCount {
            #expect(result.finalState.gallery.count == count, "\(name): last-write-wins, not cumulative")
        }

        if let stateAtFirstStarted = result.stateAtFirstStarted {
            #expect(StudioSelectors.hasInProgressEvents(stateAtFirstStarted),
                    "\(name): replaying up to a code_execution{started} makes hasInProgressEvents true")
        }
        if let stateAtMatchingCompleted = result.stateAtMatchingCompleted {
            #expect(StudioSelectors.agentStatus(stateAtMatchingCompleted) != .executing,
                    "\(name): replaying up to its matching code_execution{completed} clears .executing")
        }
    }

    /// Accumulated observations from one full `replay` pass, consumed by the
    /// §10.1-style assertions in `replaysFixture` above. Splitting the replay
    /// loop from its assertions keeps each function small and single-purpose.
    private struct ReplayResult {
        var finalState: StudioState
        var sawThinkingOrExecuting = false
        var thinkingDeltaTotalLength = 0
        var codeExecutionMessageCount = 0
        var lastPieceStateNumber: Int?
        var lastGalleryUpdateCount: Int?
        var stateAtFirstStarted: StudioState?
        var stateAtMatchingCompleted: StudioState?
    }

    /// Decodes and routes every message in `messages` through
    /// `MessageRouter.route` + `StudioReducer.reduce`, recording the
    /// observations `replaysFixture`'s assertions need along the way.
    private static func replay(_ messages: [[String: Any]], fixtureName name: String) throws -> ReplayResult {
        var state = StudioState()
        // Fixtures are recordings of an already-in-progress agent turn on an
        // unpaused canvas (they start mid-session, not from a fresh `init`)
        // — none of the three include a `paused` message, so seed the
        // precondition explicitly rather than replaying from
        // `StudioState()`'s "assume paused until told otherwise" default
        // (protocol-state spec §4, §10.1).
        state.paused = false
        let counter = Counter()
        let environment = RoutingEnvironment(now: { Double(counter.next()) }, nextID: { "id_\(counter.next())" })
        var result = ReplayResult(finalState: state)
        var pendingStartedIteration: (tool: String, iteration: Int)?

        for wrapped in messages {
            let type = try #require(wrapped["type"] as? String)
            let payload = try #require(wrapped["data"])
            let payloadData = try JSONSerialization.data(withJSONObject: payload)
            let message = try JSONDecoder().decode(ServerMessage.self, from: payloadData)

            if case .unknown = message {
                Issue.record("\(name): message type '\(type)' decoded to .unknown")
            }

            if case .agentStrokesReady = message {
                // §6.1: agent_strokes_ready routes to zero dispatched actions.
                let events = MessageRouter.route(message, environment: environment)
                #expect(events.isEmpty, "\(name): agent_strokes_ready must dispatch zero StudioEvents")
                continue
            }

            if case let .thinkingDelta(text, _) = message {
                result.thinkingDeltaTotalLength += text.count
            }

            for event in MessageRouter.route(message, environment: environment) {
                state = StudioReducer.reduce(state, event)
            }

            let status = StudioSelectors.agentStatus(state)
            if status == .thinking || status == .executing { result.sawThinkingOrExecuting = true }

            if case let .codeExecution(codePayload) = message {
                result.codeExecutionMessageCount += 1
                if codePayload.status == .started, pendingStartedIteration == nil, let tool = codePayload.toolName {
                    pendingStartedIteration = (tool, codePayload.iteration)
                    result.stateAtFirstStarted = state
                }
                if codePayload.status == .completed, let pending = pendingStartedIteration,
                   codePayload.toolName == pending.tool, codePayload.iteration == pending.iteration {
                    result.stateAtMatchingCompleted = state
                }
            }
            if case let .pieceState(number, _) = message {
                result.lastPieceStateNumber = number
            }
            if case let .galleryUpdate(canvases) = message {
                result.lastGalleryUpdateCount = canvases.count
            }
        }

        result.finalState = state
        return result
    }

    private static func loadFixtureMessages(named name: String) throws -> [[String: Any]] {
        let url = Self.fixturesDirectory.appendingPathComponent(name)
        let data = try Data(contentsOf: url)
        let root = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return try #require(root["messages"] as? [[String: Any]])
    }

    /// Synthetic (non-fixture) check that an `error` message produces
    /// derived status `.error` and exactly one `.error` `AgentMessage`
    /// (protocol-state spec §10.1's final, non-fixture-driven assertion).
    @Test("a synthetic error message produces derived status .error")
    func errorMessageProducesErrorStatus() {
        var state = StudioState()
        state.paused = false
        let environment = RoutingEnvironment(now: { 0 }, nextID: { "err_1" })
        let message = ServerMessage.error(message: "boom", details: "trace")
        for event in MessageRouter.route(message, environment: environment) {
            state = StudioReducer.reduce(state, event)
        }
        #expect(StudioSelectors.agentStatus(state) == .error)
        #expect(state.messages.filter { $0.type == .error }.count == 1)
        #expect(state.messages.first { $0.type == .error }?.text == "boom")
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
