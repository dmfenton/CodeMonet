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

    @Test("an active turn with nothing streaming reads as thinking, on the pill and the easel line")
    func activeTurnPill() {
        var state = StudioState()
        state.paused = false
        state.turnActive = true
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "thinking", isActive: true))
        #expect(StudioPresentation.easelStatusLine(for: state) == "thinking")
        state.paused = true
        #expect(StudioPresentation.statusPill(for: state) == .init(label: "paused", isActive: false))
    }

    @Test("an open tool call names the activity: critique, painting, looking")
    func executingPills() {
        var state = StudioState()
        state.paused = false
        // Messages reach both the status window and the notebook log via the reducer.
        for tool in ["critique_canvas", "paint", "view_canvas"] {
            state = StudioReducer.reduce(state, .clearMessages)
            state = StudioReducer.reduce(state, .addMessage(makeMessage(type: .codeExecution, toolName: tool, status: .started)))
            let expected = ["critique_canvas": "critique", "paint": "painting", "view_canvas": "looking"][tool]
            #expect(StudioPresentation.statusPill(for: state) == .init(label: expected ?? "", isActive: true))
        }
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
