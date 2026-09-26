@testable import CodeMonet
import Foundation
import MonetProtocol
import MonetStudio
import Testing

/// Coverage for `StudioPresentation`'s pure rules: the status pill, the
/// Home easel status line, and the notebook's tool lines.
@Suite("StudioPresentation")
struct StudioPresentationTests {
    // MARK: - Status pill

    @Test("paused, viewing, and idle pills are inactive")
    func inactivePills() {
        var state = StudioState()
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "paused", isActive: false))
        state.paused = false
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "idle", isActive: false))
        state.viewingPiece = 3
        #expect(StudioPresentation.statusPill(for: state).label == "viewing")
    }

    @Test("an open tool call names the activity: critique, painting, looking")
    func executingPills() {
        var state = StudioState()
        state.paused = false
        state.messages = [makeMessage(type: .codeExecution, toolName: "critique_canvas", status: .started)]
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "critique", isActive: true))
        state.messages = [makeMessage(type: .codeExecution, toolName: "paint", status: .started)]
        #expect(StudioPresentation.statusPill(for: state).label == "painting")
        state.messages = [makeMessage(type: .codeExecution, toolName: "view_canvas", status: .started)]
        #expect(StudioPresentation.statusPill(for: state).label == "looking")
    }

    @Test("a revealing painting reads as painting; plotter strokes as drawing")
    func drawingPills() {
        var state = StudioState()
        state.paused = false
        state.drawingStyle = .paint
        state.painting = PaintingState(
            base: nil,
            playing: PaintingVersionRef(pieceNumber: 1, version: 1, assetBase: "/a/", imageWidth: 1, imageHeight: 1)
        )
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "painting", isActive: true))
        state.drawingStyle = .plotter
        #expect(StudioPresentation.statusPill(for: state).label == "drawing")
    }

    @Test("currentTool is the most recent code_execution's tool")
    func currentTool() {
        let messages = [
            makeMessage(type: .codeExecution, toolName: "view_canvas"),
            makeMessage(type: .thinking),
            makeMessage(type: .codeExecution, toolName: "paint"),
        ]
        #expect(StudioPresentation.currentTool(messages: messages) == "paint")
        #expect(StudioPresentation.currentTool(messages: [makeMessage(type: .thinking)]) == nil)
    }

    // MARK: - Tool lines

    @Test("a finished paint line reads 'paint v4 · 318 strokes · 2.1s'")
    func paintLine() {
        let call = NotebookToolCall(toolName: "paint", inProgress: false, durationMs: 2100, producedVersion: 4)
        #expect(StudioPresentation.toolLine(call, strokes: 318) == "paint v4 · 318 strokes · 2.1s")
        #expect(StudioPresentation.toolLine(call, strokes: nil) == "paint v4 · 2.1s")
    }

    @Test("running, failed, and non-paint tool lines")
    func otherLines() {
        #expect(StudioPresentation.toolLine(NotebookToolCall(toolName: "paint", inProgress: true), strokes: nil) == "paint…")
        let failed = NotebookToolCall(toolName: "paint", inProgress: false, failed: true)
        #expect(StudioPresentation.toolLine(failed, strokes: 9) == "paint · failed")
        let look = NotebookToolCall(toolName: "view_canvas", inProgress: false, durationMs: 400)
        #expect(StudioPresentation.toolLine(look, strokes: 12) == "look at canvas · 0.4s")
        #expect(StudioPresentation.formatDuration(milliseconds: 64_000) == "1m 04s")
    }

    // MARK: - Fixtures

    private func makeMessage(
        type: AgentMessageType,
        toolName: String? = nil,
        status: ToolExecutionStatus? = nil
    ) -> AgentMessage {
        AgentMessage(
            id: UUID().uuidString,
            type: type,
            text: "",
            timestamp: 0,
            iteration: 1,
            status: status,
            metadata: toolName.map { AgentMessageMetadata(toolName: $0) }
        )
    }
}
