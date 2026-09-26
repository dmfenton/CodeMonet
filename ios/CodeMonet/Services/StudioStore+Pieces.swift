import Foundation
import MonetProtocol
import MonetStudio

/// Starting pieces and nudging — the two user-authored inputs the redesign's
/// Home composer and Studio nudge bar send.
extension StudioStore {
    /// Starts a new piece (Home composer's Begin / Surprise me) and resumes
    /// the agent. The direction becomes the piece's prompt and first notebook
    /// entry once the server confirms the new canvas.
    public func startNewPiece(direction: String?, style: DrawingStyleType, width: Int?, height: Int?) {
        let trimmed = direction?.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = trimmed?.isEmpty == false ? trimmed : nil
        pendingPrompt = prompt
        setStyle(style)
        send(.newCanvas(direction: prompt, drawingStyle: style, canvasWidth: width, canvasHeight: height))
        setPausedLocally(false)
        send(.resume(direction: nil))
    }

    /// Sends a nudge and records it in the notebook as the user's own entry.
    public func sendNudge(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        apply(.addMessage(Self.userMessage(trimmed)))
        send(.nudge(text: trimmed))
    }

    func applyPendingPrompt() {
        guard let prompt = pendingPrompt else { return }
        pendingPrompt = nil
        apply(.setPrompt(prompt))
        apply(.addMessage(Self.userMessage(prompt)))
    }

    private static func userMessage(_ text: String) -> AgentMessage {
        AgentMessage(
            id: UUID().uuidString,
            type: .userNudge,
            text: text,
            timestamp: Date().timeIntervalSince1970 * 1000
        )
    }
}
