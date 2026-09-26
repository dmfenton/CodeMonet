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
    /// The live piece's title (a completed `name_piece` call).
    case setTitle(String?)
    /// The direction the live piece was started with (this device's own
    /// `new_canvas` request, applied once the server confirms the new piece).
    case setPrompt(String?)

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

    // Program painting (program-painting spec §4.1)
    /// A `painting_version` message arrived (or `init.painting` was
    /// non-nil, routed the same way minus the `INIT` guards — see
    /// `.initialize`, which sets `painting` directly rather than going
    /// through this event's guard chain). `stages`/`ops` never affect
    /// playback (spec §4.2); they're kept only on the accepted version's
    /// `StudioState.versions` entry for display.
    case paintingVersion(PaintingVersionRef, stages: [String] = [], ops: Int? = nil)
    /// The reveal layer finished animating `playing` and drew its final
    /// image. `assetBase` is the version that just finished, so a stale
    /// completion (a newer version already superseded it) can be detected
    /// and ignored (spec §4.1).
    case paintingPlaybackDone(assetBase: String)
}
