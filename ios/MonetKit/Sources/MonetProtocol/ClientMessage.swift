import Foundation

/// The client -> server wire vocabulary (protocol-state spec §3). The server
/// duck-types these off a raw dict rather than validating against a schema,
/// so this encoder is the actual contract — every case below is grounded in
/// `user_handlers.py`, not the server's unused Pydantic `ClientMessage`
/// union. Every message is a flat top-level JSON object; `type` plus that
/// case's own fields, nothing nested.
public enum ClientMessage: Equatable, Sendable {
    /// A finished human touch-stroke. Server builds `Path(type: .polyline,
    /// author: .human)` from these points and rate-limits per user.
    case stroke(points: [Point])
    case nudge(text: String)
    case clear
    case pause
    /// `direction`, if present, is queued as a nudge before the agent resumes.
    case resume(direction: String?)
    case newCanvas(direction: String?, drawingStyle: DrawingStyleType?, canvasWidth: Int?, canvasHeight: Int?)
    /// Read-only: switches every connection of this user into gallery-view.
    case loadCanvas(pieceNumber: Int)
    /// Signals the server that client-side playback of `batchID` finished,
    /// unblocking the agent's `_draw_paths` wait.
    case animationDone(batchID: Int)
}

extension ClientMessage: Encodable {
    private enum CodingKeys: String, CodingKey {
        case type, points, text
        case direction
        case drawingStyle = "drawing_style"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case pieceNumber = "piece_number"
        case batchID = "batch_id"
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .stroke(points):
            try container.encode("stroke", forKey: .type)
            try container.encode(points, forKey: .points)
        case let .nudge(text):
            try container.encode("nudge", forKey: .type)
            try container.encode(text, forKey: .text)
        case .clear:
            try container.encode("clear", forKey: .type)
        case .pause:
            try container.encode("pause", forKey: .type)
        case let .resume(direction):
            try container.encode("resume", forKey: .type)
            try container.encodeIfPresent(direction, forKey: .direction)
        case let .newCanvas(direction, drawingStyle, canvasWidth, canvasHeight):
            try container.encode("new_canvas", forKey: .type)
            try container.encodeIfPresent(direction, forKey: .direction)
            try container.encodeIfPresent(drawingStyle, forKey: .drawingStyle)
            try container.encodeIfPresent(canvasWidth, forKey: .canvasWidth)
            try container.encodeIfPresent(canvasHeight, forKey: .canvasHeight)
        case let .loadCanvas(pieceNumber):
            try container.encode("load_canvas", forKey: .type)
            try container.encode(pieceNumber, forKey: .pieceNumber)
        case let .animationDone(batchID):
            try container.encode("animation_done", forKey: .type)
            try container.encode(batchID, forKey: .batchID)
        }
    }
}
