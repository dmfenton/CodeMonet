import MonetProtocol

/// Every state transition `StudioState.reduce` understands (protocol-state
/// spec §5, `CanvasAction`). One event per reducer case in the spec's
/// tables; unknown/unhandled events are impossible by construction since
/// this is a closed enum (the TS reducer's "unknown action -> no-op" escape
/// hatch has no equivalent need here).
public enum StudioEvent: Equatable, Sendable {
    // Strokes (§5.1)
    case addStroke(Path)
    case setStrokes([Path])
    case startStroke(Point)
    case addPoint(Point)
    case endStroke

    // Thinking / messages (§5.2)
    case setThinking(String)
    case appendThinking(String)
    /// Archives the current `thinking` accumulator as a `.thinking`
    /// `AgentMessage`, if non-empty. `messageID`/`timestamp` are supplied by
    /// the caller (not generated inside the reducer) so `reduce` stays a
    /// pure, deterministic, total function of `(state, event)` — see
    /// `MonetStudio.IDGenerating`/injected clocks in `MessageRouter`.
    case archiveThinking(messageID: String, timestamp: Double)
    case addMessage(AgentMessage)
    case clearMessages

    // Metadata (§5.3)
    case toggleDrawing
    case setCanvasSize(width: Int, height: Int)
    case setPieceNumber(Int)
    case setGallery([GalleryEntry])
    case setStyle(DrawingStyleType, DrawingStyleConfig)
    case setPaused(Bool)
    case setIteration(current: Int, max: Int)
    case resetTurn

    // Canvas lifecycle (§5.4)
    case clear
    case loadCanvas(LoadCanvasPayload)
    case clearViewing
    case initialize(InitPayload)

    // Performance / animation pipeline (§5.5)
    case enqueueWords(String)
    case enqueueEvent(AgentMessage)
    case enqueueStrokes([PendingStroke])
    case advanceStage
    case revealWord
    case strokeProgressBatch(points: [Point], style: PartialStrokeStyle?)
    case strokeComplete
    case penTravelBatch([Point])
    case penTravelComplete
    case stageComplete
    case clearPerformance
}
