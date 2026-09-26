import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// Notebook entries: version tagging (work toward vN is everything after
/// v(N-1) arrived), tool-call pairing, critiques, nudges, the live thought.
@Suite("Notebook")
struct NotebookTests {
    /// Sequential ids/timestamps so pairing and durations are deterministic.
    private final class Clock: @unchecked Sendable {
        var time: Double = 0
        var counter = 0
    }

    private let clock = Clock()

    private var environment: RoutingEnvironment {
        let clock = clock
        return RoutingEnvironment(
            now: { clock.time },
            nextID: {
                clock.counter += 1
                return "m\(clock.counter)"
            }
        )
    }

    private func route(_ message: ServerMessage, _ state: StudioState, at time: Double) -> StudioState {
        clock.time = time
        return MessageRouter.route(message, environment: environment).reduce(state, StudioReducer.reduce)
    }

    private func tool(_ name: String, _ status: ToolExecutionStatus, stdout: String? = nil, returnCode: Int? = nil) -> ServerMessage {
        .codeExecution(CodeExecutionPayload(
            status: status, toolName: name, toolInput: nil, stdout: stdout, stderr: nil,
            returnCode: status == .completed ? (returnCode ?? 0) : nil, iteration: 1
        ))
    }

    private func version(_ number: Int, ops: Int? = nil) -> ServerMessage {
        .paintingVersion(
            PaintingVersionRef(pieceNumber: 1, version: number, assetBase: "/a/\(number)/", imageWidth: 10, imageHeight: 10),
            stages: ["ground"], ops: ops
        )
    }

    /// thought -> paint (v1 arrives mid-call) -> thought -> critique -> nudge
    /// -> paint (v2) -> live thought.
    private func paintSession() -> StudioState {
        var state = StudioState()
        state.pieceNumber = 1
        state = route(.thinkingDelta(text: "Blocking in the water first.", iteration: 1), state, at: 0)
        state = route(tool("paint", .started), state, at: 1000)
        state = route(version(1, ops: 142), state, at: 2000)
        state = route(tool("paint", .completed, stdout: "ok"), state, at: 2400)
        state = route(.thinkingDelta(text: "The pads need the dark to sit on.", iteration: 1), state, at: 3000)
        state = route(tool("critique_canvas", .started), state, at: 4000)
        state = route(tool("critique_canvas", .completed, stdout: "Reflections are too literal."), state, at: 5000)
        state = StudioReducer.reduce(state, .addMessage(AgentMessage(id: "n1", type: .userNudge, text: "More pink", timestamp: 5500)))
        state = route(tool("paint", .started), state, at: 6000)
        state = route(version(2, ops: 318), state, at: 7000)
        state = route(tool("paint", .completed), state, at: 8100)
        state = route(.thinkingDelta(text: "Now glazing", iteration: 1), state, at: 9000)
        return state
    }

    @Test("entries read thought -> tool -> thought in order, with the streaming thought last")
    func entryOrder() {
        let entries = Notebook.entries(paintSession())
        let kinds = entries.map { entry -> String in
            switch entry.kind {
            case .thought: "thought"
            case let .tool(call): "tool:\(call.toolName ?? "?")"
            case .critique: "critique"
            case .nudge: "nudge"
            case .error: "error"
            case .pieceComplete: "done"
            case .housekeeping: "housekeeping"
            }
        }
        #expect(kinds == ["thought", "tool:paint", "thought", "critique", "nudge", "tool:paint", "thought"])
        #expect(entries.last?.isLive == true)
        #expect(entries.last?.id == Notebook.liveThoughtID)
    }

    @Test("each entry is tagged with the version it works toward")
    func versionTagging() {
        let entries = Notebook.entries(paintSession())
        // v1 work: first thought + first paint. v2 work: everything after v1
        // arrived, through the second paint. The live thought works toward v3.
        #expect(entries.map(\.version) == [1, 1, 2, 2, 2, 2, 3])
    }

    @Test("a paint call reports the version it produced, its duration, and completion")
    func paintToolLine() throws {
        let entries = Notebook.entries(paintSession())
        guard case let .tool(first) = entries[1].kind, case let .tool(second) = entries[5].kind else {
            Issue.record("expected tool entries")
            return
        }
        #expect(first.producedVersion == 1)
        #expect(first.durationMs == 1400)
        #expect(first.inProgress == false)
        #expect(second.producedVersion == 2)
        #expect(second.durationMs == 2100)
    }

    @Test("an in-progress tool shows as in progress; a failed paint produces no version")
    func inProgressAndFailed() {
        var state = StudioState()
        state.pieceNumber = 1
        state = route(tool("paint", .started), state, at: 0)
        guard case let .tool(open) = Notebook.entries(state).last?.kind else {
            Issue.record("expected tool entry")
            return
        }
        #expect(open.inProgress)
        #expect(open.producedVersion == nil)

        state = route(tool("paint", .completed, returnCode: 1), state, at: 500)
        guard case let .tool(failed) = Notebook.entries(state).last?.kind else {
            Issue.record("expected tool entry")
            return
        }
        #expect(failed.failed)
        #expect(failed.producedVersion == nil)
    }

    @Test("a completed critique becomes a critique entry carrying its output")
    func critiqueEntry() {
        let entries = Notebook.entries(paintSession())
        #expect(entries[3].kind == .critique("Reflections are too literal."))
        #expect(entries[4].kind == .nudge("More pink"))
    }

    @Test("a tool call starting archives the thinking before it")
    func toolStartArchivesThinking() {
        var state = StudioState()
        state = route(.thinkingDelta(text: "Looking.", iteration: 1), state, at: 0)
        state = route(tool("view_canvas", .started), state, at: 10)
        #expect(state.thinking.isEmpty)
        #expect(state.messages.map(\.type) == [.thinking, .codeExecution])
    }
}

@Suite("Notebook unclosed tools")
struct NotebookUnclosedToolTests {
    @Test("a tool with no completed message stops reading as running once anything follows it")
    func unclosedToolSettles() {
        let started = AgentMessage(
            id: "b", type: .codeExecution, text: "Executing...", timestamp: 0, iteration: 1, status: .started,
            metadata: AgentMessageMetadata(toolName: "Bash"), version: 1
        )
        let open = Notebook.entries(messages: [started], liveThinking: "", versions: [], workingVersion: 1)
        #expect(Notebook.runningTool(open)?.toolName == "Bash")

        let later = Notebook.entries(messages: [started], liveThinking: "Now the sky", versions: [], workingVersion: 1)
        guard case let .tool(call) = later[0].kind else {
            Issue.record("expected tool entry")
            return
        }
        #expect(call.inProgress == false)
        #expect(Notebook.runningTool(later) == nil)
    }
}
