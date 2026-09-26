import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

@Suite("Reconnect and notebook bounds")
struct ReconnectNotebookTests {
    private final class Clock: @unchecked Sendable {
        var time: Double = 0
        var counter = 0
    }

    private let clock = Clock()

    private var environment: RoutingEnvironment {
        let clock = clock
        return RoutingEnvironment(now: { clock.time }, nextID: {
            clock.counter += 1
            return "m\(clock.counter)"
        })
    }

    private func route(_ message: ServerMessage, _ state: StudioState) -> StudioState {
        clock.time += 100
        return MessageRouter.route(message, environment: environment).reduce(state, StudioReducer.reduce)
    }

    private func tool(_ name: String, _ status: ToolExecutionStatus, iteration: Int = 1) -> ServerMessage {
        .codeExecution(CodeExecutionPayload(
            status: status, toolName: name, toolInput: nil, stdout: status == .completed ? "ok" : nil, stderr: nil,
            returnCode: status == .completed ? 0 : nil, iteration: iteration
        ))
    }

    private func summary(_ version: Int, ops: Int? = nil) -> PaintingVersionSummary {
        PaintingVersionSummary(version: version, assetBase: "/a/\(version)/", imageWidth: 10, imageHeight: 10, ops: ops)
    }

    private func initPayload(
        piece: Int,
        versions: [PaintingVersionSummary] = [],
        title: String? = nil,
        prompt: String? = nil,
        monologue: String = ""
    ) -> InitPayload {
        InitPayload(
            strokes: [], gallery: [], status: "idle", paused: false, pieceNumber: piece,
            canvasWidth: 800, canvasHeight: 600, monologue: monologue, drawingStyle: .paint, styleConfig: .paint,
            painting: versions.last?.ref(pieceNumber: piece), title: title, paintingVersions: versions, prompt: prompt
        )
    }

    /// A session on piece 3 with a prompt, a title, two versions, and some notebook.
    private func session() -> StudioState {
        var state = StudioReducer.reduce(StudioState(), .initialize(initPayload(
            piece: 3, versions: [summary(1), summary(2)], title: "Dusk", prompt: "a pond at dusk"
        )))
        state = route(.thinkingDelta(text: "Loosening the water.", iteration: 1), state)
        state = route(tool("paint", .started), state)
        state = route(.paintingVersion(summary(3, ops: 30).ref(pieceNumber: 3), stages: ["water"], ops: 30), state)
        state = route(tool("paint", .completed), state)
        return state
    }

    @Test("reconnecting to the same piece keeps the notebook, merges versions, keeps omitted title and prompt")
    func samePieceReconnect() {
        let before = session()
        // The server lost v3 (e.g. it predates history) and omits title/prompt.
        let after = StudioReducer.reduce(before, .initialize(initPayload(piece: 3, versions: [summary(1), summary(2, ops: 22)])))
        #expect(after.notebook == before.notebook)
        #expect(after.versions.map(\.version) == [1, 2, 3])
        #expect(after.versions[1].ops == 22)
        #expect(after.title == "Dusk")
        #expect(after.prompt == "a pond at dusk")
        #expect(after.messages.isEmpty)
        #expect(!Notebook.entries(after).isEmpty)
    }

    @Test("a different piece resets and seeds the notebook from prompt and monologue")
    func differentPieceResets() {
        let after = StudioReducer.reduce(session(), .initialize(initPayload(
            piece: 4, prompt: "a harbor in fog", monologue: "Starting with the fog bank."
        )))
        #expect(after.versions.isEmpty)
        #expect(after.title == nil)
        let entries = Notebook.entries(after)
        #expect(entries.map(\.kind) == [.nudge("a harbor in fog"), .thought("Starting with the fog bank.")])
    }

    @Test("an empty notebook on the same piece is seeded from the monologue")
    func monologueSeedsEmptyNotebook() {
        var state = StudioState()
        state.pieceNumber = 5
        let after = StudioReducer.reduce(state, .initialize(initPayload(piece: 5, monologue: "Blocking in the sky.")))
        #expect(Notebook.entries(after).map(\.kind) == [.thought("Blocking in the sky.")])
    }

    @Test("the prompt survives a long turn: the notebook keeps 200 entries, a tool pair counting once")
    func promptSurvivesLongTurn() {
        var state = session()
        for index in 0 ..< 90 {
            state = route(.thinkingDelta(text: "step \(index)", iteration: 1), state)
            state = route(tool("Bash", .started), state)
            state = route(tool("Bash", .completed), state)
        }
        // 90 thoughts + 90 tool lines + the session's 4 entries > 50 messages,
        // yet < 200 notebook entries.
        #expect(state.messages.count == StudioState.maxMessages)
        #expect(Notebook.entries(state).first?.kind == .nudge("a pond at dusk"))

        for index in 0 ..< 40 {
            state = route(.thinkingDelta(text: "more \(index)", iteration: 1), state)
            state = route(tool("Read", .started), state)
            state = route(tool("Read", .completed), state)
        }
        let entries = Notebook.entries(state)
        #expect(entries.count <= StudioState.maxNotebookEntries + 1)
        #expect(entries.count >= StudioState.maxNotebookEntries - 1)
        // Trimming never leaves an orphaned completion at the front.
        #expect(!(state.notebook.first?.type == .codeExecution && state.notebook.first?.status == .completed))
    }

    @Test("parallel calls of one tool: a completion closes the oldest running call")
    func parallelCallsCloseOldest() {
        var state = StudioState()
        state = route(tool("view_canvas", .started), state)
        state = route(tool("view_canvas", .started), state)
        state = route(tool("view_canvas", .completed), state)
        let calls = Notebook.entries(state).compactMap { entry -> NotebookToolCall? in
            if case let .tool(call) = entry.kind { return call }
            return nil
        }
        #expect(calls.count == 2)
        #expect(calls[0].inProgress == false)
        #expect(calls[0].durationMs != nil)
        #expect(calls[1].inProgress == true)

        // A completion from another iteration doesn't close this one.
        state = route(tool("view_canvas", .completed, iteration: 2), state)
        let lastCall = Notebook.entries(state).compactMap { entry -> NotebookToolCall? in
            if case let .tool(call) = entry.kind { return call }
            return nil
        }
        // It becomes its own line; the running call isn't paired with it
        // (it only stops reading as running because something followed it).
        #expect(lastCall.count == 3)
        #expect(lastCall[1].durationMs == nil)
    }
}
