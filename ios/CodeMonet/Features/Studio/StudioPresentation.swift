import Foundation
import MonetProtocol
import MonetStudio

/// Pure, SwiftUI-independent presentation rules for the Studio and Home
/// status lines and the notebook's tool lines — kept free of SwiftUI so
/// they're unit-testable against plain `StudioState` values.
enum StudioPresentation {
    // MARK: - Status pill

    struct StatusPill: Equatable {
        var label: String
        /// The agent is actively working (drives the pill's live dot).
        var isActive: Bool
    }

    /// The Studio top bar's status: paused / error / thinking / the running
    /// tool (painting, critique, …) / idle.
    static func statusPill(for state: StudioState) -> StatusPill {
        if state.viewingPiece != nil { return StatusPill(label: "viewing", isActive: false) }
        switch StudioSelectors.agentStatus(state) {
        case .paused:
            return StatusPill(label: "paused", isActive: false)
        case .error:
            return StatusPill(label: "error", isActive: false)
        case .thinking:
            return StatusPill(label: "thinking", isActive: true)
        case .executing, .drawing, .idle:
            // `agentStatus` counts any never-completed tool call as still
            // executing, but the server only closes its own drawing tools —
            // so the running tool comes from the notebook instead, which
            // settles a call once anything follows it.
            if let running = Notebook.runningTool(Notebook.entries(state)) {
                return StatusPill(label: activityLabel(forTool: running.toolName), isActive: true)
            }
            if state.painting.playing != nil || hasStrokesPending(state) {
                return StatusPill(label: state.drawingStyle == .paint ? "painting" : "drawing", isActive: true)
            }
            return StatusPill(label: "idle", isActive: false)
        }
    }

    private static func hasStrokesPending(_ state: StudioState) -> Bool {
        if case .strokes = state.performance.onStage { return true }
        return state.performance.buffer.contains { if case .strokes = $0 { true } else { false } }
    }

    /// Home's "on the easel" status line, e.g. "painting · v4 · poplars".
    /// Version and stage appear only when a painting version exists.
    static func easelStatusLine(for state: StudioState) -> String {
        var parts = [statusPill(for: state).label]
        if let latest = state.versions.last {
            parts.append("v\(latest.version)")
            if let stage = latest.stages.last { parts.append(stage) }
        }
        return parts.joined(separator: " · ")
    }

    /// The tool driving the current status, derived from the most recent
    /// `code_execution` message.
    static func currentTool(messages: [AgentMessage]) -> String? {
        messages.last { $0.type == .codeExecution }?.metadata?.toolName
    }

    static func activityLabel(forTool toolName: String?) -> String {
        switch toolName {
        case "paint": "painting"
        case "critique_canvas": "critique"
        case "view_canvas": "looking"
        case "imagine": "imagining"
        case "draw_paths", "generate_svg": "drawing"
        case "name_piece": "naming"
        case "sign_canvas": "signing"
        case "mark_piece_done": "finishing"
        default: "working"
        }
    }
}
